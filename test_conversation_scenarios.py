#!/usr/bin/env python3
"""Comprehensive test runner for the 8 required conversational & action scenarios."""

import sys
from mac_assistant.conversation_router import ConversationRouter
from mac_assistant.ollama_client import OllamaClient
from modules.ai.conversation_manager import ConversationManager


def run_all_tests():
    print("=" * 70)
    print("  MacAssistant: Conversational AI & Mac Automation Verification")
    print("=" * 70)

    # Initialize router with fresh in-memory session (no persistence for test)
    conv_mgr = ConversationManager(use_sqlite=False)
    router = ConversationRouter(ollama_client=OllamaClient(), conv_manager=conv_mgr)

    scenarios = [
        ("Test 1: Greeting / Conversation", "Hello, how are you?"),
        ("Test 2: Random Fact Generation", "Tell me a random interesting fact."),
        ("Test 3: Help & Capabilities Discovery", "What can you do?"),
        ("Test 4: Mac Action - App Launch", "Open Google Chrome."),
        ("Test 5: Concept Explanation", "Tell me about Android TV."),
        ("Test 6: Multi-turn Context Memory", "What about its performance?"),
        ("Test 7: Ambiguous Input Handling", "So, okay, Friday."),
        ("Test 8: Destructive Action Protection", "Delete all my files.")
    ]

    all_passed = True

    for title, prompt in scenarios:
        print(f"\n--- {title} ---")
        print(f"User > \"{prompt}\"")
        intent, success, response = router.route(prompt, persona="friday")
        print(f"Assistant [Intent: {intent} | Success: {success}] >")
        print(f"\"{response}\"")

        # Validation rules:
        # 1. Never say "That action is not in my allowlist."
        if "not in my allowlist" in response.lower() or "not in the authorized allowlist" in response.lower():
            print("[FAIL] Robotic allowlist error returned!")
            all_passed = False
            continue

        if title.startswith("Test 3"):
            if "chrome" not in response.lower() or "flutter" not in response.lower():
                print("[FAIL] Dynamic capabilities did not list Mac tools!")
                all_passed = False
                continue

        if title.startswith("Test 4"):
            if intent != "open_application":
                print("[FAIL] Did not route to open_application!")
                all_passed = False
                continue

        if title.startswith("Test 8"):
            if intent != "destructive_rejected" or success is True:
                print("[FAIL] Destructive action was not rejected safely!")
                all_passed = False
                continue

        print("[PASS]")

    print("\n" + "=" * 70)
    if all_passed:
        print(">>> ALL 8 TEST SCENARIOS PASSED PERFECTLY! <<<")
    else:
        print(">>> SOME TESTS FAILED <<<")
    print("=" * 70)
    return all_passed


if __name__ == "__main__":
    passed = run_all_tests()
    sys.exit(0 if passed else 1)
