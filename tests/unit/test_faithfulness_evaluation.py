import importlib.util
import json
import sys
from pathlib import Path

import pytest


def test_faithfulness_dataset_is_disjoint_and_labeled() -> None:
    calibration = json.loads(
        Path("data/evaluation/retrieval_calibration_cases.json").read_text(encoding="utf-8")
    )
    holdout = json.loads(
        Path("data/evaluation/retrieval_test_cases.json").read_text(encoding="utf-8")
    )
    faithfulness = json.loads(
        Path("data/evaluation/faithfulness_v2_cases.json").read_text(encoding="utf-8")
    )

    calibration_ids = {case["id"] for case in calibration}
    holdout_ids = {case["id"] for case in holdout}
    faithfulness_ids = {case["id"] for case in faithfulness}

    assert len(faithfulness) == 12
    assert sum(case.get("answerable", True) for case in faithfulness) == 8
    assert sum(not case.get("answerable", True) for case in faithfulness) == 4
    assert faithfulness_ids.isdisjoint(calibration_ids | holdout_ids)
    assert all(
        case["required_claims"] and case["relevant_sources"]
        for case in faithfulness
        if case.get("answerable", True)
    )
    assert all(
        not case["required_claims"] and not case["relevant_sources"]
        for case in faithfulness
        if not case.get("answerable", True)
    )


def test_faithfulness_evaluation_defaults_and_output_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "evaluate_faithfulness", Path("scripts/evaluate_faithfulness.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", ["evaluate_faithfulness.py"])

    args = module.parse_args()

    assert args.dataset == Path("data/evaluation/faithfulness_v2_cases.json")
    assert args.output == Path("docs/evaluation/results/faithfulness-deterministic-v1.json")
