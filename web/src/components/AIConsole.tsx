import { useEffect, useRef, useState } from 'react';

interface Message {
  type: string;
  content: string;
}

interface Props {
  storyId: number;
  active: boolean;
  onDone?: () => void;
}

const roleColor: Record<string, string> = {
  assistant: '#52c41a',
  tool: '#1890ff',
  error: '#ff4d4f',
  system: '#faad14',
};

export default function AIConsole({ storyId, active, onDone }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!active) return;

    const es = new EventSource(`/api/stories/${storyId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const msg: Message = JSON.parse(e.data);
        setMessages((prev) => [...prev, msg]);
        if (msg.type === 'done' || msg.type === 'error') {
          es.close();
          onDone?.();
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
    };
  }, [storyId, active, onDone]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div
      style={{
        background: '#1e1e1e',
        color: '#d4d4d4',
        borderRadius: 8,
        padding: 16,
        fontFamily: "'Menlo', 'Consolas', monospace",
        fontSize: 13,
        lineHeight: 1.6,
        maxHeight: 500,
        overflowY: 'auto',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {messages.length === 0 && (
        <div style={{ color: '#666' }}>等待 AI 输出...</div>
      )}
      {messages.map((msg, i) => (
        <div key={i} style={{ color: roleColor[msg.type] || '#d4d4d4', marginBottom: 4 }}>
          <span style={{ opacity: 0.5 }}>[{msg.type}]</span> {msg.content}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
