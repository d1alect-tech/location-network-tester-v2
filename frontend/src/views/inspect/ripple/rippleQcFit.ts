/** Подгонка видимой строки QC под фиксированный слот панели. */

/** Код причины и его видимый текст: один текст может закрывать несколько кодов. */
export type QcCodeEntry = {
  readonly text: string;
  readonly codes: readonly string[];
};

/** Результат подгонки: что видно и какие коды остались за кадром. */
export type QcFit = {
  readonly text: string;
  readonly hidden: readonly string[];
};

/** Емкость видимой строки: две строки слота QC при 1280×720.
 * Слот — 475 px, шрифт 10 px IBM Plex Mono ≈ 7,2 px на символ, значит
 * строка держит ≈ 65 символов на строку и 130 на две строки. */
export const QC_VISIBLE_BUDGET = 130;

/** Текст кода длиннее этого в видимую строку не попадает. */
export const QC_MAX_CODE_TEXT = 40;

/** Число кодов в русском склонении: 1 код, 2 кода, 5 кодов. */
export function pluralCodes(count: number): string {
  const mod100 = count % 100;
  const mod10 = count % 10;
  if (mod100 >= 11 && mod100 <= 14) return "кодов";
  if (mod10 === 1) return "код";
  if (mod10 >= 2 && mod10 <= 4) return "кода";
  return "кодов";
}

/** Подгоняет видимую строку QC под слот: показывает столько текстов кодов,
 * сколько влезает, и честно называет число оставшихся за кадром. Ничего не
 * прячет: каждый код, чей текст не показан, посчитан и назван числом. */
export function fitQcText(
  head: readonly string[],
  entries: readonly QcCodeEntry[],
  represented: ReadonlySet<string>,
  distinct: ReadonlySet<string>,
): QcFit {
  const usable = entries.filter((entry) => entry.text.length <= QC_MAX_CODE_TEXT);
  for (let k = usable.length; k >= 0; k -= 1) {
    const shown = usable.slice(0, k);
    const shownCodes = new Set<string>(represented);
    for (const entry of shown) {
      for (const code of entry.codes) shownCodes.add(code);
    }
    const hidden = [...distinct].filter((code) => !shownCodes.has(code));
    const parts = k > 0 ? [...head, shown.map((entry) => entry.text).join(" · ")] : head;
    const marker =
      hidden.length > 0 ? ` · ещё ${hidden.length} ${pluralCodes(hidden.length)} QC` : "";
    const text = `QC: ${parts.join(" · ")}${marker}`;
    if (text.length <= QC_VISIBLE_BUDGET) return { text, hidden };
  }
  // Предельный случай: даже счётчик не влезает рядом с фактами — тогда строка
  // говорит только фактическое число не показанных кодов, но не молчит.
  const all = [...distinct];
  return { text: `QC: ещё ${all.length} ${pluralCodes(all.length)} QC`, hidden: all };
}
