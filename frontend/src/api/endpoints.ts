import { apiJson } from "./client";
import type {
  AppSettings, Character, MemoryEntity, MemoryFlags, MemoryRevisionEntry, MemorySummary,
  PromptInspectorResponse, SearchResultItem, TimelineEntry,
} from "./types";

// --- Characters -------------------------------------------------------

export const CharactersApi = {
  list: (chatId: string) => apiJson<Character[]>(`/chats/${chatId}/characters`),
  create: (chatId: string, payload: Record<string, unknown>) =>
    apiJson<Character>(`/chats/${chatId}/characters`, { method: "POST", body: JSON.stringify(payload) }),
  update: (chatId: string, id: string, payload: Record<string, unknown>) =>
    apiJson<Character>(`/chats/${chatId}/characters/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  setFlags: (chatId: string, id: string, flags: Partial<MemoryFlags>) =>
    apiJson<Character>(`/chats/${chatId}/characters/${id}/flags`, { method: "PATCH", body: JSON.stringify(flags) }),
  remove: (chatId: string, id: string) =>
    apiJson<void>(`/chats/${chatId}/characters/${id}`, { method: "DELETE" }),
  history: (chatId: string, id: string) =>
    apiJson<MemoryRevisionEntry[]>(`/chats/${chatId}/characters/${id}/history`),
};

// --- Generic memory entities -------------------------------------------

export const MemoryApi = {
  summary: (chatId: string) => apiJson<MemorySummary>(`/chats/${chatId}/memory/summary`),
  list: (chatId: string, entityType: string) =>
    apiJson<MemoryEntity[]>(`/chats/${chatId}/memory/${entityType}`),
  create: (chatId: string, entityType: string, payload: Record<string, unknown>) =>
    apiJson<MemoryEntity>(`/chats/${chatId}/memory/${entityType}`, { method: "POST", body: JSON.stringify(payload) }),
  update: (chatId: string, entityType: string, id: string, payload: Record<string, unknown>) =>
    apiJson<MemoryEntity>(`/chats/${chatId}/memory/${entityType}/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  setFlags: (chatId: string, entityType: string, id: string, flags: Record<string, unknown>) =>
    apiJson<MemoryEntity>(`/chats/${chatId}/memory/${entityType}/${id}/flags`, { method: "PATCH", body: JSON.stringify(flags) }),
  remove: (chatId: string, entityType: string, id: string) =>
    apiJson<void>(`/chats/${chatId}/memory/${entityType}/${id}`, { method: "DELETE" }),
  history: (chatId: string, entityType: string, id: string) =>
    apiJson<MemoryRevisionEntry[]>(`/chats/${chatId}/memory/${entityType}/${id}/history`),
};

// --- Timeline / Search --------------------------------------------------

export const TimelineApi = {
  get: (chatId: string) => apiJson<TimelineEntry[]>(`/chats/${chatId}/timeline`),
};

export const SearchApi = {
  run: (chatId: string, q: string) =>
    apiJson<SearchResultItem[]>(`/chats/${chatId}/search?q=${encodeURIComponent(q)}`),
};

// --- Settings -------------------------------------------------------------

export const SettingsApi = {
  get: () => apiJson<AppSettings>(`/settings`),
  set: (key: string, value: unknown) =>
    apiJson<{ key: string; value: unknown }>(`/settings/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),
};

// --- Prompt Inspector -------------------------------------------------------

export const PromptInspectorApi = {
  inspect: (chatId: string, draftMessage: string) =>
    apiJson<PromptInspectorResponse>(`/chats/${chatId}/inspect-prompt`, {
      method: "POST",
      body: JSON.stringify({ draft_message: draftMessage }),
    }),
};
