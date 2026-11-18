#!/usr/bin/env python3
"""
Avatar Overlay Subprocess for MacAssistant.
Renders an on-screen character overlay in the top-right corner using native macOS AppKit.

Features:
- Borderless, transparent, floating level (always on top, visible across all Spaces and full-screen apps).
- Click-through (ignoresMouseEvents = True), no Dock icon (NSApplicationActivationPolicyAccessory).
- Driven by IPC commands over a local Unix domain socket (/tmp/macassistant_avatar.sock).
- Smooth animations: fade & slide in, idle breathing/bobbing, speaking pulse, thinking slow glow.
- Debounced hide timer with configurable linger time (default 1.5s).
- 0% idle CPU when hidden (timers stop completely when not visible).
- Interactive demo mode: `python -m modules.ui.avatar_overlay --demo`.
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
from typing import Any, Dict, Optional

# AppKit & Foundation bindings via PyObjC
try:
    import objc
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSBackingStoreBuffered,
        NSColor,
        NSImage,
        NSImageView,
        NSImageScaleProportionallyUpOrDown,
        NSScreen,
        NSView,
        NSWindow,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowCollectionBehaviorStationary,
    )
    from Foundation import NSDate, NSObject, NSRect, NSPoint, NSSize, NSTimer
except ImportError:
    print("Error: pyobjc-framework-Cocoa is required. Install via pip install pyobjc-framework-Cocoa")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MacAssistant.AvatarOverlay")

SOCKET_PATH = "/tmp/macassistant_avatar.sock"
DEFAULT_AVATAR_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "avatar.png"


class AvatarController(NSObject):
    """AppKit delegate and controller managing the overlay window and animation loops."""

    def init(self):
        self = objc.super(AvatarController, self).init()
        if self is None:
            return None

        self.config: Dict[str, Any] = {
            "enabled": True,
            "image_path": str(DEFAULT_AVATAR_PATH),
            "width": 260,
            "margin": 24,
            "linger_seconds": 1.5,
            "opacity": 1.0,
            "screen": "main"
        }

        self.window: Optional[NSWindow] = None
        self.image_view: Optional[NSImageView] = None
        self.state = "hidden"  # hidden, speaking, thinking, lingering
        self.anim_timer: Optional[NSTimer] = None
        self.linger_timer: Optional[NSTimer] = None
        self.anim_step = 0.0
        self.base_origin_y = 0.0
        self.base_origin_x = 0.0
        self.target_width = 260.0
        self.target_height = 420.0
        self.max_opacity = 1.0

        return self

    def setupWindow(self):
        """Builds borderless, transparent, click-through floating NSWindow."""
        screen = NSScreen.mainScreen()
        if not screen:
            logger.error("No screen found for avatar window.")
            return

        visible_frame = screen.visibleFrame()
        width = float(self.config.get("width", 260))
        margin = float(self.config.get("margin", 24))

        # Load image to inspect aspect ratio
        img_path = Path(self.config.get("image_path", str(DEFAULT_AVATAR_PATH)))
        if not img_path.is_absolute():
            img_path = Path(__file__).resolve().parent.parent.parent / img_path

        if not img_path.exists():
            logger.warning("Avatar image not found at %s. Running without visible character.", img_path)
            ns_img = None
            height = width * 1.6
        else:
            ns_img = NSImage.alloc().initWithContentsOfFile_(str(img_path))
            if ns_img and ns_img.size().width > 0:
                aspect = ns_img.size().height / ns_img.size().width
                height = width * aspect
            else:
                height = width * 1.6

        self.target_width = width
        self.target_height = height
        self.max_opacity = float(self.config.get("opacity", 1.0))

        # Position in top-right corner below menu bar / notch
        x = visible_frame.origin.x + visible_frame.size.width - width - margin
        y = visible_frame.origin.y + visible_frame.size.height - height - margin
        self.base_origin_x = x
        self.base_origin_y = y

        window_rect = NSRect(NSPoint(x, y), NSSize(width, height))

        # NSWindow styleMask: 0 (borderless)
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            window_rect, 0, NSBackingStoreBuffered, False
        )

        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(NSColor.clearColor())
        self.window.setHasShadow_(True)
        self.window.setIgnoresMouseEvents_(True)  # Click-through

        # Window level: Floating / StatusWindow (always on top of normal and full screen apps)
        # kCGStatusWindowLevel = 25, floating level = 3
        self.window.setLevel_(25)

        # Collection behavior: All spaces + full screen auxiliary
        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        self.window.setCollectionBehavior_(behavior)
        self.window.setAlphaValue_(0.0)

        # Content view with image
        content_view = self.window.contentView()
        self.image_view = NSImageView.alloc().initWithFrame_(NSRect(NSPoint(0, 0), NSSize(width, height)))
        self.image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        if ns_img:
            self.image_view.setImage_(ns_img)
        content_view.addSubview_(self.image_view)

        # Order window front but invisible
        self.window.orderFrontRegardless()
        logger.info("Avatar window created at (%.1f, %.1f) size (%.1fx%.1f).", x, y, width, height)

    def updateConfig_(self, new_cfg):
        """Hot-reloads configuration properties."""
        self.config.update(new_cfg)
        self.max_opacity = float(self.config.get("opacity", 1.0))
        img_path = Path(self.config.get("image_path", str(DEFAULT_AVATAR_PATH)))
        if img_path.exists() and self.image_view:
            ns_img = NSImage.alloc().initWithContentsOfFile_(str(img_path))
            if ns_img:
                self.image_view.setImage_(ns_img)

    def handleCommand_(self, cmd_data):
        """Dispatches commands arriving from the daemon socket."""
        action = cmd_data.get("action")
        if not action:
            return

        if action == "speaking_start":
            self.onSpeakingStart()
        elif action == "speaking_end":
            self.onSpeakingEnd()
        elif action == "thinking":
            self.onThinking()
        elif action == "hide":
            self.onHideImmediate()
        elif action == "config_update":
            cfg = cmd_data.get("config", {})
            self.updateConfig_(cfg)

    def onSpeakingStart(self):
        """Cancels any pending linger timer and transitions to active speaking state."""
        if not self.config.get("enabled", True):
            return

        if self.linger_timer:
            self.linger_timer.invalidate()
            self.linger_timer = None

        self.state = "speaking"
        self._startAnimationTimer()

    def onSpeakingEnd(self):
        """Starts linger timer before fading out."""
        if self.state == "hidden":
            return

        self.state = "lingering"
        linger = float(self.config.get("linger_seconds", 1.5))

        if self.linger_timer:
            self.linger_timer.invalidate()

        self.linger_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            linger, self, "onLingerExpired:", None, False
        )

    def onLingerExpired_(self, timer):
        """Fades out smoothly after linger time elapses."""
        self.state = "fading_out"

    def onThinking(self):
        """Transitions avatar to breathing/thinking glow."""
        if not self.config.get("enabled", True):
            return

        if self.linger_timer:
            self.linger_timer.invalidate()
            self.linger_timer = None

        self.state = "thinking"
        self._startAnimationTimer()

    def onHideImmediate(self):
        """Immediately conceals the window and stops all CPU timers."""
        if self.linger_timer:
            self.linger_timer.invalidate()
            self.linger_timer = None
        if self.anim_timer:
            self.anim_timer.invalidate()
            self.anim_timer = None

        self.state = "hidden"
        if self.window:
            self.window.setAlphaValue_(0.0)

    def _startAnimationTimer(self):
        """Starts 60fps display timer if not already ticking."""
        if not self.anim_timer:
            # 60fps = ~0.016s interval
            self.anim_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.016, self, "animationTick:", None, True
            )

    def animationTick_(self, timer):
        """Smoothly interpolates position, scale, opacity, and bobbing."""
        if not self.window:
            return

        current_alpha = self.window.alphaValue()
        self.anim_step += 0.05

        if self.state in ("speaking", "lingering"):
            target_alpha = self.max_opacity
            # Gentle vertical bobbing (amplitude ~4px, frequency ~2.5 Hz)
            bob_offset = math.sin(self.anim_step * 2.5) * 4.0
            # Subtle breathing scale (1.0 to 1.02)
            pulse_scale = 1.0 + 0.015 * math.sin(self.anim_step * 3.0)

            # Slide-in transition interpolation
            new_alpha = min(target_alpha, current_alpha + 0.08)
            self.window.setAlphaValue_(new_alpha)

            # Update frame with bob
            target_y = self.base_origin_y + bob_offset
            self.window.setFrameOrigin_(NSPoint(self.base_origin_x, target_y))

        elif self.state == "thinking":
            # Soft pulsating opacity between 0.45 and 0.75
            pulse_alpha = 0.55 + 0.20 * math.sin(self.anim_step * 1.5)
            self.window.setAlphaValue_(pulse_alpha * self.max_opacity)
            bob_offset = math.sin(self.anim_step * 1.2) * 2.0
            self.window.setFrameOrigin_(NSPoint(self.base_origin_x, self.base_origin_y + bob_offset))

        elif self.state == "fading_out":
            # Smooth fade-out (~350ms)
            new_alpha = max(0.0, current_alpha - 0.06)
            self.window.setAlphaValue_(new_alpha)
            # Slight slide upwards on exit
            self.window.setFrameOrigin_(NSPoint(self.base_origin_x, self.base_origin_y + (1.0 - new_alpha) * 10.0))

            if new_alpha <= 0.001:
                # Fully hidden -> Stop all timers to reach 0% CPU
                self.state = "hidden"
                self.anim_timer.invalidate()
                self.anim_timer = None
                self.window.setFrameOrigin_(NSPoint(self.base_origin_x, self.base_origin_y))


class SocketServerThread(threading.Thread):
    """Background listener servicing Unix domain socket commands."""

    def __init__(self, controller: AvatarController):
        super().__init__(daemon=True, name="AvatarSocketServer")
        self.controller = controller
        self.running = True

    def run(self):
        if os.path.exists(SOCKET_PATH):
            try:
                os.unlink(SOCKET_PATH)
            except OSError:
                pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o777)
        server.listen(5)
        logger.info("Avatar socket listening on %s", SOCKET_PATH)

        while self.running:
            try:
                conn, _ = server.accept()
                with conn:
                    data = conn.recv(4096)
                    if data:
                        text = data.decode("utf-8").strip()
                        # Allow newline-separated JSON or plain command
                        for line in text.splitlines():
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                payload = json.loads(line)
                            except json.JSONDecodeError:
                                payload = {"action": line}

                            # Schedule dispatch onto macOS Main RunLoop
                            self._dispatch_to_main(payload)
            except Exception as e:
                if self.running:
                    logger.debug("Socket connection error: %s", e)

    def _dispatch_to_main(self, payload: Dict[str, Any]):
        """Dispatches command to AppKit main thread via performSelectorOnMainThread."""
        class Dispatcher(NSObject):
            def runOnMain_(self, arg):
                controller, cmd = arg
                controller.handleCommand_(cmd)

        d = Dispatcher.alloc().init()
        d.performSelectorOnMainThread_withObject_waitUntilDone_(
            "runOnMain:", (self.controller, payload), False
        )


def run_demo(controller: AvatarController):
    """Executes animated demonstration cycles: think -> speak -> linger -> hide."""
    time.sleep(1.0)
    logger.info("DEMO: [1/4] Sending 'thinking' event (pulsing at soft opacity)...")
    controller.handleCommand_({"action": "thinking"})

    time.sleep(2.5)
    logger.info("DEMO: [2/4] Sending 'speaking_start' event (slide-in and lively bob)...")
    controller.handleCommand_({"action": "speaking_start"})

    time.sleep(4.0)
    logger.info("DEMO: [3/4] Sending 'speaking_end' event (lingers 1.5s then fades out)...")
    controller.handleCommand_({"action": "speaking_end"})

    time.sleep(3.0)
    logger.info("DEMO: [4/4] Demo cycle complete. Terminating overlay.")
    NSApplication.sharedApplication().terminate_(None)


def main():
    parser = argparse.ArgumentParser(description="MacAssistant On-Screen Avatar Overlay")
    parser.add_argument("--demo", action="store_true", help="Run interactive animation demo and exit")
    parser.add_argument("--config", type=str, default=None, help="JSON string or path to config")
    args = parser.parse_args()

    # Initialize NSApplication as Accessory (no Dock icon, no menu bar)
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = AvatarController.alloc().init()

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

    controller.setupWindow()

    # Start socket server
    sock_thread = SocketServerThread(controller)
    sock_thread.start()

    if args.demo:
        demo_thread = threading.Thread(target=run_demo, args=(controller,), daemon=True)
        demo_thread.start()

    logger.info("Avatar overlay application running.")
    app.run()


if __name__ == "__main__":
    main()
