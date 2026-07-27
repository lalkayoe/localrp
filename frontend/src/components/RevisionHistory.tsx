import type { MemoryRevisionEntry } from "../api/types";

const CHANGE_LABELS_RU: Record<string, string> = {
  created: "создано",
  edited: "изменено",
  deleted: "удалено",
  pinned: "закреплено",
  unpinned: "откреплено",
  marked_canon: "отмечено каноном",
  marked_false: "отмечено ложным",
  enabled: "включено",
  disabled: "отключено",
};

export default function RevisionHistory({ entries }: { entries: MemoryRevisionEntry[] }) {
  if (entries.length === 0) {
    return <div className="history-empty">История изменений пуста</div>;
  }
  return (
    <ul className="history-list">
      {entries.map((e) => (
        <li key={e.id} className="history-item">
          <div className="history-item-head">
            <span className="history-change-type">
              {e.change_type
                .split(",")
                .map((c) => CHANGE_LABELS_RU[c] || c)
                .join(", ")}
            </span>
            <span className="history-date">{new Date(e.created_at).toLocaleString("ru-RU")}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
