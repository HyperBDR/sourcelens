"""Bounded retrieval plans, evidence bundles, and citation validation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import subprocess


MAX_FILES = 15
MAX_SOURCE_WINDOW_LINES = 250
MAX_EVIDENCE_TOKENS = 20000
MAX_QUERY_CHARS = 500
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


class PlanValidationError(ValueError):
    """Raised when a model-generated retrieval plan is not safe to run."""


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

        args = {"operation": self.operation}
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


def parse_retrieval_plan(raw):
    """Parse, validate, and bound an untrusted planner response."""

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PlanValidationError("retrieval plan must be JSON") from exc
    if not isinstance(raw, dict):
        raise PlanValidationError("retrieval plan must be an object")

    objective = _required_text(raw.get("objective"), "objective")
    codegraph_queries = []
    for item in _list_value(raw.get("codegraph_queries")):
        if not isinstance(item, dict):
            raise PlanValidationError("codegraph query must be an object")
        operation = _required_text(item.get("operation"), "operation")
        if operation not in ALLOWED_CODEGRAPH_OPERATIONS:
            raise PlanValidationError(
                f"unsupported CodeGraph operation: {operation}"
            )
        query = _bounded_query(item.get("query"))
        symbol = _bounded_query(item.get("symbol"))
        if not query and not symbol:
            raise PlanValidationError("CodeGraph query needs query or symbol")
        codegraph_queries.append(
            CodeGraphQuery(operation=operation, query=query, symbol=symbol)
        )

    windows = []
    for item in _list_value(raw.get("source_windows")):
        if not isinstance(item, dict):
            raise PlanValidationError("source window must be an object")
        path = _required_text(item.get("path"), "source window path")
        start = _positive_int(item.get("start_line"), 1)
        end = item.get("end_line")
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
            _positive_int(
                raw_budgets.get("max_source_window_lines"),
                MAX_SOURCE_WINDOW_LINES,
            ),
            MAX_SOURCE_WINDOW_LINES,
        ),
        max_evidence_tokens=min(
            _positive_int(
                raw_budgets.get("max_evidence_tokens"),
                MAX_EVIDENCE_TOKENS,
            ),
            MAX_EVIDENCE_TOKENS,
        ),
    )
    return RetrievalPlan(
        objective=objective,
        project=_bounded_query(raw.get("project")),
        repository=_bounded_query(raw.get("repository")),
        revision=_bounded_query(raw.get("revision")),
        question_type=_bounded_query(raw.get("question_type")) or "mixed",
        evidence_requirements=_unique_texts(
            raw.get("evidence_requirements")
        ),
        codegraph_queries=tuple(codegraph_queries),
        literal_queries=_unique_queries(raw.get("literal_queries")),
        file_scopes=_unique_queries(raw.get("file_scopes")),
        source_windows=tuple(windows),
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

    def __init__(self, workspace_tools=None, codegraph_tools=None):
        self.workspace_tools = dict(workspace_tools or {})
        self.codegraph_tools = dict(codegraph_tools or {})

    def execute(self, plan):
        """Run independent planned operations concurrently."""

        requests = []
        for query in plan.codegraph_queries:
            adapter = self.codegraph_tools.get(query.operation)
            if adapter is not None:
                requests.append(
                    ("codegraph", query.operation, adapter, query.as_args())
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
            futures = {
                pool.submit(_invoke_adapter, adapter, args): (
                    evidence_type,
                    provenance,
                )
                for evidence_type, provenance, adapter, args in requests
            }
            for future in as_completed(futures):
                evidence_type, provenance = futures[future]
                call_counts[evidence_type] += 1
                try:
                    result = future.result()
                except Exception as exc:
                    raw_items.append(
                        {
                            "evidence_type": "retrieval_error",
                            "content": type(exc).__name__,
                            "provenance": provenance,
                        }
                    )
                    continue
                raw_items.extend(
                    _items_from_result(result, evidence_type, provenance)
                )

        reader = self.workspace_tools.get("read_workspace_file")
        if reader is not None:
            windows = plan.source_windows[: plan.max_files]
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
                try:
                    result = _invoke_adapter(
                        reader,
                        {
                            "path": window.path,
                            "offset": window.start_line,
                            "limit": limit,
                        },
                    )
                except Exception as exc:
                    raw_items.append(
                        {
                            "evidence_type": "retrieval_error",
                            "path": window.path,
                            "content": type(exc).__name__,
                            "provenance": "read_workspace_file",
                        }
                    )
                else:
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


def validate_citations(citations, bundle, workspace_root):
    """Return citations that match real files, lines, and evidence items."""

    root = Path(workspace_root).resolve()
    valid = []
    invalid = []
    for citation in citations or ():
        path_text = str((citation or {}).get("path") or "")
        try:
            path = (root / path_text).resolve()
            path.relative_to(root)
            start = int(citation.get("start_line"))
            end = int(citation.get("end_line"))
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            matches = any(
                item.evidence_type == "source"
                and item.path == path_text
                and item.start_line is not None
                and item.end_line is not None
                and item.start_line <= start <= item.end_line
                and item.start_line <= end <= item.end_line
                for item in bundle.items
            )
            if (
                not path.is_file()
                or start < 1
                or end < start
                or end > line_count
                or not matches
            ):
                raise ValueError
        except (OSError, TypeError, ValueError, AttributeError):
            invalid.append(path_text or "<missing-path>")
            continue
        valid.append(dict(citation))
    return tuple(valid), tuple(invalid)


def _invoke_adapter(adapter, args):
    if callable(adapter):
        return adapter(**args)
    return adapter.invoke(args)


def _items_from_result(result, evidence_type, provenance):
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            return [
                {
                    "evidence_type": evidence_type,
                    "content": result,
                    "provenance": provenance,
                }
            ]
    if isinstance(result, dict):
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
        result = json.dumps(result, ensure_ascii=False)
    return [
        {
            "evidence_type": evidence_type,
            "content": str(result),
            "provenance": provenance,
        }
    ]


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


def _required_text(value, label):
    text = str(value or "").strip()
    if not text or len(text) > MAX_QUERY_CHARS:
        raise PlanValidationError(f"{label} is missing or too long")
    return text


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
        query = _bounded_query(item)
        if query:
            queries.append(query)
    return tuple(dict.fromkeys(queries))


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
