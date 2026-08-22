/** Типизированные ошибки тайла спектрограммы (todo 42): код причины +
 * русское сообщение для баннера восстановления. Никаких голых Error. */

export type TileErrorCode =
  | "tile_too_large"
  | "corrupt_payload"
  | "empty_window"
  | "unsupported_compression";

const RU_MESSAGES: Record<TileErrorCode, string> = {
  tile_too_large:
    "Фрагмент спектрограммы больше лимита 524000 ячеек и не будет отображён целиком. Уменьшите область просмотра.",
  corrupt_payload:
    "Файл спектрограммы повреждён или неполон: не удалось прочитать массивы NPZ. Повторите анализ сессии.",
  empty_window: "Выбранная область не содержит ячеек спектрограммы. Расширьте границы окна.",
  unsupported_compression:
    "Браузер не поддерживает распаковку NPZ. Откройте панель в актуальном Chromium.",
};

export class TileError extends Error {
  readonly code: TileErrorCode;

  constructor(code: TileErrorCode, options: { cause?: unknown; detail?: string } = {}) {
    super(
      options.detail === undefined ? RU_MESSAGES[code] : `${RU_MESSAGES[code]} ${options.detail}`,
      {
        cause: options.cause,
      },
    );
    this.name = "TileError";
    this.code = code;
  }
}
