"""Application launch command handlers."""

from typing import Dict, Any
from modules.services.mac_automation import MacAutomationService


def handle_open_app(args: Dict[str, Any]) -> Dict[str, Any]:
    """Handles tool call for opening applications."""
    app_name = args.get("app_name", "").strip()
    if not app_name:
        return {"success": False, "error": "app_name parameter is required."}

    success, message = MacAutomationService.open_application(app_name)
    return {"success": success, "message": message}
