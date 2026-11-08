# OpsPilot — Local LLM Evaluation Log

## 1. Purpose

This document records manual evaluations of the local Qwen3 4B model through Ollama for the OpsPilot AI Incident Investigator project.

The goal is to evaluate structured output, evidence handling, incident isolation, reasoning quality, and investigation reliability.

## 2. Test Environment

- Model: qwen3:4b
- Runtime: Ollama
- API: http://localhost:11434
- Evaluation type: Manual, synthetic incident scenarios
- Operating environment: Windows / PowerShell

These experiments evaluate model behavior. They do not constitute production reliability, real-world incident response, or a benchmark against a representative production dataset.

## 3. Evaluation Results

### Test 23 — Evidence Relevance and Noise Filtering

**Objective:** Determine whether the model can distinguish directly relevant, contextual, and irrelevant evidence.

**Result:** Partial pass.

- Correctly classified the three directly relevant payment-service observations.
- Correctly treated the deployment as contextual evidence rather than proof of causation.
- Correctly identified unrelated frontend and notification-service observations as irrelevant to the supplied incident.
- Failed to preserve the incident ID accurately: INC-5070 became INC-507:5070.

**Lesson:** Evidence classification can be useful, but identifiers must be controlled and validated by the backend.

### Test 24 — Evidence Duplication and Redundancy Detection

**Objective:** Test whether the model can identify duplicate evidence without incorrectly discarding independent observations.

**Result:** Pass for the synthetic scenario.

- Correctly grouped E1 and E2, which represented the same event.
- Kept E3, E4, E5, and E6 separate.
- Did not automatically classify differently worded timeout observations as duplicates.
- Accounted for all supplied evidence IDs.
- Kept the root cause unconfirmed.

**Lesson:** Deduplication should consider event identity, timestamps, source metadata, and correlation rules. Different IDs alone do not conclusively establish independent real-world events.

### Test 25 — Temporal Reasoning and Event Ordering

**Objective:** Evaluate chronological ordering and classification of pre-incident, failure, and recovery events.

**Result:** Partial pass.

- Correctly ordered all six evidence items chronologically.
- Correctly identified the failure and recovery events.
- Omitted one pre-incident event from its classification.
- Used causal language suggesting an earlier database pool increase led to timeouts, although the supplied timestamps established sequence, not causation.

**Lesson:** Timestamp ordering and causal reasoning are different tasks. Chronological ordering should be deterministic wherever possible, while causal claims require additional evidence.

### Test 26 — Hypothesis Ranking and Confidence Calibration

**Objective:** Evaluate ranking of competing hypotheses, evidence citations, and confidence labels.

**Result:** Partial pass.

- Included all four hypotheses exactly once.
- Assigned ranks 1 through 4.
- Ranked database connection pressure first, consistent with the strongest supplied evidence.
- Used valid evidence references and preserved the unconfirmed root cause.
- Assigned medium confidence to the deployment hypothesis despite lacking evidence of a deployment regression.
- Confidence labels were not statistically calibrated.

**Lesson:** A plausible hypothesis ranking does not establish calibrated confidence or a confirmed root cause. Confidence should not be treated as a measured probability without empirical calibration.

## 4. Overall Observations

The experiments demonstrate several useful capabilities and limitations:

1. The model can perform basic evidence classification and structured hypothesis ranking.
2. It can identify duplicate evidence in a controlled scenario.
3. It can produce valid structured output, but valid JSON does not guarantee factual correctness.
4. Incident identifiers can be corrupted and must be validated independently.
5. Temporal proximity must not be treated as proof of causation.
6. Confidence labels require calibration before they can support operational decisions.
7. Backend validation must remain authoritative for incident ownership, evidence references, and root-cause confirmation.

## 5. Evaluation Limitations

- All scenarios are synthetic.
- The tests are manually executed rather than an automated benchmark.
- Results from a single model and a small number of scenarios cannot establish general reliability.
- Model output may vary between runs.
- A successful response in one scenario does not establish resistance to adversarial inputs in general.

## 6. Next Evaluation

### Test 27 — Missing Evidence and Investigation Gaps

**Objective:** Determine whether the model can identify unavailable measurements, distinguish facts from unknowns, and recommend useful follow-up investigation steps without inventing evidence.

**Status:** In progress.

## 7. Important Engineering Principle

The LLM is an investigative assistant, not the authority for operational truth.

OpsPilot must enforce critical constraints through backend validation and deterministic application logic rather than relying solely on model instructions.
