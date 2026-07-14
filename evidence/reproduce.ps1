$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $projectRoot

python scripts\capture_evidence_environment.py
python scripts\run_retrieval_evidence.py --skip-local-embed
python scripts\run_hard_forget_evidence.py
python scripts\run_mutation_evidence.py
python -m pytest tests -q -p no:cacheprovider --junitxml=evidence\raw\pytest.xml --cov=memory_garden --cov-branch --cov-report=json:evidence\raw\coverage.json --cov-report=term
