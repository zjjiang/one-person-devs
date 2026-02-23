import { useEffect, useState } from "react";
import MessageList, { type StreamMessage } from "./MessageList";

interface Props {
  projectId: number;
  active: boolean;
  onDone?: (msg: string) => void;
  onError?: (msg: string) => void;
}

export default function SyncConsole({
  projectId,
  active,
  onDone,
  onError,
}: Props) {
  const [messages, setMessages] = useState<StreamMessage[]>([]);
  const [running, setRunning] = useState(true);

  useEffect(() => {
    if (!active) return;

    const es = new EventSource(`/api/projects/${projectId}/sync-stream`);

    es.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as StreamMessage;
        setMessages((prev) => [...prev, msg]);
        if (msg.type === "done") {
          setRunning(false);
          es.close();
          onDone?.(msg.content || "");
        } else if (msg.type === "error") {
          setRunning(false);
          es.close();
          onError?.(msg.content || "未知错误");
        }
      } catch {
        // ignore
      }
    };

    es.onerror = () => {
      setRunning(false);
      es.close();
    };

    return () => es.close();
  }, [projectId, active, onDone, onError]);

  return (
    <MessageList
      messages={messages}
      variant="dark"
      loading={running && messages.length > 0}
      loadingText="AI 生成中..."
      emptyText="正在准备同步..."
    />
  );
}
