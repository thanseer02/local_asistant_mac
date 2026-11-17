"""Smart greeting manager providing time-aware, non-repetitive greetings."""

import random
import time
from datetime import datetime
from typing import Optional


class GreetingManager:
    """
    Manages natural, time-aware greetings while strictly preventing repetitive hellos:
    - Avoids saying 'Good morning' or 'Hello Sir' on every single activation.
    - Caches the last greeted timestamp; uses simple acknowledgments ('I'm here', 'Standing by') if recently spoken.
    """

    def __init__(self, repeat_cooldown_seconds: float = 600.0):
        self.repeat_cooldown = repeat_cooldown_seconds
        self.last_greeting_time: float = 0.0
        self._last_chosen_greeting: Optional[str] = None

    def get_activation_greeting(self, persona: str = "friday", force_full: bool = False) -> str:
        now = time.time()
        hour = datetime.now().hour

        # If recently greeted (within 10 minutes), use brief acknowledgments
        if not force_full and (now - self.last_greeting_time < self.repeat_cooldown):
            quick_acks = [
                "I'm here. What's on your mind?",
                "Right here! What do you need?",
                "Listening! How can I help?",
                "Standing by.",
                "Yes? What can I do for you?"
            ]
            return random.choice(quick_acks)

        self.last_greeting_time = now

        if 5 <= hour < 12:
            pool = [
                "Good morning! I'm ready whenever you are.",
                "Morning! Hope you have a productive day ahead.",
                "Good morning. Systems are primed and ready."
            ]
        elif 12 <= hour < 17:
            pool = [
                "Good afternoon! How's your day going so far?",
                "Good afternoon. Standing by for whatever you need.",
                "Afternoon! Ready to assist."
            ]
        elif 17 <= hour < 22:
            pool = [
                "Good evening! Ready to wrap up or keep going?",
                "Good evening. How can I help you finish up today?",
                "Evening! What are we working on?"
            ]
        else:
            pool = [
                "Working late tonight? I'm right here with you.",
                "Still up? Let's get this done so you can rest.",
                "Night shift! What can I take off your plate?"
            ]

        candidates = [g for g in pool if g != self._last_chosen_greeting] or pool
        chosen = random.choice(candidates)
        self._last_chosen_greeting = chosen
        return chosen
