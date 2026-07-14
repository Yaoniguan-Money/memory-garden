# First retrieval dataset rejected by the admission gate

The first completed retrieval matrix contained 100 rows created as five surface forms of 20 base intents. The raw results and misses remain in `raw/retrieval_surface_variant_audit.json` and `failures/retrieval_surface_variant_failures.jsonl`.

This design was rejected before metric approval because it did not satisfy the independent-query requirement. It was replaced with 100 unique, manually labeled questions including negative, boundary, conflict, and failure cases. No result from the rejected matrix appears in the approved registry.
