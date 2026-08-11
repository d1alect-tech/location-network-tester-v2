"""CSS-artifact contracts for hidden semantics and every runtime state class.

These assert the stylesheet deliverable that governs rendering (the same style
as ``test_ui_chart_contract``); the observable behaviour is proven separately by
the real-browser QA. They exist because the review found initially hidden panels
leaking and runtime-emitted classes with no CSS at all.
"""

import re
from pathlib import Path
from typing import Final

STATIC_DIR: Final = Path(__file__).resolve().parent.parent / "src/lnt/ui/static"
STYLES_PATH: Final = STATIC_DIR / "styles.css"
STATUS_VIEWS_PATH: Final = STATIC_DIR / "status-views.js"
SESSION_VIEWS_PATH: Final = STATIC_DIR / "session-views.js"


def _styles() -> str:
    return STYLES_PATH.read_text(encoding="utf-8")


def test_hidden_attribute_is_authoritative_over_component_display() -> None:
    # A global rule forces [hidden] to none so component display:grid/flex cannot
    # leak initially hidden panels (error banner, analysis states, charts).
    assert re.search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important;\s*\}", _styles())


def test_runtime_emitted_literal_classes_all_have_css() -> None:
    js = STATUS_VIEWS_PATH.read_text(encoding="utf-8") + SESSION_VIEWS_PATH.read_text(
        encoding="utf-8"
    )
    emitted = set(re.findall(r'"(is-[a-z]+|delta-[a-z]+)"', js))
    emitted |= set(re.findall(r'classList\.add\("(is-[a-z]+)"\)', js))
    required = {
        "is-current",
        "is-done",
        "is-failed",
        "delta-improved",
        "delta-worse",
        "delta-neutral",
    }
    assert required <= emitted, f"expected runtime classes not emitted: {required - emitted}"
    styles = _styles()
    missing = sorted(cls for cls in emitted if f".{cls}" not in styles)
    assert missing == [], f"runtime classes emitted without CSS: {missing}"


def test_measurement_rail_and_state_families_have_css() -> None:
    styles = _styles()
    for cls in (
        ".rail-ok",
        ".rail-warn",
        ".rail-error",
        ".rail-running",
        ".state-error",
        ".state-ok",
    ):
        assert cls in styles, f"missing rail/state CSS: {cls}"


def test_job_step_states_carry_a_non_color_glyph_cue() -> None:
    styles = _styles()
    for selector in (".is-current::before", ".is-done::before", ".is-failed::before"):
        assert selector in styles


def test_disabled_buttons_do_not_react_to_hover() -> None:
    styles = _styles()
    for variant in ("button-primary", "button-secondary", "button-danger-secondary"):
        assert f".{variant}:not(:disabled):hover" in styles


def test_checkbox_is_excluded_from_text_input_base_styling() -> None:
    assert 'input:not([type="checkbox"]):not([type="radio"])' in _styles()


def test_numeric_cells_use_tabular_lining_numerals() -> None:
    assert "font-variant-numeric: tabular-nums lining-nums" in _styles()


def test_touch_targets_meet_the_44px_contract() -> None:
    styles = _styles()
    nav = re.search(r"\.anchor-nav a \{[^}]*\}", styles)
    summary = re.search(r"details > summary \{[^}]*\}", styles)
    assert nav is not None
    assert summary is not None
    assert "min-block-size: var(--touch-target-min)" in nav.group(0)
    assert "min-block-size: var(--touch-target-min)" in summary.group(0)


def test_config_root_truncates_and_is_not_inside_the_nav() -> None:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    nav = html.split('class="anchor-nav"', maxsplit=1)[1].split("</nav>", maxsplit=1)[0]
    assert "config-root" not in nav, "session root must not live inside the scrollable nav"
    rule = re.search(r"\.config-root \{[^}]*\}", _styles())
    assert rule is not None
    assert "text-overflow: ellipsis" in rule.group(0)
    assert "white-space: nowrap" in rule.group(0)
