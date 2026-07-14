import type { ComparisonPayload } from "../types";

type Props = { data: ComparisonPayload };

function cellTone(scoreClass?: string): string {
  if (!scoreClass) return "bg-[var(--color-surface-muted)]";
  if (scoreClass.includes("strong") || scoreClass.includes("low")) {
    return "bg-[var(--color-tier-low-bg)] text-[var(--color-tier-low)]";
  }
  if (scoreClass.includes("mid") || scoreClass.includes("medium")) {
    return "bg-[var(--color-tier-medium-bg)] text-[var(--color-tier-medium)]";
  }
  if (scoreClass.includes("weak") || scoreClass.includes("high")) {
    return "bg-[var(--color-tier-high-bg)] text-[var(--color-tier-high)]";
  }
  if (scoreClass.includes("critical")) {
    return "bg-[var(--color-tier-critical-bg)] text-[var(--color-tier-critical)]";
  }
  return "bg-[var(--color-surface-muted)]";
}

export function ComparisonHeatmap({ data }: Props) {
  const { models, rows } = data;
  if (!models.length || !rows.length) {
    return <p class="text-sm text-[var(--color-text-muted)]">Not enough data for comparison.</p>;
  }

  return (
    <div class="comparison-heatmap overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] shadow-[var(--shadow-card)]">
      <table class="w-full min-w-[32rem] border-collapse text-sm">
        <thead>
          <tr class="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]">
            <th class="sticky left-0 z-10 bg-[var(--color-surface-muted)] px-4 py-3 text-left font-semibold">Metric</th>
            {models.map((m) => (
              <th key={m} class="px-3 py-3 text-left font-semibold whitespace-nowrap">{m}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} class="border-b border-[var(--color-border)] last:border-0">
              <td class="sticky left-0 z-10 bg-[var(--color-surface-raised)] px-4 py-3 font-medium">
                <span class={row.badge_class || "badge"}>{row.label}</span>
              </td>
              {models.map((m) => {
                const cell = row.cells[m];
                if (!cell) {
                  return <td key={m} class="px-3 py-3 text-[var(--color-text-subtle)]">—</td>;
                }
                const inner = cell.slug ? (
                  <a href={cell.slug.startsWith("/") ? cell.slug : `/${cell.slug}`} class="font-medium hover:underline">
                    {cell.display}
                  </a>
                ) : (
                  <span class={`font-medium ${cell.score_class || ""}`}>{cell.display}</span>
                );
                return (
                  <td key={m} class="px-3 py-2">
                    <div class={`rounded-md px-2 py-2 ${cellTone(cell.score_class)}`}>{inner}</div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
