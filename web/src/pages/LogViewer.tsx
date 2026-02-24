import { useEffect, useRef, useState, useCallback } from "react";
import { Select, Input, Radio, Button, Space, Tag, message } from "antd";
import {
  ClearOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  DisconnectOutlined,
} from "@ant-design/icons";
import { fetchLogHistory, type LogEntry } from "../api/logs";

const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];

const LEVEL_COLOR: Record<string, string> = {
  DEBUG: "#8c8c8c",
  INFO: "#52c41a",
  WARNING: "#faad14",
  ERROR: "#ff4d4f",
  CRITICAL: "#ff4d4f",
};

const MAX_LIVE_ENTRIES = 5000;
const PAGE_SIZE = 200;
const RECONNECT_DELAY_MS = 3000;

type Mode = "live" | "history";

export default function LogViewer() {
  const [mode, setMode] = useState<Mode>("live");
  const [level, setLevel] = useState<string | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const [connected, setConnected] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const pausedRef = useRef(false);
  const bufferRef = useRef<LogEntry[]>([]);

  // Keep pausedRef in sync so SSE callback can read it without re-subscribing
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  // --- Live mode SSE (stays connected even when paused) ---
  useEffect(() => {
    if (mode !== "live") return;

    setLogs([]);
    bufferRef.current = [];

    const connect = () => {
      const url = `/api/logs/stream${level ? `?level=${level}` : ""}`;
      const es = new EventSource(url);
      esRef.current = es;

      es.onopen = () => setConnected(true);

      es.onmessage = (e) => {
        try {
          const entry = JSON.parse(e.data) as LogEntry;
          if (pausedRef.current) {
            // Buffer while paused, cap buffer too
            if (bufferRef.current.length < MAX_LIVE_ENTRIES) {
              bufferRef.current.push(entry);
            }
          } else {
            setLogs((prev) => {
              const next = [...prev, entry];
              return next.length > MAX_LIVE_ENTRIES
                ? next.slice(-MAX_LIVE_ENTRIES)
                : next;
            });
          }
        } catch {
          // ignore parse errors
        }
      };

      es.onerror = () => {
        es.close();
        esRef.current = null;
        setConnected(false);
        // Auto-reconnect after delay
        setTimeout(() => {
          if (esRef.current === null) connect();
        }, RECONNECT_DELAY_MS);
      };
    };

    connect();

    return () => {
      esRef.current?.close();
      esRef.current = null;
      setConnected(false);
    };
  }, [mode, level]);

  // Flush buffer when unpausing
  useEffect(() => {
    if (!paused && bufferRef.current.length > 0) {
      const buffered = bufferRef.current;
      bufferRef.current = [];
      setLogs((prev) => {
        const merged = [...prev, ...buffered];
        return merged.length > MAX_LIVE_ENTRIES
          ? merged.slice(-MAX_LIVE_ENTRIES)
          : merged;
      });
    }
  }, [paused]);

  // Auto-scroll in live mode (only when not paused)
  useEffect(() => {
    if (mode === "live" && !paused) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, mode, paused]);

  // --- History mode ---
  const loadHistory = useCallback(
    async (page: number) => {
      setLoading(true);
      try {
        const res = await fetchLogHistory({
          page,
          page_size: PAGE_SIZE,
          level: level || undefined,
          search: search || undefined,
        });
        setLogs(res.items);
        setHistoryTotal(res.total);
        setHistoryPage(page);
      } catch (err) {
        message.error("日志加载失败");
        console.error("Failed to load log history:", err);
      } finally {
        setLoading(false);
      }
    },
    [level, search],
  );

  useEffect(() => {
    if (mode === "history") {
      loadHistory(1);
    }
  }, [mode, loadHistory]);

  const handleModeChange = (m: Mode) => {
    setLogs([]);
    setPaused(false);
    bufferRef.current = [];
    setMode(m);
  };

  const handleClear = () => setLogs([]);

  const handleSearchSubmit = () => {
    if (mode === "history") loadHistory(1);
  };

  const totalPages = Math.ceil(historyTotal / PAGE_SIZE);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minHeight: 0,
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 0",
          flexWrap: "wrap",
        }}
      >
        <Radio.Group
          value={mode}
          onChange={(e) => handleModeChange(e.target.value)}
          optionType="button"
          buttonStyle="solid"
          size="small"
        >
          <Radio.Button value="live">实时</Radio.Button>
          <Radio.Button value="history">历史</Radio.Button>
        </Radio.Group>

        <Select
          placeholder="日志级别"
          allowClear
          value={level}
          onChange={(v) => setLevel(v)}
          style={{ width: 120 }}
          size="small"
          options={LEVELS.map((l) => ({ label: l, value: l }))}
        />

        {mode === "history" && (
          <Input.Search
            placeholder="搜索关键词"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onSearch={handleSearchSubmit}
            style={{ width: 200 }}
            size="small"
            allowClear
          />
        )}

        <Space>
          {mode === "live" && (
            <Button
              size="small"
              icon={paused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
              onClick={() => setPaused(!paused)}
            >
              {paused ? "继续" : "暂停"}
            </Button>
          )}
          <Button size="small" icon={<ClearOutlined />} onClick={handleClear}>
            清屏
          </Button>
        </Space>

        {mode === "history" && (
          <Space size={4}>
            <Button
              size="small"
              disabled={historyPage <= 1 || loading}
              onClick={() => loadHistory(historyPage - 1)}
            >
              上一页
            </Button>
            <span style={{ fontSize: 12, color: "#666" }}>
              {historyPage} / {totalPages || 1}
            </span>
            <Button
              size="small"
              disabled={historyPage >= totalPages || loading}
              onClick={() => loadHistory(historyPage + 1)}
            >
              下一页
            </Button>
          </Space>
        )}

        <span style={{ fontSize: 12, color: "#999", marginLeft: "auto" }}>
          {mode === "live" && !connected && (
            <DisconnectOutlined style={{ color: "#ff4d4f", marginRight: 6 }} />
          )}
          {logs.length} 条日志
        </span>
      </div>

      {/* Log panel */}
      <div
        style={{
          flex: 1,
          background: "#1a1a2e",
          borderRadius: 8,
          padding: "12px 16px",
          overflowY: "auto",
          fontFamily: "'Menlo', 'Consolas', monospace",
          fontSize: 13,
          lineHeight: 1.7,
          minHeight: 0,
        }}
      >
        {logs.length === 0 && (
          <div style={{ color: "#555", textAlign: "center", marginTop: 60 }}>
            {mode === "live"
              ? "等待日志..."
              : loading
                ? "加载中..."
                : "无匹配日志"}
          </div>
        )}
        {logs.map((entry, i) => (
          <div key={i} style={{ marginBottom: 2 }}>
            <span style={{ color: "#555", fontSize: 11, marginRight: 8 }}>
              {entry.ts}
            </span>
            <Tag
              color={LEVEL_COLOR[entry.level] || "#8c8c8c"}
              style={{
                fontSize: 10,
                lineHeight: "16px",
                padding: "0 4px",
                marginRight: 6,
                borderRadius: 3,
              }}
            >
              {entry.level}
            </Tag>
            <span style={{ color: "#7ec8e3", fontSize: 11, marginRight: 8 }}>
              {entry.name}
            </span>
            <span style={{ color: "#d4d4d4" }}>{entry.msg}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
