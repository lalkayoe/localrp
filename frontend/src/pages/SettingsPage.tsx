import { useEffect, useState } from "react";
import { SettingsApi } from "../api/endpoints";
import type { AppSettings } from "../api/types";
import { THEMES, applyTheme, getStoredTheme, storeTheme } from "../theme";
import "../styles/settings.css";

const PROVIDERS = [
  { value: "llama_cpp", label: "llama.cpp" },
  { value: "lmstudio", label: "LM Studio" },
  { value: "ollama", label: "Ollama" },
  { value: "openai_compatible", label: "OpenAI Compatible API" },
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    SettingsApi.get().then((s) => {
      setSettings(s);
      // The backend is the source of truth once fetched (so the choice follows
      // you across devices) — reconcile it with whatever was applied instantly
      // from localStorage on page load, in case they differ.
      const backendTheme = typeof s.ui_theme === "string" ? s.ui_theme : null;
      if (backendTheme && backendTheme !== getStoredTheme()) {
        applyTheme(backendTheme);
        storeTheme(backendTheme);
      }
    });
  }, []);

  function selectTheme(themeId: string) {
    applyTheme(themeId);
    storeTheme(themeId);
    commit("ui_theme", themeId);
  }

  async function commit(key: string, value: unknown) {
    if (!settings) return;
    setSettings({ ...settings, [key]: value });
    await SettingsApi.set(key, value);
    setSaved(true);
    setTimeout(() => setSaved(false), 1200);
  }

  if (!settings) return <div className="memory-empty">Загрузка...</div>;

  return (
    <div className="settings-page scrollbar-subtle">
      <h2>Настройки</h2>
      {saved && <div className="settings-saved-toast">Сохранено</div>}

      <section className="settings-section">
        <h3>Внешний вид</h3>
        <div className="theme-swatch-grid">
          {THEMES.map((t) => {
            const active = (typeof settings.ui_theme === "string" ? settings.ui_theme : "graphite") === t.id;
            return (
              <button
                key={t.id}
                className={`theme-swatch ${active ? "active" : ""}`}
                onClick={() => selectTheme(t.id)}
                title={t.name}
              >
                <span className="theme-swatch-preview" style={{ background: t.swatch[0] }}>
                  <span className="theme-swatch-dot" style={{ background: t.swatch[1] }} />
                </span>
                <span className="theme-swatch-name">{t.name}</span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="settings-section">
        <h3>Провайдер модели</h3>
        <label className="settings-field">
          <span>Провайдер</span>
          <select value={settings.default_provider} onChange={(e) => commit("default_provider", e.target.value)}>
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="settings-field">
          <span>Модель</span>
          <input
            value={settings.default_model}
            onChange={(e) => setSettings({ ...settings, default_model: e.target.value })}
            onBlur={(e) => commit("default_model", e.target.value)}
            placeholder="gemma-4-26b"
          />
        </label>
        <label className="settings-field">
          <span>API URL</span>
          <input
            value={settings.default_api_base}
            onChange={(e) => setSettings({ ...settings, default_api_base: e.target.value })}
            onBlur={(e) => commit("default_api_base", e.target.value)}
            placeholder="http://localhost:11434"
          />
        </label>
      </section>

      <section className="settings-section">
        <h3>Параметры генерации</h3>
        <div className="settings-grid">
          <NumberField label="Context Size" value={settings.default_context_size} onCommit={(v) => commit("default_context_size", v)} step={512} />
          <NumberField label="Temperature" value={settings.default_temperature} onCommit={(v) => commit("default_temperature", v)} step={0.05} />
          <NumberField label="Top P" value={settings.default_top_p} onCommit={(v) => commit("default_top_p", v)} step={0.01} />
          <NumberField label="Top K" value={settings.default_top_k} onCommit={(v) => commit("default_top_k", v)} step={1} />
          <NumberField label="Repeat Penalty" value={settings.default_repeat_penalty} onCommit={(v) => commit("default_repeat_penalty", v)} step={0.01} />
          <NumberField label="Max Tokens" value={settings.default_max_tokens} onCommit={(v) => commit("default_max_tokens", v)} step={64} />
        </div>
      </section>

      <section className="settings-section">
        <h3>Память</h3>
        <label className="settings-field">
          <span>Режим извлечения релевантности</span>
          <select value={settings.memory_retrieval_mode} onChange={(e) => commit("memory_retrieval_mode", e.target.value)}>
            <option value="tags">По тегам/сущностям</option>
            <option value="embeddings">По эмбеддингам</option>
            <option value="hybrid">Гибридный</option>
          </select>
        </label>
        <label className="settings-checkbox">
          <input
            type="checkbox"
            checked={settings.memory_extraction_enabled}
            onChange={(e) => commit("memory_extraction_enabled", e.target.checked)}
          />
          <span>Автоматическое извлечение памяти после каждого ответа</span>
        </label>
      </section>
    </div>
  );
}

function NumberField({ label, value, onCommit, step }: { label: string; value: number; onCommit: (v: number) => void; step: number }) {
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);
  return (
    <label className="settings-field">
      <span>{label}</span>
      <input
        type="number"
        step={step}
        value={local}
        onChange={(e) => setLocal(Number(e.target.value))}
        onBlur={() => onCommit(local)}
      />
    </label>
  );
}
