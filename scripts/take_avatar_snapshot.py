#!/usr/bin/env python3
"""Renders a snapshot of the 3D VRM avatar into a PNG file."""

import os
import sys
import time
from pathlib import Path

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSColor,
    NSWindow,
    NSWindowCollectionBehaviorStationary,
)
from Foundation import NSObject, NSPoint, NSRect, NSSize, NSTimer, NSURL
from WebKit import WKWebView, WKWebViewConfiguration

PROJECT_ROOT = Path(__file__).resolve().parent
HTML_PATH = PROJECT_ROOT / "modules" / "ui" / "web" / "avatar.html"
OUTPUT_PNG = Path("/Users/tanseer/.gemini/antigravity/brain/e8462cbd-4c26-485b-b8fc-5df0e1ed02f6/avatar_render.png")


class SnapshotTaker(NSObject):
    def init(self):
        self = objc.super(SnapshotTaker, self).init()
        self.window = None
        self.webview = None
        return self

    def start(self):
        rect = NSRect(NSPoint(100, 100), NSSize(480, 560))
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, 0, 2, False
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(NSColor.clearColor())

        cfg = WKWebViewConfiguration.alloc().init()
        cfg.preferences().setValue_forKey_(True, "allowFileAccessFromFileURLs")
        cfg.setValue_forKey_(True, "allowUniversalAccessFromFileURLs")

        self.webview = WKWebView.alloc().initWithFrame_configuration_(
            self.window.contentView().bounds(), cfg
        )
        self.webview.setValue_forKey_(False, "drawsBackground")
        self.window.contentView().addSubview_(self.webview)

        html_url = NSURL.fileURLWithPath_(str(HTML_PATH.resolve()))
        self.webview.loadFileURL_allowingReadAccessToURL_(
            html_url, NSURL.fileURLWithPath_(str(PROJECT_ROOT.resolve()))
        )
        self.window.orderFrontRegardless()

        # Wait 4 seconds for model to load and render, then snapshot
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            4.0, self, "captureSnapshot:", None, False
        )

    def captureSnapshot_(self, timer):
        print("Capturing snapshot of rendered avatar...")

        def _completion_handler(image, error):
            if error:
                print("Snapshot error:", error)
            elif image:
                bitmap_rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
                png_data = bitmap_rep.representationUsingType_properties_(
                    NSBitmapImageFileTypePNG, None
                )
                OUTPUT_PNG.parent.mkdir(parents=True, exist_ok=True)
                png_data.writeToFile_atomically_(str(OUTPUT_PNG), True)
                print(f"Snapshot successfully saved to {OUTPUT_PNG}")
            NSApplication.sharedApplication().terminate_(None)

        self.webview.takeSnapshotWithConfiguration_completionHandler_(None, _completion_handler)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    taker = SnapshotTaker.alloc().init()
    taker.start()
    app.run()


if __name__ == "__main__":
    main()
