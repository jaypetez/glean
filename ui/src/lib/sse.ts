import { getApiKey } from "./api";

export type RunEventType = "run_started" | "run_completed" | "run_failed";
export type DigestEventType = "digest.persisted";

export interface RunEvent {
  type: RunEventType;
  feed: string;
  timestamp: string;
  fetched: number | null;
  after_dedup: number | null;
  sent: number | null;
  duration_ms: number | null;
  error: string | null;
}

export interface DigestPersistedEvent {
  type: DigestEventType;
  feed_name: string;
  timestamp: string;
  digest_ids: number[] | null;
  sent_at: string | null;
  trace_id: string | null;
  item_count: number | null;
}

export type AppEvent = RunEvent | DigestPersistedEvent;

export interface EventSubscription {
  close: () => void;
}

interface SubscribeEventsOptions {
  onEvent: (event: AppEvent) => void;
  onConnectionChange?: (connected: boolean) => void;
  onError?: (error: unknown) => void;
}

interface EventTokenResponse {
  token: string;
  expires_in: number;
}

const runEventTypes = ["run_started", "run_completed", "run_failed"] as const;
const eventTypes = [...runEventTypes, "digest.persisted"] as const;
const initialReconnectDelayMs = 2_000;
const maxReconnectDelayMs = 30_000;

class EventTokenError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`POST /api/v1/events/token -> ${status}`);
    this.name = "EventTokenError";
    this.status = status;
  }
}

function isRunEvent(value: unknown): value is RunEvent {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<RunEvent>;
  return (
    typeof candidate.feed === "string" &&
    typeof candidate.timestamp === "string" &&
    runEventTypes.includes(candidate.type as RunEventType)
  );
}

function isDigestPersistedEvent(value: unknown): value is DigestPersistedEvent {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<DigestPersistedEvent>;
  return candidate.type === "digest.persisted" && typeof candidate.feed_name === "string";
}

function isAppEvent(value: unknown): value is AppEvent {
  return isRunEvent(value) || isDigestPersistedEvent(value);
}

function eventsUrl(token: string): string {
  const url = new URL("/api/v1/events", window.location.origin);
  url.searchParams.set("token", token);
  return `${url.pathname}${url.search}`;
}

export async function fetchEventToken(): Promise<string> {
  const apiKey = await getApiKey();
  const headers = new Headers();
  if (apiKey) headers.set("X-Glean-Api-Key", apiKey);
  const resp = await fetch("/api/v1/events/token", { method: "POST", headers });
  if (!resp.ok) throw new EventTokenError(resp.status);
  const payload = (await resp.json()) as EventTokenResponse;
  return payload.token;
}

export function subscribeEvents(options: SubscribeEventsOptions): EventSubscription {
  let source: EventSource | null = null;
  let closed = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectDelayMs = initialReconnectDelayMs;

  const handleEvent = (message: MessageEvent) => {
    try {
      const payload = JSON.parse(message.data) as unknown;
      if (isAppEvent(payload)) {
        options.onEvent(payload);
      }
    } catch (error) {
      options.onError?.(error);
    }
  };

  function clearReconnect(): void {
    if (reconnectTimer === null) return;
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  function resetReconnectDelay(): void {
    reconnectDelayMs = initialReconnectDelayMs;
  }

  function shouldReconnect(error: unknown): boolean {
    if (error instanceof EventTokenError) {
      return error.status !== 401 && error.status !== 403;
    }
    return true;
  }

  function scheduleReconnect(): void {
    if (closed || reconnectTimer !== null) return;
    const delayMs = reconnectDelayMs;
    reconnectDelayMs = Math.min(reconnectDelayMs * 2, maxReconnectDelayMs);
    source?.close();
    source = null;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      void open();
    }, delayMs);
  }

  async function open(): Promise<void> {
    try {
      const token = await fetchEventToken();
      if (closed) return;

      source?.close();
      source = new EventSource(eventsUrl(token));
      source.onopen = () => {
        resetReconnectDelay();
        options.onConnectionChange?.(true);
      };
      source.onerror = (event) => {
        options.onConnectionChange?.(false);
        options.onError?.(event);
        scheduleReconnect();
      };

      for (const eventType of eventTypes) {
        source.addEventListener(eventType, handleEvent);
      }
    } catch (error) {
      if (!closed) {
        options.onConnectionChange?.(false);
        options.onError?.(error);
        if (shouldReconnect(error)) {
          scheduleReconnect();
        }
      }
    }
  }

  void open();

  return {
    close: () => {
      closed = true;
      clearReconnect();
      source?.close();
      source = null;
    },
  };
}
