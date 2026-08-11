# DESIGN.md — LNT (Location Network Tester)

> **Примечание о восстановлении:** первые ~4 КБ документа (заголовок и начальные
> разделы) утрачены при сбое диска — битые сектора во всех найденных копиях.
> Ниже — уцелевшая часть оригинального документа (с байта 4096).

---

[...утрачено ~4 КБ: титул, цели проекта и начало архитектурного обзора...]

  --accent: #63C5C9;
  --accent-hover: #82D2D5;
  --accent-active: #48AEB3;
  --focus: #77D7DB;
  --status-ok: #69D0A0;
  --status-ok-bg: #15352A;
  --status-warn: #F1C66A;
  --status-warn-bg: #3B2E13;
  --status-error: #FF8D95;
  --status-error-bg: #421F23;
  --status-running: #63C5C9;
  --status-running-bg: #16363A;
  --plot-line-a: #69D5DB;
  --plot-line-b: #F0B76B;
  --plot-grid: #354248;
  --plot-bg: #101719;
  --shadow-sticky: 0 4px 16px rgba(0, 0, 0, 0.24);
}
```

При системной теме JavaScript устанавливает фактический `data-theme` из
`prefers-color-scheme`; отдельного набора `system` в CSS нет.

### 2.2. Проверенные контрасты

| Пара | Light | Dark |
|---|---:|---:|
| primary / canvas | 15.27:1 | 16.43:1 |
| secondary / panel | 6.14:1 | 8.12:1 |
| on-accent / accent | 5.92:1 | 9.26:1 |
| accent / panel | 5.92:1 | 8.51:1 |
| focus / canvas | 4.52:1 | 11.07:1 |
| strong border / control | 3.88:1 | 3.17:1 |
| ok / ok-bg | 5.26:1 | 7.07:1 |
| warn / warn-bg | 5.48:1 | 8.21:1 |
| error / error-bg | 5.39:1 | 6.54:1 |
| plot A / plot-bg | 4.97:1 | 10.48:1 |
| plot B / plot-bg | 5.21:1 | 10.09:1 |

Текстовый минимум — 4.5:1; значимые нетекстовые элементы — 3:1. Графики A/B
дополнительно различаются подписью и solid/dash.

## 3. Типографика и пространство

### 3.1. Шрифты

Шрифты поставляются локально в WOFF2 с кириллицей; внешние запросы запрещены.

```css
:root {
  --font-ui: "IBM Plex Sans", "Segoe UI Variable Text", "Segoe UI", sans-serif;
  --font-mono: "IBM Plex Mono", "Cascadia Mono", Consolas, monospace;
  --weight-regular: 400;
  --weight-medium: 500;
  --weight-semibold: 600;
}
```

Планируемые начертания: IBM Plex Sans 400/500/600 и IBM Plex Mono 400/500.
Каждый `@font-face` использует `font-display: swap`. Локальный same-origin
IBM Plex Sans 400 получает `<link rel="preload" as="font" type="font/woff2"
crossorigin>` для быстрой первичной отрисовки; остальные начертания
загружаются по потребности. Chromium в headless может показать безобидное
предупреждение «preloaded but not used within a few seconds» — оно
документировано и не является поводом убирать обязательный preload.

| Роль | Размер / line-height | Вес |
|---|---|---:|
| caption | 12px / 16px | 400 |
| label | 13px / 18px | 500 |
| body | 15px / 22px | 400 |
| section | 17px / 24px | 600 |
| page | 22px / 28px | 600 |
| numeric | 13px / 20px | 400 mono |

На mobile input/select имеют минимум 16px. Числа используют
`font-variant-numeric: tabular-nums lining-nums`.

### 3.2. Пространственные токены

Базовая единица — 4px.

```css
:root {
  --space-0: 0;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --radius-panel: 8px;
  --radius-control: 6px;
  --radius-status: 4px;
  --border-width: 1px;
  --control-height: 44px;
  --touch-target-min: 44px;
  --table-row-min: 44px;
  --checkbox-size: 20px;
  --status-rail-width: 3px;
  --content-max: 1480px;
  --session-list-width: 320px;
  --session-list-max-height: 680px;
  --header-height: 56px;
  --chart-height-mobile: 300px;
  --chart-height-tablet: 400px;
  --chart-height-desktop: 520px;
  --waveform-height: 260px;
  --focus-width: 2px;
  --focus-offset: 2px;
  --plot-line-width: 2px;
  --plot-dash-b: 6px 4px;
  --z-sticky: 10;
}
```

Постоянные панели не имеют `box-shadow`. Единственная допустимая тень —
`--shadow-sticky` для sticky-header после прокрутки; она сообщает elevation и
не используется как разделитель обычного контента.

## 4. Архитектура страницы

### 4.1. Порядок DOM

1. Skip-link.
2. Sticky-header: LNT, якорная навигация, корень каталога, выбор темы.
3. Командная область: устройство → захват → активная задача.
4. Workspace: каталог сессий → детальный анализ.
5. Сравнение A/B.
6. Вторичные инструменты: симуляция → selftest.
7. Встроенный error-banner остаётся первым элементом `main`.

### 4.2. Desktop, 1280px и шире

- Командная область занимает всю ширину. Устройство и задача компактны;
  основные поля захвата образуют горизонтальную сетку, primary-кнопка остаётся
  в той же визуальной строке.
- Workspace: `minmax(280px, 320px) minmax(0, 1fr)`. График получает основную
  ширину страницы.
- Compare расположен сразу под workspace. Инструменты — последним блоком.

### 4.3. Tablet, от 768px

- Командная область — сетка 2×2; захват занимает полную ширину.
- Каталог располагается над анализом и имеет ограниченную высоту.
- Формы используют две колонки; длинные поля занимают обе.

### 4.4. Mobile, 375px

- Одна колонка: устройство → захват → задача → сессии → анализ → сравнение →
  инструменты.
- Навигация прокручивается горизонтально, но основная страница не имеет
  горизонтального overflow.
- Все действия занимают доступную ширину, touch target не меньше 44px.
- Таблицы сравнения переходят в подписанные строки A/B/Delta без горизонтальной
  прокрутки.

Единственный владелец прокрутки страницы — документ. Каталог может иметь свою
именованную прокрутку только на tablet/desktop.

## 5. Примитивы и состояния

### 5.1. Button

- Primary: `accent` + `text-on-accent`; hover/active используют соответствующие
  accent-токены.
- Secondary: transparent/panel, `border-strong`, `text-primary`.
- Danger: status-error foreground/border; заливка error-bg только при hover или
  фактической ошибке.
- Disabled использует нативный `disabled`, muted tokens и не полагается только
  на opacity.
- Active меняет только `transform`; focus-visible использует 2px `focus` с
  offset 2px.

### 5.2. Field и select

Структура: видимый label → control → helper либо inline-error. Высота 44px,
фон `surface-raised`, граница `border-strong`. Error сохраняет красную границу,
а focus рисуется поверх неё. Placeholder не заменяет label.

### 5.3. Theme selector

Нативный select `Системная / Светлая / Тёмная` с видимым label. Значение
хранится в `localStorage` под ключом `lnt-theme`. При `system` интерфейс слушает
изменения `prefers-color-scheme`; явный выбор их игнорирует. Минимальный код в
`head` устанавливает тему до CSS-paint и предотвращает вспышку неверной темы.

### 5.4. Session row и search

Строка показывает ID, статус и метаданные; selected использует
`surface-selected` и измерительную рейку accent. Error/running используют
соответствующие status tokens и текст. Бейджи типа сессии: `badge-selfnoise`
(самошум, warn-токены) и `badge-single-channel` («1 канал», нейтральный
вторичный тон) — одноканальные сессии без CH2 видны прямо в каталоге.
Поле поиска фильтрует уже загруженные
сессии по имени и метке без API-запросов; пустой результат объясняет фильтр и
предлагает его очистить.

### 5.5. Disclosure

Нативные `details/summary` применяются для блока `Серия и режим`, манифеста и
вторичных инструментов. Фокус, hover и `aria-expanded` обеспечиваются нативной
семантикой. Layout раскрытия не анимируется.

### 5.6. Primitive showcase gate

До сборки продуктового экрана должны быть визуально проверены в обеих темах:
button, field, select, checkbox, theme selector, status label, session row,
disclosure и error banner во всех применимых состояниях default/hover/focus/
active/disabled/error/selected/running.

## 6. Компоненты продукта и поведение

- **Устройство:** компактный итог, цепочка драйвер/устройство/прошивка,
  восстановительное действие; измерительная рейка кодирует итог.
- **Захват:** каталог, длительность, диапазон и метка видны сразу. Самошум,
  повторы и интервал находятся в disclosure `Серия и режим`. API payload и
  доменная семантика не меняются.
- **Задача:** текстовая стадия, реальный progress и `i/N`; без spinner и
  выдуманного процента. Отмена явно обещает остановку после текущей сессии.
- **Сессии:** поиск, список, статусы и refresh. Поиск локальный и не изменяет
  порядок исходного массива.
- **Анализ:** метрики и спектр предшествуют сворачиваемому манифесту. Спектр
  подписан как сырой scope-plane PSD канала CH1; статус CH1 input-reference из
  `metrics.json` показывается честно (доступен/недоступен с причиной), без
  несуществующего переключателя скорректированной плоскости. Plotly
  загружается только при первом построении графика из локального vendor-файла.
  Во время загрузки выводится текстовый статус, не фиктивный skeleton данных.
- **Сравнение:** A/B, правило `Delta = B - A`, знак, направление и слово
  `улучшение/ухудшение`; цвет — дополнительный признак.
- **Инструменты:** симуляция и selftest сохраняют все поля и сценарии, но имеют
  меньший визуальный вес.
- **Ошибки:** встроенный `role=alert`, причина и следующий шаг; traceback не
  показывается. Ошибка поля остаётся рядом с полем.
- **Empty states:** нет сессий, нет результатов поиска, не выбран анализ, нет
  анализа и нет пиков — разные допустимые состояния, не error.
- **Favicon/meta:** локальный SVG favicon и содержательный meta description.

Backend, API, capture/analyze/compare, форматы сессий и коды ошибок не меняются.

## 7. Motion, производительность и доступность

```css
:root {
  --motion-fast: 100ms;
  --motion-standard: 160ms;
  --motion-status: 240ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
}
```

Motion сообщает hover/press/status/disclosure и использует только transform,
opacity, color и background-color. Декоративных, циклических и stagger-анимаций
нет. `prefers-reduced-motion: reduce` отключает все переходы.

Начальная страница не загружает 1.6MB Plotly; loader добавляет локальный script
один раз при первом графике и кэширует Promise. IBM Plex Sans 400 получает
`preload`; остальные WOFF2-начертания грузятся по требованию через
`font-display: swap`. Внешние запросы, CDN и
telemetry запрещены.

WCAG 2.2 AA: один H1, последовательные H2/H3, landmarks, skip-link, видимые
labels, focus-visible, минимум 44px, логичный DOM/tab-order, live regions без
дублирования и графики с текстовой таблицей. Темы проверяются независимо.

## 8. Проверка, ограничения и долг

Обязательные проверки:

- light и dark на 375/768/1280px;
- системная тема и смена ОС без reload;
- клавиатурный проход всего сценария;
- zoom 200%, reduced motion, длинный путь/ID и 200 сессий;
- все состояния primitive showcase;
- contrast WCAG, Plotly colors и A/B solid/dash;
- Lighthouse mobile/desktop в реальном Chrome;
- `/visual-qa`, затем review-work с проверкой accessibility и heuristic flow.

Жёсткие запреты: внешние ресурсы, webfont CDN, UI libraries, React/Tailwind,
emoji-иконки, glass, blur, градиенты, декоративные тени и motion без смысла.

Accepted debt:

| Долг | Причина | Условие выхода |
|---|---|---|
| Нет отдельного high-contrast theme | Scope — две основные темы; forced-colors сохраняет нативные контролы | Отдельный аудит Windows High Contrast |
| Поиск не индексирует содержимое metrics | Достаточно имени и метки; backend search вне visual redesign | Запрос полнотекстового поиска |
| Нет virtualized session list | 200 строк проходят stress test без библиотеки | Подтверждённая деградация на больших архивах |

Рабочая директория не является git-репозиторием; commit этого контракта
невозможен в текущем окружении.
