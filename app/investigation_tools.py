
MAX_QUERY_LENGTH = 500
MAX_RESULTS_LIMIT = 10
MAX_TEXT_LENGTH = 1000


def search_incident_evidence(
    query: str,
    incident_id: int,
    evidence_items,
    max_results: int = 5,
) -> list[dict]:
    """Search bounded evidence belonging to one incident."""

    if not isinstance(query, str):
        raise ValueError("Query must be a string.")

    query = query.strip()

    if not query:
        raise ValueError("Query cannot be empty.")

    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(
            f"Query cannot exceed {MAX_QUERY_LENGTH} characters."
        )

    if not isinstance(max_results, int) or isinstance(max_results, bool):
        raise ValueError("max_results must be an integer.")

    if not 1 <= max_results <= MAX_RESULTS_LIMIT:
        raise ValueError(
            f"max_results must be between 1 and {MAX_RESULTS_LIMIT}."
        )

    query_terms = set(query.casefold().split())
    matches = []

    for item in evidence_items:
        # Ignore malformed records rather than failing the entire search.
        try:
            item_incident_id = item.incident_id
            evidence_id = item.id
            source_type = item.source_type
            content = item.content
        except AttributeError:
            continue

        # Keep the search strictly scoped to this incident.
        if item_incident_id != incident_id:
            continue

        # Validate fields used in matching and returned results.
        if (
            not isinstance(evidence_id, int)
            or isinstance(evidence_id, bool)
            or not isinstance(source_type, str)
            or not isinstance(content, (str, type(None)))
        ):
            continue

        text = content or ""
        normalized_text = text.casefold()

        matching_terms = [
            term for term in query_terms
            if term in normalized_text
        ]

        if not matching_terms:
            continue

        matches.append(
            {
                "incident_id": item_incident_id,
                "evidence_id": evidence_id,
                "source_type": source_type,
                "text": text[:MAX_TEXT_LENGTH],
                "match_count": len(matching_terms),
            }
        )

    # Rank by matching terms; preserve original order for ties.
    matches.sort(
        key=lambda result: result["match_count"],
        reverse=True,
    )

    return [
        {
            "incident_id": result["incident_id"],
            "evidence_id": result["evidence_id"],
            "source_type": result["source_type"],
            "text": result["text"],
        }
        for result in matches[:max_results]
    ]
