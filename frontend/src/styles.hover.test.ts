/**
 * The global `button:hover` rule once repainted every button purple, including
 * card-shaped ones that set their own light background. Their text stayed dark,
 * so the label became unreadable on hover (~2:1 contrast) — reported on the
 * topic picker, and present on four other screens besides.
 *
 * jsdom does not resolve `:hover`, so this asserts the invariant on the
 * stylesheet source instead: every card-shaped button that paints its own
 * background must be excluded from the generic hover fill.
 */
import { describe, expect, it } from "vitest";

// Read through require so the build's `tsc` pass never needs @types/node for a
// test-only file; vitest runs in Node, where this resolves normally. The path is
// derived from this file's own location, so it does not depend on the cwd.
declare const require: (id: string) => any;
const CSS: string = require("fs").readFileSync(
  require("path").join(__dirname, "styles.css"),
  "utf8"
);
declare const __dirname: string;

/** Buttons that paint their own background and own their hover state. */
const SELF_PAINTING_BUTTONS = [
  "topic-card",
  "subtopic-card",
  "board-card",
  "material-folder-row",
  "flow-tab",
  "progress-topic-head",
  "app-sidebar-link",
];

function genericHoverRule(): string {
  // The exclusion list spans several lines, so match across newlines.
  const match = CSS.match(
    /(?:^|\n)button:hover:not\(:disabled\)[\s\S]*?\{[\s\S]*?\}/
  );
  if (!match) throw new Error("generic button:hover rule not found in styles.css");
  return match[0];
}

describe("the generic button hover fill", () => {
  it("still darkens ordinary buttons", () => {
    expect(genericHoverRule()).toContain("--primary-dark");
  });

  it.each(SELF_PAINTING_BUTTONS)(
    "does not repaint .%s, whose text would become unreadable",
    (cls) => {
      expect(genericHoverRule()).toContain(`.${cls}`);
    }
  );

  it("keeps the selected topic card purple rather than reverting it to white", () => {
    // The selected card is purple with white text; a hover rule that forced the
    // surface colour back would make the selection vanish under the cursor.
    const selected = CSS.match(/\.topic-card\.selected\s*\{[^}]*\}/)?.[0] ?? "";
    expect(selected).toContain("--color-primary");
    expect(CSS).not.toMatch(
      /\.topic-card:hover:not\(:disabled\)\s*\{[^}]*background:\s*var\(--color-surface\)/
    );
  });
});
