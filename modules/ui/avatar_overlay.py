#!/usr/bin/env python3
"""
VRM 3D Avatar & Message Bubble Overlay Subprocess for MacAssistant.
Renders:
1. A borderless, click-through, floating 3D VRM avatar window using WKWebView, Three.js, and @pixiv/three-vrm.
2. A queued glassmorphic message bubble window in the top-right corner that fades in with spoken messages and fades out cleanly.

Zero-dependency core architecture: driven over local Unix domain socket IPC (/tmp/macassistant_avatar.sock).
"""

import argparse
import json
import logging
import math
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# AppKit & WebKit bindings via PyObjC
try:
    import objc
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSBackingStoreBuffered,
        NSColor,
        NSFont,
        NSScreen,
        NSTextView,
        NSView,
        NSVisualEffectBlendingModeBehindWindow,
        NSVisualEffectMaterialHUDWindow,
        NSVisualEffectStateActive,
        NSVisualEffectView,
        NSWindow,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowCollectionBehaviorStationary,
    )
    from Foundation import (
        NSDate,
        NSObject,
        NSPoint,
        NSRect,
        NSSize,
        NSTimer,
        NSURL,
    )
    from WebKit import WKUserContentController, WKWebView, WKWebViewConfiguration
except ImportError as e:
    print(f"Error importing PyObjC AppKit/WebKit: {e}")
    print("Run: pip install pyobjc-framework-Cocoa pyobjc-framework-WebKit")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MacAssistant.VRMOverlay")

SOCKET_PATH = "/tmp/macassistant_avatar.sock"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HTML_PATH = PROJECT_ROOT / "modules" / "ui" / "web" / "avatar.html"
DEFAULT_VRM = PROJECT_ROOT / "assets" / "vrm" / "default.vrm"


def is_socket_in_use(path: str) -> bool:
    """Checks whether another live instance is actively responding on the socket."""
    if not os.path.exists(path):
        return False
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.3)
        sock.connect(path)
        sock.close()
        return True
    except (ConnectionRefusedError, socket.error):
        return False


class MessageItem:
    """Item representing a queued popup message bubble."""
    def __init__(self, text: str, sender: str = "Assistant"):
        self.text = text
        self.sender = sender
        # Duration proportional to length: ~45 words/min reading speed (~0.06s per char), min 3.0s, max 10.0s
        self.display_duration = max(3.0, min(10.0, len(text) * 0.055 + 1.5))


class VRMOverlayController(NSObject):
    """Manages the 3D VRM avatar window and queued top-right popup message bubbles."""

    def init(self):
        self = objc.super(VRMOverlayController, self).init()
        if self is None:
            return None

        self.config: Dict[str, Any] = {
            "vrm_path": str(DEFAULT_VRM),
            "enabled": True,
            "position": "bottom-right",  # "bottom-right", "bottom-left", "top-right"
            "scale": 1.0,
            "width": 320,
            "height": 400,
            "bubble_enabled": True,
            "bubble_min_duration": 3.0,
            "bubble_max_duration": 10.0,
        }

        # Avatar Window & WebKit components
        self.avatar_window: Optional[NSWindow] = None
        self.webview: Optional[WKWebView] = None

        # Message Bubble Window & Views
        self.bubble_window: Optional[NSWindow] = None
        self.bubble_effect_view: Optional[NSVisualEffectView] = None
        self.bubble_text_view: Optional[NSTextView] = None

        # Message Queue & State
        self.message_queue: List[MessageItem] = []
        self.current_message: Optional[MessageItem] = None
        self.bubble_state = "hidden"  # "hidden", "fading_in", "visible", "fading_out"
        self.bubble_timer: Optional[NSTimer] = None
        self.bubble_anim_timer: Optional[NSTimer] = None

        # Avatar State
        self.avatar_state = "idle"  # "idle", "listening", "thinking", "speaking"

        return self

    @objc.python_method
    def setupWindows(self):
        """Constructs both the 3D Avatar window and the Message Bubble window."""
        screen = NSScreen.mainScreen()
        if not screen:
            logger.error("No screen found.")
            return

        visible = screen.visibleFrame()

        # ----------------------------------------------------
        # 1. VRM 3D Avatar Window (Bottom-Right / Configurable)
        # ----------------------------------------------------
        w = float(self.config.get("width", 320))
        h = float(self.config.get("height", 400))
        pos = self.config.get("position", "bottom-right")

        if pos == "bottom-right":
            ax = visible.origin.x + visible.size.width - w - 20
            ay = visible.origin.y + 20
        elif pos == "bottom-left":
            ax = visible.origin.x + 20
            ay = visible.origin.y + 20
        else:  # top-right
            ax = visible.origin.x + visible.size.width - w - 20
            ay = visible.origin.y + visible.size.height - h - 30

        avatar_rect = NSRect(NSPoint(ax, ay), NSSize(w, h))
        self.avatar_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            avatar_rect, 0, NSBackingStoreBuffered, False
        )
        self.avatar_window.setOpaque_(False)
        self.avatar_window.setBackgroundColor_(NSColor.clearColor())
        self.avatar_window.setHasShadow_(False)
        self.avatar_window.setIgnoresMouseEvents_(True)  # Click-through
        self.avatar_window.setLevel_(25)  # Always on top

        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        self.avatar_window.setCollectionBehavior_(behavior)

        # WKWebView with transparent background and file URL access
        wk_config = WKWebViewConfiguration.alloc().init()
        wk_config.preferences().setValue_forKey_(True, "allowFileAccessFromFileURLs")
        wk_config.setValue_forKey_(True, "allowUniversalAccessFromFileURLs")

        self.webview = WKWebView.alloc().initWithFrame_configuration_(
            self.avatar_window.contentView().bounds(), wk_config
        )
        self.webview.setValue_forKey_(False, "drawsBackground")  # Fully transparent
        self.avatar_window.contentView().addSubview_(self.webview)

        # Load web/avatar.html
        if HTML_PATH.exists():
            html_url = NSURL.fileURLWithPath_(str(HTML_PATH.resolve()))
            self.webview.loadFileURL_allowingReadAccessToURL_(
                html_url, NSURL.fileURLWithPath_(str(PROJECT_ROOT.resolve()))
            )
        else:
            logger.error("Avatar HTML not found at %s", HTML_PATH)

        self.avatar_window.orderFrontRegardless()
        logger.info("VRM avatar window created at (%d, %d).", ax, ay)

        # ----------------------------------------------------
        # 2. Top-Right Message Bubble Window
        # ----------------------------------------------------
        bw = 360.0
        bh = 130.0
        bx = visible.origin.x + visible.size.width - bw - 24
        by = visible.origin.y + visible.size.height - bh - 28

        bubble_rect = NSRect(NSPoint(bx, by), NSSize(bw, bh))
        self.bubble_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            bubble_rect, 0, NSBackingStoreBuffered, False
        )
        self.bubble_window.setOpaque_(False)
        self.bubble_window.setBackgroundColor_(NSColor.clearColor())
        self.bubble_window.setHasShadow_(True)
        self.bubble_window.setIgnoresMouseEvents_(True)  # Click-through
        self.bubble_window.setLevel_(26)  # Slightly above avatar
        self.bubble_window.setCollectionBehavior_(behavior)
        self.bubble_window.setAlphaValue_(0.0)

        # Visual Effect Blur Layer (Glassmorphism)
        self.bubble_effect_view = NSVisualEffectView.alloc().initWithFrame_(
            self.bubble_window.contentView().bounds()
        )
        self.bubble_effect_view.setMaterial_(NSVisualEffectMaterialHUDWindow)
        self.bubble_effect_view.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        self.bubble_effect_view.setState_(NSVisualEffectStateActive)
        self.bubble_effect_view.setWantsLayer_(True)
        self.bubble_effect_view.layer().setCornerRadius_(16.0)
        self.bubble_effect_view.layer().setMasksToBounds_(True)
        self.bubble_effect_view.layer().setBorderWidth_(1.0)
        self.bubble_effect_view.layer().setBorderColor_(
            NSColor.colorWithWhite_alpha_(1.0, 0.25).CGColor()
        )

        # Text View for message
        text_rect = NSRect(NSPoint(16, 12), NSSize(bw - 32, bh - 24))
        self.bubble_text_view = NSTextView.alloc().initWithFrame_(text_rect)
        self.bubble_text_view.setBackgroundColor_(NSColor.clearColor())
        self.bubble_text_view.setDrawsBackground_(False)
        self.bubble_text_view.setEditable_(False)
        self.bubble_text_view.setSelectable_(False)
        self.bubble_text_view.setTextColor_(NSColor.whiteColor())
        self.bubble_text_view.setFont_(NSFont.systemFontOfSize_weight_(13.5, 0.2))

        self.bubble_effect_view.addSubview_(self.bubble_text_view)
        self.bubble_window.contentView().addSubview_(self.bubble_effect_view)
        self.bubble_window.orderFrontRegardless()

        # Load initial VRM after short delay for webview readiness
        timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.2, self, "onInitialVrmLoad:", None, False
        )

    def onInitialVrmLoad_(self, timer):
        """Triggers load of default or configured VRM model into WebKit."""
        vrm_path = Path(self.config.get("vrm_path", str(DEFAULT_VRM)))
        if not vrm_path.is_absolute():
            vrm_path = PROJECT_ROOT / vrm_path
        scale = float(self.config.get("scale", 1.0))
        self.loadVRM(str(vrm_path.resolve()), scale)

    @objc.python_method
    def loadVRM(self, vrm_path: str, scale: float = 1.0):
        """Loads .vrm model into Three.js canvas."""
        if not self.webview:
            return
        if not os.path.exists(vrm_path):
            logger.warning("VRM model not found at %s. Waiting for model file.", vrm_path)
            return

        file_url = f"file://{os.path.abspath(vrm_path)}"
        js = f"window.loadVRM('{file_url}', {scale});"
        self.webview.evaluateJavaScript_completionHandler_(js, None)
        logger.info("Triggered VRM load in webview: %s (scale=%.2f)", vrm_path, scale)

    @objc.python_method
    def setAvatarState(self, state: str):
        """Sets avatar state: idle, listening, thinking, speaking."""
        self.avatar_state = state
        if self.webview:
            js = f"window.setState('{state}');"
            self.webview.evaluateJavaScript_completionHandler_(js, None)

    @objc.python_method
    def setLipSync(self, amplitude: float, vowel: str = "aa"):
        """Drives mouth blendshape with audio loudness amplitude."""
        if self.webview:
            js = f"window.setAmplitude({amplitude:.3f}, '{vowel}');"
            self.webview.evaluateJavaScript_completionHandler_(js, None)

    @objc.python_method
    def setExpression(self, expression: str, weight: float = 1.0):
        """Sets facial expression blendshape."""
        if self.webview:
            js = f"window.setExpression('{expression}', {weight:.2f});"
            self.webview.evaluateJavaScript_completionHandler_(js, None)

    # ----------------------------------------------------
    # Message Bubble Queue Management
    # ----------------------------------------------------
    @objc.python_method
    def queueMessage(self, text: str, sender: str = "Assistant"):
        """Enqueues popup message to show in sequence."""
        if not text or not text.strip():
            return
        clean = text.strip()
        item = MessageItem(clean, sender)
        self.message_queue.append(item)
        if self.bubble_state == "hidden":
            self._showNextMessage()

    @objc.python_method
    def _showNextMessage(self):
        """Pops next message and initiates slide-in / fade-in."""
        if not self.message_queue:
            return

        self.current_message = self.message_queue.pop(0)
        prefix = f"[{self.current_message.sender.upper()}]\n" if self.current_message.sender else ""
        self.bubble_text_view.setString_(f"{prefix}{self.current_message.text}")

        self.bubble_state = "fading_in"
        self._startBubbleAnimTimer()

    @objc.python_method
    def _startBubbleAnimTimer(self):
        """Runs smooth 60fps interpolation for bubble fade-in/out."""
        if not self.bubble_anim_timer:
            self.bubble_anim_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.016, self, "bubbleTick:", None, True
            )

    def bubbleTick_(self, timer):
        """Animates bubble window alpha and subtle slide."""
        if not self.bubble_window:
            return

        alpha = self.bubble_window.alphaValue()

        if self.bubble_state == "fading_in":
            new_alpha = min(1.0, alpha + 0.12)
            self.bubble_window.setAlphaValue_(new_alpha)
            if new_alpha >= 0.99:
                self.bubble_state = "visible"
                duration = self.current_message.display_duration if self.current_message else 4.0
                if self.bubble_timer:
                    self.bubble_timer.invalidate()
                self.bubble_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    duration, self, "onBubbleDurationExpired:", None, False
                )

        elif self.bubble_state == "fading_out":
            new_alpha = max(0.0, alpha - 0.08)
            self.bubble_window.setAlphaValue_(new_alpha)
            if new_alpha <= 0.001:
                self.bubble_state = "hidden"
                self.bubble_window.setAlphaValue_(0.0)
                if self.bubble_anim_timer:
                    self.bubble_anim_timer.invalidate()
                    self.bubble_anim_timer = None
                # Check for next queued message
                if self.message_queue:
                    self._showNextMessage()

    def onBubbleDurationExpired_(self, timer):
        """Starts fade-out transition after display duration."""
        self.bubble_timer = None
        self.bubble_state = "fading_out"
        self._startBubbleAnimTimer()

    # ----------------------------------------------------
    # Command Dispatching
    # ----------------------------------------------------
    def handleCommand_(self, cmd_data):
        """Handles socket actions arriving from daemon."""
        action = cmd_data.get("action")
        if not action:
            return

        if action == "speaking_start":
            self.setAvatarState("speaking")
            msg = cmd_data.get("message", "")
            if msg:
                self.queueMessage(msg, cmd_data.get("persona", "Assistant"))
        elif action == "speaking_end":
            self.setAvatarState("idle")
            self.setLipSync(0.0)
        elif action == "thinking":
            self.setAvatarState("thinking")
        elif action == "listening":
            self.setAvatarState("listening")
        elif action == "idle":
            self.setAvatarState("idle")
        elif action == "amplitude":
            amp = float(cmd_data.get("amplitude", 0.0))
            vowel = cmd_data.get("vowel", "aa")
            self.setLipSync(amp, vowel)
        elif action == "expression":
            exp = cmd_data.get("expression", "neutral")
            weight = float(cmd_data.get("weight", 1.0))
            self.setExpression(exp, weight)
        elif action == "message":
            text = cmd_data.get("text", "")
            sender = cmd_data.get("sender", "Assistant")
            if text:
                self.queueMessage(text, sender)
        elif action == "config_update":
            cfg = cmd_data.get("config", {})
            self.updateConfig_(cfg)

    def updateConfig_(self, new_cfg):
        """Hot-reloads configuration properties."""
        self.config.update(new_cfg)
        vrm_path = Path(self.config.get("vrm_path", str(DEFAULT_VRM)))
        if not vrm_path.is_absolute():
            vrm_path = PROJECT_ROOT / vrm_path
        scale = float(self.config.get("scale", 1.0))
        self.loadVRM(str(vrm_path.resolve()), scale)
        logger.info("VRM overlay configuration hot-reloaded.")


class SocketServerThread(threading.Thread):
    """Background listener servicing Unix domain socket commands safely."""

    def __init__(self, controller: VRMOverlayController):
        super().__init__(daemon=True, name="VRMSocketServer")
        self.controller = controller
        self.running = True

    def run(self):
        if is_socket_in_use(SOCKET_PATH):
            logger.warning("Another live VRMOverlay instance is currently using %s. Socket server exiting.", SOCKET_PATH)
            return

        if os.path.exists(SOCKET_PATH):
            try:
                os.unlink(SOCKET_PATH)
            except OSError:
                pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o777)
        server.listen(5)
        logger.info("VRM socket listening on %s", SOCKET_PATH)

        while self.running:
            try:
                conn, _ = server.accept()
                with conn:
                    data = conn.recv(4096)
                    if data:
                        text = data.decode("utf-8").strip()
                        for line in text.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                payload = json.loads(line)
                            except json.JSONDecodeError:
                                payload = {"action": line}
                            self._dispatch_to_main(payload)
            except Exception as e:
                if self.running:
                    logger.debug("Socket connection error: %s", e)

    def _dispatch_to_main(self, payload: Dict[str, Any]):
        """Dispatches command payload to AppKit main thread."""
        class Dispatcher(NSObject):
            def runOnMain_(self, arg):
                controller, cmd = arg
                controller.handleCommand_(cmd)

        d = Dispatcher.alloc().init()
        d.performSelectorOnMainThread_withObject_waitUntilDone_(
            "runOnMain:", (self.controller, payload), False
        )


def run_demo(controller: VRMOverlayController):
    """Executes automated demo: listening -> thinking -> speaking with message bubble -> idle."""
    time.sleep(2.0)
    logger.info("DEMO: [1/4] Triggering 'listening' state (head tilt)...")
    controller.handleCommand_({"action": "listening"})

    time.sleep(2.5)
    logger.info("DEMO: [2/4] Triggering 'thinking' state (contemplative glance)...")
    controller.handleCommand_({"action": "thinking"})

    time.sleep(2.5)
    logger.info("DEMO: [3/4] Triggering 'speaking' with message bubble and simulated blendshapes...")
    demo_msg = "Good afternoon, Sir! All systems are nominal and your VRM avatar is fully operational."
    controller.handleCommand_({"action": "speaking_start", "message": demo_msg, "persona": "Friday"})

    # Simulate amplitude modulation
    for _ in range(35):
        amp = 0.3 + 0.6 * math.sin(time.time() * 12.0)
        vowel = ["aa", "ih", "ou", "ee", "oh"][int(time.time() * 5) % 5]
        controller.handleCommand_({"action": "amplitude", "amplitude": max(0.1, amp), "vowel": vowel})
        time.sleep(0.1)

    logger.info("DEMO: [4/4] Finishing speech and returning to idle...")
    controller.handleCommand_({"action": "speaking_end"})

    time.sleep(6.0)
    logger.info("DEMO: Sequence complete. Terminating overlay.")
    NSApplication.sharedApplication().terminate_(None)


def main():
    parser = argparse.ArgumentParser(description="MacAssistant VRM 3D Avatar & Message Bubble Overlay")
    parser.add_argument("--demo", action="store_true", help="Run interactive VRM animation & message bubble demo")
    parser.add_argument("--config", type=str, default=None, help="JSON string or path to config")
    args = parser.parse_args()

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = VRMOverlayController.alloc().init()

    if args.config:
        try:
            if os.path.exists(args.config):
                with open(args.config, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f).get("avatar", {})
            else:
                cfg_data = json.loads(args.config)
            controller.config.update(cfg_data)
        except Exception as e:
            logger.warning("Could not parse config: %s", e)

    controller.setupWindows()

    # Start socket listener
    sock_thread = SocketServerThread(controller)
    sock_thread.start()

    if args.demo:
        demo_thread = threading.Thread(target=run_demo, args=(controller,), daemon=True)
        demo_thread.start()

    logger.info("VRM Avatar & Message Bubble Overlay running.")
    app.run()


if __name__ == "__main__":
    main()
