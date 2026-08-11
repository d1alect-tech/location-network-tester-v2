# Отчёт о восстановлении проекта LNT

Дата: 05.08.2026. Источник: `D:\Repair1\RecoveredData` (два прохода восстановления
одного повреждённого диска). Оригинальный путь проекта на старом диске:
`Users\Kirill\Documents\WindowsOptimizations\InputLag\trusted\fable5-inputlag\output\projects\location-network-tester`.

## Использованные источники

1. Основная копия проекта (Documents) — оба раздела повреждены идентично.
2. Кэш uv (`AppData\Local\uv\cache\archive-v0\*\lnt`) — 6 копий установленного
   пакета `lnt`; повреждения в других кластерах, что позволило собрать многие
   файлы «по кусочкам» (chunk-merge по 4 КБ кластерам).
3. `fonts/manifest.json` (цел) — sha256-хэши для перекачки шрифтов из npm.
4. Дизассемблированный байткод `__pycache__/*.pyc` (для `selftest.py`).
5. Уцелевшие контрактные тесты и модули-потребители (для реконструкции).

ВНИМАНИЕ: каталоги `LostFiles\test_*` на восстановленном диске содержат
подставные файлы-заглушки (57–76 байт, только путь внутри) — это артефакты
тестового стенда, НЕ реальные данные.

## Статус файлов

### Восстановлено байт-в-байт (из копий кэша uv / merge)
- `src/lnt/*.py` — все модули ядра, кроме перечисленных ниже
- `src/lnt/ui/*.py` — app, dependencies, device, job_worker, launcher, models,
  operations, payloads, routes_jobs, routes_sessions, sessions
- `src/lnt/ui/static/*.js` — все JS-модули, showcase.html, favicon, plotly vendor
- Шрифты `*.woff2` — перекачаны из npm по манифесту, sha256 совпали 1:1

### Реконструировано (функционально эквивалентно, проверено тестами)
- `src/lnt/selftest.py` — 1:1 по дизассемблированному байткоду (.pyc был цел)
- `src/lnt/_manifest_schema.py` — голова (~4 КБ) реконструирована по контрактным
  тестам; хвост оригинальный
- `src/lnt/ui/job_state.py` — полностью реконструирован по test_ui_job_state.py
  и потребителям
- `src/lnt/ui/jobs.py`, `src/lnt/ui/decimation.py` — головы (~4 КБ)
  реконструированы; хвосты оригинальные
- `src/lnt/ui/models.py` — голова (~4 КБ) реконструирована; хвост оригинальный.
  ВНИМАНИЕ: в части копий кластеры были перезаписаны ЧУЖИМИ данными без
  нулевых байтов (кэш браузера, локализации Steam) — такие файлы выглядят
  «целыми» по нулям, но содержат мусор; выявлено проверкой синтаксиса
- `src/lnt/ui/static/index.html`, `styles.css` — первые 8 КБ реконструированы
  по тестам, JS-модулям и уцелевшим хвостам; хвосты оригинальные
- `src/lnt/ui/static/showcase.html` — первые 12 КБ утрачены; шапка и светлая
  секция реконструированы зеркалированием уцелевшей тёмной секции
- `scripts/vendor_ibm_plex.py` — хвост (~40 строк) реконструирован
- `uv.lock` — регенерирован (`uv lock`) из pyproject.toml

### Частично утрачено (текст, невосстановимо — битые сектора во всех копиях)
- `README.md` — первые ~3,5 КБ утрачены; остальное извлечено из METADATA
  wheel-пакета (помечено в файле)
- `DESIGN.md` — первые ~4 КБ утрачены (помечено в файле)

### Утрачено: тесты (в `_recovery/corrupted_tests/`, суффикс `.corrupted`)
Полностью: test_module_size, test_needles, test_selftest, test_series,
test_spectrum, test_ui_dependencies, test_ui_font_assets, test_ui_frontend_api,
test_ui_frontend_controller, test_ui_jobs, test_ui_js_module_size,
test_ui_launcher, test_ui_models, test_ui_operations, test_ui_payloads,
test_ui_sessions, tests/js: job-controller, session-filter, session-search.
Частично (уцелевшие куски внутри): test_cli (хвост 4,2 КБ), test_simulate,
test_ui_job_routes (хвост 1,1 КБ).
Функциональность, которую они покрывали, работает (проверено вручную и
уцелевшими тестами); сами тесты при желании можно написать заново.

## Верификация (05.08.2026)
- pytest: **193 passed** (все уцелевшие тесты).
- node --test tests/js: **28 passed**.
- ruff check по всем реконструированным модулям: чисто.
- CLI E2E: `lnt simulate` → `lnt analyze` → `lnt compare` → `lnt selftest` — OK.
- UI E2E в реальном браузере (Playwright): страница, светлая/тёмная темы,
  список сессий, детальный анализ, Plotly-спектр и осциллограмма, запуск
  selftest/simulate-задач через панель — всё работает, 0 ошибок в консоли.
- Шрифты WOFF2: sha256 совпадают с fonts/manifest.json (байт-в-байт оригинал).
