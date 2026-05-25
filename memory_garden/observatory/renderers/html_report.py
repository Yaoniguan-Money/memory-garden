"""Static HTML report renderer — self-contained, zero-dependency.

Produces a single HTML file that opens in any browser with no network
access required.  CSS is inlined.  No JavaScript beyond optional
collapsible sections.

Design source: planning Layer 6, Section 7 "Static HTML Report".
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

_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #1a1a2e; background: #f8f9fa; }
h1 { color: #2d6a4f; border-bottom: 3px solid #40916c; padding-bottom: .5rem; }
h2 { color: #40916c; margin-top: 2rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { padding: .5rem .75rem; text-align: left; border-bottom: 1px solid #dee2e6; }
th { background: #d8f3dc; color: #1b4332; }
.card { background: white; border-radius: 8px; padding: 1rem; margin: .75rem 0;
        box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.card-title { font-weight: 600; color: #2d6a4f; }
.tag { display: inline-block; background: #d8f3dc; color: #1b4332; padding: .15rem .5rem;
       border-radius: 4px; font-size: .8rem; margin: .15rem; }
.meta { color: #6c757d; font-size: .85rem; }
.verdict-plant { color: #2d6a4f; }
.verdict-compost { color: #b5651d; }
.verdict-greenhouse { color: #1d70b8; }
.verdict-hold { color: #6c757d; }
.verdict-forget { color: #d4351c; }
.section-count { font-size: .85rem; color: #6c757d; margin-left: .5rem; }
.footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #dee2e6;
          font-size: .8rem; color: #6c757d; }
"""


def render_html_report(view: GardenSummaryView, title: str = "Garden Observatory Report") -> str:
    """Render a full observatory summary as a self-contained HTML document."""
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head><meta charset='utf-8'>")
    parts.append(f"<title>{_esc(title)}</title>")
    parts.append(f"<style>{_CSS}</style>")
    parts.append("</head><body>")
    parts.append(f"<h1>{_esc(title)}</h1>")
    parts.append(f"<p class='meta'>Generated: {_esc(view.generated_at)}</p>")

    _render_map_html(parts, view.map)
    _render_memories_html(parts, view.recent_memories)
    _render_seeds_html(parts, view.recent_seeds)
    _render_cases_html(parts, view.recent_cases)
    _render_dreams_html(parts, view.recent_dreams)

    parts.append("<div class='footer'>Memory Garden Observatory Report</div>")
    parts.append("</body></html>")
    return "\n".join(parts)


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


def _render_map_html(parts: list[str], m: GardenMapData) -> None:
    parts.append("<h2>Garden Map</h2>")
    parts.append("<table>")
    rows = [
        ("Memory Cards", m.memory_count), ("Seeds", m.seed_count),
        ("Court Cases", m.court_case_count), ("Dream Records", m.dream_record_count),
        ("Greenhouse Records", m.greenhouse_count), ("Compost Records", m.compost_count),
        ("Pruning Records", m.pruning_count), ("Garden Events", m.event_count),
    ]
    for label, val in rows:
        parts.append(f"<tr><td>{label}</td><td><strong>{val}</strong></td></tr>")
    parts.append("</table>")

    if m.memory_by_lifecycle:
        parts.append("<h3>By Lifecycle</h3><table>")
        for lc, cnt in sorted(m.memory_by_lifecycle.items()):
            parts.append(f"<tr><td>{_esc(lc)}</td><td>{cnt}</td></tr>")
        parts.append("</table>")

    if m.memory_by_type:
        parts.append("<h3>By Type</h3><table>")
        for mt, cnt in sorted(m.memory_by_type.items()):
            parts.append(f"<tr><td>{_esc(mt)}</td><td>{cnt}</td></tr>")
        parts.append("</table>")


def _render_memories_html(parts: list[str], memories: list[MemoryCardView]) -> None:
    parts.append(f"<h2>Recent Memories<span class='section-count'>{len(memories)}</span></h2>")
    for card in memories[:20]:
        parts.append("<div class='card'>")
        parts.append(f"<div class='card-title'>{_esc(card.title or card.memory_id)}</div>")
        parts.append(f"<span class='tag'>{_esc(card.lifecycle)}</span> ")
        parts.append(f"<span class='tag'>{_esc(card.memory_type)}</span>")
        if card.tags:
            for t in card.tags[:8]:
                parts.append(f"<span class='tag'>{_esc(t)}</span>")
        if card.essence:
            parts.append(f"<p>{_esc(card.essence[:300])}</p>")
        parts.append(f"<span class='meta'>ID: {_esc(card.memory_id)} | Created: {_esc(card.created_at)} | Events: {card.related_event_count}</span>")
        parts.append("</div>")


def _render_seeds_html(parts: list[str], seeds: list[SeedJourneyView]) -> None:
    parts.append(f"<h2>Recent Seeds<span class='section-count'>{len(seeds)}</span></h2>")
    for seed in seeds[:20]:
        parts.append("<div class='card'>")
        parts.append(f"<div class='card-title'>{_esc(seed.seed_id)}</div>")
        parts.append(f"<span class='tag'>{_esc(seed.status)}</span> ")
        parts.append(f"<span class='tag'>{_esc(seed.signal_type)}</span>")
        if seed.source_excerpt:
            parts.append(f"<p>{_esc(seed.source_excerpt[:200])}</p>")
        parts.append(f"<span class='meta'>Created: {_esc(seed.created_at)} | Events: {seed.related_event_count}</span>")
        parts.append("</div>")


def _render_cases_html(parts: list[str], cases: list[CourtroomView]) -> None:
    parts.append(f"<h2>Recent Court Cases<span class='section-count'>{len(cases)}</span></h2>")
    for case in cases[:20]:
        verdict_class = f"verdict-{case.judge_verdict}" if case.judge_verdict else ""
        parts.append("<div class='card'>")
        parts.append(f"<div class='card-title'>{_esc(case.court_case_id)}")
        parts.append(f" → <span class='{verdict_class}'>{_esc(case.judge_verdict)}</span></div>")
        if case.verdict_reason:
            parts.append(f"<p>{_esc(case.verdict_reason[:200])}</p>")
        parts.append(f"<span class='meta'>Seed: {_esc(case.seed_id)} | Created: {_esc(case.created_at)}</span>")
        parts.append("</div>")


def _render_dreams_html(parts: list[str], dreams: list[DreamView]) -> None:
    parts.append(f"<h2>Recent Dreams<span class='section-count'>{len(dreams)}</span></h2>")
    for dream in dreams[:10]:
        parts.append("<div class='card'>")
        parts.append(f"<div class='card-title'>{_esc(dream.dream_record_id)}</div>")
        if dream.observation:
            parts.append(f"<p><strong>Observation:</strong> {_esc(dream.observation[:200])}</p>")
        if dream.reflection:
            parts.append(f"<p><strong>Reflection:</strong> {_esc(dream.reflection[:200])}</p>")
        parts.append(f"<span class='meta'>Created: {_esc(dream.created_at)}</span>")
        parts.append("</div>")
