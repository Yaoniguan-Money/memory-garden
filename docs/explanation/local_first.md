# Why Local-First?

Memory Garden stores all data locally. There is no cloud backend, no telemetry, no API calls home.

## Rationale

### Privacy

Memory data is among the most sensitive data an AI system handles. Preferences, facts, emotional patterns, and behavioral signals should not live on a third-party server by default.

### Auditability

A local SQLite file can be inspected with standard tools. You can run `SELECT * FROM memory_cards` and see exactly what the system remembers. Cloud services may or may not provide equivalent access.

### Offline Operation

No network dependency means the memory layer works in air-gapped environments, during network outages, and on edge devices.

### Zero Trust

You don't need to trust a service provider with your users' memory data. The entire system runs in your process.

## Trade-offs

- **No cross-device sync**: If you need memory available on multiple devices, you must implement sync yourself.
- **No backup by default**: You are responsible for backing up the SQLite file.
- **No horizontal scaling**: The local SQLite store is single-writer. For high-throughput multi-user scenarios, you would need to swap in a different backend.
