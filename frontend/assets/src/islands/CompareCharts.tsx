import { useEffect, useRef } from "preact/hooks";
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Legend,
  LinearScale,
  Title,
  Tooltip,
} from "chart.js";
import type { CompareChartsPayload } from "../types";

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Legend, Title, Tooltip);

type Props = { data: CompareChartsPayload };

export function CompareCharts({ data }: Props) {
  const { models } = data;
  const safetyRef = useRef<HTMLCanvasElement>(null);
  const evalRef = useRef<HTMLCanvasElement>(null);
  const benchRef = useRef<HTMLCanvasElement>(null);
  const chartsRef = useRef<Chart[]>([]);

  useEffect(() => {
    chartsRef.current.forEach((c) => c.destroy());
    chartsRef.current = [];

    const labels = models.map((m) => m.display_name || m.slug);
    const safetyData = models.map((m) => (m.safety?.pass_rate != null ? m.safety.pass_rate * 100 : null));
    const evalData = models.map((m) => m.eval?.best_overall ?? null);

    if (safetyRef.current && safetyData.some((v) => v != null)) {
      chartsRef.current.push(
        new Chart(safetyRef.current, {
          type: "bar",
          data: {
            labels,
            datasets: [{ label: "Safety pass rate (%)", data: safetyData, backgroundColor: "#012169" }],
          },
          options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { max: 100 } } },
        }),
      );
    }

    if (evalRef.current && evalData.some((v) => v != null)) {
      chartsRef.current.push(
        new Chart(evalRef.current, {
          type: "bar",
          data: {
            labels,
            datasets: [{ label: "Best eval (/5)", data: evalData, backgroundColor: "#166534" }],
          },
          options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { max: 5 } } },
        }),
      );
    }

    const benchKinds = new Set<string>();
    models.forEach((m) => {
      if (m.benchmark) Object.keys(m.benchmark).forEach((k) => benchKinds.add(k));
    });
    if (benchRef.current && benchKinds.size) {
      const kinds = [...benchKinds];
      chartsRef.current.push(
        new Chart(benchRef.current, {
          type: "bar",
          data: {
            labels,
            datasets: kinds.map((kind, i) => ({
              label: kind,
              data: models.map((m) => m.benchmark?.[kind]?.headline_value ?? null),
              backgroundColor: ["#012169", "#166534", "#a16207", "#7c3aed"][i % 4],
            })),
          },
          options: { responsive: true, scales: { y: { max: 100 } } },
        }),
      );
    }

    return () => chartsRef.current.forEach((c) => c.destroy());
  }, [models]);

  if (!models.length) {
    return <p class="text-sm text-[var(--color-text-muted)]">Add models to compare.</p>;
  }

  return (
    <div class="compare-charts grid gap-6 md:grid-cols-2">
      <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-card)]">
        <h3 class="mb-3 text-sm font-semibold">Safety pass rate</h3>
        <canvas ref={safetyRef} height="200" />
      </div>
      <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-card)]">
        <h3 class="mb-3 text-sm font-semibold">Best eval score</h3>
        <canvas ref={evalRef} height="200" />
      </div>
      <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-card)] md:col-span-2">
        <h3 class="mb-3 text-sm font-semibold">Benchmark headlines</h3>
        <canvas ref={benchRef} height="240" />
      </div>
    </div>
  );
}
