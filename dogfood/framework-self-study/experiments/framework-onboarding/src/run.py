from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping


TASK_IDS = (
    "T1-locate-contracts",
    "T2-create-experiment",
    "T3-validate-experiment",
    "T4-run-review",
    "T5-human-gate",
)
DECISIONS = {"pass", "fail", "not_evaluable"}


def _required(row: Mapping[str, str], name: str, session_id: str) -> str:
    value = (row.get(name) or "").strip()
    if not value:
        raise ValueError(f"session {session_id!r}: {name} is required")
    return value


def _nonnegative_int(value: str, field: str, session_id: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"session {session_id!r}: {field} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"session {session_id!r}: {field} must be nonnegative")
    return parsed


def analyze_rows(rows: Iterable[Mapping[str, str]]) -> dict[str, object]:
    rows = list(rows)
    if not rows:
        raise ValueError("No observations recorded; benchmark execution is intentionally blocked.")

    seen: set[str] = set()
    strata: dict[str, list[int]] = defaultdict(list)
    censored = 0
    deviations = 0
    critical_violations = 0
    measured_tokens: list[int] = []
    missing_tokens = 0
    flow = Counter()

    for row in rows:
        session_id = _required(row, "session_id", "<unknown>")
        if session_id in seen:
            raise ValueError(f"duplicate session_id: {session_id!r}")
        seen.add(session_id)

        task_id = _required(row, "task_id", session_id)
        if task_id not in TASK_IDS:
            raise ValueError(f"session {session_id!r}: unknown task_id {task_id!r}")
        censor_status = _required(row, "censor_status", session_id)
        if censor_status not in {"uncensored", "censored"}:
            raise ValueError(f"session {session_id!r}: invalid censor_status")
        censor_reason = (row.get("censor_reason") or "").strip()
        if (censor_status == "censored") != bool(censor_reason):
            raise ValueError(f"session {session_id!r}: censored sessions require a reason and uncensored sessions forbid one")

        deviation = _required(row, "protocol_deviation", session_id)
        if deviation not in {"yes", "no"}:
            raise ValueError(f"session {session_id!r}: protocol_deviation must be yes or no")
        deviation_reason = (row.get("deviation_reason") or "").strip()
        if (deviation == "yes") != bool(deviation_reason):
            raise ValueError(f"session {session_id!r}: deviations require a reason and non-deviations forbid one")
        deviations += deviation == "yes"

        scorer_1 = _required(row, "scorer_1_decision", session_id)
        scorer_2 = _required(row, "scorer_2_decision", session_id)
        adjudicated = _required(row, "adjudicated_decision", session_id)
        if scorer_1 not in DECISIONS or scorer_2 not in DECISIONS or adjudicated not in DECISIONS:
            raise ValueError(f"session {session_id!r}: invalid scorer decision")

        critical = _nonnegative_int(
            _required(row, "critical_protocol_violations", session_id),
            "critical_protocol_violations",
            session_id,
        )
        critical_violations += critical

        token_status = _required(row, "onboarding_tokens_status", session_id)
        token_value = (row.get("onboarding_tokens") or "").strip()
        if token_status == "measured":
            token_count = _nonnegative_int(token_value, "onboarding_tokens", session_id)
            if censor_status == "uncensored":
                measured_tokens.append(token_count)
        elif token_status == "unavailable":
            if token_value:
                raise ValueError(f"session {session_id!r}: unavailable onboarding tokens must be blank")
            missing_tokens += censor_status == "uncensored"
        else:
            raise ValueError(f"session {session_id!r}: invalid onboarding_tokens_status")

        flow[censor_status] += 1
        if censor_status == "censored":
            censored += 1
            continue
        if "not_evaluable" in {scorer_1, scorer_2, adjudicated}:
            raise ValueError(f"session {session_id!r}: uncensored scorer decisions cannot be not_evaluable")
        task_success = int(adjudicated == "pass" and critical == 0)
        strata[task_id].append(task_success)

    counts = {task_id: len(strata[task_id]) for task_id in TASK_IDS}
    if any(count != 3 for count in counts.values()) or sum(counts.values()) != 15:
        raise ValueError(f"primary analysis requires exactly 15 uncensored sessions, three per task; observed {counts}")

    task_rates = {task_id: sum(strata[task_id]) / 3 for task_id in TASK_IDS}
    primary_rate = sum(task_rates.values()) / len(TASK_IDS)
    tokens_complete = missing_tokens == 0
    maximum_tokens = max(measured_tokens) if measured_tokens else None
    return {
        "total_attempts": len(rows),
        "sessions": 15,
        "censored_sessions": censored,
        "protocol_deviations": deviations,
        "task_counts": counts,
        "task_success_rates": task_rates,
        "task_success_rate": primary_rate,
        "critical_protocol_violations": critical_violations,
        "estimated_onboarding_tokens": maximum_tokens if tokens_complete else None,
        "maximum_measurable_onboarding_tokens": maximum_tokens,
        "onboarding_token_missing_sessions": missing_tokens,
        "onboarding_token_claim": "evaluable" if tokens_complete else "inconclusive",
        "flow": dict(flow),
    }


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    source = root / "data" / "raw" / "observations-v3.csv"
    with source.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    try:
        results = analyze_rows(rows)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    output = root / "artifacts" / "results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
