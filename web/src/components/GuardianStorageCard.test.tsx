// @vitest-environment jsdom
// The storage ledger is a health surface, so it must not spend minutes of
// `PRAGMA integrity_check` on page load, and it must not report an unmeasured
// size as if the home were empty.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const mocks = vi.hoisted(() => ({
  guardianStorage: vi.fn(),
  guardianDatabaseHealth: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: mocks }));

import { GuardianStorageCard } from "./GuardianStorageCard";

let container: HTMLDivElement;
let root: Root;

function storagePayload(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: "2026-11-06T12:00:00Z",
    integrity: "not_run",
    capacity: {
      level: "normal",
      free_gb: 40.1,
      total_gb: 475.5,
      used_percent: 91.6,
      // The fast path skips the recursive walk and reports 0.
      hermes_size_gb: 0,
    },
    locations: [
      {
        name: "state_db",
        path: "C:/hermes/state.db",
        category: "database",
        exists: true,
        readable: true,
        writable: true,
        size_bytes: 2048,
        failure: "none",
      },
    ],
    category_sizes: { database: 2048 },
    failures: [],
    databases: [],
    checked_at: "2026-11-06T12:00:00Z",
    ...overrides,
  };
}

async function render() {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<GuardianStorageCard />));
}

async function clickButton(label: string) {
  const button = Array.from(container.querySelectorAll("button")).find((node) =>
    node.textContent?.includes(label),
  );
  if (!button) throw new Error(`button "${label}" not found`);
  await act(async () => button.dispatchEvent(new MouseEvent("click", { bubbles: true })));
}

beforeEach(() => {
  mocks.guardianStorage.mockResolvedValue(storagePayload());
  mocks.guardianDatabaseHealth.mockResolvedValue({
    generated_at: "2026-11-06T12:00:00Z",
    integrity: "checked",
    error: null,
    count: 2,
    invalid: 1,
    databases: [
      { path: "C:/hermes/state.db", valid: true, checks: [] },
      { path: "C:/hermes/cron/executions.db", valid: false, checks: [], error: "malformed" },
    ],
  });
});

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
  vi.clearAllMocks();
});

describe("GuardianStorageCard", () => {
  it("never runs the integrity sweep on mount", async () => {
    await render();

    expect(mocks.guardianStorage).toHaveBeenCalledTimes(1);
    expect(mocks.guardianDatabaseHealth).not.toHaveBeenCalled();
  });

  it("reports an unmeasured home size instead of 0 GB", async () => {
    await render();

    expect(container.textContent).toContain("not measured");
    expect(container.textContent).not.toContain("0.00 GB");
  });

  it("runs a forced sweep when the operator asks", async () => {
    await render();
    await clickButton("Verify databases");

    expect(mocks.guardianDatabaseHealth).toHaveBeenCalledWith(true);
    expect(container.textContent).toContain("1 invalid");
    expect(container.textContent).toContain("malformed");
  });
});
