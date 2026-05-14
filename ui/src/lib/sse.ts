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

const runEventTypes: RunEventType[] = ["run_started", "run_completed", "run_failed"];

function isRunEvent(value: unknown): value is RunEvent {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<RunEvent>;
  return (
    typeof candidate.feed === "string" &&
    typeof candidate.timestamp === "string" &&
    runEventTypes.includes(candidate.type as RunEventType)
  );
}

function eventsUrl(apiKey: string): string {
  const url = new URL("/api/v1/events", window.location.origin);
  url.searchParams.set("api_key", apiKey);
  return `${url.pathname}${url.search}`;
}

export function subscribeEvents(options: SubscribeEventsOptions): EventSubscription {
  let source: EventSource | null = null;
  let closed = false;

  const open = async () => {
    try {
      const apiKey = await getApiKey();
      if (closed) return;

      source = new EventSource(eventsUrl(apiKey));
      source.onopen = () => options.onConnectionChange?.(true);
      source.onerror = (event) => {
        options.onConnectionChange?.(false);
        options.onError?.(event);
      };

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

      for (const eventType of runEventTypes) {
        source.addEventListener(eventType, handleRunEvent);
      }
    } catch (error) {
      if (!closed) {
        options.onConnectionChange?.(false);
        options.onError?.(error);
      }
    }
  };

  void open();

  return {
    close: () => {
      closed = true;
      source?.close();
      source = null;
    },
  };
}
