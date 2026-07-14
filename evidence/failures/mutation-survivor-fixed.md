# Mutation survivor and test gap

The first focused mutation run killed 3 of 4 mutants. The survivor disabled removal of plaintext `queries` from persisted proof-check evidence. Existing end-to-end tests did not construct metadata containing that field, so they could not detect the change.

Two redaction assertions were added, including a direct contract test with a plaintext query in proof evidence. Re-running the unchanged four-mutant set killed 4 of 4. The final raw run is `raw/mutation_runs.json`; the initial survivor is retained here as the failure history rather than hidden.
