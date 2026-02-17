import { useEffect, useRef, useState } from "react";

interface Message {
  type: string;
  content: string;
  timestamp?: number;
}

interface Props {
  storyId: number;
  active: boolean;
  onDone?: () => void;
}

const roleColor: Record<string, string> = {
  assistant: "#52c41a",
  tool: "#1890ff",
  error: "#ff4d4f",
  system: "#faad14",
};

const roleLabel: Record<string, string> = {
  assistant: "AI",
  tool: "Tool",
  error: "Error",
  system: "System",
};

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString("zh-CN", { hour12: false });
}

export default function AIConsole({ storyId, active, onDone }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  // Elapsed time counter
  useEffect(() => {
    if (!active || !running) return;
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(timer);
  }, [active, running]);

  useEffect(() => {
    if (!active) return;

    const es = new EventSource(`/api/stories/${storyId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as Message;
        const enriched = { ...msg, timestamp: Date.now() };
        setMessages((prev) => [...prev, enriched]);
        if (msg.type === "done" || msg.type === "error") {
          setRunning(false);
          es.close();
          onDone?.();
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setRunning(false);
      es.close();
    };

    return () => {
      es.close();
    };
  }, [storyId, active, onDone]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div
      style={{
        background: "#1a1a2e",
        borderRadius: 8,
        fontFamily: "'Menlo', 'Consolas', monospace",
        fontSize: 13,
        lineHeight: 1.6,
        maxHeight: 500,
        overflowY: "auto",
      }}
    >
      {/* Status bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 16px",
          borderBottom: "1px solid #2a2a4a",
          fontSize: 12,
          color: "#888",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: running ? "#52c41a" : "#666",
              display: "inline-block",
              animation: running ? "pulse 1.5s ease-in-out infinite" : "none",
            }}
          />
          <span>
            {running
              ? "AI 运行中"
              : messages.some((m) => m.type === "error")
                ? "执行出错"
                : "执行完成"}
          </span>
        </div>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          ⏱ {formatElapsed(elapsed)}
        </span>
      </div>

      {/* Messages */}
      <div
        style={{
          padding: "8px 16px",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {messages.length === 0 && (
          <div style={{ color: "#555", padding: "16px 0" }}>
            <span className="ai-dots">等待 AI 输出</span>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              marginBottom: 6,
              animation: "fadeIn 0.3s ease-in",
            }}
          >
            <span style={{ color: "#555", fontSize: 11, marginRight: 8 }}>
              {msg.timestamp ? formatTime(msg.timestamp) : ""}
            </span>
            <span
              style={{
                color: roleColor[msg.type] || "#d4d4d4",
                fontWeight: 600,
                fontSize: 11,
                padding: "1px 6px",
                borderRadius: 3,
                background: `${roleColor[msg.type] || "#d4d4d4"}18`,
                marginRight: 8,
              }}
            >
              {roleLabel[msg.type] || msg.type}
            </span>
            <span style={{ color: "#d4d4d4" }}>{msg.content}</span>
          </div>
        ))}
        {running && messages.length > 0 && <span className="ai-cursor">▊</span>}
        <div ref={bottomRef} />
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        @keyframes dots {
          0% { content: ''; }
          25% { content: '.'; }
          50% { content: '..'; }
          75% { content: '...'; }
        }
        .ai-cursor {
          color: #52c41a;
          animation: blink 1s step-end infinite;
        }
        .ai-dots::after {
          content: '';
          animation: dots 1.5s steps(4, end) infinite;
        }
      `}</style>
    </div>
  );
}
