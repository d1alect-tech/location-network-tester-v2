/** Минимальный DOM-хелпер: createElement + textContent, никакого innerHTML
 * для пользовательских данных. */
export interface ElOptions {
  className?: string;
  text?: string;
  attrs?: Record<string, string>;
}

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  options: ElOptions = {},
  children: Node[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  if (options.attrs) {
    for (const [name, value] of Object.entries(options.attrs)) node.setAttribute(name, value);
  }
  for (const child of children) node.append(child);
  return node;
}

/** Заменяет содержимое элемента (без innerHTML). */
export function clearElement(node: Element): void {
  while (node.firstChild) node.removeChild(node.firstChild);
}

let counter = 0;

/** Стабильные уникальные id для aria-связок. */
export function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}-${counter}`;
}
