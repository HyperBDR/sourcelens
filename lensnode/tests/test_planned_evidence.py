import json
import threading
import time

import pytest

from lensnode.planned_evidence import (
    EvidenceExecutor,
    PlanValidationError,
    build_evidence_bundle,
    parse_retrieval_plan,
    validate_citations,
    validate_evidence_sufficiency,
)


def test_retrieval_plan_normalizes_bounded_limits():
    plan = parse_retrieval_plan(
        {
            "objective": "trace the exception",
            "project": "SourceLens",
            "revision": "abc123",
            "question_type": "runtime_error",
            "evidence_requirements": ["runtime error text", "source lines"],
            "codegraph_queries": [
                {"operation": "explore", "query": "raise None"},
            ],
            "literal_queries": ["raise None", "raise None"],
            "file_scopes": ["lensnode/", "lensnode/"],
            "max_files": 1000,
            "max_fallback_rounds": 99,
            "budgets": {
                "max_source_window_lines": 1000,
                "max_evidence_tokens": 999999,
            },
        }
    )

    assert plan.max_files == 15
    assert plan.max_fallback_rounds == 1
    assert plan.budgets.max_source_window_lines == 250
    assert plan.budgets.max_evidence_tokens == 20000
    assert len(plan.codegraph_queries) == 1
    assert plan.literal_queries == ("raise None",)


def test_retrieval_plan_rejects_missing_objective_and_invalid_operation():
    with pytest.raises(PlanValidationError):
        parse_retrieval_plan({"literal_queries": ["error"]})

    with pytest.raises(PlanValidationError):
        parse_retrieval_plan(
            {
                "objective": "inspect flow",
                "codegraph_queries": [
                    {"operation": "execute_shell", "query": "rm -rf"}
                ],
            }
        )


def test_executor_runs_independent_retrievals_in_parallel_and_deduplicates():
    started = []
    barrier = threading.Barrier(2)

    def search(query, **kwargs):
        del kwargs
        started.append(query)
        barrier.wait(timeout=1)
        return json.dumps(
            {
                "matches": [
                    {"path": "app.py", "line": 10, "text": query}
                ]
            }
        )

    def graph(query, **kwargs):
        del kwargs
        started.append(query)
        barrier.wait(timeout=1)
        return "symbol evidence"

    plan = parse_retrieval_plan(
        {
            "objective": "trace flow",
            "codegraph_queries": [
                {"operation": "explore", "query": "target"}
            ],
            "literal_queries": ["error", "error"],
            "budgets": {"max_evidence_tokens": 1000},
        }
    )
    executor = EvidenceExecutor(
        workspace_tools={"search_workspace": search},
        codegraph_tools={"explore": graph},
    )

    bundle = executor.execute(plan)

    assert set(started) == {"target", "error"}
    assert len(bundle.items) == 2
    assert bundle.metrics["retrieval_call_count"] == 2
    assert bundle.metrics["deduplicated_item_count"] == 0


def test_evidence_bundle_deduplicates_and_applies_token_budget():
    bundle = build_evidence_bundle(
        [
            {
                "evidence_type": "source",
                "path": "app.py",
                "symbol": "load",
                "start_line": 1,
                "end_line": 2,
                "content": "x" * 100,
            },
            {
                "evidence_type": "source",
                "path": "app.py",
                "symbol": "load",
                "start_line": 1,
                "end_line": 2,
                "content": "x" * 100,
            },
            {
                "evidence_type": "runtime",
                "path": "run.log",
                "content": "raise None",
            },
        ],
        max_tokens=30,
    )

    assert len(bundle.items) == 2
    assert bundle.metrics["deduplicated_item_count"] == 1
    assert bundle.metrics["evidence_tokens"] <= 30


def test_executor_merges_overlapping_source_windows():
    reads = []

    def read_workspace_file(**kwargs):
        reads.append(kwargs)
        return json.dumps(
            {
                "path": kwargs["path"],
                "start_line": kwargs["offset"],
                "end_line": kwargs["offset"] + kwargs["limit"] - 1,
                "content": "source",
            }
        )

    plan = parse_retrieval_plan(
        {
            "objective": "inspect source",
            "source_windows": [
                {"path": "app.py", "start_line": 10, "end_line": 20},
                {"path": "app.py", "start_line": 18, "end_line": 30},
            ],
        }
    )

    bundle = EvidenceExecutor(
        workspace_tools={"read_workspace_file": read_workspace_file}
    ).execute(plan)

    assert reads == [{"path": "app.py", "offset": 10, "limit": 21}]
    assert bundle.metrics["file_read_call_count"] == 1


def test_sufficiency_reports_missing_categories_without_fabrication():
    bundle = build_evidence_bundle(
        [
            {
                "evidence_type": "structural",
                "path": "app.py",
                "symbol": "load",
                "start_line": 1,
                "end_line": 3,
                "content": "load delegates to driver",
            }
        ],
        max_tokens=100,
    )

    result = validate_evidence_sufficiency(
        bundle,
        ["runtime error text", "source lines", "caller context"],
    )

    assert result.sufficient is False
    assert result.gaps == (
        "runtime_error",
        "source",
        "caller_context",
    )


def test_citations_require_existing_source_lines_and_matching_evidence(
    tmp_path,
):
    source = tmp_path / "app.py"
    source.write_text("def load():\n    return 1\n", encoding="utf-8")
    bundle = build_evidence_bundle(
        [
            {
                "evidence_type": "source",
                "path": "app.py",
                "symbol": "load",
                "start_line": 1,
                "end_line": 2,
                "content": "def load():\n    return 1",
            }
        ],
        max_tokens=100,
    )

    valid, invalid = validate_citations(
        [
            {
                "project": "SourceLens",
                "repository": "SourceLens",
                "revision": "workspace",
                "path": "app.py",
                "symbol": "load",
                "start_line": 1,
                "end_line": 2,
                "evidence_type": "source",
            },
            {
                "project": "SourceLens",
                "repository": "SourceLens",
                "revision": "workspace",
                "path": "missing.py",
                "symbol": "missing",
                "start_line": 1,
                "end_line": 4,
                "evidence_type": "source",
            },
        ],
        bundle,
        workspace_root=tmp_path,
    )

    assert len(valid) == 1
    assert invalid == ("missing.py",)
