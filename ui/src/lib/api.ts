/**
 * Minimal typed API client. Reads the API key from localStorage and adds
 * X-Glean-Api-Key to authenticated calls. First-run key entry is handled
 * by the app shell after /api/v1/initialize reports auth is enabled.
 */

import type {
  Defaults,
  DefaultsConfig,
  FeedConfig,
  FeedListItem,
  FeedStatus,
  RotateResponse,
  SkillConfig,
  SystemInfo,
  ValidateResponse,
} from "./types";

const API_KEY_STORAGE_KEY = "glean.api_key";

let apiKeyPromise: Promise<string> | null = null;
let authDisabled = false;

export class ApiKeyRequiredError extends Error {
  constructor() {
    super("Paste your glean API key to continue.");
    this.name = "ApiKeyRequiredError";
  }
}

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

export function getStoredApiKey(): string | null {
  return storage()?.getItem(API_KEY_STORAGE_KEY) ?? null;
}

export function setApiKey(newKey: string): void {
  const key = newKey.trim();
  storage()?.setItem(API_KEY_STORAGE_KEY, key);
  apiKeyPromise = Promise.resolve(key);
}

async function fetchApiKey(): Promise<string> {
  const stored = getStoredApiKey();
  if (stored) return stored;
  if (authDisabled) return "";
  throw new ApiKeyRequiredError();
}

function ensureApiKey(): Promise<string> {
  if (!apiKeyPromise) {
    apiKeyPromise = fetchApiKey();
  }
  return apiKeyPromise;
}

export function getApiKey(): Promise<string> {
  return ensureApiKey();
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const key = await ensureApiKey();
  const headers = new Headers(init.headers ?? {});
  if (key) headers.set("X-Glean-Api-Key", key);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(path, { ...init, headers });
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await apiFetch(path, init);
  if (!resp.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} -> ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export interface InitializeResponse {
  version: string;
  auth_disabled: boolean;
}

export async function getInitialize(): Promise<InitializeResponse> {
  const resp = await fetch("/api/v1/initialize");
  if (!resp.ok) throw new Error(`initialize: ${resp.status}`);
  const body = (await resp.json()) as InitializeResponse;
  authDisabled = body.auth_disabled;
  if (authDisabled) apiKeyPromise = Promise.resolve("");
  return body;
}

export async function validateAndStoreApiKey(candidate: string): Promise<void> {
  const key = candidate.trim();
  if (!key) throw new Error("API key is required.");

  const headers = new Headers();
  headers.set("X-Glean-Api-Key", key);
  const resp = await fetch("/api/v1/system/info", { headers });
  if (!resp.ok) {
    throw new Error(resp.status === 401 ? "Invalid API key." : `system info: ${resp.status}`);
  }
  setApiKey(key);
}

// --- Defaults ---

export async function getDefaults(): Promise<Defaults> {
  return apiJson<Defaults>("/api/v1/config/defaults");
}

export async function updateDefaults(defaults: DefaultsConfig): Promise<void> {
  const resp = await apiFetch("/api/v1/config/defaults", {
    method: "PUT",
    body: JSON.stringify(defaults),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`update defaults failed: ${resp.status} ${text}`);
  }
}

export async function rotateApiKey(): Promise<RotateResponse> {
  const response = await apiJson<RotateResponse>("/api/v1/auth/rotate", { method: "POST" });
  setApiKey(response.api_key);
  return response;
}

export async function getSystemInfo(): Promise<SystemInfo> {
  return apiJson<SystemInfo>("/api/v1/system/info");
}

// --- Feed config CRUD ---

export async function listFeedConfigs(): Promise<FeedListItem[]> {
  return apiJson<FeedListItem[]>("/api/v1/config/feeds");
}

export async function getFeedConfig(name: string): Promise<FeedConfig> {
  return apiJson<FeedConfig>(`/api/v1/config/feeds/${encodeURIComponent(name)}`);
}

export async function createFeedConfig(feed: FeedConfig): Promise<void> {
  const resp = await apiFetch("/api/v1/config/feeds", {
    method: "POST",
    body: JSON.stringify(feed),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`create feed failed: ${resp.status} ${text}`);
  }
}

export async function updateFeedConfig(name: string, feed: FeedConfig): Promise<void> {
  const resp = await apiFetch(`/api/v1/config/feeds/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify(feed),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`update feed failed: ${resp.status} ${text}`);
  }
}

export async function deleteFeedConfig(name: string): Promise<void> {
  const resp = await apiFetch(`/api/v1/config/feeds/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`delete feed failed: ${resp.status} ${text}`);
  }
}

export async function validateConfig(config: {
  defaults?: DefaultsConfig;
  feeds?: FeedConfig[];
}): Promise<ValidateResponse> {
  return apiJson<ValidateResponse>("/api/v1/config/validate", {
    method: "POST",
    body: JSON.stringify({ feeds: [], ...config }),
  });
}

export async function validateFeedConfig(
  feed: FeedConfig,
  defaults: DefaultsConfig = {}
): Promise<ValidateResponse> {
  return validateConfig({ defaults, feeds: [feed] });
}

export async function listFeedStatuses(): Promise<FeedStatus[]> {
  return apiJson<FeedStatus[]>("/api/v1/feeds");
}

export async function runFeedNow(name: string): Promise<void> {
  const resp = await apiFetch(`/api/v1/feeds/${encodeURIComponent(name)}/run`, {
    method: "POST",
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`run feed failed: ${resp.status} ${text}`);
  }
}

// --- Skill config CRUD ---

export async function listSkills(): Promise<SkillConfig[]> {
  return apiJson<SkillConfig[]>("/api/v1/config/skills");
}

export async function getSkill(name: string): Promise<SkillConfig> {
  return apiJson<SkillConfig>(`/api/v1/config/skills/${encodeURIComponent(name)}`);
}

export async function createSkill(skill: SkillConfig): Promise<void> {
  const resp = await apiFetch("/api/v1/config/skills", {
    method: "POST",
    body: JSON.stringify(skill),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`create skill failed: ${resp.status} ${text}`);
  }
}

export async function updateSkill(name: string, skill: SkillConfig): Promise<void> {
  const resp = await apiFetch(`/api/v1/config/skills/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify(skill),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`update skill failed: ${resp.status} ${text}`);
  }
}

export async function deleteSkill(name: string): Promise<void> {
  const resp = await apiFetch(`/api/v1/config/skills/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`delete skill failed: ${resp.status} ${text}`);
  }
}
