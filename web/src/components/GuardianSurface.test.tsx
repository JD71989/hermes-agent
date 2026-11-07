// @vitest-environment jsdom
// Guardian surfaces are projections over stores that may not exist on this
// machine. These invariants pin the honesty contract: a missing or unreadable
// store is labelled as such, and revenue with no evidence is never presented
// as a number.

import { describe, it, expect, afterEach } from "vitest";
import { act } from "react";
import type { ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";

import type { GuardianSource } from "@/lib/api";
import { GuardianSourceBadge } from "./GuardianSurface";
import { cell, formatBytes, formatMoney, sourceLabel } from "@/lib/guardian";

let container: HTMLDivElement;
let root: Root;

async function render(node: ReactNode) {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(node));
  return container.textContent ?? "";
}

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
});

const source = (overrides: Partial<GuardianSource>): GuardianSource => ({
  configured: true,
  available: true,
  path: null,
  updated_at: null,
  size_bytes: 0,
  error: null,
  ...overrides,
});

describe("GuardianSourceBadge", () => {
  it("labels an unconfigured store as not found rather than live", async () => {
    const text = await render(
      <GuardianSourceBadge source={source({ configured: false, available: false })} />,
    );

    expect(text).toContain("not found");
  });

  it("surfaces a read error for a configured but unavailable store", async () => {
    const text = await render(
      <GuardianSourceBadge source={source({ available: false, error: "unreadable" })} />,
    );

    expect(text).toContain("unreadable");
  });
});

describe("sourceLabel", () => {
  it("distinguishes a missing store from an empty one", () => {
    expect(sourceLabel(undefined)).toBe("no source");
    expect(sourceLabel(source({ configured: false, available: false }))).toBe("not found");
    expect(sourceLabel(source({ available: false, error: "permission denied" }))).toBe("permission denied");
    expect(sourceLabel(source({}))).toBe("live");
  });
});

describe("revenue formatting", () => {
  it("never renders an unverified total as a plain zero", () => {
    expect(formatMoney({})).toBe("0 (unverified)");
  });

  it("keeps each currency separate", () => {
    expect(formatMoney({ GBP: 120.5, USD: 40 })).toBe("GBP 120.50 + USD 40.00");
  });
});

describe("cell", () => {
  it("skips empty values and takes the first present field", () => {
    expect(cell({ name: "", title: "Real title", value_usd: 0 }, ["name", "title"])).toBe("Real title");
    expect(cell({ value_usd: 0 }, ["value_usd"])).toBe("0");
    expect(cell({}, ["name"])).toBe("-");
  });
});

describe("formatBytes", () => {
  it("treats an absent measurement as zero bytes", () => {
    expect(formatBytes(null)).toBe("0 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
  });
});
