import { useState } from "react";
import ChatSelector from "../components/ChatSelector";
import { PromptInspectorApi } from "../api/endpoints";
import { useChatStore } from "../store/chatStore";
import type { PromptInspectorResponse } from "../api/types";
import "../styles/inspector.css";

export default function PromptInspectorPage() {
  const activeChatId = useChatStore((s) => s.activeChatId);
  const [draftMessage, setDraftMessage] = useState("");
  const [result, setResult] = useState<PromptInspectorResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  async function inspect() {
    if (!activeChatId) return;
    setLoading(true);
    try {
      setResult(await PromptInspectorApi.inspect(activeChatId, draftMessage));
      setExpanded(null);
    } finally {
      setLoading(false);
    }
  }

  const maxTokens = result ? Math.max(...result.blocks.map((b) => b.token_count), 1) : 1;

  return (
    <div className="inspector-page">
      <div className="inspector-toolbar">
        <ChatSelector />
      </div>

      <div className="inspector-body">
        <div className="inspector-input-pane">
          <label className="memory-field">
            <span>Черновик сообщения пользователя</span>
            <textarea
              rows={6}
              value={draftMessage}
              onChange={(e) => setDraftMessage(e.target.value)}
              placeholder="Введите сообщение, чтобы увидеть, какой промпт будет собран..."
            />
          </label>
          <button className="btn-small" onClick={inspect} disabled={!activeChatId || loading}>
            {loading ? "Собираем промпт..." : "Собрать промпт"}
          </button>

          {result && (
            <div className="inspector-total">
              Итого токенов: <strong>{result.total_tokens}</strong>
            </div>
          )}
        </div>

        <div className="inspector-blocks-pane scrollbar-subtle">
          {!result && <div className="memory-empty centered">Результат появится здесь</div>}
          {result &&
            result.blocks.map((block, idx) => (
              <div key={idx} className="inspector-block">
                <div className="inspector-block-head" onClick={() => setExpanded(expanded === idx ? null : idx)}>
                  <span className="inspector-block-label">{block.label}</span>
                  <span className="inspector-block-tokens">{block.token_count} ток.</span>
                </div>
                <div className="inspector-block-bar-track">
                  <div className="inspector-block-bar-fill" style={{ width: `${(block.token_count / maxTokens) * 100}%` }} />
                </div>

                {block.selected_entities.length > 0 && (
                  <div className="inspector-entities">
                    {block.selected_entities.map((e, i) => (
                      <div key={i} className="inspector-entity">
                        <span className="inspector-entity-type">{e.type}</span>
                        <span className="inspector-entity-label">{e.label}</span>
                        <span className="inspector-entity-score">score {e.score}</span>
                        {e.reasons.length > 0 && (
                          <span className="inspector-entity-reasons">{e.reasons.join(", ")}</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {expanded === idx && <pre className="inspector-block-content">{block.content}</pre>}
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
