
from typing import Any, Sequence

from app.telemetry import build_service_topology


MAX_TOPOLOGY_NODES = 30
MAX_TOPOLOGY_EDGES = 60
MAX_EVIDENCE_IDS_PER_ITEM = 20


def get_incident_service_topology(
    *,
    incident_id: int,
    evidence_items: Sequence[Any],
) -> dict:
    """Build a bounded, incident-scoped topology for AI investigation."""

    scoped_evidence = [
        item
        for item in evidence_items
        if getattr(item, "incident_id", None) == incident_id
    ]

    topology = build_service_topology(scoped_evidence)

    all_nodes = topology["nodes"]
    all_edges = topology["edges"]

    nodes = all_nodes[:MAX_TOPOLOGY_NODES]
    edges = all_edges[:MAX_TOPOLOGY_EDGES]

    returned_evidence_ids: set[int] = set()

    def bound_evidence_ids(item: dict) -> dict:
        raw_ids = item.get("evidence_ids", [])

        valid_ids = sorted(
            {
                evidence_id
                for evidence_id in raw_ids
                if isinstance(evidence_id, int)
                and not isinstance(evidence_id, bool)
            }
        )

        visible_ids = valid_ids[:MAX_EVIDENCE_IDS_PER_ITEM]
        returned_evidence_ids.update(visible_ids)

        return {
            **item,
            "evidence_ids": visible_ids,
            "evidence_ids_truncated": (
                len(valid_ids) > MAX_EVIDENCE_IDS_PER_ITEM
            ),
        }

    bounded_nodes = [
        bound_evidence_ids(node)
        for node in nodes
    ]

    bounded_edges = [
        bound_evidence_ids(edge)
        for edge in edges
    ]

    return {
        "topology": {
            "nodes": bounded_nodes,
            "edges": bounded_edges,
            "trace_count": topology["trace_count"],
            "total_nodes": len(all_nodes),
            "total_edges": len(all_edges),
            "truncated": (
                len(all_nodes) > MAX_TOPOLOGY_NODES
                or len(all_edges) > MAX_TOPOLOGY_EDGES
            ),
        },
        "evidence_ids": sorted(returned_evidence_ids),
    }
