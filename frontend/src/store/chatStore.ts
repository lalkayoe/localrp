import { create } from "zustand";
import { apiJson } from "../api/client";
import type { Chat } from "../api/types";

interface ChatState {
  chats: Chat[];
  activeChatId: string | null;
  loaded: boolean;
  loadChats: () => Promise<void>;
  setActiveChatId: (id: string) => void;
  createChat: (title?: string) => Promise<Chat>;
  renameChat: (id: string, title: string) => Promise<void>;
  deleteChat: (id: string) => Promise<void>;
  activeChat: () => Chat | null;
}

export const useChatStore = create<ChatState>((set, get) => ({
  chats: [],
  activeChatId: null,
  loaded: false,

  loadChats: async () => {
    const chats = await apiJson<Chat[]>("/chats");
    set((state) => ({
      chats,
      loaded: true,
      activeChatId: state.activeChatId ?? (chats.length > 0 ? chats[0].id : null),
    }));
  },

  setActiveChatId: (id) => set({ activeChatId: id }),

  createChat: async (title = "New Chat") => {
    const chat = await apiJson<Chat>("/chats", { method: "POST", body: JSON.stringify({ title }) });
    set((state) => ({ chats: [chat, ...state.chats], activeChatId: chat.id }));
    return chat;
  },

  renameChat: async (id, title) => {
    const updated = await apiJson<Chat>(`/chats/${id}`, { method: "PATCH", body: JSON.stringify({ title }) });
    set((state) => ({ chats: state.chats.map((c) => (c.id === id ? updated : c)) }));
  },

  deleteChat: async (id) => {
    await apiJson<void>(`/chats/${id}`, { method: "DELETE" });
    set((state) => {
      const chats = state.chats.filter((c) => c.id !== id);
      const activeChatId = state.activeChatId === id ? (chats[0]?.id ?? null) : state.activeChatId;
      return { chats, activeChatId };
    });
  },

  activeChat: () => {
    const { chats, activeChatId } = get();
    return chats.find((c) => c.id === activeChatId) || null;
  },
}));
