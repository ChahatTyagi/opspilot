
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TraceSpan:
    """Validated trace span with its source evidence identity."""

    evidence_id: int
    trace_id: str
    span_id: str
    parent_span_id: str | None
    service_name: str


@dataclass(frozen=True)
class DirectionalTopologySelection:
    """
    Evidence selected from a query-anchored service topology.

    Direct service evidence:
        Spans belonging to services explicitly named in the query.

    Downstream evidence:
        Child spans whose parent belongs to a queried service.

    Upstream context:
        Parent spans of queried-service spans. These provide context,
        but are deliberately not promoted by the V3 ranking policy.
    """

    matched_services: frozenset[str]
    direct_service_evidence_ids: frozenset[int]
    downstream_evidence_ids: frozenset[int]
    upstream_context_evidence_ids: frozenset[int]

    @property
    def boosted_evidence_ids(self) -> frozenset[int]:
        """Evidence IDs eligible for the V3 topology boost."""

        return (
            self.direct_service_evidence_ids
            | self.downstream_evidence_ids
        )


def _normalize_service_name(value: str) -> str:
    """Normalize service names and query text into whole-word tokens."""

    return " ".join(
        re.findall(r"[a-z0-9]+", value.casefold())
    )


def _contains_phrase(query: str, phrase: str) -> bool:
    """Check whether phrase tokens occur contiguously in query tokens."""

    query_tokens = query.split()
    phrase_tokens = phrase.split()

    if not phrase_tokens or len(phrase_tokens) > len(query_tokens):
        return False

    phrase_length = len(phrase_tokens)

    return any(
        query_tokens[index:index + phrase_length] == phrase_tokens
        for index in range(len(query_tokens) - phrase_length + 1)
    )


def _is_hex_identifier(value: Any, expected_length: int) -> bool:
    """Validate a fixed-length hexadecimal trace identifier."""

    return (
        isinstance(value, str)
        and len(value) == expected_length
        and all(
            character in "0123456789abcdefABCDEF"
            for character in value
        )
    )


def _parse_trace_span(evidence: Any) -> TraceSpan | None:
    """
    Convert one evidence record into a validated TraceSpan.

    Invalid or non-trace evidence is ignored rather than causing
    retrieval to fail.
    """

    if getattr(evidence, "source_type", None) != "trace":
        return None

    evidence_id = getattr(evidence, "id", None)

    if (
        not isinstance(evidence_id, int)
        or isinstance(evidence_id, bool)
    ):
        return None

    content = getattr(evidence, "content", None)

    if not isinstance(content, str) or not content:
        return None

    try:
        record = json.loads(content)
    except (TypeError, ValueError):
        return None

    if not isinstance(record, dict):
        return None

    if (
        record.get("schema_version") != 1
        or record.get("signal") != "trace"
    ):
        return None

    trace_id = record.get("trace_id")
    span_id = record.get("span_id")
    parent_span_id = record.get("parent_span_id")
    service_name = record.get("service_name")

    if not _is_hex_identifier(trace_id, 32):
        return None

    if not _is_hex_identifier(span_id, 16):
        return None

    if parent_span_id is not None and not _is_hex_identifier(
        parent_span_id,
        16,
    ):
        return None

    if not isinstance(service_name, str):
        return None

    service_name = service_name.strip()[:200]

    if not service_name:
        return None

    return TraceSpan(
        evidence_id=evidence_id,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        service_name=service_name,
    )


def _collect_valid_spans(
    evidence_items: list[Any],
) -> dict[str, dict[str, TraceSpan]]:
    """
    Index valid spans by trace ID and span ID.

    Parent-child relationships are resolved only within the same trace.
    Duplicate span identities are ignored after their first occurrence.
    """

    spans_by_trace: dict[str, dict[str, TraceSpan]] = {}

    for evidence in evidence_items:
        span = _parse_trace_span(evidence)

        if span is None:
            continue

        trace_spans = spans_by_trace.setdefault(
            span.trace_id,
            {},
        )

        if span.span_id in trace_spans:
            continue

        trace_spans[span.span_id] = span

    return spans_by_trace


def select_directional_topology_evidence(
    query: str,
    evidence_items: list[Any],
) -> DirectionalTopologySelection:
    """
    Select topology evidence without erasing dependency direction.

    V3 policy:

    1. Queried service spans are directly relevant.
    2. Child spans called by a queried service are downstream candidates.
    3. Parent spans of a queried service are context only.
    4. Unconnected services are not selected.
    5. Relationships are resolved within the same trace only.

    The function does not modify evidence, scores, or production retrieval.
    """

    empty_selection = DirectionalTopologySelection(
        matched_services=frozenset(),
        direct_service_evidence_ids=frozenset(),
        downstream_evidence_ids=frozenset(),
        upstream_context_evidence_ids=frozenset(),
    )

    if not isinstance(query, str) or not query.strip():
        return empty_selection

    normalized_query = _normalize_service_name(query)

    if not normalized_query:
        return empty_selection

    spans_by_trace = _collect_valid_spans(evidence_items)

    if not spans_by_trace:
        return empty_selection

    all_spans = [
        span
        for trace_spans in spans_by_trace.values()
        for span in trace_spans.values()
    ]

    matched_services = frozenset(
        span.service_name
        for span in all_spans
        if _contains_phrase(
            normalized_query,
            _normalize_service_name(span.service_name),
        )
    )

    if not matched_services:
        return empty_selection

    direct_service_ids: set[int] = set()
    downstream_ids: set[int] = set()
    upstream_context_ids: set[int] = set()

    # First collect all evidence belonging to queried services.
    for span in all_spans:
        if span.service_name in matched_services:
            direct_service_ids.add(span.evidence_id)

    # Then resolve actual parent-child relationships.
    # The child span's evidence ID represents the downstream operation.
    for trace_spans in spans_by_trace.values():
        for child in trace_spans.values():
            parent_id = child.parent_span_id

            if parent_id is None:
                continue

            parent = trace_spans.get(parent_id)

            if parent is None:
                continue

            # Same-service spans do not represent a cross-service edge.
            if parent.service_name == child.service_name:
                continue

            if parent.service_name in matched_services:
                downstream_ids.add(child.evidence_id)

            elif child.service_name in matched_services:
                # Upstream parent evidence is retained as context only.
                upstream_context_ids.add(parent.evidence_id)

    # Keep the categories mutually exclusive for clearer diagnostics.
    downstream_ids.difference_update(direct_service_ids)
    upstream_context_ids.difference_update(direct_service_ids)
    upstream_context_ids.difference_update(downstream_ids)

    return DirectionalTopologySelection(
        matched_services=matched_services,
        direct_service_evidence_ids=frozenset(direct_service_ids),
        downstream_evidence_ids=frozenset(downstream_ids),
        upstream_context_evidence_ids=frozenset(upstream_context_ids),
    )


def directional_topology_relevant_evidence_ids(
    query: str,
    evidence_items: list[Any],
) -> set[int]:
    """
    Compatibility adapter for the existing EvidenceRetriever.

    The existing retriever expects a set of evidence IDs to boost.
    V3 returns queried-service and downstream evidence only.
    """

    selection = select_directional_topology_evidence(
        query=query,
        evidence_items=evidence_items,
    )

    return set(selection.boosted_evidence_ids)
