"""Bot V's tools: native functions, Home Assistant and MCP servers, all in JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from bot_v.config import Settings, settings as default_settings
from bot_v.tools.mcp_client import MCPManager
from bot_v.tools.native import register_native_tools
from bot_v.tools.registry import Approver, Tool, ToolRegistry


def build_default_tools(s: Optional[Settings] = None, approver: Optional[Approver] = None
                        ) -> Tuple[ToolRegistry, Optional[MCPManager]]:
    """Registry with native tools, Home Assistant (if configured) and the MCP manager.

    MCP servers are not started here; Bot V starts them on first tool use.
    """
    s = s or default_settings
    registry = ToolRegistry(approver=approver)
    register_native_tools(registry)
    if s.ha_url and s.ha_token:
        from bot_v.integrations.home_assistant import HomeAssistantClient, register_home_assistant_tools

        client = HomeAssistantClient(s.ha_url, s.ha_token, entities=s.ha_entities,
                                     allow_dangerous=s.ha_allow_dangerous)
        register_home_assistant_tools(registry, client)
    mcp = MCPManager(Path(s.mcp_config)) if s.mcp_config else None
    return registry, mcp


__all__ = ["MCPManager", "Tool", "ToolRegistry", "build_default_tools"]
