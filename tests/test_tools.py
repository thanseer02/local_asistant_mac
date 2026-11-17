"""Tests for tool registry and safe automation execution."""

import json
from modules.ai.tool_registry import ToolRegistry


def test_tool_definitions():
    registry = ToolRegistry()
    tools = registry.get_tool_definitions()
    assert len(tools) >= 5
    names = [t["name"] for t in tools]
    assert "open_application" in names
    assert "search_flutter_projects" in names
    assert "get_current_datetime" in names


def test_datetime_tool_execution():
    registry = ToolRegistry()
    res = registry.execute_tool("get_current_datetime", "{}")
    data = json.loads(res)
    assert data.get("success") is True
    assert "time" in data
    assert "date" in data


def test_unauthorized_app_blocked():
    registry = ToolRegistry()
    res = registry.execute_tool("open_application", json.dumps({"app_name": "malicious_app_name"}))
    data = json.loads(res)
    assert data.get("success") is False
    assert "not in the authorized allowlist" in data.get("message", "")


if __name__ == "__main__":
    test_tool_definitions()
    test_datetime_tool_execution()
    test_unauthorized_app_blocked()
    print("All tool registry tests passed successfully!")
