export interface Chat {
  id: string;
  title: string;
  folder_id: string | null;
  primary_character_id: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sequence: number;
  created_at: string;
}

export interface MemoryFlags {
  is_pinned: boolean;
  is_canon: boolean;
  is_false: boolean;
  is_enabled: boolean;
  importance: number;
}

export interface Character extends MemoryFlags {
  id: string;
  chat_id: string;
  name: string;
  description: string | null;
  age: string | null;
  gender: string | null;
  race: string | null;
  personality: string | null;
  backstory: string | null;
  current_state: string | null;
  updated_at: string;
}

/** Generic shape returned by the /memory/{entity_type} endpoints — every
 * entity carries the flag fields plus whatever type-specific columns the
 * backend serialized, and a computed `label` for list display. */
export interface MemoryEntity extends MemoryFlags {
  id: string;
  chat_id: string;
  entity_type: string;
  label: string;
  updated_at: string;
  created_at: string;
  [key: string]: unknown;
}

export interface MemoryRevisionEntry {
  id: string;
  change_type: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

export interface MemorySummary {
  [entityType: string]: number;
}

export interface TimelineEntry {
  story_day: number;
  title: string;
  entity_type: string;
  entity_id: string;
}

export interface SearchResultItem {
  entity_type: string;
  entity_id: string;
  chat_id: string;
  title: string;
  snippet: string;
}

export interface AppSettings {
  default_provider: string;
  default_model: string;
  default_api_base: string;
  default_context_size: number;
  default_temperature: number;
  default_top_p: number;
  default_top_k: number;
  default_repeat_penalty: number;
  default_max_tokens: number;
  memory_retrieval_mode: string;
  memory_extraction_enabled: boolean;
  ui_theme?: string;
  [key: string]: unknown;
}

export interface PromptInspectorSelectedEntity {
  type: string;
  label: string;
  score: number;
  reasons: string[];
}

export interface PromptInspectorBlock {
  label: string;
  content: string;
  token_count: number;
  selected_entities: PromptInspectorSelectedEntity[];
}

export interface PromptInspectorResponse {
  blocks: PromptInspectorBlock[];
  total_tokens: number;
}
