# Test and mutation evidence

The final full suite passed with 1,458 tests and 5 skips. The machine-readable results are in `raw/pytest.xml` and `raw/coverage.json`.

The final coverage capture reported:

- statement coverage: 87.44% (12,178 / 13,928)
- branch coverage: 70.91% (2,679 / 3,778)
- combined coverage.py total: 83.91%

The focused Hard Forget mutation audit changes four high-risk semantics one at a time: proof verdict logic, successful-delete product cleanup, retrieval-event purge, and proof-query redaction. The initial audit killed 3/4; the redaction mutant survived. A direct assertion for removal of plaintext probe queries was then added. The final audit killed 4/4 mutants. This score is useful engineering evidence but is not approved as a resume metric because the scope is only four targeted mutants.
