"""Безопасный самодостаточный offline HTML report renderer."""

from html import escape
from typing import Final

from lnt.reporting.models import PlaneKind, PlaneReport, ReportSchema1

_PLANE_LABELS: Final = {
    PlaneKind.SOURCE: "Исходная плоскость",
    PlaneKind.SECONDARY: "Вторичная плоскость",
    PlaneKind.PRIMARY: "Первичная плоскость",
}
_REASON_LABELS: Final = {
    "self_noise_baseline_missing": "нет базовой сессии самошума",
    "manifest_schema_v1": "манифест не содержит квалифицированной установки CH1",
    "measurement_ch1_setup_mismatch": "установка CH1 не поддерживает приведение",
}


def _e(value: str | float | None) -> str:
    return escape("" if value is None else str(value), quote=True)


def _plane(plane: PlaneReport) -> str:
    label = _PLANE_LABELS[plane.kind]
    if not plane.available:
        reason = _REASON_LABELS.get(plane.reason_code or "", plane.reason_code or "неизвестно")
        return "".join(
            (
                f'<section class="plane"><h3>{_e(label)}</h3>',
                f'<p class="unavailable">{_e(label.lower())} недоступна: {_e(reason)}</p>',
                "</section>",
            )
        )
    rows = "".join(
        "".join(
            (
                "<tr>",
                f"<td>{index}</td><td>{_e(value.mean_effect)}</td>",
                f"<td>{_e(plane.unit)}</td><td>{_e(plane.estimator)}</td>",
                f"<td>{_e(plane.n)}</td></tr>",
            )
        )
        for index, value in enumerate(plane.values, start=1)
    )
    return "".join(
        (
            f'<section class="plane"><h3>{_e(label)}</h3>',
            f"<p>Сессия {_e(plane.session_id)}, участник {_e(plane.member_id)}.</p>",
            "<table><thead><tr><th>№</th><th>Значение</th><th>Единица</th>",
            f"<th>Оцениватель</th><th>N</th></tr></thead><tbody>{rows}</tbody></table>",
            "</section>",
        )
    )


def render_html(report: ReportSchema1) -> str:
    """Рендерит escaped HTML без сценариев и внешних ресурсов."""
    exclusions = [item for item in report.qc_exclusions if item.state.value == "excluded"]
    exclusion_html = (
        "<p>исключений нет</p>"
        if not exclusions
        else "<ul>"
        + "".join(f"<li>{_e(item.member_id)} — {_e(item.reason)}</li>" for item in exclusions)
        + "</ul>"
    )
    notes = "".join(f"<li>{_e(note)}</li>" for note in report.setup_context.notes)
    limitations = "".join(
        f"<li><code>{_e(item.code)}</code>: {_e(item.detail)}</li>" for item in report.limitations
    )
    hypotheses = "".join(
        f"<li>{_e(item.hypothesis_id)} — {_e(item.status_label)} ({_e(item.status)})</li>"
        for item in report.linked_hypotheses
    )
    recipes = "".join(
        f"<li>{_e(item.session_id)} / {_e(item.artifact_key)} / {_e(item.recipe_sha256)}</li>"
        for item in report.recipes_used
    )
    planes = "".join(_plane(plane) for plane in report.planes)
    confounds = _e(", ".join(report.drift_confounds.confound_columns))
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Научный отчёт LNT</title>
<style>
:root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
body {{ max-width: 1100px; margin: 0 auto; padding: 2rem; color: #17202a; }}
h1,h2,h3 {{ break-after: avoid; }} section {{ margin: 1.5rem 0; }}
table {{ border-collapse: collapse; width: 100%; }}
th,td {{ border: 1px solid #899; padding: .4rem; }}
th {{ background: #eef3f5; text-align: left; }} code {{ overflow-wrap: anywhere; }}
.unavailable {{ border-left: .3rem solid #a44; padding-left: .7rem; }}
@media print {{ body {{ max-width: none; padding: 0; }} section,table {{ break-inside: avoid; }} }}
</style></head><body>
<header><h1>Научный отчёт</h1>
<p>Этот отчёт для личного анализа. Schema {_e(report.schema_version)}.
Это описание наблюдений без причинных выводов.</p></header>
<section><h2>Происхождение</h2>
<p>Эксперимент: {_e(report.provenance.experiment_id)};
код: {_e(report.provenance.code_identity)};
создано: {_e(report.provenance.created_at)}.</p></section>
<section><h2>Установка и контекст</h2>
<p>CH1: {_e(report.setup_context.ch1_setup)};
профиль: {_e(report.setup_context.profile)}.</p><ul>{notes}</ul></section>
<section><h2>QC и исключения</h2><p>Решения T30 сохраняются с причинами.</p>
<h3>Исключения</h3>{exclusion_html}</section>
<section><h2>Использованные рецепты</h2><ul>{recipes}</ul></section>
<section><h2>Измерительные плоскости</h2>
<p>Сырые, вторичные и приведённые ко входу величины не смешиваются.</p>
{planes}</section>
<section><h2>Дрейф и смешивающие факторы</h2>
<p>{_e(report.drift_confounds.aba_label)};
дрейф: {_e(report.drift_confounds.drift_value)} {_e(report.drift_confounds.drift_unit)};
колонки: {confounds}.</p></section>
<section><h2>Кандидаты событий</h2><p>Сводка T23 описывает кандидаты, а не причины.</p></section>
<section><h2>Ограничения</h2><ul>{limitations}</ul></section>
<section><h2>Связанные гипотезы</h2><ul>{hypotheses}</ul></section>
</body></html>\n"""
