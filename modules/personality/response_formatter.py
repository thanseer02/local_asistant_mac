"""Cleans and shapes text for human-like spoken responses, managing reaction sounds and fillers."""

import random
import re
from typing import Optional


class ReactionSoundManager:
    """Manages natural thinking and reaction words:

    - Injected sparingly, about once every 2-3 replies (~35-40% probability).
    - Matches moment: tricky/uncertain, realization, success, error/correction, surprise.
    - Placed at the start followed by a comma or ellipsis.
    - Never used for urgent alerts, reminders, or short confirmations ("Done.").
    - Never spells out laughter or sounds like *sigh* or *laughs*.
    """

    _turn_counter: int = 0

    FILLERS = {
        "thinking": ["Hmm...", "Let me think...", "Well..."],
        "realization": ["Ohh, I see.", "Ahh, that makes sense.", "Ahh, right."],
        "success": ["Oh nice!", "Ha, that worked."],
        "correction": ["Oh wait, actually..."],
        "error": ["Oops, sorry about that.", "Oops, my bad."],
        "surprise": ["Oh? Interesting."],
        "general": ["Okay, so...", "Ah, got it.", "Alright,"]
    }

    @classmethod
    def clean_spelled_out_sounds(cls, text: str) -> str:
        """Removes spelled-out sounds like *sigh*, *laughs*, *chuckles*, [laughs]."""
        if not text:
            return ""
        # Remove *sigh*, *laughs*, *chuckles*, (sigh), etc.
        t = re.sub(r"[\*\({\[]\s*(sigh|laughs?|chuckles?|gasps?|giggles?|clears throat)\s*[\*\)}\]]", "", text, flags=re.IGNORECASE)
        return t.strip()

    @classmethod
    def maybe_add_filler(cls, text: str, context_type: str = "general") -> str:
        """Adds a natural filler sparingly (~once every 2-3 turns) if not already present."""
        if not text or len(text.strip()) == 0:
            return text

        clean = text.strip()

        # Never add to short confirmations, urgent alerts, or reminders
        if clean in ["Done.", "Done", "On it.", "Understood.", "Right away."]:
            return clean

        # Check if already has a filler
        for category, items in cls.FILLERS.items():
            for f in items:
                f_clean = f.rstrip(".!,").lower()
                if clean.lower().startswith(f_clean):
                    return clean

        cls._turn_counter += 1

        # Trigger once every 2-3 replies
        if cls._turn_counter % 3 == 0:
            pool = cls.FILLERS.get(context_type, cls.FILLERS["general"])
            chosen = random.choice(pool)
            return f"{chosen} {clean}"

        return clean


class ResponseFormatter:
    """Formats LLM output into clean, natural speech:

    - Removes markdown syntax, asterisks, bullet points, and code blocks.
    - Strips URLs and replaces degree signs with words.
    - Injects subtle natural breathing pauses and reaction fillers.
    - Removes redundant 'Sir' or 'As an AI language model' boilerplate.
    """

    @classmethod
    def format_for_speech(cls, text: str, max_sentences: int = 2) -> str:
        if not text:
            return ""

        t = text.strip()

        # Clean spelled out sounds like *sigh* or *laughs*
        t = ReactionSoundManager.clean_spelled_out_sounds(t)

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

        # Spoken units and times
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
