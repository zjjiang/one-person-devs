import { useEffect, useRef, useState } from "react";
import { Input, Button, Space } from "antd";
import { SendOutlined } from "@ant-design/icons";
import MessageList, { type StreamMessage } from "./MessageList";

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
  const [messages, setMessages] = useState<StreamMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
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
              { type: "done", content: "AI 处理完成" },
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
            { type: "error", content: msg.content },
          ]);
          setLoading(false);
          return;
        }
        if (msg.type === "assistant" && msg.content) {
          hasNewAssistantMsg.current = true;
          setMessages((prev) => [
            ...prev,
            { type: "assistant", content: msg.content },
          ]);
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setLoading(false);
    };

    return () => es.close();
  }, [storyId, active]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || loading) return;
    setMessages((prev) => [...prev, { type: "user", content: text }]);
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
      <MessageList
        messages={messages}
        variant="light"
        loading={loading}
        loadingText="AI 思考中..."
        emptyText="输入消息和 AI 讨论，完善文档"
      />
      <Space.Compact style={{ margin: "0 16px 8px", flexShrink: 0 }}>
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
