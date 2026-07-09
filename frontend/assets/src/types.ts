export type Finding = {
  id?: string;
  title: string;
  severity: string;
  source: string;
  category?: string;
  passed?: boolean;
  file_path?: string;
  description?: string;
  remediation?: string;
  raw_tool_severity?: string;
  corroborated_by?: string[];
  probe_id?: string;
  probe_suite?: string;
  scoring_excluded?: boolean;
};

export type ComparisonCell = {
  display: string;
  score_class?: string;
  slug?: string;
};

export type ComparisonRow = {
  key: string;
  label: string;
  badge_class?: string;
  cells: Record<string, ComparisonCell>;
};

export type ComparisonPayload = {
  models: string[];
  rows: ComparisonRow[];
  pillar?: string;
};

export type LiveRunStage = {
  id: string;
  label: string;
  status: "pending" | "running" | "complete" | "failed";
  duration?: string;
  count?: number;
};

export type LiveRunPayload = {
  pollUrl: string;
  intervalMs?: number;
  cancelUrl?: string;
  retryUrl?: string;
  showRetry?: boolean;
  initialStatus?: string;
  initialMessage?: string;
  hint?: string;
  stages?: LiveRunStage[];
  progressLabel?: string;
};

export type CompareModel = {
  slug: string;
  display_name: string;
  scan?: { tier?: string; overall_risk_score?: number };
  safety?: { tier?: string; pass_rate?: number };
  eval?: { best_overall?: number; mean_latency_ms?: number; total_cost_usd?: number };
  benchmark?: Record<string, { headline_value?: number; headline_display?: string }>;
};

export type CompareChartsPayload = {
  models: CompareModel[];
  mode?: "page" | "picker";
  compareUrl?: string;
};

export type OverviewChartsPayload = {
  scanTierLabels: string[];
  scanTierCounts: number[];
  safetyPassLabels: string[];
  safetyPassValues: number[];
  pillarCountLabels: string[];
  pillarCountValues: number[];
};
