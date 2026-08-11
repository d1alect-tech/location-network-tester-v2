import re
from pathlib import Path
from typing import Final

STATIC_DIR: Final = Path(__file__).resolve().parent.parent / "src/lnt/ui/static"
INDEX_PATH: Final = STATIC_DIR / "index.html"
SHOWCASE_PATH: Final = STATIC_DIR / "showcase.html"
STYLES_PATH: Final = STATIC_DIR / "styles.css"


def _tag_for_id(markup: str, element_id: str) -> str:
    match = re.search(rf'<[^>]+\bid="{re.escape(element_id)}"[^>]*>', markup)
    assert match is not None
    return match.group(0)


def _theme(markup: str, name: str) -> str:
    match = re.search(
        rf'<section class="theme-preview" data-theme="{name}"[^>]*>(?P<body>.*?)</section>',
        markup,
        re.DOTALL,
    )
    assert match is not None
    return match.group("body")


def test_header_exposes_short_name_and_full_accessible_name() -> None:
    html = INDEX_PATH.read_text(encoding="utf-8")
    heading = re.search(r"<h1(?P<attributes>[^>]*)>(?P<text>[^<]+)</h1>", html)
    assert heading is not None
    assert heading.group("text").strip() == "LNT"
    assert 'aria-label="Location Network Tester"' in heading.group("attributes")
    assert 'title="Location Network Tester"' in heading.group("attributes")


def test_capture_action_precedes_disclosure_and_joins_desktop_settings() -> None:
    html = INDEX_PATH.read_text(encoding="utf-8")
    styles = STYLES_PATH.read_text(encoding="utf-8")
    form = html.split('id="capture-form"', maxsplit=1)[1].split("</form>", maxsplit=1)[0]
    assert form.index('class="form-actions') < form.index('id="capture-advanced"')
    assert 'class="field capture-label"' in form
    tablet, desktop = styles.split("@media (min-width: 768px)", maxsplit=1)[1].split(
        "@media (min-width: 1280px)", maxsplit=1
    )
    assert "#capture-form .form-actions .button { inline-size: 100%; }" in tablet
    for contract in (
        "#capture-form { grid-template-columns: repeat(6, minmax(0, 1fr)); }",
        "#capture-form > .field { grid-column: span 2; }",
        "#capture-form > .field-wide { grid-column: 1 / -1; }",
        "#capture-form > .capture-label { grid-column: span 3; }",
        "#capture-form > .form-actions { grid-column: span 3; }",
        "#capture-advanced { grid-column: 1 / -1; }",
    ):
        assert contract in desktop


def test_showcase_error_controls_have_unique_descriptions() -> None:
    html = SHOWCASE_PATH.read_text(encoding="utf-8")
    described_ids: list[str] = []
    for theme_name in ("light", "dark"):
        preview = _theme(html, theme_name)
        text_tag = _tag_for_id(preview, f"{theme_name}-text-error")
        select_tag = _tag_for_id(preview, f"{theme_name}-select-error")
        assert 'data-state="error"' in select_tag
        for control in (text_tag, select_tag):
            assert 'aria-invalid="true"' in control
            describedby = re.search(r'aria-describedby="(?P<id>[^"]+)"', control)
            assert describedby is not None
            error_id = describedby.group("id")
            described_ids.append(error_id)
            assert preview.count(f'id="{error_id}"') == 1
    assert len(described_ids) == len(set(described_ids))


def test_showcase_state_fixtures_and_groups_are_semantic() -> None:
    html = SHOWCASE_PATH.read_text(encoding="utf-8")
    styles = STYLES_PATH.read_text(encoding="utf-8")
    assert '<span class="state-caption">' not in html
    assert ".state-fixture {" in styles
    for theme_name in ("light", "dark"):
        preview = _theme(html, theme_name)
        figures = re.findall(r'<figure class="state-fixture">(.*?)</figure>', preview, re.DOTALL)
        assert len(figures) == 26
        assert all(figure.count('<figcaption class="state-caption">') == 1 for figure in figures)
        groups = re.findall(
            r'<div class="primitive-group" role="group" aria-labelledby="([^"]+)">(.*?)</div>',
            preview,
            re.DOTALL,
        )
        assert len(groups) == 9
        for heading_id, body in groups:
            assert f'<h3 id="{heading_id}">' in body
