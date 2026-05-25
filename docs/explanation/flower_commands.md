# Why 花花开 / 花花关?

Memory Garden uses Chinese phrases for session control commands: 花花开 (flower open) to start a session and 花花关 (flower close) to end one. English aliases exist but the canonical forms are Chinese.

## Rationale

### Unambiguous Boundary

"花花开" is unlikely to appear in normal conversation. It creates a clear, intentional signal that the user wants to start or end a memory session. English equivalents like "start session" or "begin" could appear in casual chat and trigger false positives.

### Exact Match Only

The command parser uses whole-string exact matching. "我觉得花花开很好看" does not trigger a session open. Only the bare phrase "花花开" does. This prevents accidental session boundaries.

### Never Memorized

Control commands are short-circuited before observation. The text "花花开" never becomes a Seed, never enters Court, never appears in a Garden Brief. This is enforced at the Runtime layer and verified by Lab regression cases.

### English Aliases

For English-speaking users, the following also work:

- `flower open` / `garden open` → session open
- `flower close` / `garden close` → session close

These are secondary; the canonical commands remain the Chinese forms.

## Cultural Note

The flower metaphor (花) runs through the entire project: seeds, planting, gardens. 花花开/花花关 extends this to the session boundary. It is not a localization gimmick; it reflects the project's design language.
