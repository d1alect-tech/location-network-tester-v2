import re
from pathlib import Path
from typing import Final

STATIC_DIR: Final = Path(__file__).resolve().parent.parent / "src/lnt/ui/static"
INDEX_PATH: Final = STATIC_DIR / "index.html"
STYLES_PATH: Final = STATIC_DIR / "styles.css"
VIEW_MODULES: Final = {
    "view-dom.js": frozenset(),
    "ch1-input-reference.js": frozenset(),
    "line-quality-views.js": frozenset({"./view-dom.js"}),
    "uplot-chart.js": frozenset({"./vendor/uPlot.esm.js"}),
    "chart-views.js": frozenset({"./uplot-chart.js", "./view-dom.js"}),
    "session-views.js": frozenset(
        {
            "./chart-views.js",
            "./ch1-input-reference.js",
            "./line-quality-views.js",
            "./view-dom.js",
        }
    ),
    "status-views.js": frozenset({"./view-dom.js"}),
    "views.js": frozenset({"./chart-views.js", "./session-views.js", "./status-views.js"}),
}
FACADE_EXPORTS: Final = frozenset(
    {
        "plotSpectrum",
        "plotWaveform",
        "renderCompare",
        "renderDeviceStatus",
        "renderError",
        "renderJobProgress",
        "renderSelftest",
        "renderSessionDetail",
        "renderSessions",
    }
)


def _tag(markup: str, element_id: str) -> str:
    match = re.search(rf'<[^>]+\bid="{re.escape(element_id)}"[^>]*>', markup)
    assert match is not None, f"missing #{element_id}"
    return match.group(0)


def _rule(styles: str, selector: str) -> str:
    match = re.search(rf"(?:^|\}})\s*{re.escape(selector)}\s*\{{(?P<body>[^}}]+)\}}", styles)
    assert match is not None, f"missing CSS rule for {selector}"
    return match.group("body")


def _imports(source: str) -> frozenset[str]:
    return frozenset(re.findall(r'from\s+["\'](?P<path>\./[^"\']+)["\']', source))


def test_view_modules_are_acyclic_and_within_size_budget() -> None:
    for filename, expected_imports in VIEW_MODULES.items():
        path = STATIC_DIR / filename
        assert path.is_file(), f"missing view module: {path}"
        source = path.read_text(encoding="utf-8")
        pure_loc = sum(
            bool(line.strip()) and not line.lstrip().startswith("//")
            for line in source.splitlines()
        )
        assert pure_loc <= 250, f"{filename} has {pure_loc} pure LOC"
        assert _imports(source) == expected_imports


def test_views_is_a_nine_name_reexport_facade() -> None:
    source = (STATIC_DIR / "views.js").read_text(encoding="utf-8")
    groups = re.findall(r"export\s*\{(?P<names>[^}]+)\}\s*from", source, re.DOTALL)
    exports = {
        name.strip().split(" as ")[-1]
        for group in groups
        for name in group.split(",")
        if name.strip()
    }
    assert exports == FACADE_EXPORTS
    assert "function " not in source
    assert "const " not in source


def test_static_chart_shells_have_named_figures_and_sibling_statuses() -> None:
    html = INDEX_PATH.read_text(encoding="utf-8")
    assert 'role="img"' not in html
    for name, caption, hidden in (
        ("spectrum", "Логарифмический спектр мощности выбранной сессии", False),
        ("waveform", "Превью осциллограммы выбранной сессии", True),
    ):
        block = _tag(html, f"{name}-chart")
        figure = _tag(html, f"{name}-figure")
        target = _tag(html, f"{name}-plot")
        status = _tag(html, f"{name}-status")
        assert all(value in block for value in ('class="chart-block"', 'role="region"'))
        assert f'aria-labelledby="{name}-caption"' in block
        assert all(
            value in figure
            for value in ('class="chart-figure"', f'aria-labelledby="{name}-caption"')
        )
        assert all(
            value in target
            for value in (
                'aria-busy="false"',
                'data-chart-state="idle"',
                f'aria-describedby="{name}-status"',
            )
        )
        assert all(
            value in status
            for value in (
                'class="chart-status"',
                'role="status"',
                'aria-live="polite"',
                'aria-atomic="true"',
            )
        )
        caption_markup = (
            f'<figcaption id="{name}-caption" class="visually-hidden">{caption}</figcaption>'
        )
        figure_body = html.split(figure, maxsplit=1)[1].split("</figure>", maxsplit=1)[0]
        assert caption_markup in figure_body
        assert f'id="{name}-status"' not in figure_body
        assert (" hidden" in block) is hidden
        assert (" hidden" in figure) is hidden
        assert (" hidden" in target) is hidden


def test_dynamic_session_charts_use_the_shared_shell_without_image_roles() -> None:
    source = (STATIC_DIR / "session-views.js").read_text(encoding="utf-8")
    assert source.count("createChartShell({") == 2
    assert re.search(r'createChartShell\(\{\s*name:\s*"spectrum"', source)
    waveform = source.split('name: "waveform"', maxsplit=1)[1]
    assert "hidden: true" in waveform.split("});", maxsplit=1)[0]
    assert 'role = "img"' not in source
    assert 'setAttribute("role", "img")' not in source


def test_chart_shell_styles_are_token_based_and_preserve_plot_sizes() -> None:
    styles = STYLES_PATH.read_text(encoding="utf-8")
    for selector in (".chart-block", ".chart-figure"):
        rule = _rule(styles, selector)
        assert "display: grid" in rule
        assert "gap: var(--space-2)" in rule
        assert "min-inline-size: var(--space-0)" in rule
    assert "margin: var(--space-0)" in _rule(styles, ".chart-figure")
    assert "min-block-size: var(--line-body)" in _rule(styles, ".chart-status")
    assert "position: absolute" in _rule(styles, ".visually-hidden")
    assert "block-size: var(--chart-height-mobile)" in _rule(styles, ".plot-spectrum")
    assert "block-size: var(--waveform-height)" in _rule(styles, ".plot-waveform")
