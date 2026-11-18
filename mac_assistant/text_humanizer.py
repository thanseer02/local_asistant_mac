"""Text humanization, number-to-words conversion, and spoken language cleaning."""

import re
from typing import List

# Number maps for spoken conversion
ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen"
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_to_words(n: int) -> str:
    """Converts an integer (up to millions) into natural spoken English words."""
    if n < 0:
        return f"minus {number_to_words(abs(n))}"
    if n < 20:
        return ONES[n]
    if n < 100:
        remainder = n % 10
        return TENS[n // 10] if remainder == 0 else f"{TENS[n // 10]}-{ONES[remainder]}"
    if n < 1000:
        remainder = n % 100
        base = f"{ONES[n // 100]} hundred"
        return base if remainder == 0 else f"{base} and {number_to_words(remainder)}"
    if n < 1_000_000:
        thousands = n // 1000
        remainder = n % 1000
        base = f"{number_to_words(thousands)} thousand"
        return base if remainder == 0 else f"{base}, {number_to_words(remainder)}"
    return str(n)


def convert_time_to_spoken(match: re.Match) -> str:
    """Converts 24h or 12h time strings like '19:30' or '07:15' into natural spoken phrasing."""
    hour = int(match.group(1))
    minute = int(match.group(2))

    period = "in the morning"
    if hour >= 12:
        period = "in the afternoon" if hour < 17 else "in the evening"
    if hour == 0:
        h12 = 12
    elif hour > 12:
        h12 = hour - 12
    else:
        h12 = hour

    h_word = number_to_words(h12)
    if minute == 0:
        return f"{h_word} o'clock {period}"
    elif minute < 10:
        return f"{h_word} oh {number_to_words(minute)} {period}"
    else:
        return f"{h_word} {number_to_words(minute)} {period}"


def humanize(text: str) -> str:
    """
    Cleans raw text and converts it into pure spoken English suitable for TTS:
    - Strips markdown, emojis, code spans, URLs, and [[say commands]]
    - Converts temperatures (22°C -> twenty-two degrees)
    - Converts clock times (19:30 -> seven thirty in the evening)
    - Expands abbreviations (Dr., vs., e.g., i.e.)
    - Replaces dashes with soft commas for natural phrasing
    - Normalizes punctuation and sentence flow
    """
    if not text:
        return ""

    s = text.strip()

    # Strip say-specific embedded tags like [[pbas +0]] or [[slnc 150]]
    s = re.sub(r"\[\[[^\]]+\]\]", " ", s)

    # Strip URLs
    s = re.sub(r"https?://\S+", "", s)

    # Strip markdown headers, bold, italics, code blocks
    s = re.sub(r"```[\s\S]*?```", "", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.MULTILINE)

    # Strip emojis (high unicode range)
    s = re.sub(r"[\U00010000-\U0010ffff]", "", s)
    s = re.sub(r"[\u2600-\u27bf]", "", s)

    # Temperatures: e.g. 29°C, -4°C, 75°F, 22 deg
    def _replace_temp(m: re.Match) -> str:
        val = int(m.group(1))
        unit = m.group(2)
        words = number_to_words(val)
        if unit.upper() == "F":
            return f"{words} degrees Fahrenheit"
        return f"{words} degrees"

    s = re.sub(r"(-?\d+)\s*°\s*([CcFf])?", _replace_temp, s)
    s = re.sub(r"(-?\d+)\s*(?:deg|degrees)\s*([CcFf])?", _replace_temp, s)

    # 24-hour / 12-hour clock times e.g. 19:30, 08:45
    s = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", convert_time_to_spoken, s)

    # Percentages: 45% -> forty-five percent
    s = re.sub(r"(\d+)\s*%", lambda m: f"{number_to_words(int(m.group(1)))} percent", s)

    # Common abbreviations expansion
    abbreviations = [
        (r"\bDr\.\s*", "Doctor "),
        (r"\bvs\.?\s*", "versus "),
        (r"\be\.g\.,?\s*", "for example, "),
        (r"\bi\.e\.,?\s*", "that is, "),
        (r"\betc\.?\s*", "and so forth "),
        (r"\bapprox\.?\s*", "approximately "),
        (r"\bmin\.\s*", "minimum "),
        (r"\bmax\.\s*", "maximum "),
        (r"\bhrs?\.\s*", "hours "),
        (r"\bsec\.\s*", "seconds "),
    ]
    for pattern, replacement in abbreviations:
        s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)

    # Dashes and bullet hyphens into commas / pauses
    s = re.sub(r"\s*--\s*", ", ", s)
    s = re.sub(r"\s*—\s*", ", ", s)
    s = re.sub(r"^\s*[-*•]\s*", "", s, flags=re.MULTILINE)

    # Clean multiple spaces or awkward commas
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r",\s*,+", ",", s)
    s = re.sub(r"\s+([.,!?])", r"\1", s)

    return s.strip()


def split_sentences(text: str) -> List[str]:
    """Splits text into spoken sentence chunks preserving punctuation for audio pipelining."""
    if not text:
        return []
    # Split on period, exclamation, question mark, or semicolon followed by whitespace or end of string
    raw_parts = re.split(r"(?<=[.!?])\s+", text)
    sentences = [p.strip() for p in raw_parts if p.strip()]
    return sentences if sentences else [text.strip()]
