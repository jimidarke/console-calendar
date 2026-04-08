#!/usr/bin/env python3
"""Test the AI parser with sample family inputs."""

import asyncio
import json
import sys
import os

# Ensure we can import the app
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from app.ai_parser import parse


TEST_CASES = [
    # (input_text, description)
    ("jonnie pta thursday 445pm", "Kid's event with name, day, casual time"),
    ("dentist tomorrow 2pm", "Simple event with relative date"),
    ("family dinner saturday 6", "Ambiguous time (6 = 6pm in dinner context)"),
    ("jonnie soccer practice friday 330", "After-school activity"),
    ("jimi oil change next tuesday 10am", "Personal errand with specific day"),
    ("school concert december 15 7pm", "Future date event"),
    ("groceries", "Minimal input - just a task name"),
    ("jonnie birthday party at the park june 21 1pm to 4pm", "Longer input with location and duration"),
    ("pta meeting", "No time, no date"),
    ("asdfghjkl", "Gibberish - should be unparseable"),
]


async def main():
    print("=" * 70)
    print("CAL-QUICKADD AI PARSER TEST")
    print("=" * 70)

    passed = 0
    failed = 0

    for text, description in TEST_CASES:
        print(f"\n--- {description} ---")
        print(f"Input: \"{text}\"")

        try:
            result = await parse(text)
            print(f"Output: {json.dumps(result, indent=2)}")

            # Basic validation
            assert "title" in result, "Missing 'title'"
            assert "date" in result, "Missing 'date'"
            assert "confidence" in result, "Missing 'confidence'"
            assert result["confidence"] in ("high", "low", "unparseable"), f"Bad confidence: {result['confidence']}"

            print(f"Result: PASS (confidence={result['confidence']})")
            passed += 1

        except Exception as e:
            print(f"Result: FAIL - {e}")
            failed += 1

    print(f"\n{'=' * 70}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(TEST_CASES)}")
    print(f"{'=' * 70}")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
