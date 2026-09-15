# Verification automation with public evidence

This repository is a small reference implementation of an automation service
for executable RTL verification evidence. One command fetches three public
examples at immutable commits, runs their real simulations, checks what their
summaries claim against the downloaded sources, and archives a top-level
manifest with measured timings.

The pinned jobs are:

| Example | Commit | Verification focus |
| --- | --- | --- |
| [ready-valid-verification](https://github.com/Rivoryxa-Technologies/ready-valid-verification) | `7c4c1913d7db92192b13de47dcb666f445c4717e` | ready/valid stability and ordering |
| [reset-recovery-verification](https://github.com/Rivoryxa-Technologies/reset-recovery-verification) | `66555fcb2a060e9269dbc464d6b20fc1cfb3415e` | reset flush and recovery |
| [round-robin-verification](https://github.com/Rivoryxa-Technologies/round-robin-verification) | `049b015a782d48ae3ed491a2ef102147e7906705` | arbitration safety and fairness |

## Run from a fresh clone

Install Git, Python 3, Icarus Verilog, and its `vvp` runtime. No Python package
installation is needed. Then run:

```sh
make test
```

The command first runs focused tests of the automation boundary and then runs
all three RTL repositories. Network access to GitHub is required. Every fetched
checkout must resolve to its full pinned commit. The checkouts are temporary to
the evidence run and are removed after validation.

Each run creates `artifacts/<UTC run id>/manifest.json`. The same directory
retains fetch, checkout, revision, and test logs; each upstream summary; and its
simulation logs and compiled evidence. The manifest records each exact URL and
revision, subprocess result, timeout state, measured duration, validation
decision, environment, and the automation runner hash.

Use a different per-process limit when needed:

```sh
python3 tools/run.py --timeout 180
```

## What counts as a pass

A zero process exit alone is insufficient. For every job, the automation
requires all of the following:

- fetch and detached checkout succeed at the pinned full commit;
- the upstream runner completes before its timeout;
- exactly one new schema-version-1 summary is created by this invocation;
- the summary's overall result is the JSON boolean `true`;
- every required case appears exactly once, in the pinned runner's expected
  matrix, and its exact-outcome field is the JSON boolean `true`;
- every required source has a declared SHA-256 and every declared hash matches
  the file in the pinned checkout.

The unit fixtures are deliberately separate from RTL mutants. They demonstrate
that a missing executable, killed timeout, malformed summary, stale summary,
source mismatch, extra failure, or truthy non-boolean cannot be reported as a
successful automation job. The upstream examples own the deliberate RTL bugs
and their domain-specific expected-failure checks.

## Evidence limits

This automation establishes provenance and consistently evaluates the finite
simulation evidence emitted by the pinned repositories. It does not turn those
simulations into exhaustive or formal proofs. A valid source hash proves that
the reported file matches the fetched checkout; it does not independently
prove the design correct. GitHub availability, Git object integrity, the local
toolchain, and the upstream test quality remain part of the trust boundary.

The runner is intentionally sequential and local. It demonstrates the core of
a hosted worker: immutable input, separate per-job directories, bounded direct
processes, semantic result validation, and durable evidence. Those directories
are organizational separation, not a security sandbox. The upstream runners
also enforce timeouts on their compile and simulation process groups; a nested
process that deliberately escapes both process groups is outside this example's
cleanup guarantee. This repository does not provide a queue, authentication,
multi-tenant isolation, object storage, signatures, or a web API.

## Repository map

- `tools/run.py` — stdlib-only orchestration and evidence validation
- `tools/test_runner.py` — self-contained infrastructure failure fixtures
- `.github/workflows/verification.yml` — clean Linux execution and artifact upload

This project is available under the MIT License.
