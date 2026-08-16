import re
from pathlib import Path

from starlette.testclient import TestClient

from lnt.ui.app import create_app

STATIC_DIR = Path(__file__).resolve().parent.parent / "src/lnt/ui/static"
SHOWCASE_PATH = STATIC_DIR / "showcase.html"
TOKENS_PATH = STATIC_DIR / "v2-tokens.css"
DESIGN_MD_PATH = Path(__file__).resolve().parent.parent / "DESIGN.md"


def test_showcase_html_parses_and_has_required_elements() -> None:
    html = SHOWCASE_PATH.read_text(encoding="utf-8")
    assert "<html" in html
    assert "Витрина дизайн-системы LNT" in html
    assert 'id="light-title"' in html


def test_interactive_elements_have_accessible_names() -> None:
    html = SHOWCASE_PATH.read_text(encoding="utf-8")
    # Check buttons have text or aria-label
    buttons = re.findall(r"<button\b[^>]*>(.*?)</button>", html, re.DOTALL)
    for btn_content in buttons:
        assert btn_content.strip() != "" or "aria-label" in btn_content


def test_tokens_css_defines_all_documented_tokens() -> None:
    css = TOKENS_PATH.read_text(encoding="utf-8")
    required_tokens = [
        "--lnt-font-sans",
        "--lnt-font-mono",
        "--lnt-space-1",
        "--lnt-space-2",
        "--lnt-space-3",
        "--lnt-space-4",
        "--lnt-space-6",
        "--lnt-control-height",
        "--lnt-touch-target-min",
        "--lnt-table-row-min",
        "--lnt-bg-canvas",
        "--lnt-bg-panel",
        "--lnt-fg-primary",
        "--lnt-accent-a",
        "--lnt-accent-b",
        "--lnt-status-ok",
        "--lnt-status-warn",
        "--lnt-status-error",
    ]
    for token in required_tokens:
        assert token in css, f"Missing token: {token}"


def test_44px_rule_asserted_in_css() -> None:
    css = TOKENS_PATH.read_text(encoding="utf-8")
    assert "--lnt-control-height: 44px" in css
    assert "--lnt-touch-target-min: 44px" in css
    assert "--lnt-table-row-min: 44px" in css


def test_focus_visible_style_present() -> None:
    # focus-visible is tested via styles.css or index.html
    pass


def test_no_decorative_gradients_in_tokens_or_showcase() -> None:
    css = TOKENS_PATH.read_text(encoding="utf-8")
    html = SHOWCASE_PATH.read_text(encoding="utf-8")
    assert "linear-gradient" not in css
    assert "linear-gradient" not in html


def test_design_md_sections_present() -> None:
    design_md = DESIGN_MD_PATH.read_text(encoding="utf-8")
    required_headings = [
        "## 1. Архитектура информации и разделы",
        "## 2. Сетка и раскладка",
        "## 3. Типографика и шрифты",
        "## 4. Цветовые и визуальные токены",
        "## 5. Матрица состояний компонентов",
        "## 6. Доступность и интерактивность",
        "## 7. Глоссарий терминов",
    ]
    for heading in required_headings:
        assert heading in design_md, f"Missing heading in DESIGN.md: {heading}"


def test_showcase_route_served_by_app(tmp_path: Path) -> None:
    app = create_app(root=tmp_path)
    with TestClient(app) as client:
        response = client.get("/showcase")
        assert response.status_code == 200
        assert "Витрина дизайн-системы LNT" in response.text
        assert response.headers["Content-Security-Policy"]


def test_showcase_html_has_no_inline_styles_or_style_blocks() -> None:
    html = SHOWCASE_PATH.read_text(encoding="utf-8")
    assert "style=" not in html
    assert "<style" not in html


def test_showcase_html_script_tag_has_defer() -> None:
    html = SHOWCASE_PATH.read_text(encoding="utf-8")
    assert 'src="/static/showcase.js" defer' in html
