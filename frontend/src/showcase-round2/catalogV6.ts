/** Каталог V6: структура вместо плоского списка.
 *  Три претензии к прежнему виду: сессии свалены в кучу, порядок нельзя изменить,
 *  и не видно связей — какая сессия с какой сравнивается и что служит самошумом.
 *  Поэтому здесь: дни как заголовки групп, сортировка кликом по колонке, поиск
 *  по метке и роли сессий, совпадающие с полосой пары А—Б. */
import { SESSIONS, type ShowcaseSession } from "../showcase-redesign/data";
import { h } from "./kit";

type SortKey = "label" | "type" | "date";
type SortDir = "ascending" | "descending";

interface CatalogPair {
  base: ShowcaseSession;
  compare: ShowcaseSession;
}

interface CatalogState {
  query: string;
  sort: SortKey;
  dir: SortDir;
}

const DAY_FORMAT = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" });
const SHORT_DAY_FORMAT = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" });

/** «2026-08-29» -> «29 августа»: день читается словами, а не машинной датой. */
function formatDay(date: string): string {
  const parsed = new Date(`${date}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? date : DAY_FORMAT.format(parsed);
}

/** «2026-08-29_14-30-00_rc» -> «14:30». Когда день уже назван заголовком группы,
 *  повторять его в каждой строке незачем — внутри дня сессии различаются временем. */
/** «2026-08-25» -> «25 авг.»: полная ISO-дата съедала ширину у метки; точная дата в подсказке. */
function formatShortDay(date: string): string {
  const parsed = new Date(`${date}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? date : SHORT_DAY_FORMAT.format(parsed);
}

function formatTime(id: string): string {
  const match = /_(\d{2})-(\d{2})-\d{2}/.exec(id);
  return match === null ? "" : `${match[1]}:${match[2]}`;
}

function sortValue(session: ShowcaseSession, key: SortKey): string {
  if (key === "label") return session.label;
  if (key === "type") return session.typeLabel;
  return session.date;
}

function compareSessions(
  left: ShowcaseSession,
  right: ShowcaseSession,
  state: CatalogState,
): number {
  const order = sortValue(left, state.sort).localeCompare(sortValue(right, state.sort), "ru");
  const signed = state.dir === "ascending" ? order : -order;
  // Внутри одного дня порядок должен быть устойчивым, иначе строки прыгают.
  return signed === 0 ? left.id.localeCompare(right.id) : signed;
}

/** Роль сессии в текущей работе — это и есть та самая «связь» между записями.
 *
 *  Самошум своего чипа не получает: колонка «Тип» и так говорит «Самошум», а его
 *  принадлежность дню выражена группой. Дублирующий чип сжимал метку до «са…». */
function roleOf(session: ShowcaseSession, pair: CatalogPair): { key: string; text: string } | null {
  if (session.id === pair.base.id) return { key: "a", text: "А" };
  if (session.id === pair.compare.id) return { key: "b", text: "Б" };
  return null;
}

const ROLE_TITLE: Readonly<Record<string, string>> = {
  a: "Слот А полосы сравнения: база",
  b: "Слот Б полосы сравнения: сравнение",
};

function buildRow(session: ShowcaseSession, pair: CatalogPair, grouped: boolean): HTMLElement {
  // data-row — общий признак строки каталога во всех витринах (контракт S6),
  // data-session — адрес записи для связей внутри V6.
  const row = h("tr", session.id === pair.base.id ? "is-selected" : "", {
    "data-row": session.storagePath === undefined ? session.id : "edge",
    "data-session": session.id,
    "data-cat-date": session.date,
    title: session.storagePath ?? session.id,
  });
  const labelCell = h("td", "cat-label-cell", {}, [
    h("span", "cell-ellipsis", { "data-cat-label": "", title: session.label }, [session.label]),
  ]);
  const role = roleOf(session, pair);
  if (role !== null) {
    labelCell.append(
      h(
        "span",
        `cat-role cat-role-${role.key}`,
        { "data-cat-role": role.key, title: ROLE_TITLE[role.key] ?? "" },
        [role.text],
      ),
    );
  }
  row.append(
    h("td", "", {}, [
      h(
        "span",
        `glyph glyph-${session.health}`,
        { title: session.healthLabel, "aria-label": session.healthLabel },
        [session.glyph],
      ),
    ]),
    labelCell,
    h("td", "cell-ellipsis", { title: session.typeLabel }, [session.typeLabel]),
    // В режиме групп день назван выше, и колонка отдаёт ширину типу, показывая время.
    h("td", "num", { title: session.date }, [
      grouped ? formatTime(session.id) : formatShortDay(session.date),
    ]),
  );
  return row;
}

function buildGroupRow(date: string, count: number): HTMLElement {
  // Содержимое раскладывает вложенный flex, а не сам th: display:flex на ячейке выбивает
  // её из табличной модели, colspan перестаёт действовать и заголовок схлопывается до первой колонки.
  return h("tr", "cat-group", { "data-cat-group": date }, [
    h("th", "", { colspan: "4", scope: "colgroup" }, [
      h("div", "cat-group-in", {}, [
        h("span", "cat-group-day", {}, [formatDay(date)]),
        h("span", "cat-group-count", { "data-cat-count": "" }, [String(count)]),
      ]),
    ]),
  ]);
}

function buildEmptyRow(): HTMLElement {
  return h("tr", "", {}, [
    h("td", "cat-empty", { colspan: "4", "data-cat-empty": "" }, ["По запросу ничего не найдено"]),
  ]);
}

const COLUMNS: readonly { key: SortKey; title: string }[] = [
  { key: "label", title: "Метка" },
  { key: "type", title: "Тип" },
  { key: "date", title: "Дата" },
];

export function buildCatalogV6(pair: CatalogPair): HTMLElement {
  const state: CatalogState = { query: "", sort: "date", dir: "descending" };

  const tbody = h("tbody");
  const table = h("table", "tbl tbl-tight tbl-cat");
  const found = h("span", "cat-found", { "data-cat-found": "" });
  const search = h("input", "cat-search", {
    type: "search",
    "data-cat-search": "",
    placeholder: "Поиск по метке",
    "aria-label": "Поиск сессий по метке",
  });
  const clear = h("button", "btn-quiet", { type: "button", "data-cat-clear": "" }, ["Сбросить"]);

  const headRow = h("tr", "", {}, [h("th", "", { scope: "col", "aria-label": "Состояние" })]);
  const heads = new Map<SortKey, HTMLElement>();
  const titles = new Map<SortKey, Text>();
  for (const column of COLUMNS) {
    const title = document.createTextNode(column.title);
    titles.set(column.key, title);
    const cell = h("th", "cat-th", { scope: "col", "data-cat-sort": column.key }, [
      h("button", "cat-sort", { type: "button" }, [
        title,
        h("span", "cat-sort-mark", { "aria-hidden": "true" }),
      ]),
    ]);
    cell.addEventListener("click", () => {
      if (state.sort === column.key) {
        state.dir = state.dir === "ascending" ? "descending" : "ascending";
      } else {
        state.sort = column.key;
        state.dir = "ascending";
      }
      render();
    });
    heads.set(column.key, cell);
    headRow.append(cell);
  }
  table.append(h("thead", "", {}, [headRow]), tbody);

  function render(): void {
    for (const [key, cell] of heads) {
      cell.setAttribute("aria-sort", state.sort === key ? state.dir : "none");
    }
    const needle = state.query.trim().toLocaleLowerCase("ru");
    const visible = SESSIONS.filter(
      (session) => needle === "" || session.label.toLocaleLowerCase("ru").includes(needle),
    ).sort((left, right) => compareSessions(left, right, state));

    tbody.replaceChildren();
    // Группировка по дням честна только когда и порядок идёт по дням.
    const grouped = state.sort === "date";
    // В группах колонка показывает время, и заголовок не должен говорить «Дата».
    const dateTitle = titles.get("date");
    if (dateTitle !== undefined) dateTitle.data = grouped ? "Время" : "Дата";
    // Без групп колонка несёт полную дату и требует больше места, чем «14:30».
    table.classList.toggle("is-flat", !grouped);
    if (visible.length === 0) {
      tbody.append(buildEmptyRow());
    } else if (grouped) {
      let day = "";
      for (const session of visible) {
        if (session.date !== day) {
          day = session.date;
          tbody.append(buildGroupRow(day, visible.filter((item) => item.date === day).length));
        }
        tbody.append(buildRow(session, pair, true));
      }
    } else {
      for (const session of visible) tbody.append(buildRow(session, pair, false));
    }
    found.textContent = `${visible.length} из ${SESSIONS.length}`;
  }

  search.addEventListener("input", () => {
    state.query = search.value;
    render();
  });
  clear.addEventListener("click", () => {
    search.value = "";
    state.query = "";
    state.sort = "date";
    state.dir = "descending";
    render();
  });
  render();

  return h("section", "panel cat-v6", { "data-showcase": "catalog" }, [
    h("div", "panel-hd", {}, [h("h2", "panel-title", {}, ["Каталог сессий"]), found]),
    h("div", "cat-tools", {}, [
      h("span", "cat-find", { "aria-hidden": "true" }, ["⌕"]),
      search,
      clear,
    ]),
    h("div", "panel-bd is-bare", {}, [h("div", "tbl-wrap", {}, [table])]),
  ]);
}
