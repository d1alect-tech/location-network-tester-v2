/** Чтение дизайн-токенов DESIGN.md из CSS-переменных для uPlot-канвы.
 * Темы переключаются атрибутом data-theme; цвета читаются на момент вызова. */

export interface ChartTheme {
  accentA: string;
  accentB: string;
  panel: string;
  canvasBg: string;
  fgSecondary: string;
  borderSubtle: string;
  fontMono: string;
  fontSans: string;
  lineWidth: number;
}

/** Резервные цвета — светлая тема DESIGN.md §4.1 (jsdom не вычисляет
 * custom properties); в браузере всегда читаются актуальные токены. */
const FALLBACK: ChartTheme = {
  accentA: "#5681ff",
  accentB: "#e68619",
  panel: "#323232",
  canvasBg: "#1d1d1d",
  fgSecondary: "#d1d1d1",
  borderSubtle: "#3f3f3f",
  fontMono: '"Source Code Pro Variable", Consolas, monospace',
  fontSans: '"Golos Text Variable", "Segoe UI", system-ui, sans-serif',
  lineWidth: 1,
};

function token(styles: CSSStyleDeclaration, name: string): string {
  const value = styles.getPropertyValue(name).trim();
  return value;
}

export function readChartTheme(root: Element = document.documentElement): ChartTheme {
  const styles = getComputedStyle(root);
  return {
    accentA: token(styles, "--lnt-accent-a") || FALLBACK.accentA,
    accentB: token(styles, "--lnt-accent-b") || FALLBACK.accentB,
    panel: token(styles, "--lnt-bg-panel") || FALLBACK.panel,
    canvasBg: token(styles, "--lnt-bg-canvas") || FALLBACK.canvasBg,
    fgSecondary: token(styles, "--lnt-fg-secondary") || FALLBACK.fgSecondary,
    borderSubtle: token(styles, "--lnt-border-subtle") || FALLBACK.borderSubtle,
    fontMono: token(styles, "--lnt-font-mono") || FALLBACK.fontMono,
    fontSans: token(styles, "--lnt-font-sans") || FALLBACK.fontSans,
    lineWidth: Number.parseFloat(token(styles, "--lnt-border-width")) || FALLBACK.lineWidth,
  };
}
