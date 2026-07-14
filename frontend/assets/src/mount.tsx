import { render } from "preact";
import { FindingsPanel } from "./islands/FindingsPanel";
import { ComparisonHeatmap } from "./islands/ComparisonHeatmap";
import { LiveRunProgress } from "./islands/LiveRunProgress";
import { CompareCharts } from "./islands/CompareCharts";
import type {
  CompareChartsPayload,
  ComparisonPayload,
  Finding,
  LiveRunPayload,
} from "./types";

type IslandName = "findings" | "comparison-heatmap" | "live-run" | "compare-charts";

export function hydrateIsland(name: IslandName, el: HTMLElement, payload: unknown): void {
  switch (name) {
    case "findings":
      render(<FindingsPanel findings={payload as Finding[]} />, el);
      break;
    case "comparison-heatmap":
      render(<ComparisonHeatmap data={payload as ComparisonPayload} />, el);
      break;
    case "live-run":
      render(<LiveRunProgress config={payload as LiveRunPayload} />, el);
      break;
    case "compare-charts":
      render(<CompareCharts data={payload as CompareChartsPayload} />, el);
      break;
    default:
      console.warn(`Unknown island: ${name}`);
  }
}

export function mountAllIslands(): void {
  document.querySelectorAll<HTMLElement>("[data-island]").forEach((el) => {
    const name = el.dataset.island as IslandName | undefined;
    if (!name) return;
    const payloadEl = el.querySelector('script[type="application/json"]');
    let payload: unknown = {};
    if (payloadEl?.textContent) {
      try {
        payload = JSON.parse(payloadEl.textContent);
      } catch (err) {
        console.error(`Failed to parse island payload for ${name}`, err);
      }
    }
    hydrateIsland(name, el, payload);
  });
}
