// Mirrors src/glean/config/schema.py (subset relevant for editing).

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

export type StageName = "dedup" | "rank" | "summarize" | "digest" | "apply_skill";
export type StageSpecYaml = string | { [stageName: string]: Record<string, unknown> };

export interface StageSpec {
  name: StageName;
  params?: Record<string, unknown>;
}

export type BootstrapMode = "skip-and-mark" | "send-last-N" | "send-all";

export interface FeedConfig {
  name: string;
  schedule: string;
  chat_id?: string | number | null;
  sinks?: Array<Record<string, unknown>> | null;
  sources: Array<Record<string, unknown>>;
  pipeline: StageSpec[] | StageSpecYaml[];
  llm?: LLMConfig | null;
  render?: RenderConfig | null;
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
