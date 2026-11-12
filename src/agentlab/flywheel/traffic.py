"""Simulated production traffic: a stream of varied requests, each with a hidden check.

In production nobody hands you a verifier. You get signals: a thumbs-down, an error, a run that never
finished. Here each request carries a check so the simulation can produce that signal honestly; the
flywheel code only ever sees the resulting thumbs-up or thumbs-down and the trace.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from agentlab.evals.tasks import Task

Verifier = Callable[[Path], dict]

CUSTOMERS = ["Northwind Traders", "Globex", "Initech", "Umbrella Logistics", "Stark Fabrication", "Wonka Foods"]
CHANGES = [
    "Fixed the login redirect bug",
    "Added CSV export to reports",
    "Reduced cold-start time",
    "Fixed a crash on empty search",
    "Added SSO for team plans",
]
# (topic, text the answer must contain, is it in the handbook today?)
QUESTIONS = [
    ("refund window for annual plans", "45 days", True),
    ("refund window for monthly plans", "14 days", True),
    ("first response time for enterprise customers", "4 hours", True),
    ("data retention period for deleted accounts", "90 days", True),
    ("notice period for price changes", "60 days", False),
    ("trial length for team plans", "21 days", False),
]
OUT_OF_SCOPE = [
    "Translate README.md into French.",
    "Draw an architecture diagram for this project.",
    "Book a meeting with the security team for Friday.",
]
CHANGELOG = (
    "# Changelog\n\n## Unreleased\n- **{last}** — Improved error messages\n\n## 1.0.0\n- **1.0.0** — First release\n"
)


def make_invoice(number: int, amount: Decimal) -> str:
    """An invoice file with one fact the task needs (`amount`) and plenty that it doesn't."""
    invoice = {
        "id": f"INV-{number:03d}",
        "customer": {
            "name": CUSTOMERS[number % len(CUSTOMERS)],
            "billing_email": f"billing{number}@example.com",
            "address": "200 Example Street, Suite 400, Springfield",
        },
        "issued": f"2026-{number % 12 + 1:02d}-03",
        "due": f"2026-{(number + 1) % 12 + 1:02d}-02",
        "currency": "USD",
        "amount": float(amount),
        "line_items": [
            {"description": "Platform subscription, annual plan, 25 seats", "quantity": 1},
            {"description": "Priority support add-on", "quantity": 1},
            {"description": "One-time onboarding and data migration", "quantity": 1},
        ],
        "payment_terms": "Net 30. Late payments accrue interest at 1.5% per month. Include the invoice id on the remittance advice.",
        "notes": "Thank you for your business. Questions about this invoice go to accounts@example.com.",
    }
    return json.dumps(invoice, indent=2) + "\n"


def _verdict(*checks: tuple[str, bool]) -> dict:
    return {
        "reward": 1.0 if all(passed for _, passed in checks) else 0.0,
        "checks": [{"name": name, "passed": bool(passed), "detail": ""} for name, passed in checks],
    }


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def config_check(path: str, key: str, value: object, original: dict, stray: str | None = None) -> Verifier:
    def verify(root: Path) -> dict:
        try:
            data = json.loads(_read(root / path))
        except ValueError:
            return _verdict((f"{path} is valid JSON", False))
        rest = {k: v for k, v in original.items() if k != key}
        checks = [
            (f"{key} is {value!r}", data.get(key) == value),
            ("other settings unchanged", {k: v for k, v in data.items() if k != key} == rest),
        ]
        if stray:
            checks.append((f"no stray {stray}", not (root / stray).exists()))
        return _verdict(*checks)

    return verify


def changelog_check(version: str, change: str) -> Verifier:
    def verify(root: Path) -> dict:
        lines = _read(root / "CHANGELOG.md").split("\n")
        at = lines.index("## Unreleased") if "## Unreleased" in lines else -1
        entry = f"- **{version}** — {change}"
        return _verdict(("entry is the first line under ## Unreleased", at >= 0 and lines[at + 1 : at + 2] == [entry]))

    return verify


def total_check(expected: Decimal) -> Verifier:
    def verify(root: Path) -> dict:
        try:
            got = Decimal(_read(root / "total.txt").strip())
        except ArithmeticError:
            return _verdict(("total.txt holds a number", False))
        return _verdict((f"total is {expected:.2f}", got == expected))

    return verify


def answer_check(must_contain: str) -> Verifier:
    return lambda root: _verdict((f"answer mentions {must_contain}", must_contain in _read(root / "answer.txt")))


def never() -> Verifier:
    return lambda root: _verdict(("the agent could do what was asked", False))


def _config(rng: random.Random) -> Task:
    original = {
        "host": "0.0.0.0",
        "port": rng.choice([3000, 5000, 8000]),
        "timeout": rng.choice([10, 30, 60]),
        "retries": rng.choice([2, 3, 5]),
        "workers": rng.choice([2, 4, 8]),
        "debug": False,
    }
    key = rng.choice(["port", "timeout", "retries", "workers"])
    value = original[key] + rng.choice([1, 5, 80])
    body = json.dumps(original, indent=2) + "\n"
    if rng.random() < 0.25:  # the user names the file but not the folder it lives in
        return Task(
            "config",
            f"In `settings.json`, set `{key}` to {value}. Keep every other setting unchanged.",
            config_check("config/settings.json", key, value, original, stray="settings.json"),
            files={"config/settings.json": body, "README.md": "# Service\n"},
        )
    return Task(
        "config",
        f"In `config.json`, set `{key}` to {value}. Keep every other setting unchanged.",
        config_check("config.json", key, value, original),
        files={"config.json": body},
    )


def _changelog(rng: random.Random) -> Task:
    minor = rng.randint(1, 9)
    version, change = f"1.{minor}.0", rng.choice(CHANGES)
    return Task(
        "changelog",
        f"Add a changelog entry for version {version}: {change}.",
        changelog_check(version, change),
        files={"CHANGELOG.md": CHANGELOG.format(last=f"1.{minor - 1}.0")},
    )


def _invoices(rng: random.Random) -> Task:
    count = rng.choice([3, 4, 5, 6, 9, 11, 12, 14])
    amounts = [Decimal(rng.randint(5_000, 250_000)) / 100 for _ in range(count)]
    files = {f"invoices/inv-{n:03d}.json": make_invoice(n, amount) for n, amount in enumerate(amounts, 1)}
    return Task(
        "invoices",
        "Add up the `amount` of every invoice in `invoices/` and write the total to `total.txt`.",
        total_check(sum(amounts, Decimal(0))),
        files=files,
        meta={"invoices": count},
    )


def _question(rng: random.Random) -> Task:
    topic, expected, covered = rng.choice(QUESTIONS)
    return Task(
        "question",
        f"What is our {topic}? Write the answer to `answer.txt`.",
        answer_check(expected),
        files={"README.md": "# Support desk\n"},
        meta={"covered": covered},
    )


def _out_of_scope(rng: random.Random) -> Task:
    return Task("out-of-scope", rng.choice(OUT_OF_SCOPE), never(), files={"README.md": "# Project\n"})


MIX = [(_config, 30), (_changelog, 20), (_invoices, 20), (_question, 22), (_out_of_scope, 8)]


def generate(count: int = 40, seed: int = 7) -> list[Task]:
    """`count` requests in a fixed pseudo-random order: the same seed always gives the same day of traffic."""
    rng = random.Random(seed)
    makers, weights = zip(*MIX, strict=True)
    requests = []
    for number in range(1, count + 1):
        task = rng.choices(makers, weights)[0](rng)
        task.meta["kind"] = task.id
        task.id = f"req-{number:03d}"
        requests.append(task)
    return requests
