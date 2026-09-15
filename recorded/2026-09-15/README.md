# Independent reproduction, 15 September 2026

A separate clone of automation source revision `141e649` ran `make test` successfully. Fourteen infrastructure regressions pass. All three public pinned projects reproduce their full 8, 18, and 16 case matrices, including the deliberately expected RTL failures.

[manifest.json](manifest.json) records the runner hash, upstream revisions, command results, and timings. Per-project validated summaries and raw logs are retained below `jobs/`. Generated binaries are omitted; the runner rebuilds them on each invocation.

The measured full run took 5.781 seconds including network fetch and execution on the recorded machine. This is a single observation, not a performance guarantee or engineering delivery estimate. See the root README for trust and process-cleanup limits.
