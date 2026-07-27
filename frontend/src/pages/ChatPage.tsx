import { memo, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiFetch, apiJson } from "../api/client";
import { useChatStore } from "../store/chatStore";
import type { Message } from "../api/types";
import "../styles/chat.css";

interface StreamingState {
  content: string;
  active: boolean;
}

// Page size for message history. A long RP chat can have thousands of
// messages; fetching only a page at a time (instead of the entire chat
// every time it's opened) keeps network payload, JSON parsing, and initial
// render cost bounded — this is what was making long sessions feel fine on
// desktop but grind to a halt on a phone.
const MESSAGES_PAGE_SIZE = 200;

export default function ChatPage() {
  const { chats, activeChatId, loaded, loadChats, setActiveChatId, createChat, renameChat, deleteChat, activeChat } = useChatStore();
  const [messages, setMessages] = useState<Message[]>([]);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState<StreamingState>({ content: "", active: false });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    if (!loaded) loadChats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded]);

  useEffect(() => {
    if (activeChatId) loadMessages(activeChatId);
    else setMessages([]);
    stickToBottomRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChatId]);

  useEffect(() => {
    // Only auto-scroll if the user was already at (or near) the bottom —
    // otherwise a streaming reply would keep yanking them back down while
    // they're reading older messages. Also skip the "smooth" animation
    // during streaming: re-triggering a smooth-scroll animation on every
    // single token is itself a source of jank on slower phones.
    if (!stickToBottomRef.current) return;
    const behavior = streaming.active ? "auto" : "smooth";
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior });
  }, [messages, streaming.content]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceFromBottom < 120;
  }

  async function loadMessages(chatId: string) {
    const msgs = await apiJson<Message[]>(`/chats/${chatId}/messages?limit=${MESSAGES_PAGE_SIZE}`);
    setMessages(msgs);
    setHasMoreHistory(msgs.length === MESSAGES_PAGE_SIZE);
  }

  async function loadOlderMessages() {
    if (!activeChatId || messages.length === 0 || loadingMore) return;
    setLoadingMore(true);
    try {
      const oldest = messages[0].sequence;
      const older = await apiJson<Message[]>(
        `/chats/${activeChatId}/messages?limit=${MESSAGES_PAGE_SIZE}&before_sequence=${oldest}`,
      );
      // Prepending changes the scroll container's content height above the
      // viewport, which would otherwise yank the view to a random spot —
      // hold the current scroll offset steady across the DOM update.
      const el = scrollRef.current;
      const prevHeight = el?.scrollHeight ?? 0;
      setMessages((prev) => [...older, ...prev]);
      setHasMoreHistory(older.length === MESSAGES_PAGE_SIZE);
      requestAnimationFrame(() => {
        if (el) el.scrollTop += el.scrollHeight - prevHeight;
      });
    } finally {
      setLoadingMore(false);
    }
  }

  async function createNewChat() {
    await createChat("Новый чат");
    setSidebarOpen(false);
  }

  function startRename(chatId: string, currentTitle: string) {
    setEditingChatId(chatId);
    setEditingTitle(currentTitle);
  }

  async function commitRename() {
    if (editingChatId && editingTitle.trim()) {
      await renameChat(editingChatId, editingTitle.trim());
    }
    setEditingChatId(null);
  }

  async function handleDeleteChat(chatId: string) {
    if (!window.confirm("Удалить чат безвозвратно? Вся память и сообщения этого чата будут удалены.")) return;
    await deleteChat(chatId);
  }

  async function sendMessage() {
    if (!activeChatId || !draft.trim() || streaming.active) return;
    const content = draft;
    setDraft("");

    const optimisticUser: Message = {
      id: `temp-${Date.now()}`, role: "user", content, sequence: messages.length + 1, created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);
    setStreaming({ content: "", active: true });

    const res = await apiFetch(`/chats/${activeChatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    if (!res.body) return;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullText = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const payload = JSON.parse(line.slice(5).trim());
        if (payload.delta) {
          fullText += payload.delta;
          setStreaming({ content: fullText, active: true });
        } else if (payload.done) {
          setStreaming({ content: "", active: false });
          setMessages((prev) => [
            ...prev,
            { id: payload.message_id, role: "assistant", content: fullText, sequence: prev.length + 1, created_at: new Date().toISOString() },
          ]);
        }
      }
    }
  }

  return (
    <div className="chat-layout">
      <button className="mobile-sidebar-toggle" onClick={() => setSidebarOpen((s) => !s)}>
        ☰
      </button>

      <aside className={`chat-sidebar ${sidebarOpen ? "open" : ""}`}>
        <button className="chat-sidebar-item" style={{ textAlign: "left", border: "1px solid var(--border-hair)" }} onClick={createNewChat}>
          + Новый чат
        </button>
        <div style={{ overflowY: "auto", flex: 1 }} className="scrollbar-subtle">
          {chats.map((c) => (
            <div
              key={c.id}
              className={`chat-sidebar-item ${activeChatId === c.id ? "active" : ""}`}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              {editingChatId === c.id ? (
                <input
                  autoFocus
                  className="chat-sidebar-rename-input"
                  value={editingTitle}
                  onChange={(e) => setEditingTitle(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    if (e.key === "Escape") setEditingChatId(null);
                  }}
                />
              ) : (
                <span
                  style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  onClick={() => {
                    setActiveChatId(c.id);
                    setSidebarOpen(false);
                  }}
                >
                  {c.title}
                </span>
              )}
              <button
                className="chat-sidebar-item-action"
                title="Переименовать"
                onClick={(e) => {
                  e.stopPropagation();
                  startRename(c.id, c.title);
                }}
              >
                ✎
              </button>
              <button
                className="chat-sidebar-item-action danger"
                title="Удалить чат"
                onClick={(e) => {
                  e.stopPropagation();
                  handleDeleteChat(c.id);
                }}
              >
                🗑
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className="chat-main">
        <div className="chat-header">{activeChat()?.title || "Выберите чат"}</div>

        <div className="chat-scroll scrollbar-subtle" ref={scrollRef} onScroll={handleScroll}>
          {hasMoreHistory && (
            <button className="chat-sidebar-item" style={{ margin: "8px auto", display: "block" }} onClick={loadOlderMessages} disabled={loadingMore}>
              {loadingMore ? "Загрузка..." : "Показать более раннюю историю"}
            </button>
          )}
          {messages.map((m) => (
            <MessageRow key={m.id} message={m} />
          ))}
          {streaming.active && (
            <div className="message-row assistant">
              <div className="memory-thread" />
              <div className={`message-bubble ${streaming.content ? "" : "typing-cursor"}`}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{streaming.content}</ReactMarkdown>
                {streaming.content && <span className="typing-cursor" />}
              </div>
            </div>
          )}
        </div>

        <div className="composer">
          <div className="composer-inner">
            <textarea
              className="composer-textarea"
              rows={1}
              value={draft}
              placeholder="Напишите сообщение..."
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
            />
            <button className="send-button" disabled={!draft.trim() || streaming.active} onClick={sendMessage}>
              ↑
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

const MessageRow = memo(function MessageRow({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div className={`message-row ${isUser ? "user" : "assistant"}`}>
      {!isUser && <div className="memory-thread" />}
      <div className="message-bubble">
        {isUser ? message.content : <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>}
      </div>
    </div>
  );
});
