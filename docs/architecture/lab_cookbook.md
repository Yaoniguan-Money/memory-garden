# Lab Cookbook / CI Contracts Architecture

This document describes the seventh layer of Memory Garden: a lightweight Lab tooling layer built on top of the v0.6 Garden Lab. It does not replace the snapshot runner or introduce a new runtime. It makes the existing Lab easier to catalog, load, package, report, and audit.

## Purpose

The v0.6 Garden Lab already defines assertions, fixture suites, a snapshot runner, and run reports. The seventh layer adds developer-facing structure around those pieces:

- a catalog of available Lab suites and cases
- JSON loaders for external EvalCase-style definitions
- reusable rule templates for Memory Garden safety contracts
- suite packs for smoke, safety, and full checks
- compact CI report contracts
- coverage and gap reports for known Memory Garden mechanisms

The layer exists so contributors can understand what the Lab currently protects, pick a small suite pack, and see which garden mechanisms still need stronger snapshots.

## Boundaries

This layer is read-only and metadata-oriented. It must not:

- execute Core, Runtime, Harvest, Observatory, or Integration flows
- create Seed, MemoryCard, CourtCase, DreamRecord, or GardenEvent objects through product APIs
- access storage or change schemas
- call external model services or semantic ranking systems
- create `.memory_garden`, `garden.db`, or generated report files
- turn the Lab into a CLI or Web product

All public objects are Pydantic models or pure functions over `LabSuite`, `LabCase`, `LabRun`, or `LabRunSummary`.

## Modules

| Module | Role |
|---|---|
| `memory_garden/lab/catalog.py` | Builds a stable metadata catalog from suites and cases without copying fixture snapshot bodies. |
| `memory_garden/lab/case_loader.py` | Loads Lab cases and suites from JSON-compatible dictionaries with explicit validation errors. |
| `memory_garden/lab/rule_templates.py` | Provides reusable Memory Garden contract assertions such as command short-circuit and greenhouse leak checks. |
| `memory_garden/lab/suite_packs.py` | Defines smoke, safety, and full suite pack selectors. |
| `memory_garden/lab/report_contract.py` | Converts Lab runs or summaries into compact CI-safe report objects. |
| `memory_garden/lab/coverage.py` | Reports covered, snapshot-only, and missing Memory Garden mechanisms from suite metadata. |

## Current Coverage

The default Lab fixtures cover snapshot contracts for seed extraction, runtime command short-circuiting, court/growth safety, harvest brief constraints, and public observatory redaction.

The coverage report intentionally marks some areas as incomplete:

- Dream Cycle has no default fixture coverage yet.
- Hard Forget has a safety-pack placeholder but still needs caller-provided snapshots.
- End-to-end adapter behavior is not driven by the Lab layer and should remain externally supplied as snapshots.

## Design Sources

The layer borrows engineering patterns rather than code:

- OpenAI Evals-style registry/case organization becomes `LabCatalog` and JSON case loading.
- promptfoo-style smoke/safety/full selection becomes local suite packs.
- DeepEval-style reusable assertions become Memory Garden rule templates.
- CI report contracts from common evaluation systems become compact `LabCIReport`.

The implementation stays local-first, deterministic, and dependency-light.

