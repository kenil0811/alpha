# ruff: noqa: E501
"""Deterministic assistant responses for the `fake` route (offline control tests only)."""

from __future__ import annotations

import json
import re
import time
from typing import Any


def _tracker(answered: bool) -> dict[str, Any]:
    questions = (
        []
        if answered
        else [
            {
                "id": "portion",
                "question": "How do you want to enter how much you ate?",
                "options": ["Rough portions (small/medium/large)", "Grams or millilitres", "Both"],
                "why_it_matters": "It changes how calories are estimated and how much typing each entry takes.",
            },
            {
                "id": "target",
                "question": "Do you have a daily calorie target to compare against?",
                "options": ["Yes, I'll give a number", "No target, just history and trends"],
                "why_it_matters": "A target changes what the daily summary and trend show.",
            },
        ]
    )
    return {
        "delivery": "app",
        "interpretation": {
            "outcome": "A personal food diary with calories, daily totals, history and a trend.",
            "main_input": "Short food entries typed as you eat, with how much.",
            "useful_result": "Today's total, an editable history and a week-over-week trend.",
            "important_assumptions": [
                "Single user on this Mac",
                "Estimates are labelled and editable",
            ],
        },
        "reply": "I can make a small food diary you keep on this Mac. Two quick questions first."
        if not answered
        else "Got it. I'll make the food diary with those choices.",
        "questions": questions,
        "assumptions": ["Single user on this Mac", "Calorie estimates are labelled and editable"]
        + (["Portions entered as chosen", "Target handled as chosen"] if answered else []),
        "brief_draft": {
            "goal": "Track what I eat and how much, with calories, history and trends",
            "success_summary": "Entries take seconds, today's total is always right, history is editable, and the trend is meaningful.",
            "surfaces": ["custom_ui"],
            "primary_journey": [
                {
                    "action": "Type a food and how much",
                    "expected_result": "An entry with an estimated calorie value appears in today's list",
                },
                {
                    "action": "Correct an estimate",
                    "expected_result": "The entry and today's total update",
                },
                {
                    "action": "Open the trend",
                    "expected_result": "Daily totals over the last weeks; missing days shown as missing",
                },
            ],
            "data_needs": [
                {
                    "collection": "food_entries",
                    "purpose": "Everything eaten, with calories",
                    "fields": [
                        {
                            "name": "eaten_at",
                            "kind": "datetime",
                            "description": "When it was eaten",
                            "required": True,
                        },
                        {
                            "name": "food",
                            "kind": "text",
                            "description": "What was eaten",
                            "required": True,
                        },
                        {
                            "name": "amount",
                            "kind": "text",
                            "description": "How much",
                            "required": True,
                        },
                        {
                            "name": "calories",
                            "kind": "number",
                            "description": "Estimated or corrected calories",
                            "required": True,
                        },
                    ],
                    "provenance": "user",
                    "retention": "until deleted",
                }
            ],
            "actions": [
                {
                    "id": "add_entry",
                    "title": "Add an entry",
                    "description": "Save a food entry with an estimate",
                    "inputs": ["food", "amount"],
                    "outputs": ["entry"],
                    "effect_class": "local_write",
                    "required_capabilities": ["records"],
                },
                {
                    "id": "daily_total",
                    "title": "Today's total",
                    "description": "Sum calories for a day",
                    "inputs": ["date"],
                    "outputs": ["total"],
                    "effect_class": "none",
                    "required_capabilities": ["records"],
                },
            ],
            "recurrence": None,
            "constraints": ["Runs on this Mac only"],
            "acceptance_examples": [
                {"description": "Three entries on one day sum correctly", "kind": "success"},
                {
                    "description": "A day with no entries shows as missing, not zero",
                    "kind": "boundary",
                },
            ],
            "unavailable_capabilities": ["records", "custom_ui"],
        },
    }


def _artifact() -> dict[str, Any]:
    return {
        "delivery": "task",
        "interpretation": {
            "outcome": "A one-page summary file made from the notes you give me.",
            "main_input": "The notes text you paste.",
            "useful_result": "A downloadable summary you can share.",
            "important_assumptions": ["Plain text output is fine for now"],
        },
        "reply": "I can turn your notes into a one-page summary as a one-off. File output is not connected yet, so I'd show the summary text here for now.",
        "questions": [],
        "assumptions": ["Plain text output is fine for now"],
        "brief_draft": {
            "goal": "Turn my notes into a one-page brief",
            "success_summary": "A short, accurate summary of the supplied notes.",
            "surfaces": ["conversation", "artifact"],
            "primary_journey": [
                {"action": "Paste notes", "expected_result": "A one-page summary appears"}
            ],
            "data_needs": [],
            "actions": [
                {
                    "id": "summarize_notes",
                    "title": "Summarize notes",
                    "description": "Condense the notes",
                    "inputs": ["notes"],
                    "outputs": ["summary"],
                    "effect_class": "none",
                    "required_capabilities": [],
                }
            ],
            "recurrence": None,
            "constraints": [],
            "acceptance_examples": [
                {
                    "description": "Empty notes give an empty summary, not an error",
                    "kind": "boundary",
                }
            ],
            "unavailable_capabilities": ["artifacts"],
        },
    }


def _unsupported() -> dict[str, Any]:
    return {
        "delivery": "task",
        "interpretation": {
            "outcome": "A morning weather message sent to a contact.",
            "main_input": "A location and a contact.",
            "useful_result": "The message text, prepared each morning.",
            "important_assumptions": [],
        },
        "reply": "Sending WhatsApp messages and fetching weather are not connected in Alpha yet. I can prepare the message text for you to copy, but I can't send it.",
        "questions": [],
        "assumptions": [],
        "brief_draft": {
            "goal": "Send a morning weather message on WhatsApp",
            "success_summary": "Not achievable yet; a prepared message text is the useful partial outcome.",
            "surfaces": ["conversation"],
            "primary_journey": [
                {"action": "Ask for today's message", "expected_result": "A message text to copy"}
            ],
            "data_needs": [],
            "actions": [],
            "recurrence": None,
            "constraints": [],
            "acceptance_examples": [],
            "unavailable_capabilities": ["messaging", "http", "schedules"],
        },
    }


def _notes_app(with_screen: bool, directive: str | None = None) -> dict[str, Any]:
    """A neutral App brief matching the notes build fixture (control tests of creation). A
    `fake:<mode> ...` directive in the person's text travels in the goal, so a change that
    Core starts on its own still reaches the fake builder's chosen package."""
    goal = "Notes list, keep short notes and see the latest ones"
    if directive:
        goal += f" {directive}"
    return {
        "delivery": "app",
        "interpretation": {
            "outcome": "A short notes list you keep on this Mac.",
            "main_input": "Short notes you type.",
            "useful_result": "Your latest notes and how many you have.",
            "important_assumptions": ["Single user on this Mac"],
        },
        "reply": "I'll make a small notes list you can add to and look back through.",
        "questions": [],
        "assumptions": ["Single user on this Mac"],
        "brief_draft": {
            "goal": goal,
            "success_summary": "Adding a note takes a second and the latest notes are always listed.",
            "surfaces": ["custom_ui"] if with_screen else ["conversation"],
            "primary_journey": [
                {
                    "action": "Type a short note",
                    "expected_result": "It is saved with today's date and listed first",
                }
            ],
            "data_needs": [
                {
                    "collection": "notes",
                    "purpose": "The person's notes",
                    "fields": [
                        {"name": "title", "kind": "text", "description": "The note"},
                        {"name": "noted_on", "kind": "date", "description": "When it was written"},
                    ],
                }
            ],
            "actions": [
                {
                    "id": "add_note",
                    "title": "Add a note",
                    "description": "Save one note dated today",
                    "inputs": ["title"],
                    "outputs": ["id", "revision"],
                    "effect_class": "local_write",
                    "required_capabilities": ["records"],
                },
                {
                    "id": "count_notes",
                    "title": "Count notes",
                    "description": "How many notes are saved",
                    "inputs": [],
                    "outputs": ["count"],
                    "effect_class": "none",
                    "required_capabilities": ["records"],
                },
            ],
            "constraints": [],
            "acceptance_examples": [
                {
                    "description": "A note is saved",
                    "action_id": "add_note",
                    "input": {"title": "Buy milk"},
                    "expected": {},
                },
                {
                    "description": "A blank note is refused",
                    "action_id": "add_note",
                    "input": {"title": ""},
                    "kind": "failure",
                },
            ],
            "unavailable_capabilities": [],
        },
    }


def _last_answers(prompt: str) -> dict[str, Any]:
    """The most recent USER ANSWERS object in the rendered conversation, if any."""
    answers: dict[str, Any] = {}
    for line in prompt.splitlines():
        if line.startswith("USER ANSWERS: "):
            try:
                parsed = json.loads(line[len("USER ANSWERS: ") :])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                answers = parsed
    return answers


def fake_assistant(prompt: str) -> dict[str, Any]:
    text = prompt.lower()
    latest = text.split("latest user input:")[-1]
    if latest.split("user:")[-1].strip().startswith("go with"):
        # A pick from the proposal card ("Go with \"…\"") continues the request it answers:
        # the subject is in the conversation, not in the pick.
        latest = text
    if "slowly:" in latest:
        time.sleep(2.0)  # lets tests observe the `thinking` state
    if "capital of" in latest or "what is" in latest and "eat" not in latest:
        return {
            "delivery": "answer",
            "interpretation": {
                "outcome": "A direct answer.",
                "main_input": "Your question.",
                "useful_result": "The answer.",
                "important_assumptions": [],
            },
            "reply": "Canberra is the capital of Australia.",
            "questions": [],
            "assumptions": [],
            "brief_draft": None,
        }
    if "notes list" in latest:
        directive = re.search(r"fake:[a-z_]+(?: [a-z0-9_-]+)*", latest)
        return _notes_app(
            with_screen="no screen" not in latest,
            directive=directive.group(0) if directive else None,
        )
    if "whatsapp" in text or "text my" in text:
        return _unsupported()
    if "notes" in text and ("brief" in text or "summary" in text):
        return _artifact()
    if "eat" in text or "calorie" in text or "food" in text:
        answered_now = "user answers" in latest or "use your defaults" in latest
        answered_before = "user answers:" in text or "use your defaults" in text
        result = _tracker(answered_now or answered_before)
        prior_answers = _last_answers(prompt)
        if prior_answers:
            result["assumptions"] = result["assumptions"] + [
                f"{k}: {v}" for k, v in prior_answers.items()
            ]
        if not answered_now and answered_before:
            # A free-text correction after a brief: keep what was agreed and add the change,
            # the way rule 7 of the real prompt asks the model to behave.
            original_latest = prompt.split("LATEST USER INPUT:")[-1]
            correction = original_latest.split("USER:")[-1].strip().splitlines()[0].strip()
            if correction:
                result["assumptions"] = result["assumptions"] + [f"Also: {correction}"]
            result["reply"] = "Updated. I've added that to the diary and kept everything else."
        return result
    return {
        "delivery": "answer",
        "interpretation": {
            "outcome": "Clarify the goal.",
            "main_input": "Your description.",
            "useful_result": "A clear next step.",
            "important_assumptions": [],
        },
        "reply": "Tell me what outcome you want and I'll suggest how Alpha can help.",
        "questions": [],
        "assumptions": [],
        "brief_draft": None,
    }
