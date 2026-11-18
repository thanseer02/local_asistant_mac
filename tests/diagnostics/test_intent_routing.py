#!/usr/bin/env python3
"""Step 3 Diagnostic Script: Pipeline & Intent Routing Test Suite."""

from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mac_assistant.conversation_router import ConversationRouter
from mac_assistant.ollama_client import OllamaClient


def test_intent_routing():
    print("=" * 70)
    print("DIAGNOSTIC STEP 3: Intent Routing & LLM Benchmark (30 Sample Commands)")
    print("=" * 70)

    router = ConversationRouter()

    test_commands = [
        ("what time is it", "check_datetime"),
        ("what is today's date", "check_datetime"),
        ("battery status", "battery_status"),
        ("check battery level", "battery_status"),
        ("disk space", "disk_space"),
        ("how much free disk space do I have", "disk_space"),
        ("open Google Chrome", "open_application"),
        ("launch Visual Studio Code", "open_application"),
        ("open Terminal", "open_application"),
        ("find flutter projects", "find_flutter"),
        ("search for pdf", "find_pdf"),
        ("stop", "stop"),
        ("quiet", "stop"),
        ("mute microphone", "mute_mic"),
        ("switch to jarvis", "switch_persona"),
        ("switch to friday", "switch_persona"),
        ("what can you do", "capabilities"),
        ("help me", "capabilities"),
        ("remember that my gate code is 4321", "remember_fact"),
        ("what did I tell you to remember about my gate code", "recall_fact"),
        ("delete all my files", "destructive_rejected"),
        ("rm -rf system", "destructive_rejected"),
        ("toggle humor", "personality_control"),
        ("set response length to concise", "personality_control"),
        ("what were we talking about", "recall_memory"),
        ("clear history", "clear_memory"),
        ("hello", "wake_call"),
        ("how are you", "conversation_fallback"),
        ("explain recursion", "conversation"),
        ("tell me a quick joke", "conversation")
    ]

    passed = 0
    failed = 0

    for idx, (cmd, expected_intent) in enumerate(test_commands, 1):
        t0 = time.time()
        try:
            intent, ok, reply = router.route(cmd, persona="friday")
            dt = (time.time() - t0) * 1000
            # Check match
            match = (intent == expected_intent) or (expected_intent == "conversation" and intent in ["conversation", "ollama_unavailable"])
            status = "PASS" if match else "FAIL"
            if match:
                passed += 1
            else:
                failed += 1
            print(f"[{idx:02d}] {status:4s} | Cmd: '{cmd[:30]:30s}' -> Intent: '{intent}' (Exp: '{expected_intent}') in {dt:.1f}ms")
        except Exception as e:
            failed += 1
            print(f"[{idx:02d}] EXCEPTION | Cmd: '{cmd}' -> Error: {e}")

    print("-" * 70)
    print(f"Total Commands: {len(test_commands)} | Passed: {passed} | Failed: {failed}")

    # Ollama Test
    print("\n--- Ollama Local LLM Connectivity Test ---")
    ollama = OllamaClient()
    available = ollama.is_available()
    print(f"Ollama Reachable (http://localhost:11434): {available}")
    if available:
        models = ollama.list_models()
        print(f"Installed Models: {models}")
        # Test chat call
        t0 = time.time()
        try:
            res = ollama.chat(messages=[{"role": "user", "content": "Say hello in one word"}])
            dt = (time.time() - t0) * 1000
            print(f"Ollama chat response in {dt:.1f}ms: '{res}'")
        except Exception as e:
            print(f"Ollama chat call failed: {e}")

    print("=" * 70)


if __name__ == "__main__":
    test_intent_routing()
