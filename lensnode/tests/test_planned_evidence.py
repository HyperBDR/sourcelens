import json
import threading
import time

import pytest

from lensnode.planned_evidence import (
    EvidenceExecutor,
    PlanValidationError,
    assess_code_analysis_capabilities,
    build_evidence_bundle,
    parse_retrieval_plan,
    validate_citations,
    validate_evidence_sufficiency,
)


def test_code_analysis_capability_assessment_requires_one_retrieval_path():
    unavailable = assess_code_analysis_capabilities({}, {})
    assert unavailable["ready"] is False
    assert unavailable["missing"] == ("workspace", "codegraph")

    workspace_ready = assess_code_analysis_capabilities(
        {
            "search_workspace": object(),
            "read_workspace_file": object(),
        },
        {},
    )
    assert workspace_ready["ready"] is True
    assert workspace_ready["available"] == ("workspace",)

    codegraph_ready = assess_code_analysis_capabilities(
        {},
        {"explore": object()},
    )
    assert codegraph_ready["ready"] is True
    assert codegraph_ready["available"] == ("codegraph",)


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


def test_retrieval_plan_parses_bounded_text_clarification():
    plan = parse_retrieval_plan(
        {
            "objective": "Identify the affected service",
            "clarification": {
                "question": "Which deployment environment should I inspect?",
                "reason": "ambiguous_scope",
                "answer_type": "text",
            },
        }
    )

    assert plan.clarification.question == (
        "Which deployment environment should I inspect?"
    )
    assert plan.clarification.reason == "ambiguous_scope"
    assert plan.clarification.answer_type == "text"


def test_retrieval_plan_rejects_non_text_clarification():
    with pytest.raises(PlanValidationError):
        parse_retrieval_plan(
            {
                "objective": "Identify the affected service",
                "clarification": {
                    "question": "Choose an environment",
                    "answer_type": "choice",
                },
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


def test_executor_derives_source_windows_from_retrieval_matches():
    reads = []

    def search_workspace(**_kwargs):
        return json.dumps(
            {
                "matches": [
                    {"path": "app.py", "line": 10, "text": "return 1"}
                ]
            }
        )

    def read_workspace_file(**kwargs):
        reads.append(kwargs)
        return json.dumps(
            {
                "path": kwargs["path"],
                "start_line": kwargs["offset"],
                "end_line": kwargs["offset"] + kwargs["limit"] - 1,
                "content": "return 1",
            }
        )

    plan = parse_retrieval_plan(
        {
            "objective": "find the implementation",
            "literal_queries": ["return 1"],
            "source_windows": [],
        }
    )

    bundle = EvidenceExecutor(
        workspace_tools={
            "search_workspace": search_workspace,
            "read_workspace_file": read_workspace_file,
        }
    ).execute(plan)

    assert reads == [{"path": "app.py", "offset": 10, "limit": 1}]
    assert any(item.evidence_type == "source" for item in bundle.items)
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

    evidence_id = bundle.items[0].evidence_id
    valid, invalid = validate_citations(
        [
            {
                "evidence_id": evidence_id,
                "supports": "load returns the value",
            },
            {
                "evidence_id": "evidence-missing",
                "supports": "missing claim",
            },
        ],
        bundle,
        workspace_root=tmp_path,
        citation_context={
            "project": "SourceLens",
            "repository": "SourceLens",
            "revision": "abc123",
        },
    )

    assert len(valid) == 1
    assert valid[0] == {
        "id": evidence_id,
        "evidence_id": evidence_id,
        "project": "SourceLens",
        "repository": "SourceLens",
        "revision": "abc123",
        "path": "app.py",
        "symbol": "load",
        "start_line": 1,
        "end_line": 2,
        "supports": "load returns the value",
        "source": "def load():\n    return 1",
    }
    assert invalid == ("evidence-missing",)


def test_citations_normalize_absolute_paths_and_reject_workspace_escape(
    tmp_path,
):
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("value = 1\n", encoding="utf-8")
    outside = tmp_path.parent / "outside.py"
    outside.write_text("secret = 1\n", encoding="utf-8")
    bundle = build_evidence_bundle(
        [
            {
                "evidence_type": "source",
                "path": str(source),
                "symbol": "value",
                "start_line": 1,
                "end_line": 1,
                "content": "value = 1",
            },
            {
                "evidence_type": "source",
                "path": str(outside),
                "symbol": "secret",
                "start_line": 1,
                "end_line": 1,
                "content": "secret = 1",
            },
        ],
        max_tokens=100,
    )
    evidence_by_symbol = {item.symbol: item for item in bundle.items}

    valid, invalid = validate_citations(
        [
            {
                "evidence_id": evidence_by_symbol["value"].evidence_id,
                "supports": "workspace value",
            },
            {
                "evidence_id": evidence_by_symbol["secret"].evidence_id,
                "supports": "outside value",
            },
        ],
        bundle,
        workspace_root=tmp_path,
        citation_context={"revision": "abc123"},
    )

    assert len(valid) == 1
    assert valid[0]["path"] == "src/app.py"
    assert not valid[0]["path"].startswith("/")
    assert invalid == (evidence_by_symbol["secret"].evidence_id,)


def test_codegraph_results_satisfy_structural_requirements():
    bundle = EvidenceExecutor(
        codegraph_tools={"explore": lambda **_kwargs: "caller invokes load"}
    ).execute(
        parse_retrieval_plan(
            {
                "objective": "trace load",
                "evidence_requirements": ["structural flow"],
                "codegraph_queries": [
                    {"operation": "explore", "query": "load"}
                ],
            }
        )
    )

    result = validate_evidence_sufficiency(bundle, ["structural flow"])

    assert bundle.items[0].evidence_type == "structural"
    assert result.sufficient is True


def test_codegraph_error_results_do_not_satisfy_structural_requirements():
    bundle = EvidenceExecutor(
        codegraph_tools={
            "explore": lambda **_kwargs: {
                "ok": False,
                "error": "CODEGRAPH_NOT_INITIALIZED",
            }
        }
    ).execute(
        parse_retrieval_plan(
            {
                "objective": "trace load",
                "evidence_requirements": ["structural flow"],
                "codegraph_queries": [
                    {"operation": "explore", "query": "load"}
                ],
            }
        )
    )

    result = validate_evidence_sufficiency(bundle, ["structural flow"])

    assert bundle.items[0].evidence_type == "retrieval_error"
    assert result.sufficient is False
    assert result.gaps == ("structural",)


def test_codegraph_success_wrapper_exposes_structural_result():
    bundle = EvidenceExecutor(
        codegraph_tools={
            "explore": lambda **_kwargs: {
                "ok": True,
                "result": "caller invokes load",
            }
        }
    ).execute(
        parse_retrieval_plan(
            {
                "objective": "trace load",
                "evidence_requirements": ["structural flow"],
                "codegraph_queries": [
                    {"operation": "explore", "query": "load"}
                ],
            }
        )
    )

    result = validate_evidence_sufficiency(bundle, ["structural flow"])

    assert bundle.items[0].content == "caller invokes load"
    assert result.sufficient is True
