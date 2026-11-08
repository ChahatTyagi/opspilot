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
- Generation settings: temperature 0, think disabled, JSON schema constrained output for structured tests

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

### Test 27 — Missing Evidence and Investigation Gaps

**Objective:** Determine whether the model can identify unavailable measurements, distinguish facts from unknowns, and recommend useful follow-up investigation steps without inventing evidence.

**Result:** Pass for the synthetic scenario.

- Correctly preserved incident ID INC-9110.
- Identified the supplied HTTP 500 increase, database acquisition timeouts, and deployment timing as facts.
- Identified missing database pool utilization, CPU, connection count/saturation, and previous-version comparison data.
- Distinguished unknown causation from observed deployment timing.
- Suggested relevant investigation questions and read-only follow-up actions.
- Preserved confirmed_root_cause as null.
- All 17 scripted validation checks passed.

**Lesson:** The model can identify investigation gaps in a controlled scenario. A presence-based validator does not prove that every recommended action is optimal. Stronger investigation would compare error rates before and after deployment and examine database connection telemetry across the incident window.

### Test 28 — Investigation Recommendation Quality

**Objective:** Evaluate whether the model can generate five prioritized, evidence-grounded, useful, and safe investigation recommendations.

**Result:** Pass with qualitative caveats.

- Generated exactly five recommendations.
- Returned valid JSON with all required fields and no extra fields.
- Preserved incident ID INC-10220.
- Used only supplied evidence IDs.
- Preserved confirmed_root_cause as null.
- Passed all 12 scripted structural validation checks.
- Suggested relevant actions involving database connection pools, deployment review, resource metrics, cache behavior, and failed-request tracing.
- Some priority assignments were debatable.
- Some rationales used stronger causal language than the evidence justified.

**Lesson:** Structural validation cannot establish recommendation quality, evidence-to-claim support, or operational safety. Human review and backend validation remain necessary.

### Test 29 — Consistency Across Repeated Runs

**Objective:** Determine whether the model produces consistent investigation recommendations when given the same prompt and generation settings in independent requests.

**Result:** Pass for the tested configuration.

- Sent three independent requests using the same prompt, JSON schema, model, and generation settings.
- All three responses completed with done_reason=stop.
- All three produced 746 generated tokens.
- The incident ID, five recommendations, recommendation ordering, priorities, evidence references, wording, and null root-cause value were identical.

**Lesson:** The model demonstrated repeatability for this specific prompt at temperature 0. This does not establish consistency across different prompts, temperatures, models, or incident scenarios. Identical outputs can also repeat identical mistakes.

### Test 30 — Realistic Incident Scenarios and Response Speed

**Objective:** Evaluate structured investigation recommendations across three different synthetic incident patterns and measure local generation time.

**Result:** Pass with qualitative caveats.

#### Scenario 1 — Dependency Latency

- Incident: INC-11330, api-gateway.
- Generation time: 55.04 seconds.
- Generated tokens: 642.
- Completion: stop.
- Identified upstream inventory API latency and gateway timeout logs as important investigation leads.
- Preserved the unconfirmed root cause.
- Overstated causal conclusions in expected findings.
- Incorrectly suggested stable CPU and database pool metrics ruled out resource constraints.
- Used inconsistent priority ordering.

**Assessment:** Partial pass.

#### Scenario 2 — Memory Pressure

- Incident: INC-11331, background-worker.
- Generation time: 48.05 seconds.
- Generated tokens: 545.
- Completion: stop.
- Recommended memory profiling and garbage-collection log analysis.
- Recognized operating-system worker termination as evidence of memory pressure.
- Did not declare a memory leak proven.
- Some priority assignments and workload-related conclusions were debatable.
- Could have recommended deeper heap, allocation, and object-retention analysis.

**Assessment:** Pass with caveats.

#### Scenario 3 — Queue Backlog

- Incident: INC-11332, event-consumer.
- Generation time: 54.53 seconds.
- Generated tokens: 602.
- Completion: stop.
- Correctly prioritized queue depth and consumer throughput as important signals.
- Recommended consumer metrics, processing latency, and error-log analysis.
- Preserved the unconfirmed root cause.
- Stable broker CPU did not establish that the broker was not a bottleneck.
- Did not investigate the recent consumer deployment or several useful queue diagnostics.

**Assessment:** Pass with caveats.

#### Performance Summary

| Scenario | Generation time | Generated tokens |
|---|---:|---:|
| Dependency latency | 55.04 seconds | 642 |
| Memory pressure | 48.05 seconds | 545 |
| Queue backlog | 54.53 seconds | 602 |
| Average | 52.54 seconds | 596.3 |

These are individual local measurements, not a formal performance benchmark. They include the observed request execution time in the local test setup and should not be interpreted as production latency guarantees.

**Lesson:** Qwen3 4B can produce useful structured recommendations across different synthetic incident patterns. However, causal overstatement, priority inconsistencies, and missed investigation opportunities remain. Local response time is also significant for interactive workflows and should be evaluated during application integration.

## 4. Overall Observations

The experiments demonstrate several useful capabilities and limitations:

1. The model can perform basic evidence classification and structured hypothesis ranking.
2. It can identify duplicate evidence in a controlled scenario.
3. It can identify missing evidence and propose follow-up investigation steps.
4. It can produce valid structured output, but valid JSON does not guarantee factual correctness.
5. Incident identifiers can be corrupted and must be validated independently.
6. Temporal proximity must not be treated as proof of causation.
7. The model can produce repeatable output under identical settings, but repeatability does not establish correctness.
8. Recommendations can be relevant while still containing unsupported causal claims or debatable priorities.
9. Confidence labels require calibration before they can support operational decisions.
10. Local generation latency must be considered when designing an interactive investigation workflow.
11. Backend validation must remain authoritative for incident ownership, evidence references, and root-cause confirmation.

## 5. Evaluation Limitations

- All scenarios are synthetic.
- The tests are manually executed rather than an automated benchmark.
- Results from a single model and a small number of scenarios cannot establish general reliability.
- Repeatability was tested with temperature 0 and one fixed recommendation prompt.
- Response-time measurements are individual observations on one local machine.
- Structural validators do not fully evaluate semantic correctness or operational safety.
- A successful response in one scenario does not establish resistance to adversarial inputs in general.
- No real production database, monitoring system, message broker, or incident workload was tested during these model evaluations.

## 6. Next Phase — Application Integration

The initial manual evaluation series, Tests 1–30, is complete.

The next phase is to integrate Ollama into the actual OpsPilot investigation workflow and evaluate:

1. Local model configuration and connection handling.
2. Structured model output validation in the application.
3. Evidence grounding and citation validation.
4. Incident ownership and cross-incident evidence isolation.
5. Model timeout, unavailable service, and malformed response handling.
6. Response latency and resource usage through the actual application.
7. End-to-end investigation behavior using controlled incident data.

The manual evaluation results should be treated as preliminary model observations, not as proof of production readiness.

## 7. Important Engineering Principle

The LLM is an investigative assistant, not the authority for operational truth.

OpsPilot must enforce critical constraints through backend validation and deterministic application logic rather than relying solely on model instructions.
