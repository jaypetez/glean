export interface HealthStatus {
  status: "ok" | "degraded";
  db: "ok" | "error";
  scheduler: "running" | "stopped" | "n/a";
  version: string;
  uptime_s: number;
  uptime_seconds: number;
  feed_count: number;
  last_run_age_seconds: number | null;
  alert_active_feeds: string[];
}

export async function fetchHealthStatus(): Promise<HealthStatus> {
  const response = await fetch("/healthz");
  if (!response.ok) {
    throw new Error(`GET /healthz -> ${response.status}`);
  }
  return (await response.json()) as HealthStatus;
}

export function formatUptime(seconds: number | undefined): string {
  const total = Math.max(0, Math.floor(seconds ?? 0));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const parts = [
    days ? `${days}d` : null,
    hours ? `${hours}h` : null,
    minutes ? `${minutes}m` : null,
    `${secs}s`,
  ].filter((part): part is string => part !== null);
  return parts.join(" ");
}

export function formatDateTime(value: Date | null): string {
  return value ? value.toLocaleString() : "Not yet";
}
