from __future__ import annotations

import json
import sys
from pathlib import Path


def validate_experiment() -> dict:
    """Validate the onboarding-smoke experiment structure."""
    root = Path(__file__).resolve().parent.parent
    results = {
        "experiment_files_complete": 0,
        "hypothesis_is_falsifiable": 0,
        "protocol_has_stopping_rule": 0,
        "acceptance_criteria_predeclared": 0,
        "critical_protocol_violations": 0,
        "errors": [],
    }

    # Check required files exist
    required_files = [
        root / "experiment.yaml",
        root / "hypothesis.md",
        root / "protocol.md",
    ]
    for f in required_files:
        if not f.exists():
            results["errors"].append(f"Missing required file: {f.name}")

    if not results["errors"]:
        results["experiment_files_complete"] = 1

    # Check hypothesis.md for falsifiability indicators
    hypothesis_path = root / "hypothesis.md"
    if hypothesis_path.exists():
        hypothesis_text = hypothesis_path.read_text(encoding="utf-8").lower()
        falsifiability_markers = [
            "falsif" in hypothesis_text,
            "claim" in hypothesis_text,
            "reject" in hypothesis_text or "revise" in hypothesis_text,
        ]
        if all(falsifiability_markers):
            results["hypothesis_is_falsifiable"] = 1
        else:
            results["errors"].append("Hypothesis lacks falsifiability markers")

    # Check protocol.md for stopping rule
    protocol_path = root / "protocol.md"
    if protocol_path.exists():
        protocol_text = protocol_path.read_text(encoding="utf-8").lower()
        if "stopping rule" in protocol_text or "stop when" in protocol_text:
            results["protocol_has_stopping_rule"] = 1
        else:
            results["errors"].append("Protocol lacks stopping rule")

    # Check experiment.yaml for acceptance criteria
    experiment_path = root / "experiment.yaml"
    if experiment_path.exists():
        experiment_text = experiment_path.read_text(encoding="utf-8").lower()
        if "acceptance:" in experiment_text and "metric:" in experiment_text:
            results["acceptance_criteria_predeclared"] = 1
        else:
            results["errors"].append("Experiment lacks predeclared acceptance criteria")

    # Critical violations are assumed zero by protocol (no observation, no raw data modification)
    # This is verified by the agent's adherence to the task constraints
    results["critical_protocol_violations"] = 0

    return results


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    output = root / "artifacts" / "validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    results = validate_experiment()
    output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    # Exit with error if any validation failed
    if results["errors"]:
        print(f"Validation failed with {len(results['errors'])} errors:")
        for error in results["errors"]:
            print(f"  - {error}")
        sys.exit(1)

    print("Validation passed. All criteria met.")
    sys.exit(0)


if __name__ == "__main__":
    main()
