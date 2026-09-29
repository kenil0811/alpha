"""The builder's `validate`: the platform's package rules, runnable inside an attempt."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from alpha.builds.validate import validate_package, write_validate_script

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "builds" / "notes_ok"
PYTHON = Path(sys.executable)


def package(tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("ui", "tests"))
    text = re.sub(r"\{\{[A-Z_]+\}\}", "x", (target / "app.yaml.template").read_text())
    text = re.sub(r"(?m)^ui:.*\n(?:  .*\n)*", "", text)  # the declared screen is enough here
    (target / "app.yaml").write_text(text)
    (target / "app.yaml.template").unlink()
    return target


def test_a_sound_package_reports_no_problems(tmp_path: Path) -> None:
    assert validate_package(package(tmp_path), PYTHON) == []


def test_invalid_yaml_a_contract_slip_and_a_missing_handler_are_named(tmp_path: Path) -> None:
    broken = package(tmp_path)
    app_yaml = broken / "app.yaml"
    sound = app_yaml.read_text()
    app_yaml.write_text(sound.replace("description:", "description: a: b", 1))
    problems = validate_package(broken, PYTHON)
    assert problems and "not valid YAML" in problems[0]

    app_yaml.write_text(
        sound.replace(
            "handler: notes_app.handlers:count_notes", "handler: notes_app.handlers:count_note"
        )
    )
    problems = validate_package(broken, PYTHON)
    assert problems == ["action count_notes: notes_app.handlers has no function count_note"]

    app_yaml.write_text(sound)
    handlers = broken / "src" / "notes_app" / "handlers.py"
    handlers.write_text(handlers.read_text() + "\ndef broken(:\n")
    problems = validate_package(broken, PYTHON)
    assert problems and "does not compile" in problems[0]


def test_the_script_runs_from_the_attempt_directory(tmp_path: Path) -> None:
    package(tmp_path)
    script = write_validate_script(tmp_path, PYTHON)
    assert script.name == "validate" and os.access(script, os.X_OK)
    run = subprocess.run(["./validate"], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.startswith("OK:")


def test_a_screen_table_over_a_collection_is_refused_in_favour_of_the_page(tmp_path: Path) -> None:
    """Alpha draws a page for every table; a screen table only hides it (found live)."""
    broken = package(tmp_path)
    app_yaml = broken / "app.yaml"
    app_yaml.write_text(
        app_yaml.read_text()
        + "views:\n  - {id: notes.all, collection: notes}\n"
        + "screen:\n  tabs:\n    - id: notes\n      title: Notes\n      blocks:\n"
        + "        - {kind: table, view: notes.all, columns: [{field: title, title: Note}]}\n"
    )
    problems = validate_package(broken, PYTHON)
    assert len(problems) == 1 and problems[0].startswith(
        "screen tab notes block 1 is a table over notes"
    )
    assert "declare `page:`" in problems[0]
