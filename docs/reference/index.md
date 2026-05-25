# API Reference

Memory Garden's public API is organized by layer.

## Layer 1: Garden Life Core

`memory_garden.core`

| Entry Point | Description |
|---|---|
| `MemoryGardenCore` | Main facade: observe, open_court, apply_verdict, plant, compost, greenhouse, prune, forget, merge, dream, recent_events |
| `Seed` | Candidate memory unit |
| `MemoryCard` | Long-term memory card |
| `CourtCase` | Court proceeding record |
| `CourtVerdict` | Structured verdict |
| `DreamRecord` | Dream cycle output |
| `GardenEvent` | Journal event |
| `GardenRepository` | Abstract storage interface |
| `SQLiteGardenRepository` | SQLite storage implementation |

## Layer 2: Garden Runtime

`memory_garden.runtime`

| Entry Point | Description |
|---|---|
| `GardenRuntime` | Main runtime API: handle_command, open_session, close_session, before_reply, after_reply |
| `GardenSession` | Session state |
| `RuntimePolicy` | Thresholds and switches |
| `GardenBrief` | Pre-reply brief |
| `RuntimeFeedback` | Session-close feedback |
| `GardenSessionManager` | Session lifecycle |
| `RuntimeHooks` | before_reply / after_reply hooks |
| `NullHarvester` | Placeholder harvester |
| `TemplateBriefWriter` | Placeholder brief writer |

## Layer 3: Harvest Pipeline

`memory_garden.harvest`

| Entry Point | Description |
|---|---|
| `GardenHarvester` | Pipeline facade: harvest(query, cards, policy) → HarvestTrace |
| `HarvestQuery` | Query snapshot |
| `MemoryCandidate` | Scored candidate |
| `GardenBouquet` | Slotted candidates |
| `HarvestGardenBrief` | Layer-3 brief |
| `HarvestTrace` | Full pipeline trace |
| `RuntimeGardenHarvesterAdapter` | Bridges to Layer 2 HarvesterProtocol |

## Layer 4: Garden Observatory

`memory_garden.observatory`

| Entry Point | Description |
|---|---|
| `GardenObserver` | Observatory facade: observe_harvest, observe_journal, observe_runtime_turn |
| `ObservationTrace` | Full trace with spans, events, links |
| `ObservationView` | Redacted view (PUBLIC / SAFE / INTERNAL) |
| `RedactionLevel` | PUBLIC, SAFE, INTERNAL |

## Layer 5: Integration Layer

`memory_garden.integrations`

| Entry Point | Description |
|---|---|
| `SyncGardenChatAdapter` | Synchronous chat adapter |
| `AsyncGardenChatAdapter` | Asynchronous chat adapter |
| `ChatAgentProtocol` | Sync agent protocol |
| `AsyncChatAgentProtocol` | Async agent protocol |
| `GardenAdapterConfig` | Adapter configuration |
| `BriefInjectionMode` | none, context_argument, system_prefix, developer_message, metadata |
| `IntegrationResult` | Per-turn result |

## Layer 6: Garden Lab

`memory_garden.lab`

| Entry Point | Description |
|---|---|
| `LabCase` | Test case definition |
| `LabSuite` | Case suite |
| `LabAssertion` | Single assertion |
| `SnapshotLabRunner` | Case/suite runner |
| `evaluate_assertion` | Evaluate one assertion |
| `evaluate_case` | Evaluate all assertions in a case |
| `default_lab_suites` | 5 fixture suites |
| `format_lab_run_report` | Text report |

## Layer 7: Lab Cookbook

`memory_garden.lab`

| Entry Point | Description |
|---|---|
| `LabCatalog` | Suite/case metadata catalog |
| `load_cases_from_dicts` | JSON case loader |
| `smoke_pack` / `safety_pack` / `full_pack` | Suite pack selectors |
| `build_ci_report` | Compact CI report |
| `build_coverage_report` | Mechanism coverage analysis |
| `MemoryGardenContract` | Reusable rule templates |

## Layer 8: Garden Covenant

`memory_garden.covenant`

| Entry Point | Description |
|---|---|
| `GardenCovenant` | Policy configuration model |
| `PolicyEngine` | Read-only policy decision engine |
| `load_covenant` | Load from dict / YAML / env |
| `PolicyDecision` | Structured decision with reason |
| `audit_decisions` | In-memory audit helper |
| `covenant_hash` | Stable covenant hash |

## Configuration

`memory_garden.config`

| Entry Point | Description |
|---|---|
| `GardenConfig` | Top-level configuration |
