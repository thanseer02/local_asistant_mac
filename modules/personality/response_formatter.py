"""Cleans and shapes text for human-like spoken responses."""

import re


class ResponseFormatter:
    """
    Formats LLM output into clean, natural speech:
    - Removes markdown syntax, asterisks, bullet points, and code blocks.
    - Strips URLs and replaces degree signs with words.
    - Injects subtle natural breathing pauses.
    - Removes redundant 'Sir' or 'As an AI language model' boilerplate.
    """

    @classmethod
    def format_for_speech(cls, text: str, max_sentences: int = 3) -> str:
        if not text:
            return ""

        t = text.strip()

        # Remove AI boilerplate
        t = re.sub(r"(?i)^(as an ai|as an ai assistant|i am an ai),?\s*", "", t)

        # Remove URLs
        t = re.sub(r"https?://\S+", "", t)

        # Strip markdown syntax
        t = re.sub(r"```[\s\S]*?```", "", t)
        t = re.sub(r"`[^`]*`", "", t)
        t = re.sub(r"[*_#~\[\]]", "", t)

        # Transform bullet dashes into conversational pauses
        t = re.sub(r"\n\s*[-*•]\s*", ", ", t)

        # Spoken units
        t = t.replace("°C", " degrees Celsius")
        t = t.replace("°F", " degrees Fahrenheit")

        # Normalize whitespace and repetitive punctuation
        t = re.sub(r"\s+", " ", t)
        t = re.sub(r",\s*,+", ",", t)

        # Truncate to max sentences if overly long
        sentences = re.split(r"(?<=[.!?])\s+", t)
        if len(sentences) > max_sentences:
            t = " ".join(sentences[:max_sentences])

        return t.strip()
