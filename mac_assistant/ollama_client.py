"""Local Ollama client for intent classification, tool decision, and conversational response generation."""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("MacAssistant.OllamaClient")


class OllamaClient:
    """
    HTTP client for local Ollama server (http://localhost:11434).
    Provides structured intent parsing and natural conversational responses.
    Zero cloud dependencies.
    """

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.2:1b"):
        self.host = host.rstrip("/")
        self.model = model

    def is_available(self) -> bool:
        """Checks if local Ollama daemon is reachable."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Lists installed local models."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 250
    ) -> Optional[str]:
        """Generates natural conversational response given chat history."""
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                result = json.loads(resp.read().decode())
                return result.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.error("Error communicating with Ollama: %s", e)
            return None

    def classify_and_extract_tool(
        self,
        utterance: str,
        tool_descriptions: str
    ) -> Optional[Dict[str, Any]]:
        """
        Uses Ollama to determine if utterance is an action tool or conversation.
        Returns structured dictionary when an action is detected.
        """
        system_prompt = (
            "You are an intent classification engine for a macOS desktop assistant.\n"
            "Analyze the user's input and determine if it maps to an available Mac tool action or is conversation.\n"
            f"Available tools:\n{tool_descriptions}\n\n"
            "Respond ONLY with a valid JSON object in one of two formats:\n"
            "For actions:\n"
            '{"mode": "action", "action": "<tool_name>", "parameters": {<args>}, "confidence": 0.95, "requires_confirmation": false}\n'
            "For conversation/questions:\n"
            '{"mode": "conversation"}\n'
            "Do not include markdown blocks or any other text."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": utterance}
        ]

        raw = self.chat(messages, temperature=0.0, max_tokens=150)
        if not raw:
            return None

        # Clean JSON markdown if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1]
            if clean.endswith("```"):
                clean = clean.rsplit("```", 1)[0]
        clean = clean.strip()

        try:
            return json.loads(clean)
        except Exception:
            return None
