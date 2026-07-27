import { useEffect, useMemo, useState } from "react";
import ChatSelector from "../components/ChatSelector";
import MemoryFlagsBar from "../components/MemoryFlagsBar";
import RevisionHistory from "../components/RevisionHistory";
import { CharactersApi, MemoryApi } from "../api/endpoints";
import { ENTITY_SCHEMAS, ENTITY_TYPE_ORDER, ENTITY_TYPE_LABELS_RU, type FieldDef } from "../api/entitySchemas";
import { useChatStore } from "../store/chatStore";
import type { Character, MemoryEntity, MemoryFlags, MemoryRevisionEntry, MemorySummary } from "../api/types";
import "../styles/memory.css";

const CHARACTER_FIELDS: FieldDef[] = [
  { key: "name", label: "Имя", kind: "text" },
  { key: "description", label: "Описание", kind: "textarea" },
  { key: "age", label: "Возраст", kind: "text" },
  { key: "gender", label: "Пол", kind: "text" },
  { key: "race", label: "Раса", kind: "text" },
  { key: "personality", label: "Характер", kind: "textarea" },
  { key: "backstory", label: "История", kind: "textarea" },
  { key: "current_state", label: "Текущее состояние", kind: "textarea" },
];

type AnyEntity = (Character | MemoryEntity) & { entity_type?: string };

export default function MemoryEditorPage() {
  const activeChatId = useChatStore((s) => s.activeChatId);
  const [entityType, setEntityType] = useState("character");
  const [summary, setSummary] = useState<MemorySummary>({});
  const [items, setItems] = useState<AnyEntity[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [history, setHistory] = useState<MemoryRevisionEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  const fields: FieldDef[] = entityType === "character" ? CHARACTER_FIELDS : ENTITY_SCHEMAS[entityType]?.fields || [];

  useEffect(() => {
    if (activeChatId) refreshSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChatId]);

  useEffect(() => {
    if (activeChatId) {
      setSelectedId(null);
      loadList();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChatId, entityType]);

  useEffect(() => {
    const selected = items.find((i) => i.id === selectedId);
    if (selected) {
      setDraft({ ...selected });
      if (activeChatId) {
        const historyCall = entityType === "character"
          ? CharactersApi.history(activeChatId, selected.id)
          : MemoryApi.history(activeChatId, entityType, selected.id);
        historyCall.then(setHistory).catch(() => setHistory([]));
      }
    } else {
      setDraft({});
      setHistory([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  async function refreshSummary() {
    if (!activeChatId) return;
    const s = await MemoryApi.summary(activeChatId);
    const charCount = (await CharactersApi.list(activeChatId)).length;
    setSummary({ character: charCount, ...s });
  }

  async function loadList() {
    if (!activeChatId) return;
    setLoading(true);
    try {
      const list = entityType === "character"
        ? await CharactersApi.list(activeChatId)
        : await MemoryApi.list(activeChatId, entityType);
      setItems(list);
    } finally {
      setLoading(false);
    }
  }

  async function saveDraft() {
    if (!activeChatId || !selectedId) return;
    const payload: Record<string, unknown> = {};
    for (const f of fields) payload[f.key] = draft[f.key];
    const updated = entityType === "character"
      ? await CharactersApi.update(activeChatId, selectedId, payload)
      : await MemoryApi.update(activeChatId, entityType, selectedId, payload);
    setItems((prev) => prev.map((i) => (i.id === selectedId ? { ...i, ...updated } : i)));
  }

  async function setFlags(patch: Partial<MemoryFlags>) {
    if (!activeChatId || !selectedId) return;
    const updated = entityType === "character"
      ? await CharactersApi.setFlags(activeChatId, selectedId, patch)
      : await MemoryApi.setFlags(activeChatId, entityType, selectedId, patch);
    setItems((prev) => prev.map((i) => (i.id === selectedId ? { ...i, ...updated } : i)));
    setDraft((prev) => ({ ...prev, ...updated }));
  }

  async function removeSelected() {
    if (!activeChatId || !selectedId) return;
    if (!confirm("Удалить эту запись памяти без возможности восстановления?")) return;
    if (entityType === "character") await CharactersApi.remove(activeChatId, selectedId);
    else await MemoryApi.remove(activeChatId, entityType, selectedId);
    setItems((prev) => prev.filter((i) => i.id !== selectedId));
    setSelectedId(null);
    refreshSummary();
  }

  async function createNew() {
    if (!activeChatId) return;
    setCreating(true);
    try {
      const base: Record<string, unknown> = {};
      for (const f of fields) base[f.key] = f.kind === "boolean" ? false : f.kind === "number" ? 0 : "";
      if (entityType === "character") base.name = "Новый персонаж";
      const created = entityType === "character"
        ? await CharactersApi.create(activeChatId, base as Partial<Character>)
        : await MemoryApi.create(activeChatId, entityType, base);
      setItems((prev) => [created, ...prev]);
      setSelectedId(created.id);
      refreshSummary();
    } finally {
      setCreating(false);
    }
  }

  const selected = useMemo(() => items.find((i) => i.id === selectedId) || null, [items, selectedId]);

  return (
    <div className="memory-layout">
      <div className="memory-toolbar">
        <ChatSelector />
      </div>

      <div className="memory-body">
        <aside className="memory-types">
          {ENTITY_TYPE_ORDER.map((t) => (
            <button
              key={t}
              className={`memory-type-item ${entityType === t ? "active" : ""}`}
              onClick={() => setEntityType(t)}
            >
              <span>{ENTITY_TYPE_LABELS_RU[t]}</span>
              <span className="memory-type-count">{summary[t] ?? 0}</span>
            </button>
          ))}
        </aside>

        <section className="memory-list-pane">
          <div className="memory-list-head">
            <span>{ENTITY_TYPE_LABELS_RU[entityType]}</span>
            <button className="btn-small" onClick={createNew} disabled={!activeChatId || creating}>
              + Добавить
            </button>
          </div>
          <div className="memory-list scrollbar-subtle">
            {loading && <div className="memory-empty">Загрузка...</div>}
            {!loading && items.length === 0 && <div className="memory-empty">Записей пока нет</div>}
            {items.map((item) => (
              <div
                key={item.id}
                className={`memory-list-row ${selectedId === item.id ? "active" : ""} ${!item.is_enabled ? "disabled" : ""}`}
                onClick={() => setSelectedId(item.id)}
              >
                <span className="memory-row-label">
                  {"name" in item ? (item as Character).name : (item as MemoryEntity).label}
                </span>
                <span className="memory-row-badges">
                  {item.is_pinned && <span className="badge pinned">📌</span>}
                  {item.is_canon && !item.is_false && <span className="badge canon">✓</span>}
                  {item.is_false && <span className="badge false">✕</span>}
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="memory-detail-pane scrollbar-subtle">
          {!selected && <div className="memory-empty centered">Выберите запись слева</div>}
          {selected && (
            <>
              <div className="memory-detail-head">
                <h3>{"name" in selected ? (selected as Character).name : (selected as MemoryEntity).label}</h3>
                <button className="btn-small danger" onClick={removeSelected}>
                  Удалить
                </button>
              </div>

              <MemoryFlagsBar flags={selected as MemoryFlags} onChange={setFlags} />

              <div className="memory-form">
                {fields.map((f) => (
                  <label key={f.key} className="memory-field">
                    <span>{f.label}</span>
                    {f.kind === "textarea" && (
                      <textarea
                        rows={3}
                        value={(draft[f.key] as string) || ""}
                        onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                        onBlur={saveDraft}
                      />
                    )}
                    {f.kind === "text" && (
                      <input
                        type="text"
                        value={(draft[f.key] as string) || ""}
                        onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                        onBlur={saveDraft}
                      />
                    )}
                    {f.kind === "number" && (
                      <input
                        type="number"
                        value={(draft[f.key] as number) ?? 0}
                        onChange={(e) => setDraft((d) => ({ ...d, [f.key]: Number(e.target.value) }))}
                        onBlur={saveDraft}
                      />
                    )}
                    {f.kind === "boolean" && (
                      <input
                        type="checkbox"
                        checked={Boolean(draft[f.key])}
                        onChange={(e) => {
                          setDraft((d) => ({ ...d, [f.key]: e.target.checked }));
                          setTimeout(saveDraft, 0);
                        }}
                      />
                    )}
                  </label>
                ))}
              </div>

              <div className="memory-history-block">
                <h4>История изменений</h4>
                <RevisionHistory entries={history} />
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
