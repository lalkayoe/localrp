import { useState } from "react";
import ChatSelector from "../components/ChatSelector";
import { SearchApi } from "../api/endpoints";
import { useChatStore } from "../store/chatStore";
import type { SearchResultItem } from "../api/types";
import "../styles/search.css";

const TYPE_LABELS_RU: Record<string, string> = {
  character: "Персонаж",
  location: "Локация",
  organization: "Организация",
  event: "Событие",
  fact: "Факт",
  message: "Сообщение",
};

export default function SearchPage() {
  const activeChatId = useChatStore((s) => s.activeChatId);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);

  async function runSearch() {
    if (!activeChatId || !query.trim()) return;
    setLoading(true);
    try {
      const r = await SearchApi.run(activeChatId, query.trim());
      setResults(r);
      setSearched(true);
    } finally {
      setLoading(false);
    }
  }

  const grouped = results.reduce<Record<string, SearchResultItem[]>>((acc, r) => {
    (acc[r.entity_type] ||= []).push(r);
    return acc;
  }, {});

  return (
    <div className="search-page">
      <div className="search-toolbar">
        <ChatSelector />
        <input
          className="search-input"
          placeholder="Поиск по персонажам, локациям, событиям, фактам, сообщениям..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runSearch()}
        />
        <button className="btn-small" onClick={runSearch} disabled={!activeChatId || !query.trim()}>
          Найти
        </button>
      </div>

      <div className="search-results scrollbar-subtle">
        {loading && <div className="memory-empty">Ищем...</div>}
        {!loading && searched && results.length === 0 && <div className="memory-empty centered">Ничего не найдено</div>}
        {!loading &&
          Object.entries(grouped).map(([type, items]) => (
            <div key={type} className="search-group">
              <div className="search-group-title">{TYPE_LABELS_RU[type] || type}</div>
              {items.map((item) => (
                <div key={`${item.entity_type}-${item.entity_id}`} className="search-result-item">
                  <div className="search-result-title">{item.title}</div>
                  <div className="search-result-snippet">{item.snippet}</div>
                </div>
              ))}
            </div>
          ))}
      </div>
    </div>
  );
}
