import { useEffect, useState } from "react";
import ChatSelector from "../components/ChatSelector";
import MemoryFlagsBar from "../components/MemoryFlagsBar";
import { CharactersApi } from "../api/endpoints";
import { useChatStore } from "../store/chatStore";
import type { Character, MemoryFlags } from "../api/types";
import "../styles/characters.css";

export default function CharactersPage() {
  const activeChatId = useChatStore((s) => s.activeChatId);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Partial<Character>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (activeChatId) load();
    else {
      setCharacters([]);
      setSelectedId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChatId]);

  useEffect(() => {
    const c = characters.find((x) => x.id === selectedId);
    setDraft(c ? { ...c } : {});
  }, [selectedId, characters]);

  async function load() {
    if (!activeChatId) return;
    setLoading(true);
    try {
      setCharacters(await CharactersApi.list(activeChatId));
    } finally {
      setLoading(false);
    }
  }

  async function createCharacter() {
    if (!activeChatId) return;
    const created = await CharactersApi.create(activeChatId, { name: "Новый персонаж" });
    setCharacters((prev) => [...prev, created]);
    setSelectedId(created.id);
  }

  async function save() {
    if (!activeChatId || !selectedId) return;
    const { name, description, age, gender, race, personality, backstory, current_state } = draft;
    const updated = await CharactersApi.update(activeChatId, selectedId, {
      name, description, age, gender, race, personality, backstory, current_state,
    });
    setCharacters((prev) => prev.map((c) => (c.id === selectedId ? updated : c)));
  }

  async function setFlags(patch: Partial<MemoryFlags>) {
    if (!activeChatId || !selectedId) return;
    const updated = await CharactersApi.setFlags(activeChatId, selectedId, patch);
    setCharacters((prev) => prev.map((c) => (c.id === selectedId ? updated : c)));
  }

  async function remove(id: string) {
    if (!activeChatId) return;
    if (!confirm("Удалить персонажа безвозвратно?")) return;
    await CharactersApi.remove(activeChatId, id);
    setCharacters((prev) => prev.filter((c) => c.id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  const selected = characters.find((c) => c.id === selectedId) || null;

  return (
    <div className="characters-layout">
      <div className="characters-toolbar">
        <ChatSelector />
        <button className="btn-small" onClick={createCharacter} disabled={!activeChatId}>
          + Новый персонаж
        </button>
      </div>

      <div className="characters-body">
        <div className="characters-grid scrollbar-subtle">
          {loading && <div className="memory-empty">Загрузка...</div>}
          {!loading && characters.length === 0 && <div className="memory-empty">Персонажей пока нет</div>}
          {characters.map((c) => (
            <div
              key={c.id}
              className={`character-card ${selectedId === c.id ? "active" : ""} ${!c.is_enabled ? "disabled" : ""}`}
              onClick={() => setSelectedId(c.id)}
            >
              <div className="character-card-avatar">{c.name.slice(0, 1).toUpperCase()}</div>
              <div className="character-card-name">{c.name}</div>
              <div className="character-card-state">{c.current_state || c.description || "—"}</div>
              <div className="character-card-badges">
                {c.is_pinned && <span className="badge pinned">📌</span>}
                {c.is_canon && !c.is_false && <span className="badge canon">✓ канон</span>}
                {c.is_false && <span className="badge false">✕ ложь</span>}
              </div>
            </div>
          ))}
        </div>

        <div className="character-detail scrollbar-subtle">
          {!selected && <div className="memory-empty centered">Выберите персонажа слева</div>}
          {selected && (
            <>
              <div className="memory-detail-head">
                <h3>{selected.name}</h3>
                <button className="btn-small danger" onClick={() => remove(selected.id)}>
                  Удалить
                </button>
              </div>

              <MemoryFlagsBar flags={selected} onChange={setFlags} />

              <div className="memory-form">
                <label className="memory-field">
                  <span>Имя</span>
                  <input value={draft.name || ""} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} onBlur={save} />
                </label>
                <div className="field-row">
                  <label className="memory-field">
                    <span>Возраст</span>
                    <input value={draft.age || ""} onChange={(e) => setDraft((d) => ({ ...d, age: e.target.value }))} onBlur={save} />
                  </label>
                  <label className="memory-field">
                    <span>Пол</span>
                    <input value={draft.gender || ""} onChange={(e) => setDraft((d) => ({ ...d, gender: e.target.value }))} onBlur={save} />
                  </label>
                  <label className="memory-field">
                    <span>Раса</span>
                    <input value={draft.race || ""} onChange={(e) => setDraft((d) => ({ ...d, race: e.target.value }))} onBlur={save} />
                  </label>
                </div>
                <label className="memory-field">
                  <span>Описание</span>
                  <textarea rows={2} value={draft.description || ""} onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} onBlur={save} />
                </label>
                <label className="memory-field">
                  <span>Характер</span>
                  <textarea rows={2} value={draft.personality || ""} onChange={(e) => setDraft((d) => ({ ...d, personality: e.target.value }))} onBlur={save} />
                </label>
                <label className="memory-field">
                  <span>История</span>
                  <textarea rows={3} value={draft.backstory || ""} onChange={(e) => setDraft((d) => ({ ...d, backstory: e.target.value }))} onBlur={save} />
                </label>
                <label className="memory-field">
                  <span>Текущее состояние</span>
                  <textarea rows={2} value={draft.current_state || ""} onChange={(e) => setDraft((d) => ({ ...d, current_state: e.target.value }))} onBlur={save} />
                </label>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
