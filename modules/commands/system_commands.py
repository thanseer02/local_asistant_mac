"""System information, date/time, and volume command handlers."""

from datetime import datetime
from typing import Any, Dict
from modules.services.mac_automation import MacAutomationService


def handle_get_datetime(args: Dict[str, Any]) -> Dict[str, Any]:
    """Returns the current date and time."""
    now = datetime.now()
    return {
        "success": True,
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "iso": now.isoformat()
    }


def handle_get_battery(args: Dict[str, Any]) -> Dict[str, Any]:
    """Returns current battery status."""
    info = MacAutomationService.get_system_battery()
    return {"success": True, "battery": info}


def handle_set_volume(args: Dict[str, Any]) -> Dict[str, Any]:
    """Sets system audio volume level."""
    level = args.get("level", 50)
    success = MacAutomationService.set_volume(level)
    return {"success": success, "level": level}
