# Versioning

## Scheme

Memory Garden uses `vMAJOR.MINOR-layer-name` tags:

```
v0.2.0-garden-runtime
v0.3.0-harvest-pipeline
v0.4.0-garden-observatory
v0.5.0-integration-layer
v0.6.0-garden-lab
v0.7.0-lab-cookbook
v0.8.0-garden-covenant
v0.9.0-manual-nursery
```

The version in `pyproject.toml` tracks the current development version.

## When to Bump

- **Minor bump** (0.X.0): A new layer is added and frozen. Each layer gets its own minor version.
- **Patch bump** (0.X.Y, Y>0): Bug fixes, documentation improvements, or test additions within an existing layer.
- **Major bump** (1.0.0): Not yet reached. Reserved for when the core API is considered stable.

## Pre-1.0

Before 1.0, all APIs are subject to change. Backward compatibility is a goal but not a guarantee. Breaking changes will be noted in the CHANGELOG.

## Tag Format

Tags use the format: `v{major}.{minor}.{patch}-{short-descriptor}`

The short descriptor is a human-readable name for the layer or milestone. It is not used for version comparison.
