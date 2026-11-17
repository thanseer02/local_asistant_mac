"""Local Ollama-powered error analyzer for Dart, Flutter, Gradle, CocoaPods, and Python."""

import logging
from typing import Optional
from mac_assistant.ollama_client import OllamaClient
from .security import DeveloperSecurityPolicy

logger = logging.getLogger("MacAssistant.ErrorAnalyzer")


class ErrorAnalyzer:
    """
    Analyzes error stack traces using local Ollama model (100% offline).
    Specialized for:
    - Dart & Flutter syntax and runtime exceptions
    - Gradle & Android build failures
    - CocoaPods & iOS build issues
    - Python exceptions, tracebacks, and dependency conflicts
    """

    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.ollama = ollama_client or OllamaClient()

    def analyze_error(self, error_text: str, context: Optional[str] = None) -> str:
        """
        Sends error snippet to local Ollama with focused diagnostic instructions.
        Returns a concise, 1-3 sentence spoken resolution.
        """
        if not error_text or len(error_text.strip()) < 5:
            return "Please provide an error message or stack trace to diagnose."

        # Redact secrets before sending to LLM
        clean_error = DeveloperSecurityPolicy.redact_secrets(error_text.strip())[:1500]

        if not self.ollama.is_available():
            return "Local AI model is not running. Here is the raw error summary: " + clean_error[:120]

        system_instruction = (
            "You are an expert developer diagnostics assistant specializing in Flutter, Dart, "
            "Android Gradle, iOS CocoaPods, and Python. "
            "Analyze the given error and provide the root cause and concrete fix in 2 short, direct spoken sentences. "
            "Never use markdown, bullet points, asterisks, or code fences."
        )

        user_content = f"Error snippet:\n{clean_error}"
        if context:
            user_content += f"\nProject Context: {context}"

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ]

        logger.info("Analyzing error trace via local Ollama (%d chars)...", len(clean_error))
        reply = self.ollama.chat(messages, temperature=0.2, max_tokens=120)

        if reply:
            # Clean punctuation/markdown for spoken output
            clean_reply = reply.replace("*", "").replace("`", "").replace("#", "").strip()
            return clean_reply

        return "I could not identify the root cause from the provided snippet. Check if dependencies need updating."
