import type { MemoryFlags } from "../api/types";

interface Props {
  flags: MemoryFlags;
  onChange: (patch: Partial<MemoryFlags>) => void;
}

export default function MemoryFlagsBar({ flags, onChange }: Props) {
  return (
    <div className="flags-bar">
      <button
        className={`flag-pill ${flags.is_pinned ? "on pinned" : ""}`}
        onClick={() => onChange({ is_pinned: !flags.is_pinned })}
        title="Закреплено — всегда попадает в промпт, минуя оценку релевантности"
      >
        📌 Закреп
      </button>
      <button
        className={`flag-pill ${flags.is_canon ? "on canon" : ""}`}
        onClick={() => onChange({ is_canon: !flags.is_canon, is_false: flags.is_canon ? flags.is_false : false })}
        title="Канон — считается достоверным фактом истории"
      >
        ✓ Канон
      </button>
      <button
        className={`flag-pill ${flags.is_false ? "on false" : ""}`}
        onClick={() => onChange({ is_false: !flags.is_false, is_canon: flags.is_false ? flags.is_canon : false })}
        title="Помечено как ложное — исключается из памяти"
      >
        ✕ Ложь
      </button>
      <button
        className={`flag-pill ${!flags.is_enabled ? "on disabled" : ""}`}
        onClick={() => onChange({ is_enabled: !flags.is_enabled })}
        title="Отключить без удаления"
      >
        {flags.is_enabled ? "👁 Активно" : "🚫 Отключено"}
      </button>
      <label className="importance-slider">
        Важность
        <input
          type="range"
          min={1}
          max={10}
          value={flags.importance}
          onChange={(e) => onChange({ importance: Number(e.target.value) })}
        />
        <span>{flags.importance}</span>
      </label>
    </div>
  );
}
