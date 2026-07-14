import { useMemo, useState } from "preact/hooks";
import type { Finding } from "../types";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "unknown"];

function tierClass(severity: string): string {
  const s = severity.toLowerCase();
  if (SEVERITY_ORDER.includes(s)) return `tier tier-${s}`;
  return "tier tier-unknown";
}

function severityCounts(findings: Finding[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const f of findings) {
    const s = (f.severity || "unknown").toLowerCase();
    counts[s] = (counts[s] || 0) + 1;
  }
  return counts;
}

type Props = { findings: Finding[] };

export function FindingsPanel({ findings }: Props) {
  const [selectedId, setSelectedId] = useState<string | number>(findings[0]?.id ?? 0);
  const [filter, setFilter] = useState("all");

  const filtered = useMemo(() => {
    if (filter === "all") return findings;
    if (["critical", "high", "medium", "low"].includes(filter)) {
      return findings.filter((f) => f.severity?.toLowerCase() === filter);
    }
    return findings.filter((f) => f.source === filter);
  }, [findings, filter]);

  const counts = useMemo(() => severityCounts(findings), [findings]);
  const selected = filtered.find((f, i) => (f.id ?? i) === selectedId) ?? filtered[0];

  if (!findings.length) {
    return <p class="text-sm text-[var(--color-text-muted)]">No findings recorded.</p>;
  }

  const total = findings.length;
  const barSegments = SEVERITY_ORDER.filter((s) => counts[s]).map((s) => ({
    severity: s,
    count: counts[s],
    pct: (counts[s] / total) * 100,
  }));

  return (
    <div class="findings-island grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 shadow-[var(--shadow-card)]">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <span class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-subtle)]">Findings</span>
          <span class="text-sm font-semibold">{total}</span>
        </div>
        <div class="mb-4 flex h-2 overflow-hidden rounded-full bg-[var(--color-surface-muted)]">
          {barSegments.map((seg) => (
            <div
              key={seg.severity}
              class={`tier-${seg.severity}`}
              style={{ width: `${seg.pct}%`, background: `var(--color-tier-${seg.severity === "unknown" ? "unknown" : seg.severity}-bg)` }}
              title={`${seg.severity}: ${seg.count}`}
            />
          ))}
        </div>
        <div class="mb-3 flex flex-wrap gap-2">
          {["all", "critical", "high", "medium", "low"].map((f) => (
            <button
              key={f}
              type="button"
              class={`rounded-full px-2.5 py-1 text-xs font-medium ${filter === f ? "bg-[var(--color-duke-blue)] text-white" : "bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]"}`}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? `All · ${total}` : `${f} · ${counts[f] || 0}`}
            </button>
          ))}
        </div>
        <ul class="max-h-[28rem] space-y-2 overflow-y-auto" role="listbox" aria-label="Findings list">
          {filtered.map((f, i) => {
            const id = f.id ?? i;
            const active = (selected?.id ?? filtered.indexOf(selected)) === id || (selected === f);
            return (
              <li key={String(id)}>
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  class={`w-full rounded-lg border px-3 py-2 text-left transition ${active ? "border-[var(--color-duke-blue)] bg-[var(--color-duke-blue-muted)]" : "border-transparent hover:bg-[var(--color-surface-muted)]"}`}
                  onClick={() => setSelectedId(id)}
                >
                  <div class="flex items-start gap-2">
                    <span class={tierClass(f.severity)}>{f.severity}</span>
                    {f.source && <span class="badge">{f.source}</span>}
                  </div>
                  <p class="mt-1 text-sm font-medium text-[var(--color-text)]">{f.title}</p>
                  {f.file_path && <p class="mt-0.5 truncate font-mono text-xs text-[var(--color-text-subtle)]">{f.file_path}</p>}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-card)]">
        {selected ? (
          <>
            <div class="mb-4 flex flex-wrap items-center gap-2">
              <span class={tierClass(selected.severity)}>{selected.severity}</span>
              {selected.source && <span class="badge">{selected.source}</span>}
              {selected.category && <span class="badge">{selected.category}</span>}
              {selected.passed === false && <span class="status-fail">FAILED</span>}
              {selected.passed === true && <span class="status-ok">PASSED</span>}
            </div>
            <h3 class="text-lg font-semibold text-[var(--color-text)]">{selected.title}</h3>
            {selected.file_path && (
              <p class="mt-2 font-mono text-sm text-[var(--color-text-muted)]">{selected.file_path}</p>
            )}
            {selected.description && (
              <section class="mt-4">
                <h4 class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-subtle)]">Description</h4>
                <p class="mt-1 text-sm leading-relaxed">{selected.description}</p>
              </section>
            )}
            {selected.remediation && (
              <section class="mt-4">
                <h4 class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-subtle)]">Remediation</h4>
                <p class="mt-1 text-sm leading-relaxed">{selected.remediation}</p>
              </section>
            )}
            <dl class="mt-4 grid gap-2 text-sm sm:grid-cols-2">
              {selected.probe_id && (
                <>
                  <dt class="text-[var(--color-text-subtle)]">Probe</dt>
                  <dd>{selected.probe_id}</dd>
                </>
              )}
              {selected.probe_suite && (
                <>
                  <dt class="text-[var(--color-text-subtle)]">Suite</dt>
                  <dd>{selected.probe_suite}</dd>
                </>
              )}
              {selected.raw_tool_severity && (
                <>
                  <dt class="text-[var(--color-text-subtle)]">Raw severity</dt>
                  <dd>{selected.raw_tool_severity}</dd>
                </>
              )}
              {selected.corroborated_by?.length ? (
                <>
                  <dt class="text-[var(--color-text-subtle)]">Corroborated by</dt>
                  <dd>{selected.corroborated_by.join(", ")}</dd>
                </>
              ) : null}
            </dl>
          </>
        ) : (
          <p class="text-sm text-[var(--color-text-muted)]">Select a finding to view details.</p>
        )}
      </div>
    </div>
  );
}
