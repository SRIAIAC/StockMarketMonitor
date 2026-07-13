import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../api/client";

interface Message {
  role: "user" | "assistant";
  content: string;
  used_ai?: boolean;
  searched?: boolean;
}

const SUGGESTIONS = [
  "What are today's top gainers?",
  "Show recent alerts",
  "What is the overall market sentiment?",
];

export default function ChatBot() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [webSearch, setWebSearch] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      inputRef.current?.focus();
    }
  }, [messages, open]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, history, web_search: webSearch }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.reply,
          used_ai: data.used_ai,
          searched: data.searched,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Could not reach the backend. Make sure the server is running on port 8000.",
          used_ai: false,
          searched: false,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button
        className="chat-fab"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close assistant" : "Open market assistant"}
      >
        {open ? "✕" : "💬"}
      </button>

      {open && (
        <div className="chat-panel" role="dialog" aria-label="Market assistant">
          <div className="chat-header">
            <div>
              <p className="eyebrow">AI-powered</p>
              <strong className="chat-title">Market Assistant</strong>
            </div>
            <div className="chat-header-badges">
              <span className="market-chip">RAG</span>
              <span className="market-chip">MAS</span>
            </div>
          </div>

          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="chat-intro">
                <p>
                  Ask about live NSE prices, alerts, sentiment, or how the
                  multi-agent system works. Enable <strong>Web</strong> to search
                  the internet for latest news.
                </p>
                <div className="chat-suggestions">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      className="chat-suggestion"
                      onClick={() => send(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.role}`}>
                <p className="chat-bubble-text">{m.content}</p>
                {m.role === "assistant" && (
                  <div className="chat-bubble-badges">
                    {m.used_ai && <span className="alert-ai-badge">AI</span>}
                    {m.searched && <span className="chat-web-badge">Web</span>}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="chat-bubble assistant">
                <span className="chat-typing">
                  <span />
                  <span />
                  <span />
                </span>
                {webSearch && (
                  <span className="chat-searching-label">Searching the web…</span>
                )}
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          <form
            className="chat-input-row"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <button
              type="button"
              className={`chat-web-toggle ${webSearch ? "active" : ""}`}
              onClick={() => setWebSearch((w) => !w)}
              title={webSearch ? "Web search ON — click to disable" : "Web search OFF — click to enable"}
              aria-pressed={webSearch}
            >
              🌐
            </button>
            <input
              ref={inputRef}
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={webSearch ? "Search the web + market data…" : "Ask about the market…"}
              disabled={loading}
            />
            <button
              className="chat-send"
              type="submit"
              disabled={loading || !input.trim()}
              aria-label="Send"
            >
              ↑
            </button>
          </form>
        </div>
      )}
    </>
  );
}
