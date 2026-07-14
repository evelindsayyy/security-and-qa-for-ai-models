import { useEffect, useRef, useState } from "preact/hooks";
import type { LiveRunPayload } from "../types";

type StatusResponse = {
  status?: string;
  message?: string;
  log?: string;
  log_truncated?: boolean;
  progress?: number;
  total?: number;
};

function updateLogPreservingScroll(el: HTMLPreElement, text: string): void {
  if (typeof text !== "string" || text === el.textContent) return;
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 48;
  const prevTop = el.scrollTop;
  el.textContent = text;
  if (atBottom) el.scrollTop = el.scrollHeight;
  else el.scrollTop = prevTop;
}

type Props = { config: LiveRunPayload };

export function LiveRunProgress({ config }: Props) {
  const {
    pollUrl,
    intervalMs = 5000,
    cancelUrl,
    retryUrl,
    showRetry = false,
    initialStatus = "running",
    initialMessage = "",
    hint,
    stages = [],
    progressLabel,
  } = config;

  const [status, setStatus] = useState(initialStatus);
  const [message, setMessage] = useState(initialMessage);
  const [truncated, setTruncated] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState("");
  const logRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    let cancelled = false;
    let intervalId = 0;

    const applyStatus = (s: StatusResponse) => {
      if (cancelled) return;
      const st = s.status || "unknown";
      setStatus(st);
      const logText = s.message || s.log || "";
      setMessage(logText);
      setTruncated(!!s.log_truncated);
      if (typeof s.progress === "number") setProgress(s.progress);
      if (typeof s.total === "number") setTotal(s.total);
      if (logRef.current) updateLogPreservingScroll(logRef.current, logText);

      if (st === "complete" || st === "completed") {
        window.clearInterval(intervalId);
        window.location.reload();
      }
      if (st === "failed" || st === "cancelled") {
        window.clearInterval(intervalId);
      }
    };

    const poll = () => {
      fetch(pollUrl)
        .then((r) => r.json())
        .then(applyStatus)
        .catch(() => setError("Lost connection to status endpoint."));
    };

    poll();
    intervalId = window.setInterval(poll, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [pollUrl, intervalMs]);

  const pct = progress != null && total ? Math.round((progress / total) * 100) : null;

  return (
    <div class="live-run-island rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-5 shadow-[var(--shadow-card)]">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-subtle)]">Status</p>
          <p class="text-lg font-semibold capitalize">{status}</p>
        </div>
        {cancelUrl && (status === "running" || status === "pending") && (
          <button
            type="button"
            class="btn-secondary btn-sm"
            onClick={async () => {
              if (!confirm("Stop this run? Partial output may remain on disk.")) return;
              await fetch(cancelUrl, { method: "POST" });
            }}
          >
            Stop run
          </button>
        )}
      </div>

      {stages.length > 0 && (
        <div class="mb-4 flex flex-wrap gap-2" aria-label="Pipeline stages">
          {stages.map((stage) => (
            <div
              key={stage.id}
              class={`rounded-lg border px-3 py-2 text-xs ${stage.status === "complete" ? "border-emerald-200 bg-emerald-50" : stage.status === "running" ? "border-blue-200 bg-blue-50" : stage.status === "failed" ? "border-red-200 bg-red-50" : "border-[var(--color-border)] bg-[var(--color-surface-muted)]"}`}
            >
              <span class="font-semibold">{stage.label}</span>
              {stage.duration && <span class="ml-1 text-[var(--color-text-subtle)]">· {stage.duration}</span>}
              {typeof stage.count === "number" && <span class="ml-1">· {stage.count}</span>}
            </div>
          ))}
        </div>
      )}

      {pct != null && (
        <div class="mb-4">
          <div class="mb-1 flex justify-between text-xs text-[var(--color-text-muted)]">
            <span>{progressLabel || "Progress"}</span>
            <span>{progress}/{total} ({pct}%)</span>
          </div>
          <div class="h-2 overflow-hidden rounded-full bg-[var(--color-surface-muted)]">
            <div class="h-full rounded-full bg-[var(--color-duke-blue)] transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {truncated && <p class="mb-2 text-xs text-[var(--color-stale)]">Log truncated — see run log file on disk for full output.</p>}
      {error && <p class="mb-2 text-sm text-[var(--color-status-failed)]" role="alert">{error}</p>}

      <pre
        ref={logRef}
        class="max-h-96 overflow-auto rounded-lg border border-[var(--color-border)] bg-[#1e1e1e] p-4 font-mono text-xs leading-relaxed text-[#e8e8e8]"
        aria-live="polite"
      >
        {message}
      </pre>

      {hint && <p class="mt-2 text-xs text-[var(--color-text-subtle)]">{hint}</p>}

      {showRetry && status === "failed" && retryUrl && (
        <p class="mt-3">
          <a href={retryUrl} class="btn-primary btn-sm">Start a new run →</a>
        </p>
      )}
    </div>
  );
}
