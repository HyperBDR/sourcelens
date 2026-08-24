"""Bounded retrieval plans, evidence bundles, and citation validation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import math
import time
from pathlib import Path


MAX_FILES = 15
MAX_SOURCE_WINDOW_LINES = 250
MAX_EVIDENCE_TOKENS = 20000
MAX_OBJECTIVE_CHARS = 2000
MAX_QUERY_CHARS = 500
MAX_CODEGRAPH_QUERIES = 16
MAX_LITERAL_QUERIES = 32
MAX_SOURCE_WINDOWS = 32
ALLOWED_CODEGRAPH_OPERATIONS = {
    "callers",
    "callees",
    "context",
    "explore",
    "impact",
    "node",
    "search",
    "trace",
}
OPERATION_ALIASES = {
    "symbol_search": "search",
    "code_search": "search",
    "search_symbol": "search",
    "search_code": "search",
    "symbol_lookup": "node",
    "callers_of": "callers",
    "callees_of": "callees",
    "dependency_graph": "impact",
    "subgraph": "explore",
    "code_analysis": "explore",
}


class PlanValidationError(ValueError):
    """Raised when a model-generated retrieval plan is not safe to run."""


def _normalize_codegraph_operation(item):
    """Resolve a model-supplied operation to the allowed set.

    Tolerates missing or aliased operation names so a substantively good
    plan is not discarded wholesale, while still rejecting unknown values.
    """

    raw = item.get("operation")
    operation = raw.strip().lower() if isinstance(raw, str) else ""
    if not operation:
        operation = "search" if item.get("symbol") else "explore"
    operation = OPERATION_ALIASES.get(operation, operation)
    if operation not in ALLOWED_CODEGRAPH_OPERATIONS:
        raise PlanValidationError(
            f"unsupported CodeGraph operation: {operation}"
        )
    return operation


@dataclass(frozen=True)
class RetrievalBudgets:
    """Hard limits applied independently of model instructions."""

    max_source_window_lines: int = MAX_SOURCE_WINDOW_LINES
    max_evidence_tokens: int = MAX_EVIDENCE_TOKENS


@dataclass(frozen=True)
class CodeGraphQuery:
    """One structural query requested by a retrieval plan."""

    operation: str
    query: str = ""
    symbol: str = ""

    def as_args(self):
        """Return safe arguments for a CodeGraph adapter."""

        args = {}
        if self.query:
            args["query"] = self.query
        if self.symbol:
            args["symbol"] = self.symbol
        return args


@dataclass(frozen=True)
class SourceWindow:
    """A bounded source window selected by the planner."""

    path: str
    start_line: int = 1
    end_line: int | None = None


@dataclass(frozen=True)
class ClarificationRequest:
    """One bounded plain-text question required before retrieval."""

    question: str
    reason: str = "missing_input"
    answer_type: str = "text"

    def as_dict(self):
        """Return the public clarification contract."""

        return {
            "question": self.question,
            "reason": self.reason,
            "answer_type": self.answer_type,
        }


@dataclass(frozen=True)
class RetrievalPlan:
    """Validated and bounded deterministic retrieval instructions."""

    objective: str
    project: str = ""
    repository: str = ""
    revision: str = ""
    question_type: str = "mixed"
    evidence_requirements: tuple[str, ...] = ()
    codegraph_queries: tuple[CodeGraphQuery, ...] = ()
    literal_queries: tuple[str, ...] = ()
    file_scopes: tuple[str, ...] = ()
    source_windows: tuple[SourceWindow, ...] = ()
    clarification: ClarificationRequest | None = None
    max_files: int = MAX_FILES
    max_fallback_rounds: int = 1
    budgets: RetrievalBudgets = RetrievalBudgets()


@dataclass(frozen=True)
class EvidenceItem:
    """One bounded piece of evidence with provenance metadata."""

    evidence_type: str
    content: str
    path: str = ""
    symbol: str = ""
    start_line: int | None = None
    end_line: int | None = None
    provenance: str = ""
    score: int = 0
    evidence_id: str = ""

    def __post_init__(self):
        if not self.evidence_id:
            digest = hashlib.sha1(
                "\0".join(
                    [
                        self.evidence_type,
                        self.path,
                        self.symbol,
                        str(self.start_line or ""),
                        str(self.end_line or ""),
                        self.content,
                    ]
                ).encode("utf-8")
            ).hexdigest()[:16]
            object.__setattr__(self, "evidence_id", f"evidence-{digest}")

    def as_dict(self):
        """Return the stable evidence contract used by the final prompt."""

        return {
            "id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "path": self.path,
            "symbol": self.symbol,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "provenance": self.provenance,
            "content": self.content,
        }


@dataclass(frozen=True)
class EvidenceBundle:
    """Compact evidence and safe runtime metrics."""

    items: tuple[EvidenceItem, ...]
    metrics: dict

    def as_dict(self):
        """Return the JSON-compatible final-model input."""

        return {
            "items": [item.as_dict() for item in self.items],
            "metrics": dict(self.metrics),
        }

    def to_prompt(self):
        """Serialize only compact evidence, never the raw tool transcript."""

        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class SufficiencyResult:
    """Deterministic evidence sufficiency result."""

    sufficient: bool
    gaps: tuple[str, ...]
    disproved: tuple[str, ...] = ()


def assess_code_analysis_capabilities(workspace_tools, codegraph_tools):
    """Check whether Code Analysis has at least one retrieval path."""

    workspace = {
        str(name)
        for name in (workspace_tools or {})
        if name
    }
    codegraph = {
        str(name)
        for name in (codegraph_tools or {})
        if name
    }
    available = []
    if workspace & {"search_workspace", "read_workspace_file"}:
        available.append("workspace")
    if codegraph:
        available.append("codegraph")
    capabilities = ("workspace", "codegraph")
    return {
        "ready": bool(available),
        "available": tuple(available),
        "missing": tuple(
            capability
            for capability in capabilities
            if capability not in available
        ),
    }


def parse_retrieval_plan(raw):
    """Parse, validate, and bound an untrusted planner response."""

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PlanValidationError("retrieval plan must be JSON") from exc
    if not isinstance(raw, dict):
        raise PlanValidationError("retrieval plan must be an object")

    objective = _required_text(
        raw.get("objective"),
        "objective",
        max_chars=MAX_OBJECTIVE_CHARS,
    )
    codegraph_queries = []
    codegraph_items = _list_value(raw.get("codegraph_queries"))[
        :MAX_CODEGRAPH_QUERIES
    ]
    for item in codegraph_items:
        if not isinstance(item, dict):
            raise PlanValidationError("codegraph query must be an object")
        operation = _normalize_codegraph_operation(item)
        query = _bounded_query(item.get("query"))
        symbol = _bounded_query(item.get("symbol"))
        if not query and not symbol:
            raise PlanValidationError("CodeGraph query needs query or symbol")
        codegraph_queries.append(
            CodeGraphQuery(operation=operation, query=query, symbol=symbol)
        )

    windows = []
    for item in _list_value(raw.get("source_windows"))[:MAX_SOURCE_WINDOWS]:
        if not isinstance(item, dict):
            raise PlanValidationError("source window must be an object")
        path = _required_text(
            item.get("path") or item.get("file_path"),
            "source window path",
        )
        start = _positive_int(
            item.get("start_line") or item.get("line_start"),
            1,
        )
        end = item.get("end_line")
        if end is None:
            end = item.get("line_end")
        if end is not None:
            end = _positive_int(end, start)
            if end < start:
                raise PlanValidationError(
                    "source window ends before it starts"
                )
        windows.append(SourceWindow(path, start, end))

    raw_budgets = raw.get("budgets")
    if raw_budgets is None:
        raw_budgets = {}
    if not isinstance(raw_budgets, dict):
        raise PlanValidationError("budgets must be an object")
    budgets = RetrievalBudgets(
        max_source_window_lines=min(
            max(
                _positive_int(
                    raw_budgets.get("max_source_window_lines"),
                    MAX_SOURCE_WINDOW_LINES,
                ),
                1,
            ),
            MAX_SOURCE_WINDOW_LINES,
        ),
        max_evidence_tokens=min(
            max(
                _positive_int(
                    raw_budgets.get("max_evidence_tokens"),
                    MAX_EVIDENCE_TOKENS,
                ),
                1,
            ),
            MAX_EVIDENCE_TOKENS,
        ),
    )
    clarification = _parse_clarification(raw.get("clarification"))
    return RetrievalPlan(
        objective=objective,
        project=_bounded_query(raw.get("project")),
        repository=_bounded_query(raw.get("repository")),
        revision=_bounded_query(raw.get("revision")),
        question_type=_bounded_query(raw.get("question_type")) or "mixed",
        evidence_requirements=_unique_texts(
            raw.get("evidence_requirements")
        )[:MAX_LITERAL_QUERIES],
        codegraph_queries=tuple(codegraph_queries),
        literal_queries=_unique_queries(raw.get("literal_queries"))[
            :MAX_LITERAL_QUERIES
        ],
        file_scopes=_unique_queries(raw.get("file_scopes"))[
            :MAX_LITERAL_QUERIES
        ],
        source_windows=tuple(windows),
        clarification=clarification,
        max_files=min(
            max(_positive_int(raw.get("max_files"), MAX_FILES), 1),
            MAX_FILES,
        ),
        max_fallback_rounds=min(
            max(_positive_int(raw.get("max_fallback_rounds"), 1), 0),
            1,
        ),
        budgets=budgets,
    )


class EvidenceExecutor:
    """Execute a validated plan through bounded, parallel adapters."""

    def __init__(
        self,
        workspace_tools=None,
        codegraph_tools=None,
        trajectory=None,
    ):
        self.workspace_tools = dict(workspace_tools or {})
        self.codegraph_tools = dict(codegraph_tools or {})
        self.trajectory = trajectory

    def _start_subtool(self, name, arguments, parent_call_id):
        if self.trajectory is None:
            return None, time.monotonic()
        call_id = self.trajectory.start_call(
            "subtool",
            name,
            {"arguments": arguments},
            parent_call_id=parent_call_id,
        )
        return call_id, time.monotonic()

    def _finish_subtool(
        self,
        call_id,
        started_at,
        *,
        result=None,
        error=None,
    ):
        if self.trajectory is None or call_id is None:
            return
        payload = {
            "duration_ms": int((time.monotonic() - started_at) * 1000),
        }
        status = "completed"
        if error is None:
            payload["result"] = result
        else:
            status = "failed"
            payload.update(
                {
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )
        self.trajectory.finish_call(call_id, status, payload)

    def execute(self, plan):
        """Run independent planned operations concurrently."""

        parent_call_id = None
        if self.trajectory is not None:
            parent_call_id = self.trajectory.start_call(
                "tool",
                "planned_evidence",
                {
                    "objective": plan.objective,
                    "codegraph_queries": [
                        {
                            "operation": query.operation,
                            "arguments": query.as_args(),
                        }
                        for query in plan.codegraph_queries
                    ],
                    "literal_queries": list(plan.literal_queries),
                    "source_windows": [
                        {
                            "path": window.path,
                            "start_line": window.start_line,
                            "end_line": window.end_line,
                        }
                        for window in plan.source_windows
                    ],
                },
            )
        try:
            bundle = self._execute(plan, parent_call_id)
        except Exception as exc:
            if self.trajectory is not None:
                self.trajectory.finish_call(
                    parent_call_id,
                    "failed",
                    {
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            raise
        if self.trajectory is not None:
            self.trajectory.finish_call(
                parent_call_id,
                "completed",
                {"metrics": bundle.metrics},
            )
        return bundle

    def _execute(self, plan, parent_call_id):
        """Execute one plan beneath an optional trajectory parent call."""

        requests = []
        for query in plan.codegraph_queries:
            adapter = self.codegraph_tools.get(query.operation)
            args = query.as_args()
            if adapter is None:
                # The generic explore adapter covers structural questions
                # when a specific operation is unavailable; keep the query
                # alive rather than silently dropping the evidence request.
                adapter = self.codegraph_tools.get("explore")
                if adapter is not None:
                    args = {"query": " ".join(
                        filter(None, (args.get("query"), args.get("symbol")))
                    )}
            if adapter is not None:
                requests.append(
                    ("codegraph", query.operation, adapter, args)
                )
        search = self.workspace_tools.get("search_workspace")
        if search is not None:
            for query in plan.literal_queries:
                requests.append(
                    (
                        "literal",
                        query,
                        search,
                        {
                            "query": query,
                            "max_results": plan.max_files * 4,
                            "output_mode": "content",
                        },
                    )
                )

        raw_items = []
        call_counts = {"codegraph": 0, "literal": 0, "file_read": 0}
        max_workers = max(min(len(requests), 8), 1)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for evidence_type, provenance, adapter, args in requests:
                call_id, started_at = self._start_subtool(
                    provenance,
                    args,
                    parent_call_id,
                )
                future = pool.submit(_invoke_adapter, adapter, args)
                futures[future] = (
                    evidence_type,
                    provenance,
                    call_id,
                    started_at,
                )
            for future in as_completed(futures):
                (
                    evidence_type,
                    provenance,
                    call_id,
                    started_at,
                ) = futures[future]
                call_counts[evidence_type] += 1
                try:
                    result = future.result()
                except Exception as exc:
                    self._finish_subtool(
                        call_id,
                        started_at,
                        error=exc,
                    )
                    raw_items.append(
                        {
                            "evidence_type": "retrieval_error",
                            "content": type(exc).__name__,
                            "provenance": provenance,
                        }
                    )
                    continue
                self._finish_subtool(
                    call_id,
                    started_at,
                    result=result,
                )
                raw_items.extend(
                    _items_from_result(result, evidence_type, provenance)
                )

        reader = self.workspace_tools.get("read_workspace_file")
        if reader is not None:
            source_windows = list(plan.source_windows[: plan.max_files])
            source_windows.extend(
                _source_windows_from_items(raw_items)[
                    : max(plan.max_files - len(source_windows), 0)
                ]
            )
            windows = _coalesce_source_windows(
                tuple(source_windows),
                plan.budgets.max_source_window_lines,
            )
            read_requests = []
            for window in windows:
                limit = window.end_line or (
                    window.start_line
                    + plan.budgets.max_source_window_lines
                    - 1
                )
                limit = min(
                    limit - window.start_line + 1,
                    plan.budgets.max_source_window_lines,
                )
                args = {
                    "path": window.path,
                    "offset": window.start_line,
                    "limit": limit,
                }
                call_id, started_at = self._start_subtool(
                    "read_workspace_file",
                    args,
                    parent_call_id,
                )
                read_requests.append((args, call_id, started_at))
            with ThreadPoolExecutor(
                max_workers=max(min(len(read_requests), 8), 1)
            ) as pool:
                futures = [
                    pool.submit(_invoke_adapter, reader, args)
                    for args, _call_id, _started_at in read_requests
                ]
                for request, future in zip(read_requests, futures):
                    args, call_id, started_at = request
                    try:
                        result = future.result()
                    except Exception as exc:
                        self._finish_subtool(
                            call_id,
                            started_at,
                            error=exc,
                        )
                        raw_items.append(
                            {
                                "evidence_type": "retrieval_error",
                                "path": args["path"],
                                "content": type(exc).__name__,
                                "provenance": "read_workspace_file",
                            }
                        )
                    else:
                        self._finish_subtool(
                            call_id,
                            started_at,
                            result=result,
                        )
                        call_counts["file_read"] += 1
                        raw_items.extend(
                            _items_from_result(
                                result,
                                "source",
                                "read_workspace_file",
                            )
                        )

        bundle = build_evidence_bundle(
            raw_items,
            max_tokens=plan.budgets.max_evidence_tokens,
        )
        bundle.metrics.update(
            {
                "retrieval_call_count": sum(call_counts.values()),
                "codegraph_call_count": call_counts["codegraph"],
                "literal_search_call_count": call_counts["literal"],
                "file_read_call_count": call_counts["file_read"],
                "fallback_rounds": 0,
            }
        )
        return bundle


def build_evidence_bundle(items, max_tokens=MAX_EVIDENCE_TOKENS):
    """Deduplicate, rank, and truncate raw evidence to a token budget."""

    normalized = [_evidence_item(item) for item in items]
    unique = []
    seen = set()
    for item in normalized:
        key = (
            item.evidence_type,
            item.path,
            item.symbol,
            item.start_line,
            item.end_line,
            item.content,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(
        key=lambda item: (-item.score, item.path, item.start_line or 0)
    )
    selected = []
    used_tokens = 0
    for item in unique:
        remaining = max_tokens - used_tokens
        if remaining <= 0:
            break
        content = item.content[: remaining * 4]
        if not content:
            continue
        item = EvidenceItem(
            evidence_type=item.evidence_type,
            content=content,
            path=item.path,
            symbol=item.symbol,
            start_line=item.start_line,
            end_line=item.end_line,
            provenance=item.provenance,
            score=item.score,
        )
        selected.append(item)
        used_tokens += _estimate_tokens(content)
    return EvidenceBundle(
        items=tuple(selected),
        metrics={
            "evidence_item_count": len(selected),
            "deduplicated_item_count": len(normalized) - len(unique),
            "evidence_tokens": used_tokens,
            "evidence_files": len(
                {item.path for item in selected if item.path}
            ),
        },
    )


def validate_evidence_sufficiency(bundle, requirements):
    """Check required evidence categories without inferring missing facts."""

    items = bundle.items
    gaps = []
    for requirement in requirements or ():
        category = _requirement_category(requirement)
        if category in {
            "runtime_error",
            "source",
            "structural",
            "caller_context",
        }:
            if not _has_category(items, category):
                gaps.append(category)
    return SufficiencyResult(
        sufficient=not gaps,
        gaps=tuple(dict.fromkeys(gaps)),
    )


def validate_citations(
    citations,
    bundle,
    workspace_root,
    citation_context=None,
):
    """Map model-selected evidence IDs to trusted source citations."""

    root = Path(workspace_root).resolve()
    context = dict(citation_context or {})
    evidence_by_id = {
        item.evidence_id: item
        for item in bundle.items
        if item.evidence_type == "source"
    }
    valid = []
    invalid = []
    for citation in citations or ():
        citation = citation if isinstance(citation, dict) else {}
        evidence_id = str(citation.get("evidence_id") or "").strip()
        try:
            item = evidence_by_id[evidence_id]
            supports = str(citation.get("supports") or "").strip()
            if not supports:
                raise ValueError
            item_path = Path(item.path)
            path = (
                item_path.resolve()
                if item_path.is_absolute()
                else (root / item_path).resolve()
            )
            relative_path = path.relative_to(root).as_posix()
            start = int(item.start_line)
            end = int(item.end_line)
            if (
                not path.is_file()
                or start < 1
                or end < start
                or len(item.content.splitlines()) < end - start + 1
            ):
                raise ValueError
        except (KeyError, OSError, TypeError, ValueError, AttributeError):
            invalid.append(evidence_id or "<missing-evidence-id>")
            continue
        valid.append(
            {
                "id": evidence_id,
                "evidence_id": evidence_id,
                "project": str(context.get("project") or "workspace"),
                "repository": str(
                    context.get("repository") or "workspace"
                ),
                "revision": str(context.get("revision") or "workspace"),
                "path": relative_path,
                "symbol": item.symbol,
                "start_line": start,
                "end_line": end,
                "supports": supports,
                "source": item.content,
            }
        )
    return tuple(valid), tuple(invalid)


def _invoke_adapter(adapter, args):
    if callable(adapter):
        return adapter(**args)
    return adapter.invoke(args)


def _items_from_result(result, evidence_type, provenance):
    if isinstance(result, str):
        if not result.strip():
            return []
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            if evidence_type == "codegraph":
                evidence_type = "structural"
            return [
                {
                    "evidence_type": evidence_type,
                    "content": result,
                    "provenance": provenance,
                }
            ]
    if isinstance(result, dict):
        if isinstance(result.get("ok"), bool):
            if not result["ok"]:
                return [
                    {
                        "evidence_type": "retrieval_error",
                        "content": str(
                            result.get("error") or "MCP_TOOL_FAILED"
                        ),
                        "provenance": provenance,
                    }
                ]
            return _items_from_result(
                result.get("result"),
                evidence_type,
                provenance,
            )
        if result.get("error"):
            return [
                {
                    "evidence_type": "retrieval_error",
                    "path": result.get("path", ""),
                    "content": str(result["error"]),
                    "provenance": provenance,
                }
            ]
        if evidence_type == "codegraph":
            evidence_type = "structural"
        if isinstance(result.get("matches"), list):
            return [
                {
                    "evidence_type": evidence_type,
                    "path": item.get("path", ""),
                    "start_line": item.get("line"),
                    "end_line": item.get("line"),
                    "content": item.get("text", ""),
                    "provenance": provenance,
                }
                for item in result["matches"]
                if isinstance(item, dict)
            ]
        if "content" in result:
            return [
                {
                    "evidence_type": evidence_type,
                    "path": result.get("path", ""),
                    "symbol": result.get("symbol", ""),
                    "start_line": result.get("start_line"),
                    "end_line": result.get("end_line"),
                    "content": str(result.get("content") or ""),
                    "provenance": provenance,
                }
            ]
        if not result:
            return []
        result = json.dumps(result, ensure_ascii=False)
    elif isinstance(result, list):
        if not result:
            return []
        if evidence_type == "codegraph":
            evidence_type = "structural"
        result = json.dumps(result, ensure_ascii=False)
    elif result is None:
        return []
    elif evidence_type == "codegraph":
        evidence_type = "structural"
    return [
        {
            "evidence_type": evidence_type,
            "content": str(result),
            "provenance": provenance,
        }
    ]


def _coalesce_source_windows(windows, max_lines):
    """Merge overlapping windows for one path within the line budget."""

    grouped = {}
    for window in windows:
        end = window.end_line or window.start_line + max_lines - 1
        grouped.setdefault(window.path, []).append(
            (window.start_line, min(end, window.start_line + max_lines - 1))
        )
    merged = []
    for path, ranges in grouped.items():
        current_start = None
        current_end = None
        for start, end in sorted(ranges):
            if current_start is None:
                current_start, current_end = start, end
            elif start <= current_end + 1:
                current_end = min(
                    max(current_end, end),
                    current_start + max_lines - 1,
                )
            else:
                merged.append(SourceWindow(path, current_start, current_end))
                current_start, current_end = start, end
        if current_start is not None:
            merged.append(SourceWindow(path, current_start, current_end))
    return tuple(merged)


def _source_windows_from_items(items):
    """Derive exact source windows from retrieved file locations."""

    windows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("evidence_type") not in {"structural", "literal"}:
            continue
        path = str(item.get("path") or "").strip()
        start = _optional_int(item.get("start_line"))
        end = _optional_int(item.get("end_line")) or start
        if not path or start is None or start < 1 or end is None:
            continue
        if end < start:
            end = start
        windows.append(SourceWindow(path, start, end))
    return tuple(windows)


def _evidence_item(item):
    if isinstance(item, EvidenceItem):
        return item
    evidence_type = str(item.get("evidence_type") or "unknown")
    score = {
        "source": 4,
        "structural": 3,
        "runtime": 2,
        "literal": 2,
    }.get(evidence_type, 1)
    return EvidenceItem(
        evidence_type=evidence_type,
        content=str(item.get("content") or ""),
        path=str(item.get("path") or ""),
        symbol=str(item.get("symbol") or ""),
        start_line=_optional_int(item.get("start_line")),
        end_line=_optional_int(item.get("end_line")),
        provenance=str(item.get("provenance") or ""),
        score=score,
    )


def _has_category(items, category):
    if category == "runtime_error":
        return any(
            item.evidence_type in {"runtime", "literal"} for item in items
        )
    if category == "source":
        return any(
            item.evidence_type == "source"
            and item.path
            and item.start_line is not None
            and item.end_line is not None
            for item in items
        )
    if category == "structural":
        return any(item.evidence_type == "structural" for item in items)
    return any(
        item.evidence_type == "structural"
        and any(
            term in item.content.lower()
            for term in ("caller", "call", "invoke")
        )
        for item in items
    )


def _requirement_category(requirement):
    value = str(requirement).lower()
    if "runtime" in value or "traceback" in value or "error" in value:
        return "runtime_error"
    if "source" in value or "line" in value or "citation" in value:
        return "source"
    if "caller" in value or "context" in value:
        return "caller_context"
    return "structural"


def _required_text(value, label, max_chars=MAX_QUERY_CHARS):
    text = str(value or "").strip()
    if not text or len(text) > max_chars:
        raise PlanValidationError(f"{label} is missing or too long")
    return text


def _parse_clarification(value):
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise PlanValidationError("clarification must be an object")
    question = _required_text(
        value.get("question"),
        "clarification question",
    )
    if len(question) > 1_000:
        raise PlanValidationError("clarification question is too long")
    if value.get("answer_type", "text") != "text":
        raise PlanValidationError("only text clarification is supported")
    reason = str(value.get("reason") or "missing_input").strip()
    if reason not in {
        "missing_input",
        "ambiguous_scope",
        "ambiguous_target",
    }:
        reason = "missing_input"
    return ClarificationRequest(
        question=question,
        reason=reason,
    )


def _bounded_query(value):
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > MAX_QUERY_CHARS:
        raise PlanValidationError("plan query is too long")
    return text


def _list_value(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise PlanValidationError("plan list fields must be arrays")
    return value


def _unique_queries(value):
    queries = []
    for item in _list_value(value):
        query = _bounded_query(_literal_query_value(item))
        if query:
            queries.append(query)
    return tuple(dict.fromkeys(queries))


def _literal_query_value(item):
    """Accept either a plain string or an object with a pattern field."""

    if isinstance(item, dict):
        return item.get("pattern") or item.get("query") or ""
    return item


def _unique_texts(value):
    return _unique_queries(value)


def _positive_int(value, default):
    if value is None:
        return default
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise PlanValidationError(
            "plan numeric fields must be integers"
        ) from exc
    return value


def _optional_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _estimate_tokens(text):
    return max(1, math.ceil(len(text) / 4))
