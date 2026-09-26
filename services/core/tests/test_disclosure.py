"""M1 review finding F11: data-location statements come from the configured routes."""

from __future__ import annotations

from alpha.assistant.prompts import system_prompt
from alpha.assistant.turn import AssistantTurnOutput
from alpha.models.disclosure import app_data_notice, data_notice, ground_output, ground_text
from alpha.models.gateway import ROUTES

REMOTE = ROUTES["claude-code-cli"]
LOCAL = ROUTES["fake"]
NOTICE = data_notice(REMOTE, REMOTE)

# Sentences the live assistant produced in G1 on the remote route.
G1_CLAIMS = [
    "Everything stays on this Mac; nothing is sent anywhere.",
    "All data stays on this Mac.",
    "Everything stays on your Mac, and estimates come from the model, not from nutrition websites.",
    "Everything stays on your Mac, so overdue nudges aren't part of this.",
]


def test_the_notice_says_what_stays_and_what_is_sent() -> None:
    assert NOTICE.startswith("Your records and files are stored on this Mac.")
    assert "sent to Anthropic's Claude service over the internet" in NOTICE
    assert "estimate" in NOTICE
    local = data_notice(LOCAL, LOCAL)
    assert local == "Your records and files are stored on this Mac."
    assert "Anthropic" in app_data_notice(REMOTE)
    assert "test responder on this Mac" in app_data_notice(LOCAL)


def test_untrue_locality_claims_are_replaced_and_true_ones_kept() -> None:
    for claim in G1_CLAIMS:
        grounded, changed = ground_text(
            f"I'll build you a food log. {claim} You can add goals later.", NOTICE
        )
        assert changed, claim
        assert "nothing is sent" not in grounded.lower()
        assert "stays on" not in grounded.lower()
        assert NOTICE in grounded
        assert grounded.startswith("I'll build you a food log.")
        assert grounded.endswith("You can add goals later.")
    for true in (
        "Your records are stored on this Mac.",
        "Entries are saved on your Mac and you can edit them.",
    ):
        assert ground_text(true, NOTICE) == (true, False)


def test_a_turn_is_grounded_everywhere_the_person_reads_it() -> None:
    output = AssistantTurnOutput.model_validate(
        {
            "delivery": "app",
            "interpretation": {
                "outcome": "A food log.",
                "main_input": "What you eat.",
                "useful_result": "Totals.",
                "important_assumptions": [
                    "Everything stays on this Mac; nothing is sent anywhere."
                ],
            },
            "reply": "Done. Everything stays on your Mac.",
            "questions": [],
            "assumptions": ["Single user on this Mac", "All data stays on this Mac."],
            "brief_draft": None,
        }
    )
    grounded, changed = ground_output(output, NOTICE)
    assert changed == ["assumptions", "interpretation", "reply"]
    assert grounded.reply == f"Done. {NOTICE}"
    assert grounded.interpretation.important_assumptions == [NOTICE]
    assert grounded.assumptions == ["Single user on this Mac", NOTICE]


def test_the_system_prompt_carries_the_data_facts() -> None:
    prompt = system_prompt(NOTICE)
    assert "DATA FACTS" in prompt and NOTICE in prompt
    assert "Never say that nothing leaves this Mac" in prompt
