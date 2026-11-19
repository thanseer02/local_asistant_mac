#!/usr/bin/env python3
"""
Desktop AI Assistant Companion Overlay for MacAssistant (Friday/JARVIS).

Features:
- Renders your AI companion character (assets/character/companion.png) directly using native AppKit.
- 100% transparent background, floating, always-on-top, click-through.
- Smooth spring entry from bottom-right corner when a new message/notification arrives.
- Natural conversational breathing and bobbing while speaking.
- Glassmorphic speech bubble floating beside the character while speaking.
- GUARANTEED DEPARTURE: Once speech finishes (or max display duration expires), the companion
  smoothly slides down and vanishes from the screen.
- Sequential message queue: never overlaps or interrupts ongoing speech.
- 0% idle CPU when hidden.
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

# AppKit & Foundation bindings via PyObjC
try:
    import objc
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSBackingStoreBuffered,
        NSColor,
        NSFont,
        NSImage,
        NSImageView,
        NSImageScaleProportionallyUpOrDown,
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
    )
except ImportError as e:
    print(f"Error importing PyObjC AppKit: {e}")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MacAssistant.CompanionOverlay")

SOCKET_PATH = "/tmp/macassistant_avatar.sock"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMPANION_IMG = PROJECT_ROOT / "assets" / "character" / "companion.png"


def is_socket_in_use(path: str) -> bool:
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


class QueuedMessage:
    def __init__(self, text: str, sender: str = "Assistant"):
        self.text = text
        self.sender = sender
        # Estimated reading/speaking time: ~15 chars/sec + 2s baseline (min 3.5s, max 12.0s)
        self.max_duration = max(3.5, min(12.0, len(text) * 0.07 + 2.0))


class CompanionOverlayController(NSObject):
    """Coordinates companion appearance, speaking animation, speech bubble, and clean departure."""

    def init(self):
        self = objc.super(CompanionOverlayController, self).init()
        if self is None:
            return None

        self.config: Dict[str, Any] = {
            "enabled": True,
            "width": 260,
            "height": 390,
            "bubble_width": 340,
            "bubble_height": 130,
            "display_index": 0,
            "linger_seconds": 1.2,
        }

        # Windows & Views
        self.char_window: Optional[NSWindow] = None
        self.char_image_view: Optional[NSImageView] = None

        self.bubble_window: Optional[NSWindow] = None
        self.bubble_effect_view: Optional[NSVisualEffectView] = None
        self.bubble_text_view: Optional[NSTextView] = None

        # State machine: hidden, entering, speaking, exiting
        self.state = "hidden"
        self.message_queue: List[QueuedMessage] = []
        self.current_message: Optional[QueuedMessage] = None
        self.is_speech_active = False

        # Animation parameters
        self.anim_timer: Optional[NSTimer] = None
        self.speak_anim_timer: Optional[NSTimer] = None
        self.anim_progress = 0.0
        self.base_char_origin = NSPoint(0, 0)
        self.base_bubble_origin = NSPoint(0, 0)
        self.slide_offset_y = 120.0
        self.speak_step = 0.0

        # Safety & Linger timers
        self.linger_timer: Optional[NSTimer] = None
        self.max_duration_timer: Optional[NSTimer] = None

        return self

    @objc.python_method
    def setupWindows(self):
        screens = NSScreen.screens()
        idx = int(self.config.get("display_index", 0))
        screen = screens[idx] if (screens and idx < len(screens)) else NSScreen.mainScreen()
        if not screen:
            logger.error("No screen found.")
            return

        visible = screen.visibleFrame()

        cw = float(self.config.get("width", 260))
        ch = float(self.config.get("height", 390))
        bw = float(self.config.get("bubble_width", 340))
        bh = float(self.config.get("bubble_height", 130))

        # Bottom-right corner coordinates
        cx = visible.origin.x + visible.size.width - cw - 20
        cy = visible.origin.y + 15

        # Speech bubble sits adjacent to the character
        bx = cx - bw - 15
        by = cy + ch - bh - 30

        self.base_char_origin = NSPoint(cx, cy)
        self.base_bubble_origin = NSPoint(bx, by)

        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )

        # 1. Native Character Window (100% transparent, floating, click-through)
        char_rect = NSRect(NSPoint(cx, cy - self.slide_offset_y), NSSize(cw, ch))
        self.char_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            char_rect, 0, NSBackingStoreBuffered, False
        )
        self.char_window.setOpaque_(False)
        self.char_window.setBackgroundColor_(NSColor.clearColor())
        self.char_window.setHasShadow_(True)
        self.char_window.setIgnoresMouseEvents_(True)
        self.char_window.setLevel_(25)
        self.char_window.setCollectionBehavior_(behavior)
        self.char_window.setAlphaValue_(0.0)

        # Load character image into NSImageView
        self.char_image_view = NSImageView.alloc().initWithFrame_(
            self.char_window.contentView().bounds()
        )
        self.char_image_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)

        if COMPANION_IMG.exists():
            image = NSImage.alloc().initWithContentsOfFile_(str(COMPANION_IMG.resolve()))
            self.char_image_view.setImage_(image)
            logger.info("Loaded companion character image: %s", COMPANION_IMG)
        else:
            logger.warning("Character image not found at %s", COMPANION_IMG)

        self.char_window.contentView().addSubview_(self.char_image_view)

        # 2. Glassmorphic Speech Bubble Window
        bubble_rect = NSRect(NSPoint(bx, by - self.slide_offset_y), NSSize(bw, bh))
        self.bubble_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            bubble_rect, 0, NSBackingStoreBuffered, False
        )
        self.bubble_window.setOpaque_(False)
        self.bubble_window.setBackgroundColor_(NSColor.clearColor())
        self.bubble_window.setHasShadow_(True)
        self.bubble_window.setIgnoresMouseEvents_(True)
        self.bubble_window.setLevel_(26)
        self.bubble_window.setCollectionBehavior_(behavior)
        self.bubble_window.setAlphaValue_(0.0)

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
            NSColor.colorWithRed_green_blue_alpha_(0.0, 0.95, 1.0, 0.4).CGColor()
        )

        text_rect = NSRect(NSPoint(16, 12), NSSize(bw - 32, bh - 24))
        self.bubble_text_view = NSTextView.alloc().initWithFrame_(text_rect)
        self.bubble_text_view.setBackgroundColor_(NSColor.clearColor())
        self.bubble_text_view.setDrawsBackground_(False)
        self.bubble_text_view.setEditable_(False)
        self.bubble_text_view.setSelectable_(False)
        self.bubble_text_view.setTextColor_(NSColor.whiteColor())
        self.bubble_text_view.setFont_(NSFont.systemFontOfSize_weight_(13.5, 0.25))

        self.bubble_effect_view.addSubview_(self.bubble_text_view)
        self.bubble_window.contentView().addSubview_(self.bubble_effect_view)

        logger.info("Character companion overlay initialized. Hidden until message arrives.")

    # ----------------------------------------------------
    # Entrance, Speaking, and Departure Sequence
    # ----------------------------------------------------
    @objc.python_method
    def onIncomingMessage(self, text: str, sender: str = "Assistant"):
        clean_text = text.strip()
        if not clean_text:
            return

        msg = QueuedMessage(clean_text, sender)
        self.message_queue.append(msg)

        if self.state == "hidden":
            self._startEntrance()

    @objc.python_method
    def _startEntrance(self):
        if not self.message_queue:
            return

        self.current_message = self.message_queue.pop(0)
        prefix = f"[{self.current_message.sender.upper()}]\n" if self.current_message.sender else ""
        self.bubble_text_view.setString_(f"{prefix}{self.current_message.text}")

        self.char_window.orderFrontRegardless()
        self.bubble_window.orderFrontRegardless()

        self.state = "entering"
        self._ensureAnimTimer()
        self._startSpeakingBobbingTimer()

        # Maximum duration watchdog timer: guarantees dismissal even if TTS completion event is missed
        if self.max_duration_timer:
            self.max_duration_timer.invalidate()
        self.max_duration_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            self.current_message.max_duration, self, "onMaxDurationExpired:", None, False
        )

    def onMaxDurationExpired_(self, timer):
        """Watchdog fired: speech has completed or exceeded maximum time. Force exit."""
        self.max_duration_timer = None
        logger.info("Message display duration reached. Beginning departure.")
        self.is_speech_active = False
        self._startExit()

    @objc.python_method
    def _ensureAnimTimer(self):
        if not self.anim_timer:
            self.anim_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.016, self, "animTick:", None, True
            )

    @objc.python_method
    def _startSpeakingBobbingTimer(self):
        if not self.speak_anim_timer:
            self.speak_anim_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.03, self, "speakTick:", None, True
            )

    def speakTick_(self, timer):
        """Natural breathing and speaking micro-bobbing while active."""
        if self.state in ("entering", "speaking"):
            self.speak_step += 0.08
            bob = math.sin(self.speak_step * 2.5) * 2.5
            current_origin = self.char_window.frame().origin
            self.char_window.setFrameOrigin_(NSPoint(current_origin.x, self.base_char_origin.y + bob))

    def animTick_(self, timer):
        """Smooth sliding & alpha interpolation."""
        if self.state == "entering":
            self.anim_progress = min(1.0, self.anim_progress + 0.08)
            t = self.anim_progress
            eased = 1.0 - (1.0 - t) * (1.0 - t)

            offset = (1.0 - eased) * self.slide_offset_y
            self.char_window.setFrameOrigin_(
                NSPoint(self.base_char_origin.x, self.base_char_origin.y - offset)
            )
            self.bubble_window.setFrameOrigin_(
                NSPoint(self.base_bubble_origin.x, self.base_bubble_origin.y - offset)
            )

            self.char_window.setAlphaValue_(eased)
            self.bubble_window.setAlphaValue_(eased)

            if self.anim_progress >= 0.999:
                self.state = "speaking"
                self.anim_progress = 1.0
                if not self.is_speech_active:
                    self._checkSpeechFinished()

        elif self.state == "exiting":
            self.anim_progress = max(0.0, self.anim_progress - 0.07)
            t = 1.0 - self.anim_progress
            eased = t * t

            offset = eased * self.slide_offset_y
            self.char_window.setFrameOrigin_(
                NSPoint(self.base_char_origin.x, self.base_char_origin.y - offset)
            )
            self.bubble_window.setFrameOrigin_(
                NSPoint(self.base_bubble_origin.x, self.base_bubble_origin.y - offset)
            )

            self.char_window.setAlphaValue_(self.anim_progress)
            self.bubble_window.setAlphaValue_(self.anim_progress)

            if self.anim_progress <= 0.001:
                self.state = "hidden"
                self.char_window.orderOut_(None)
                self.bubble_window.orderOut_(None)

                if self.speak_anim_timer:
                    self.speak_anim_timer.invalidate()
                    self.speak_anim_timer = None

                # Check if next message in queue
                if self.message_queue:
                    self._startEntrance()
                else:
                    if self.anim_timer:
                        self.anim_timer.invalidate()
                        self.anim_timer = None

    @objc.python_method
    def onSpeechStarted(self, message: str = "", persona: str = "Assistant"):
        self.is_speech_active = True
        self.onIncomingMessage(message, persona)

    @objc.python_method
    def onSpeechEnded(self):
        self.is_speech_active = False
        self._checkSpeechFinished()

    @objc.python_method
    def _checkSpeechFinished(self):
        if not self.is_speech_active and self.state in ("speaking", "entering"):
            linger = float(self.config.get("linger_seconds", 1.2))
            if self.linger_timer:
                self.linger_timer.invalidate()
            self.linger_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                linger, self, "onLingerExpired:", None, False
            )

    def onLingerExpired_(self, timer):
        self.linger_timer = None
        self._startExit()

    @objc.python_method
    def _startExit(self):
        if self.max_duration_timer:
            self.max_duration_timer.invalidate()
            self.max_duration_timer = None

        if self.state != "hidden":
            self.state = "exiting"
            self._ensureAnimTimer()

    # ----------------------------------------------------
    # Command Dispatching
    # ----------------------------------------------------
    def handleCommand_(self, cmd):
        action = cmd.get("action")
        if not action:
            return

        if action == "speaking_start":
            msg = cmd.get("message", "")
            persona = cmd.get("persona", "Assistant")
            self.onSpeechStarted(msg, persona)
        elif action == "speaking_end":
            self.onSpeechEnded()
        elif action == "message":
            text = cmd.get("text", "")
            sender = cmd.get("sender", "Assistant")
            if text:
                self.onIncomingMessage(text, sender)
        elif action in ("hide", "dismiss"):
            self._startExit()


class SocketServerThread(threading.Thread):
    def __init__(self, controller: CompanionOverlayController):
        super().__init__(daemon=True, name="CompanionSocketServer")
        self.controller = controller
        self.running = True

    def run(self):
        if is_socket_in_use(SOCKET_PATH):
            logger.warning("Another overlay instance is using %s. Exiting listener.", SOCKET_PATH)
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
        logger.info("Companion overlay socket listening on %s", SOCKET_PATH)

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
        class Dispatcher(NSObject):
            def runOnMain_(self, arg):
                controller, cmd = arg
                controller.handleCommand_(cmd)

        d = Dispatcher.alloc().init()
        d.performSelectorOnMainThread_withObject_waitUntilDone_(
            "runOnMain:", (self.controller, payload), False
        )


def main():
    parser = argparse.ArgumentParser(description="MacAssistant Desktop AI Character Companion Overlay")
    parser.parse_args()

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    controller = CompanionOverlayController.alloc().init()
    controller.setupWindows()

    sock_thread = SocketServerThread(controller)
    sock_thread.start()

    logger.info("Desktop AI Companion character overlay running.")
    app.run()


if __name__ == "__main__":
    main()
