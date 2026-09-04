# LNT — Roadmap улучшений (brainstorm 2026-09-04)

Источник: 3 explore-разведки (архитектура / UX / домен), master @ `93c83d4`.
Порядок: всё по очереди A → B → C. Мобильная вёрстка inspect (375px) — **вычеркнута** решением владельца.

## Очередь A — Quick wins (S, дни)

| # | Что | Статус |
|---|-----|--------|
| A1 | Пустые/loading/error-состояния + retry (Experiments/Reports/Capture-timeline, скелетон спектра, CTA «Пересчитать анализ») | TODO |
| A2 | A11y-унификация табов (WAI-ARIA один паттерн), aria-live readout/scale/statusbar, label-for в командбаре | TODO |
| A3 | Мёртвый маршрут «Подготовка»: убить или реализовать; вернуть theme-переключатель в inspect | DONE (shell-a3: prepare убит + legacy-алиас на capture; таббар унифицирован is-active + aria-current, inspect под общей шапкой без is-inspect-v6) |
| A4 | Единый источник `CLI_SUBCOMMANDS` (генерация из парсера) + `scripts/pin_vendor.py` для золотых пинов | TODO |

## Очередь B — Приборные фичи (M, 1–2 недели)

| # | Что | Статус |
|---|-----|--------|
| B1 | RBW-селектор 10/30/50/100/300 Гц + окна Hann/Flattop/Kaiser + ENBW-поправки в manual | TODO |
| B2 | Trace-детекторы Average/Max-Hold/Min-Hold + межсессионное усреднение повторов | TODO |
| B3 | Маркеры Peak/Delta/Band-power/Harmonic + readout с интерполяцией | TODO |
| B4 | Limit-lines / Mask Pass-Fail редактор (SEMI-F47 + пользовательские маски PSD/трендов) | TODO |

## Очередь C — Тяжёлая артиллерия (L, квартал)

| # | Что | Статус |
|---|-----|--------|
| C1 | Честный командбар inspect (deep-link билет в capture / мини-префлайт + живой device-статус) | TODO |
| C2 | Единый мок-бэкенд фронта (один `MockLntBackend`, golden из `tests/science/corpus.py`) | TODO |
| C3 | Калибровки: ADC cal + probe/RC swept-FR + de-embedding + dBV/dBuV/dBm | TODO |
| C4 | Расслоение `_GRANDFATHERED`-модулей + граница v1/v2 анализ-трактов | TODO |

## Дисциплина исполнения (каждый пункт)

TDD RED→GREEN, модуль ≤250 чистых LOC, frozen `frontend/src/showcase-round2/` не трогать,
гейты `pytest` + `tsc` + e2e + module-size + reviewer APPROVE. Трекинг — GitHub Issues (`gh`).
