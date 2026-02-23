import { useEffect, useRef } from "react";
import {
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from "@ant-design/icons";

export interface StreamMessage {
  type: string;
  content: string;
}

type Variant = "light" | "dark";

interface Props {
  messages: StreamMessage[];
  variant?: Variant;
  loading?: boolean;
  loadingText?: string;
  emptyText?: string;
}

const bubbleBase = {
  maxWidth: "85%",
  padding: "8px 12px",
  borderRadius: 8,
  fontSize: 13,
  lineHeight: 1.6 as const,
  whiteSpace: "pre-wrap" as const,
  wordBreak: "break-word" as const,
};

const centerBase = {
  textAlign: "center" as const,
  padding: "6px 0",
  fontSize: 12,
};

const theme = {
  light: {
    bg: "transparent",
    empty: "#999",
    loading: "#999",
    assistant: { background: "#f5f5f5", color: "#333" },
    tool: { background: "#e6f4ff", color: "#333" },
    user: { background: "#1677ff", color: "#fff" },
  },
  dark: {
    bg: "#1a1a2e",
    empty: "#555",
    loading: "#888",
    assistant: { background: "#2a2a4a", color: "#d4d4d4" },
    tool: { background: "#1a2a3a", color: "#7ec8e3" },
    user: { background: "#1677ff", color: "#fff" },
  },
};

// Dark mode: role label colors and display names
const roleColor: Record<string, string> = {
  assistant: "#52c41a",
  tool: "#1890ff",
  error: "#ff4d4f",
  system: "#faad14",
  done: "#52c41a",
};
const roleLabel: Record<string, string> = {
  assistant: "AI",
  tool: "Tool",
  error: "Error",
  system: "System",
  done: "Done",
};

function formatTime(): string {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function renderLightMessage(
  msg: StreamMessage,
  i: number,
  t: (typeof theme)["light"],
) {
  const leftBubble = (style: Record<string, string>) => (
    <div
      key={i}
      style={{
        display: "flex",
        justifyContent: "flex-start",
        marginBottom: 8,
        padding: "0 4px",
      }}
    >
      <div style={{ ...bubbleBase, ...style }}>{msg.content}</div>
    </div>
  );

  switch (msg.type) {
    case "system":
      return (
        <div key={i} style={{ ...centerBase, color: "#faad14" }}>
          <LoadingOutlined style={{ marginRight: 4 }} />
          {msg.content}
        </div>
      );
    case "done":
      return (
        <div key={i} style={{ ...centerBase, color: "#52c41a" }}>
          <CheckCircleOutlined style={{ marginRight: 4 }} />
          {msg.content}
        </div>
      );
    case "error":
      return (
        <div key={i} style={{ ...centerBase, color: "#ff4d4f" }}>
          <CloseCircleOutlined style={{ marginRight: 4 }} />
          {msg.content}
        </div>
      );
    case "user":
      return (
        <div
          key={i}
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginBottom: 8,
            padding: "0 4px",
          }}
        >
          <div style={{ ...bubbleBase, ...t.user }}>{msg.content}</div>
        </div>
      );
    case "tool":
      return leftBubble(t.tool);
    default:
      return leftBubble(t.assistant);
  }
}

function renderDarkMessage(msg: StreamMessage, i: number) {
  const color = roleColor[msg.type] || "#d4d4d4";
  const label = roleLabel[msg.type] || msg.type;
  return (
    <div key={i} style={{ marginBottom: 6 }}>
      <span style={{ color: "#555", fontSize: 11, marginRight: 8 }}>
        {formatTime()}
      </span>
      <span
        style={{
          color,
          fontWeight: 600,
          fontSize: 11,
          padding: "1px 6px",
          borderRadius: 3,
          background: `${color}18`,
          marginRight: 8,
        }}
      >
        {label}
      </span>
      <span style={{ color: "#d4d4d4" }}>{msg.content}</span>
    </div>
  );
}

export default function MessageList({
  messages,
  variant = "light",
  loading = false,
  loadingText = "AI 处理中...",
  emptyText = "等待 AI 输出...",
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const t = theme[variant];
  const isDark = variant === "dark";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "8px 16px",
        minHeight: 0,
        background: t.bg,
        borderRadius: isDark ? 8 : 0,
        fontFamily: isDark ? "'Menlo', 'Consolas', monospace" : undefined,
        fontSize: isDark ? 13 : undefined,
        lineHeight: isDark ? 1.6 : undefined,
        whiteSpace: isDark ? "pre-wrap" : undefined,
        wordBreak: isDark ? "break-word" : undefined,
      }}
    >
      {messages.length === 0 && !loading && (
        <div style={{ color: t.empty, textAlign: "center", marginTop: 40 }}>
          {emptyText}
        </div>
      )}
      {messages.map((msg, i) =>
        isDark ? renderDarkMessage(msg, i) : renderLightMessage(msg, i, t),
      )}
      {loading && (
        <div style={{ padding: "8px 4px", color: t.loading }}>
          <LoadingOutlined /> {loadingText}
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
