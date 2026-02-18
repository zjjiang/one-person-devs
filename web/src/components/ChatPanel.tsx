import { useEffect, useRef, useState } from "react";
import { Input, Button, Space } from "antd";
import {
  SendOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
} from "@ant-design/icons";

interface ChatMessage {
  role: "user" | "assistant" | "system" | "error";
  content: string;
}

interface Props {
  storyId: number;
  active: boolean;
  onSend: (message: string) => void;
  onDocUpdated?: (content: string, filename: string) => void;
  onDone?: () => void;
}

export default function ChatPanel({
  storyId,
  active,
  onSend,
  onDocUpdated,
  onDone,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const hasNewAssistantMsg = useRef(false);

  // Stable refs for callbacks to avoid SSE reconnects
  const onDocUpdatedRef = useRef(onDocUpdated);
  onDocUpdatedRef.current = onDocUpdated;
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  // Connect to SSE stream
  useEffect(() => {
    if (!active) return;

    const es = new EventSource(`/api/stories/${storyId}/stream?mode=chat`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "doc_updated" || msg.type === "prd_updated") {
          onDocUpdatedRef.current?.(msg.content, msg.filename || "prd.md");
          return;
        }
        if (msg.type === "done") {
          if (hasNewAssistantMsg.current) {
            setMessages((prev) => [
              ...prev,
              { role: "system", content: "AI 处理完成" },
            ]);
            hasNewAssistantMsg.current = false;
          }
          setLoading(false);
          onDoneRef.current?.();
          return;
        }
        if (msg.type === "error") {
          setMessages((prev) => [
            ...prev,
            { role: "error", content: msg.content },
          ]);
          setLoading(false);
          return;
        }
        if (msg.type === "assistant" && msg.content) {
          hasNewAssistantMsg.current = true;
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: msg.content },
          ]);
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setLoading(false);
    };

    return () => {
      es.close();
    };
  }, [storyId, active]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    onSend(text);
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
      }}
    >
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "8px 0",
          minHeight: 0,
        }}
      >
        {messages.length === 0 && (
          <div style={{ color: "#999", textAlign: "center", marginTop: 40 }}>
            输入消息和 AI 讨论，完善文档
          </div>
        )}
        {messages.map((msg, i) =>
          msg.role === "system" ? (
            <div
              key={i}
              style={{
                textAlign: "center",
                padding: "6px 0",
                color: "#52c41a",
                fontSize: 12,
              }}
            >
              <CheckCircleOutlined style={{ marginRight: 4 }} />
              {msg.content}
            </div>
          ) : (
            <div
              key={i}
              style={{
                display: "flex",
                justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                marginBottom: 8,
                padding: "0 4px",
              }}
            >
              <div
                style={{
                  maxWidth: "85%",
                  padding: "8px 12px",
                  borderRadius: 8,
                  fontSize: 13,
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  ...(msg.role === "user"
                    ? { background: "#1677ff", color: "#fff" }
                    : msg.role === "error"
                      ? { background: "#fff2f0", color: "#ff4d4f" }
                      : { background: "#f5f5f5", color: "#333" }),
                }}
              >
                {msg.content}
              </div>
            </div>
          ),
        )}
        {loading && (
          <div style={{ padding: "8px 4px", color: "#999" }}>
            <LoadingOutlined /> AI 思考中...
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <Space.Compact style={{ marginTop: 8 }}>
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={handleSend}
          placeholder="输入修改意见或问题..."
          disabled={loading}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          disabled={loading || !input.trim()}
        />
      </Space.Compact>
    </div>
  );
}
