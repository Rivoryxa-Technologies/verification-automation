# Contributing

Keep automation changes reproducible from a fresh clone. Pin dependencies by
full immutable revision, retain enough evidence to diagnose every result, and
validate semantic outcomes rather than treating an exit status as proof.

New infrastructure failure fixtures must remain self-contained and clearly
separate from the RTL mutants in the upstream example repositories. Do not make
a fixture depend on network access, timing races, or a locally installed HDL
tool.

Run `make test` before submitting a change. Do not commit generated `artifacts/`.
Contributions are accepted under the MIT License.
