# RedactionBench (en)

R-Score from the dataset's own scorer (revision 77684d7e), 200 documents, 2,663,769 characters. Every detected entity is redacted regardless of tier; thresholds are not tuned on this set. Leaderboard for reference: Claude Opus 5.5 0.832, OpenAI Privacy Filter 0.533, nvidia/gliner-PII 0.339, gliner_multi_pii-v1 0.309, ai4privacy multilingual 0.180 (thresholds tuned on the benchmark).

| Method | R-Score | Mandatory coverage | Background FP runs | academic | code | emails | files | financial | government | legal | logs | medical | operations | terminal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rules | **0.261** | 33.8% | 452 | 0.197 | 0.324 | 0.385 | 0.319 | 0.107 | 0.168 | 0.162 | 0.413 | 0.190 | 0.166 | 0.384 |
| rules+heuristics | **0.365** | 40.1% | 734 | 0.405 | 0.290 | 0.442 | 0.296 | 0.303 | 0.327 | 0.407 | 0.421 | 0.385 | 0.406 | 0.416 |
| teacher:ai4privacy-modernbert | **0.214** | 35.6% | 5388 | 0.327 | 0.107 | 0.244 | 0.140 | 0.296 | 0.280 | 0.263 | 0.117 | 0.232 | 0.372 | 0.064 |
| rules+teacher:ai4privacy-modernbert | **0.268** | 47.2% | 5547 | 0.352 | 0.213 | 0.365 | 0.224 | 0.321 | 0.302 | 0.277 | 0.146 | 0.232 | 0.400 | 0.181 |
| teacher:gliner-multi-pii | **0.293** | 28.1% | 2880 | 0.398 | 0.048 | 0.429 | 0.198 | 0.407 | 0.427 | 0.283 | 0.196 | 0.311 | 0.529 | 0.119 |
| rules+teacher:gliner-multi-pii | **0.365** | 51.0% | 3177 | 0.413 | 0.197 | 0.493 | 0.292 | 0.413 | 0.428 | 0.293 | 0.394 | 0.314 | 0.525 | 0.359 |
| teacher:gliner-pii-nvidia | **0.487** | 55.2% | 1083 | 0.687 | 0.265 | 0.580 | 0.397 | 0.522 | 0.493 | 0.539 | 0.340 | 0.561 | 0.689 | 0.402 |
| rules+teacher:gliner-pii-nvidia | **0.507** | 61.8% | 1285 | 0.689 | 0.320 | 0.600 | 0.438 | 0.530 | 0.495 | 0.535 | 0.359 | 0.570 | 0.675 | 0.470 |
