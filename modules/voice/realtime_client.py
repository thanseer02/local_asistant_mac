"""OpenAI Realtime WebSocket client managing duplex speech-to-speech connection."""

import asyncio
import base64
import json
from typing import Any, Callable, Dict, Optional

import websockets
from modules.services.logging_service import logger


class OpenAIRealtimeClient:
    """
    Manages WebSocket connection to OpenAI Realtime API (wss://api.openai.com/v1/realtime).
    Handles duplex streaming of PCM audio in/out, VAD server events, and tool calling.
    """

    REALTIME_URL = "wss://api.openai.com/v1/realtime?model="

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-realtime-preview-2024-12-17",
        voice: str = "alloy",
        instructions: str = "",
        tools: Optional[list] = None
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.tools = tools or []

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._receive_task: Optional[asyncio.Task] = None

        # Event Callbacks
        self.on_audio_delta: Optional[Callable[[bytes], None]] = None
        self.on_speech_started: Optional[Callable[[], None]] = None
        self.on_speech_stopped: Optional[Callable[[], None]] = None
        self.on_tool_call: Optional[Callable[[str, str, str], Any]] = None  # (call_id, name, args)
        self.on_text_delta: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None

    async def connect(self) -> bool:
        """Establishes WebSocket connection to OpenAI Realtime endpoint."""
        if not self.api_key:
            logger.error("OpenAI API Key is missing. Set OPENAI_API_KEY in environment or .env file.")
            return False

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        url = f"{self.REALTIME_URL}{self.model}"

        try:
            logger.info(f"Connecting to OpenAI Realtime API ({self.model})...")
            self._ws = await websockets.connect(url, extra_headers=headers)
            self._connected = True
            logger.info("Connected to OpenAI Realtime API.")

            # Configure session parameters
            await self._update_session()

            # Start message receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            return True
        except Exception as e:
            logger.error(f"Failed connecting to OpenAI Realtime API: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Closes the WebSocket connection."""
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        logger.info("Disconnected from OpenAI Realtime API.")

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Streams a chunk of base64-encoded PCM audio to OpenAI input buffer."""
        if not self.is_connected or not pcm_bytes:
            return

        b64_audio = base64.b64encode(pcm_bytes).decode("utf-8")
        event = {
            "type": "input_audio_buffer.append",
            "audio": b64_audio
        }
        try:
            await self._ws.send(json.dumps(event))
        except Exception as e:
            logger.debug(f"Error sending audio chunk: {e}")

    async def send_tool_output(self, call_id: str, output_str: str) -> None:
        """Submits tool execution output back to the conversation session."""
        if not self.is_connected:
            return

        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": output_str
            }
        }
        await self._ws.send(json.dumps(event))

        # Request assistant response continuation
        await self._ws.send(json.dumps({"type": "response.create"}))

    async def cancel_response(self) -> None:
        """Truncates / cancels current assistant response on user barge-in."""
        if not self.is_connected:
            return
        try:
            await self._ws.send(json.dumps({"type": "response.cancel"}))
        except Exception as e:
            logger.debug(f"Error sending response.cancel: {e}")

    async def _update_session(self) -> None:
        """Sends session configuration event to OpenAI."""
        session_event = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": self.instructions,
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 600
                },
                "tools": self.tools
            }
        }
        await self._ws.send(json.dumps(session_event))
        logger.info("Session configuration updated with OpenAI Realtime.")

    async def _receive_loop(self) -> None:
        """Reads and routes incoming WebSocket events from OpenAI."""
        active_tool_calls: Dict[str, Dict[str, str]] = {}

        try:
            async for raw_message in self._ws:
                event = json.loads(raw_message)
                event_type = event.get("type", "")

                # 1. User started speaking -> Trigger immediate barge-in / interrupt
                if event_type == "input_audio_buffer.speech_started":
                    logger.info("User speech detected by server VAD -> Barge-in trigger.")
                    if self.on_speech_started:
                        self.on_speech_started()

                # 2. User stopped speaking
                elif event_type == "input_audio_buffer.speech_stopped":
                    if self.on_speech_stopped:
                        self.on_speech_stopped()

                # 3. Audio Delta received from Assistant -> Forward to speaker queue
                elif event_type == "response.audio.delta":
                    delta_b64 = event.get("delta", "")
                    if delta_b64 and self.on_audio_delta:
                        audio_bytes = base64.b64decode(delta_b64)
                        self.on_audio_delta(audio_bytes)

                # 4. Text Transcript Delta (optional logging/display)
                elif event_type == "response.audio_transcript.delta":
                    text = event.get("delta", "")
                    if text and self.on_text_delta:
                        self.on_text_delta(text)

                # 5. Function/Tool Call parts
                elif event_type == "response.function_call_arguments.delta":
                    call_id = event.get("call_id")
                    name = event.get("name", "")
                    delta = event.get("delta", "")
                    if call_id:
                        if call_id not in active_tool_calls:
                            active_tool_calls[call_id] = {"name": name, "arguments": ""}
                        active_tool_calls[call_id]["arguments"] += delta

                elif event_type == "response.function_call_arguments.done":
                    call_id = event.get("call_id")
                    name = event.get("name")
                    args = event.get("arguments", "")
                    if self.on_tool_call and call_id and name:
                        asyncio.create_task(self.on_tool_call(call_id, name, args))
                    if call_id in active_tool_calls:
                        del active_tool_calls[call_id]

                # 6. Error event
                elif event_type == "error":
                    err = event.get("error", {})
                    logger.error(f"OpenAI Realtime error: {err}")
                    if self.on_error:
                        self.on_error(str(err))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in OpenAI Realtime receive loop: {e}")
            self._connected = False
