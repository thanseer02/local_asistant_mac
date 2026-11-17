"""Local WebSocket & REST status server for Friday/Jarvis Control Center."""

import asyncio
import json
import logging
from typing import List, Set
from mac_assistant.gui.bridge_service import AssistantBridgeService

logger = logging.getLogger("MacAssistant.StatusServer")


class StatusServer:
    """
    Lightweight, localhost-only async server broadcasting WebSocket updates:
    - Binds strictly to 127.0.0.1:8765 to prevent external exposure.
    - Broadcasts live status (state, CPU, RAM, active persona) every 2 seconds.
    - Handles incoming control actions (switch persona, clear history, restart).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.bridge = AssistantBridgeService()
        self.clients: Set[Any] = set()
        self._server = None
        self._running = False

    async def register(self, ws):
        self.clients.add(ws)
        # Send immediate status on connect
        status = self.bridge.get_current_status()
        await ws.send(json.dumps({"type": "status_update", "data": status.__dict__}))

    async def unregister(self, ws):
        self.clients.discard(ws)

    async def broadcast_status(self):
        while self._running:
            if self.clients:
                status = self.bridge.get_current_status()
                message = json.dumps({"type": "status_update", "data": status.__dict__})
                disconnected = set()
                for client in self.clients:
                    try:
                        await client.send(message)
                    except Exception:
                        disconnected.add(client)
                for client in disconnected:
                    self.clients.discard(client)
            await asyncio.sleep(2.0)

    async def handle_message(self, ws, message_str: str):
        try:
            req = json.loads(message_str)
            action = req.get("action")

            if action == "switch_persona":
                target = req.get("persona")
                ok = self.bridge.switch_active_persona(target)
                await ws.send(json.dumps({"type": "response", "action": action, "success": ok}))

            elif action == "restart_daemon":
                ok, msg = self.bridge.restart_assistant_service()
                await ws.send(json.dumps({"type": "response", "action": action, "success": ok, "message": msg}))

            elif action == "clear_history":
                ok = self.bridge.clear_conversation_history()
                await ws.send(json.dumps({"type": "response", "action": action, "success": ok}))

            elif action == "get_history":
                history = self.bridge.get_conversation_history()
                await ws.send(json.dumps({"type": "history_data", "data": history}))

        except Exception as e:
            logger.error("Error handling websocket client message: %s", e)

    async def ws_handler(self, ws):
        await self.register(ws)
        try:
            async for msg in ws:
                await self.handle_message(ws, msg)
        except Exception:
            pass
        finally:
            await self.unregister(ws)

    async def start(self):
        try:
            import websockets
            self._running = True
            logger.info("Starting local WebSocket status server on ws://%s:%d...", self.host, self.port)
            self._server = await websockets.serve(self.ws_handler, self.host, self.port)
            asyncio.create_task(self.broadcast_status())
        except Exception as e:
            logger.error("Failed starting WebSocket status server: %s", e)
