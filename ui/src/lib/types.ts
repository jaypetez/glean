// Mirrors src/glean/config/schema.py (subset relevant for editing).

export type ThemeChoice = "system" | "dark" | "light";
export type DensityChoice = "comfortable" | "compact";

export interface TelegramDefaults {
  bot_token?: string | null;
  chat_id?: string | number | null;
}

export interface LLMConfig {
  provider: string;
  model: string;
  base_url?: string | null;
  api_key?: string | null;
  timeout_s?: number;
}

export interface RenderConfig {
  style?: "html" | "markdown_v2" | "plain";
  link_preview?: boolean;
  max_items?: number;
}

export interface FailureConfig {
  alert_after?: number;
  ops_chat_id?: string | number | null;
}

export type BootstrapMode = "skip-and-mark" | "send-last-N" | "send-all";

export interface DefaultsConfig {
  telegram?: TelegramDefaults;
  llm?: LLMConfig;
  render?: RenderConfig;
  sinks?: Array<Record<string, unknown>> | null;
  max_llm_calls_per_run?: number | null;
  bootstrap?: BootstrapMode;
  bootstrap_count?: number;
  failure?: FailureConfig;
}

export interface Defaults extends DefaultsConfig {
  telegram: TelegramDefaults;
  llm: LLMConfig;
  render: RenderConfig;
  max_llm_calls_per_run: number | null;
  bootstrap: BootstrapMode;
  bootstrap_count: number;
  failure: FailureConfig;
}

export interface RotateResponse {
  api_key: string;
}

export interface SystemInfo {
  version: string;
  hostname: string;
  python: string;
  platform: string;
  database_path: string;
  config_path: string;
  feeds_count: number;
  uptime_seconds: number;
  started_at: string;
  llm_provider: string | null;
  llm_model: string | null;
}

export type StageName = "dedup" | "rank" | "summarize" | "digest" | "apply_skill";
export type StageSpecYaml = string | { [stageName: string]: Record<string, unknown> };

export interface StageSpec {
  name: StageName;
  params?: Record<string, unknown>;
}

export interface FeedConfig {
  name: string;
  schedule: string;
  chat_id?: string | number | null;
  sinks?: Array<Record<string, unknown>> | null;
  sources: Array<Record<string, unknown>>;
  pipeline: StageSpec[] | StageSpecYaml[];
  llm?: LLMConfig | null;
  render?: RenderConfig | null;
  max_llm_calls_per_run?: number | null;
  bootstrap?: BootstrapMode | null;
  bootstrap_count?: number | null;
  failure?: FailureConfig | null;
}

export interface FeedListItem {
  name: string;
  schedule: string;
  sources_count: number;
  pipeline_stages: string[];
  sinks_count: number;
}

export type FeedListResponse = FeedListItem;

export interface FeedStatus {
  name: string;
  schedule: string;
  llm_provider: string;
  llm_model: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  alert_active: boolean;
  bootstrapped: boolean;
}

export interface Digest {
  id: number;
  feed_name: string;
  sent_at: string;
  style: "html" | "markdown_v2" | "plain";
  intro: string | null;
  body: string;
  fragment_index: number;
  item_count: number;
  trace_id: string | null;
}

export interface ValidateResponse {
  valid: boolean;
  feeds_count: number;
  skills_count: number;
  errors: string[];
}

export type SkillFieldType =
  | "str"
  | "int"
  | "float"
  | "bool"
  | "str | None"
  | "int | None"
  | "float | None"
  | "bool | None"
  | "list[str]"
  | "list[int]"
  | "list[float]";

export const SKILL_FIELD_TYPES: readonly SkillFieldType[] = [
  "str",
  "int",
  "float",
  "bool",
  "str | None",
  "int | None",
  "float | None",
  "bool | None",
  "list[str]",
  "list[int]",
  "list[float]",
];

export interface SkillOutputField {
  type: SkillFieldType;
  description?: string | null;
  required?: boolean;
}

export interface SkillConfig {
  name: string;
  version?: string;
  description?: string | null;
  system_prompt?: string | null;
  prompt: string;
  output_schema: Record<string, SkillFieldType | SkillOutputField>;
  llm?: LLMConfig | null;
}
