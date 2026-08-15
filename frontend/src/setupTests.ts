import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom has no media stack, so play/pause throw "Not implemented" and bury real
// failures in noise. Stub them rather than working around them in every test.
Object.defineProperty(HTMLMediaElement.prototype, "play", {
  configurable: true,
  value: () => Promise.resolve(),
});
Object.defineProperty(HTMLMediaElement.prototype, "pause", {
  configurable: true,
  value: () => undefined,
});

// Unmount between tests so a modal's portal, body scroll lock and focus restore
// cannot leak into the next test.
afterEach(() => {
  cleanup();
});
