import { useEffect, useRef } from "preact/hooks";
import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  DoughnutController,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";
import type { OverviewChartsPayload } from "../types";

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Legend,
  Tooltip,
  DoughnutController,
  ArcElement,
);

const TIER_COLORS: Record<string, string> = {
  critical: "#b91c1c",
  high: "#c45c00",
  medium: "#b8860b",
  low: "#1b7f3b",
  unknown: "#6b7280",
};

type Props = { data: OverviewChartsPayload };

export function OverviewCharts({ data }: Props) {
  const tierRef = useRef<HTMLCanvasElement>(null);
  const safetyRef = useRef<HTMLCanvasElement>(null);
  const countsRef = useRef<HTMLCanvasElement>(null);
  const chartsRef = useRef<Chart[]>([]);

  useEffect(() => {
    chartsRef.current.forEach((c) => c.destroy());
    chartsRef.current = [];

    if (tierRef.current && data.scanTierCounts.some((n) => n > 0)) {
      chartsRef.current.push(
        new Chart(tierRef.current, {
          type: "doughnut",
          data: {
            labels: data.scanTierLabels,
            datasets: [
              {
                data: data.scanTierCounts,
                backgroundColor: data.scanTierLabels.map(
                  (l) => TIER_COLORS[l.toLowerCase()] || TIER_COLORS.unknown,
                ),
              },
            ],
          },
          options: {
            responsive: true,
            plugins: { legend: { position: "bottom" } },
          },
        }),
      );
    }

    if (safetyRef.current && data.safetyPassValues.length) {
      chartsRef.current.push(
        new Chart(safetyRef.current, {
          type: "bar",
          data: {
            labels: data.safetyPassLabels,
            datasets: [
              {
                label: "Pass rate (%)",
                data: data.safetyPassValues,
                backgroundColor: "#012169",
              },
            ],
          },
          options: {
            indexAxis: "y",
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { x: { max: 100 } },
          },
        }),
      );
    }

    if (countsRef.current && data.pillarCountValues.some((n) => n > 0)) {
      chartsRef.current.push(
        new Chart(countsRef.current, {
          type: "bar",
          data: {
            labels: data.pillarCountLabels,
            datasets: [
              {
                label: "Runs",
                data: data.pillarCountValues,
                backgroundColor: ["#012169", "#166534", "#a16207", "#7c3aed"],
              },
            ],
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false } },
          },
        }),
      );
    }

    return () => chartsRef.current.forEach((c) => c.destroy());
  }, [data]);

  const hasData =
    data.scanTierCounts.some((n) => n > 0) ||
    data.safetyPassValues.length > 0 ||
    data.pillarCountValues.some((n) => n > 0);

  if (!hasData) {
    return null;
  }

  return (
    <div class="overview-charts grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <div class="overview-chart-tile rounded-lg border border-border bg-surface-muted p-3">
        <h3 class="text-xs font-bold uppercase tracking-wide text-text-subtle mb-2">Scan tiers</h3>
        <canvas ref={tierRef} height="140" />
      </div>
      <div class="overview-chart-tile rounded-lg border border-border bg-surface-muted p-3">
        <h3 class="text-xs font-bold uppercase tracking-wide text-text-subtle mb-2">Safety pass rates</h3>
        <canvas ref={safetyRef} height="140" />
      </div>
      <div class="overview-chart-tile rounded-lg border border-border bg-surface-muted p-3 sm:col-span-2 xl:col-span-1">
        <h3 class="text-xs font-bold uppercase tracking-wide text-text-subtle mb-2">Runs per pillar</h3>
        <canvas ref={countsRef} height="140" />
      </div>
    </div>
  );
}
