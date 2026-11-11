
from collections import Counter

from experiments.evaluate_final_retrieval_v2 import FINAL_TEST_CASES


# ============================================================
# OPSPILOT RETRIEVAL BENCHMARK V3 - RELEVANCE LABELS
#
# V2 remains unchanged.
#
# Labels:
# DIRECT         - Explicit failure or failure mechanism.
# CONTRIBUTING   - Condition causing or worsening the incident.
# CORROBORATING  - Independently supports the diagnosis.
# DIFFERENTIAL   - Helps distinguish a plausible alternative.
# IRRELEVANT     - Does not materially help investigate the incident.
#
# Direct benchmark:
# DIRECT only.
#
# Diagnostic benchmark:
# DIRECT + CONTRIBUTING + CORROBORATING + DIFFERENTIAL.
# ============================================================


LABEL_GROUPS = {

    "DIRECT": [
        # Scenario 1: Checkout certificate failure
        2001, 2002,

        # Scenario 2: Garbage collection pauses
        2011, 2012, 2013,

        # Scenario 3: Login clock skew
        2021, 2022,

        # Scenario 4: Upload body limit
        2031,

        # Scenario 5: Inventory cache invalidation
        2041, 2042,

        # Scenario 6: Database checkpoint pressure
        2051, 2052,

        # Scenario 7: Reporting timezone boundary
        2061,

        # Scenario 8: SMTP greylisting
        2071,

        # Scenario 9: Proxy header configuration
        2081, 2082,

        # Scenario 10: Queue redelivery
        2091, 2093,

        # Scenario 11: Stale DNS responses
        2101, 2102,

        # Scenario 12: Duplicate payments
        2111, 2113,

        # Scenario 13: Ephemeral storage exhaustion
        2121,

        # Scenario 14: Search analyzer mismatch
        2131, 2132, 2133,

        # Scenario 15: Webhook duplicate processing
        2141, 2143,

        # Scenario 16: TLS hostname mismatch
        2151, 2153,

        # Scenario 17: Read-after-write inconsistency
        2161, 2162,

        # Scenario 18: Scheduled-job timezone drift
        2171,

        # Scenario 19: Encryption key permissions
        2181,

        # Scenario 20: Circuit breaker recovery
        2192, 2193,
    ],

    "CONTRIBUTING": [
        2003,
        2016,
        2023,
        2032,
        2043,
        2053,
        2055,
        2062,
        2072,
        2092,
        2095,
        2112,
        2114,
        2122,
        2123,
        2142,
        2152,
        2163,
        2173,
        2191,
        2182,
    ],

    "CORROBORATING": [
        2033, 2038,
        2054,
        2063,
        2073,
        2083, 2088,
        2094,
        2103, 2105,
        2115,
        2127,
        2137,
        2148,
        2158,
        2172,
        2183,
    ],

    "DIFFERENTIAL": [
        2024, 2025,
        2035,
        2044, 2047,
        2057,
        2064, 2065, 2066,
        2074, 2075,
        2085, 2087,
        2098,
        2104, 2106, 2107,
        2117,
        2124, 2125,
        2134, 2135, 2138,
        2144, 2146, 2147,
        2154, 2157,
        2165, 2166, 2167,
        2174, 2175, 2178,
        2187, 2188,
        2194, 2195, 2196, 2197, 2198,
    ],

    "IRRELEVANT": [
        2004, 2005, 2006, 2007, 2008,
        2014, 2015, 2017, 2018,
        2026, 2027, 2028,
        2034, 2036, 2037,
        2045, 2046, 2048,
        2056, 2058,
        2067, 2068,
        2076, 2078, 2077,
        2084, 2086,
        2096, 2097,
        2108,
        2116, 2118,
        2126, 2128,
        2136,
        2145,
        2155, 2156,
        2164, 2168,
        2176, 2177,
        2185, 2184, 2186,
    ],
}


# ============================================================
# DERIVED RELEVANCE SETS
# ============================================================

# Convert category groups into an evidence ID -> label mapping.
EVIDENCE_LABELS = {
    evidence_id: label
    for label, evidence_ids in LABEL_GROUPS.items()
    for evidence_id in evidence_ids
}


DIRECT_RELEVANT_IDS = {
    evidence_id
    for evidence_id, label in EVIDENCE_LABELS.items()
    if label == "DIRECT"
}


DIAGNOSTIC_RELEVANT_IDS = {
    evidence_id
    for evidence_id, label in EVIDENCE_LABELS.items()
    if label in {
        "DIRECT",
        "CONTRIBUTING",
        "CORROBORATING",
        "DIFFERENTIAL",
    }
}


# ============================================================
# VALIDATION
# ============================================================

def validate_labels():

    actual_ids = []

    for case in FINAL_TEST_CASES:
        for evidence in case["evidence"]:
            actual_ids.append(evidence[0])

    actual_id_set = set(actual_ids)

    # Check that the original dataset has unique IDs.
    if len(actual_ids) != len(actual_id_set):
        raise ValueError(
            "Original benchmark contains duplicate evidence IDs."
        )

    # Check for duplicate assignments across label groups.
    assigned_ids = [
        evidence_id
        for evidence_ids in LABEL_GROUPS.values()
        for evidence_id in evidence_ids
    ]

    if len(assigned_ids) != len(set(assigned_ids)):
        raise ValueError(
            "An evidence ID has been assigned to multiple categories."
        )

    # Check for IDs missing from the classification file.
    missing_ids = actual_id_set - set(EVIDENCE_LABELS)

    if missing_ids:
        raise ValueError(
            f"Evidence IDs without classifications: {sorted(missing_ids)}"
        )

    # Check for classifications referring to nonexistent evidence.
    unknown_ids = set(EVIDENCE_LABELS) - actual_id_set

    if unknown_ids:
        raise ValueError(
            f"Unknown evidence IDs in classification file: {sorted(unknown_ids)}"
        )

    # Check expected label categories.
    allowed_labels = {
        "DIRECT",
        "CONTRIBUTING",
        "CORROBORATING",
        "DIFFERENTIAL",
        "IRRELEVANT",
    }

    if set(EVIDENCE_LABELS.values()) - allowed_labels:
        raise ValueError("Invalid classification category found.")

    # Check relevance-set consistency.
    expected_direct = {
        evidence_id
        for evidence_id, label in EVIDENCE_LABELS.items()
        if label == "DIRECT"
    }

    expected_diagnostic = {
        evidence_id
        for evidence_id, label in EVIDENCE_LABELS.items()
        if label != "IRRELEVANT"
    }

    if DIRECT_RELEVANT_IDS != expected_direct:
        raise ValueError("Direct relevance set isinconsistent.")

    if DIAGNOSTIC_RELEVANT_IDS != expected_diagnostic:
        raise ValueError("Diagnostic relevance set is inconsistent.")

    print("V3 relevance-label validation passed.")

    return True


# ============================================================
# SUMMARY REPORT
# ============================================================

def print_label_summary():

    validate_labels()

    category_counts = Counter(EVIDENCE_LABELS.values())

    print("\n" + "=" * 75)
    print("OPSPILOT RETRIEVAL BENCHMARK V3 - LABEL SUMMARY")
    print("=" * 75)

    print(f"Scenarios              : {len(FINAL_TEST_CASES)}")
    print(f"Evidence records       : {len(EVIDENCE_LABELS)}")
    print(f"Unique evidence IDs    : {len(EVIDENCE_LABELS)}")

    print("\nClassification counts:")

    for label in [
        "DIRECT",
        "CONTRIBUTING",
        "CORROBORATING",
        "DIFFERENTIAL",
        "IRRELEVANT",
    ]:
        print(f"{label:20}: {category_counts[label]}")

    print("\nEvaluation relevance counts:")
    print(f"Direct relevant       : {len(DIRECT_RELEVANT_IDS)}")
    print(f"Diagnostic relevant   : {len(DIAGNOSTIC_RELEVANT_IDS)}")
    print(
        f"Direct irrelevant     : "
        f"{len(EVIDENCE_LABELS) - len(DIRECT_RELEVANT_IDS)}"
    )
    print(
        f"Diagnostic irrelevant : "
        f"{len(EVIDENCE_LABELS) - len(DIAGNOSTIC_RELEVANT_IDS)}"
    )

    print("\nPer-scenario breakdown:")

    for index, case in enumerate(FINAL_TEST_CASES, start=1):

        scenario_counts = Counter(
            EVIDENCE_LABELS[evidence[0]]
            for evidence in case["evidence"]
        )

        direct_count = scenario_counts["DIRECT"]

        diagnostic_count = sum(
            scenario_counts[label]
            for label in [
                "DIRECT",
                "CONTRIBUTING",
                "CORROBORATING",
                "DIFFERENTIAL",
            ]
        )

        print(
            f"\n{index:02}. {case['name']}"
            f"\n    Direct relevant     : {direct_count}"
            f"\n    Diagnostic relevant : {diagnostic_count}"
            f"\n    Irrelevant          : {scenario_counts['IRRELEVANT']}"
        )

    print("\n" + "=" * 75)
    print("V3 LABEL SUMMARY COMPLETED")
    print("=" * 75)


if __name__ == "__main__":
    print_label_summary()
