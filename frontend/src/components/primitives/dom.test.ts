/** svgEl: SVG-пространство имён, точечные атрибуты, дети по порядку.
 * Примитив создан для глифов таббара оболочки (navIcons.ts) и до todo 8
 * собственного теста не имел — покрыт только косвенно через v6Shell. */

import { describe, expect, it } from "vitest";
import { svgEl } from "./dom";

const SVG_NS = "http://www.w3.org/2000/svg";

describe("svgEl", () => {
  it("создаёт элемент в пространстве имён SVG с точными атрибутами", () => {
    // Given / When
    const node = svgEl("svg", { viewBox: "0 0 16 16", fill: "none" });

    // Then
    expect(node.namespaceURI).toBe(SVG_NS);
    expect(node.tagName).toBe("svg");
    expect(node.getAttribute("viewBox")).toBe("0 0 16 16");
    expect(node.getAttribute("fill")).toBe("none");
  });

  it("добавляет детей в порядке передачи, атрибуты не растекаются", () => {
    // Given
    const child = svgEl("rect", { x: "2", y: "3", width: "12", height: "4.4", rx: "1" });

    // When
    const parent = svgEl("svg", { stroke: "currentColor" }, [child]);

    // Then
    expect(parent.children).toHaveLength(1);
    expect(parent.firstChild).toBe(child);
    expect(child.namespaceURI).toBe(SVG_NS);
    expect(child.getAttribute("width")).toBe("12");
    expect(child.getAttribute("stroke")).toBeNull();
  });

  it("без аргументов — элемент без атрибутов и детей", () => {
    // Given / When
    const node = svgEl("path");

    // Then
    expect(node.attributes.length).toBe(0);
    expect(node.childNodes.length).toBe(0);
  });
});
