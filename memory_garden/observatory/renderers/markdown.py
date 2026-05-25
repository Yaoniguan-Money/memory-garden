"""Markdown report renderer for Observatory views.

Produces a readable, structured Markdown document that answers the
questions from the planning Layer 6: what does this garden contain,
what seeds were planted, what dreams ran, what's in the greenhouse?
"""

from __future__ import annotations

from memory_garden.observatory.views import (
    CourtroomView,
    DreamView,
    GardenMapData,
    GardenSummaryView,
    MemoryCardView,
    SeedJourneyView,
)


def render_garden_summary_markdown(view: GardenSummaryView) -> str:
    """Render a full GardenSummaryView as a Markdown document."""
    lines: list[str] = []
    _h1(lines, "Garden Observatory Report")
    lines.append(f"*Generated: {view.generated_at}*")
    lines.append("")

    _render_map(lines, view.map)
    _render_memories(lines, view.recent_memories)
    _render_seeds(lines, view.recent_seeds)
    _render_cases(lines, view.recent_cases)
    _render_dreams(lines, view.recent_dreams)

    return "\n".join(lines)


def render_garden_map_markdown(garden_map: GardenMapData) -> str:
    """Render a GardenMapData as a Markdown section."""
    lines: list[str] = []
    _render_map(lines, garden_map)
    return "\n".join(lines)


def render_memory_card_markdown(card: MemoryCardView) -> str:
    """Render a single MemoryCardView as Markdown."""
    lines: list[str] = []
    _h2(lines, f"Memory: {card.title or card.memory_id}")
    lines.append(f"- **ID**: `{_safe_id(card.memory_id)}`")
    lines.append(f"- **Type**: {card.memory_type}")
    lines.append(f"- **Lifecycle**: {card.lifecycle}")
    lines.append(f"- **Sensitivity**: {card.sensitivity}")
    lines.append(f"- **Confidence**: {card.confidence:.2f}")
    lines.append(f"- **Importance**: {card.importance:.2f}")
    if card.tags:
        lines.append(f"- **Tags**: {', '.join(card.tags)}")
    if card.essence:
        lines.append(f"- **Essence**: {card.essence}")
    if card.fragrance:
        lines.append(f"- **Fragrance**: {card.fragrance}")
    if card.thorns and card.thorns != "none":
        lines.append(f"- **Thorns**: {card.thorns}")
    if card.source_seed_ids:
        lines.append(f"- **Source Seeds**: {', '.join(f'`{_safe_id(s)}`' for s in card.source_seed_ids)}")
    if card.court_case_ids:
        lines.append(f"- **Court Cases**: {', '.join(f'`{_safe_id(c)}`' for c in card.court_case_ids)}")
    lines.append(f"- **Created**: {card.created_at}")
    lines.append(f"- **Events**: {card.related_event_count}")
    lines.append("")
    return "\n".join(lines)


def render_seed_journey_markdown(seed: SeedJourneyView) -> str:
    """Render a single SeedJourneyView as Markdown."""
    lines: list[str] = []
    _h2(lines, f"Seed Journey: {seed.seed_id}")
    lines.append(f"- **Status**: {seed.status}")
    lines.append(f"- **Signal**: {seed.signal_type}")
    if seed.source_excerpt:
        excerpt = seed.source_excerpt[:200] + ("…" if len(seed.source_excerpt) > 200 else "")
        lines.append(f"- **Excerpt**: {excerpt}")
    if seed.court_case_ids:
        lines.append(f"- **Court Cases**: {', '.join(f'`{_safe_id(c)}`' for c in seed.court_case_ids)}")
    if seed.verdict:
        lines.append(f"- **Verdict**: {seed.verdict}")
    if seed.resulting_memory_ids:
        lines.append(f"- **Resulting Memories**: {', '.join(f'`{m}`' for m in seed.resulting_memory_ids)}")
    lines.append(f"- **Events**: {seed.related_event_count}")
    lines.append("")
    return "\n".join(lines)


# ── Internal helpers ───────────────────────────────────────────────

def _safe_id(raw: str) -> str:
    """Strip backticks from IDs to prevent Markdown formatting breakage."""
    return str(raw).replace("`", "'")


def _h1(lines: list[str], text: str) -> None:
    lines.append(f"# {text}")
    lines.append("")


def _h2(lines: list[str], text: str) -> None:
    lines.append(f"## {text}")
    lines.append("")


def _h3(lines: list[str], text: str) -> None:
    lines.append(f"### {text}")
    lines.append("")


def _render_map(lines: list[str], m: GardenMapData) -> None:
    _h2(lines, "Garden Map")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Memory Cards | {m.memory_count} |")
    lines.append(f"| Seeds | {m.seed_count} |")
    lines.append(f"| Court Cases | {m.court_case_count} |")
    lines.append(f"| Dream Records | {m.dream_record_count} |")
    lines.append(f"| Greenhouse Records | {m.greenhouse_count} |")
    lines.append(f"| Compost Records | {m.compost_count} |")
    lines.append(f"| Pruning Records | {m.pruning_count} |")
    lines.append(f"| Garden Events | {m.event_count} |")
    lines.append("")

    if m.memory_by_lifecycle:
        _h3(lines, "Memories by Lifecycle")
        for lc, cnt in sorted(m.memory_by_lifecycle.items()):
            lines.append(f"- **{lc}**: {cnt}")
        lines.append("")

    if m.memory_by_type:
        _h3(lines, "Memories by Type")
        for mt, cnt in sorted(m.memory_by_type.items()):
            lines.append(f"- **{mt}**: {cnt}")
        lines.append("")

    if m.seed_by_status:
        _h3(lines, "Seeds by Status")
        for st, cnt in sorted(m.seed_by_status.items()):
            lines.append(f"- **{st}**: {cnt}")
        lines.append("")

    if m.top_tags:
        _h3(lines, "Top Tags")
        for tag, cnt in m.top_tags[:10]:
            lines.append(f"- **{tag}**: {cnt}")
        lines.append("")


def _render_memories(lines: list[str], memories: list[MemoryCardView]) -> None:
    if not memories:
        return
    _h2(lines, "Recent Memories")
    for card in memories[:10]:
        lines.append(f"- **{card.title or card.memory_id}** ({card.lifecycle}) — {card.essence[:120] if card.essence else '(no essence)'}")
    lines.append("")


def _render_seeds(lines: list[str], seeds: list[SeedJourneyView]) -> None:
    if not seeds:
        return
    _h2(lines, "Recent Seeds")
    for seed in seeds[:10]:
        lines.append(f"- **{seed.seed_id}** ({seed.status}, {seed.signal_type}) — {seed.source_excerpt[:100] if seed.source_excerpt else '(no excerpt)'}")
    lines.append("")


def _render_cases(lines: list[str], cases: list[CourtroomView]) -> None:
    if not cases:
        return
    _h2(lines, "Recent Court Cases")
    for case in cases[:10]:
        lines.append(f"- **{case.court_case_id}** → {case.judge_verdict} ({case.verdict_reason[:80]})")
    lines.append("")


def _render_dreams(lines: list[str], dreams: list[DreamView]) -> None:
    if not dreams:
        return
    _h2(lines, "Recent Dreams")
    for dream in dreams[:10]:
        lines.append(f"- **{dream.dream_record_id}** — {dream.observation[:100] if dream.observation else '(no observation)'}")
    lines.append("")
