import { render } from "preact";
import { FindingsPanel } from "../islands/FindingsPanel";
import { describe, expect, it } from "vitest";

describe("FindingsPanel", () => {
  it("renders empty state", () => {
    const el = document.createElement("div");
    render(<FindingsPanel findings={[]} />, el);
    expect(el.textContent).toContain("No findings");
  });

  it("renders finding list", () => {
    const el = document.createElement("div");
    render(
      <FindingsPanel
        findings={[
          { id: "1", title: "Test finding", severity: "high", source: "modelscan" },
        ]}
      />,
      el,
    );
    expect(el.textContent).toContain("Test finding");
    expect(el.textContent).toContain("high");
  });
});
