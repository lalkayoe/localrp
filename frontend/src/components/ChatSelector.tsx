import { useEffect } from "react";
import { useChatStore } from "../store/chatStore";

export default function ChatSelector() {
  const { chats, activeChatId, loaded, loadChats, setActiveChatId } = useChatStore();

  useEffect(() => {
    if (!loaded) loadChats();
  }, [loaded, loadChats]);

  if (loaded && chats.length === 0) {
    return <div className="chat-selector-empty">Сначала создайте чат во вкладке «Чат»</div>;
  }

  return (
    <select
      className="chat-selector"
      value={activeChatId || ""}
      onChange={(e) => setActiveChatId(e.target.value)}
    >
      {chats.map((c) => (
        <option key={c.id} value={c.id}>
          {c.title}
        </option>
      ))}
    </select>
  );
}
