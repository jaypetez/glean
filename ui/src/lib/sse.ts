import { getApiKey } from "./api";

export type RunEventType = "run_started" | "run_completed" | "run_failed";

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

export interface EventSubscription {
  close: () => void;
}

interface SubscribeEventsOptions {
  onEvent: (event: RunEvent) => void;
  onConnectionChange?: (connected: boolean) => void;
  onError?: (error: unknown) => void;
}

interface EventTokenResponse {
  token: string;
  expires_in: number;
}

const runEventTypes: RunEventType[] = ["run_started", "run_completed", "run_failed"];
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

  const handleRunEvent = (message: MessageEvent) => {
    try {
      const payload = JSON.parse(message.data) as unknown;
      if (isRunEvent(payload)) {
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

      for (const eventType of runEventTypes) {
        source.addEventListener(eventType, handleRunEvent);
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
