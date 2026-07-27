import { useEffect, useState } from "react";
import ChatSelector from "../components/ChatSelector";
import { TimelineApi } from "../api/endpoints";
import { useChatStore } from "../store/chatStore";
import type { TimelineEntry } from "../api/types";
import "../styles/timeline.css";

export default function TimelinePage() {
  const activeChatId = useChatStore((s) => s.activeChatId);
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!activeChatId) {
      setEntries([]);
      return;
    }
    setLoading(true);
    TimelineApi.get(activeChatId)
      .then(setEntries)
      .finally(() => setLoading(false));
  }, [activeChatId]);

  return (
    <div className="timeline-page">
      <div className="timeline-toolbar">
        <ChatSelector />
      </div>

      <div className="timeline-scroll scrollbar-subtle">
        {loading && <div className="memory-empty">Загрузка...</div>}
        {!loading && entries.length === 0 && (
          <div className="memory-empty centered">
            Пока нет событий. Они появляются автоматически по мере развития истории.
          </div>
        )}
        {!loading && entries.length > 0 && (
          <ol className="timeline-track">
            {entries.map((e, idx) => (
              <li key={`${e.entity_id}-${idx}`} className="timeline-node">
                <div className="timeline-node-day">День {e.story_day}</div>
                <div className="timeline-node-dot" />
                <div className="timeline-node-title">{e.title}</div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
