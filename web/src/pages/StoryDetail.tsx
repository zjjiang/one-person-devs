import { useCallback, useEffect, useState } from "react";
import {
  Card,
  Button,
  Space,
  Typography,
  Tag,
  Descriptions,
  Table,
  Tabs,
  message,
  Divider,
  Dropdown,
} from "antd";
import { LoadingOutlined } from "@ant-design/icons";
import { useParams } from "react-router-dom";
import {
  getStory,
  confirmStage,
  iterateStory,
  restartStory,
  stopStory,
  sendChatMessage,
  saveStoryDoc,
  rollbackStory,
} from "../api/stories";
import type { Story } from "../types";
import { STAGE_LABELS } from "../types";
import StageStepper from "../components/StageStepper";
import AIConsole from "../components/AIConsole";
import PrdEditor from "../components/PrdEditor";
import ChatPanel from "../components/ChatPanel";
import ClarifyQA from "../components/ClarifyQA";

const AI_STAGES = [
  "preparing",
  "clarifying",
  "planning",
  "designing",
  "coding",
];
const DOC_CHAT_STAGES = ["preparing", "clarifying", "planning", "designing"];

// Stage → primary editable document
const STAGE_PRIMARY_DOC: Record<string, string> = {
  preparing: "prd",
  clarifying: "prd",
  planning: "technical_design",
  designing: "detailed_design",
};

// Document key → (filename, tab label)
const DOC_META: Record<string, { filename: string; label: string }> = {
  prd: { filename: "prd.md", label: "PRD" },
  technical_design: { filename: "technical_design.md", label: "技术方案" },
  detailed_design: { filename: "detailed_design.md", label: "详细设计" },
};

interface LocalDocs {
  prd: string;
  technical_design: string;
  detailed_design: string;
}

export default function StoryDetail() {
  const { id } = useParams();
  const [story, setStory] = useState<Story | null>(null);
  const [localDocs, setLocalDocs] = useState<LocalDocs>({
    prd: "",
    technical_design: "",
    detailed_design: "",
  });
  const [activeDocTab, setActiveDocTab] = useState("prd");
  const [rightPanelTab, setRightPanelTab] = useState("qa");
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(() => {
    getStory(Number(id)).then(setStory);
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll while AI is running so status updates automatically
  const aiRunning = story?.ai_running ?? false;
  useEffect(() => {
    if (!aiRunning) return;
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [aiRunning, refresh]);

  // Sync local docs when story loads/refreshes
  useEffect(() => {
    if (!story) return;
    setLocalDocs({
      prd: story.prd || "",
      technical_design: story.technical_design || "",
      detailed_design: story.detailed_design || "",
    });
  }, [story?.prd, story?.technical_design, story?.detailed_design]);

  // Set default active tab based on stage
  useEffect(() => {
    if (!story) return;
    const primary = STAGE_PRIMARY_DOC[story.status];
    if (primary) setActiveDocTab(primary);
    // Right panel: default to Q&A if clarifying with unanswered questions
    if (
      story.status === "clarifying" &&
      story.clarifications.some((c) => !c.answer)
    ) {
      setRightPanelTab("qa");
    } else {
      setRightPanelTab("chat");
    }
  }, [story?.status]);

  if (!story) return null;

  const isAiStage = AI_STAGES.includes(story.status);
  const isDocChatStage = DOC_CHAT_STAGES.includes(story.status);
  const primaryDoc = STAGE_PRIMARY_DOC[story.status] || "prd";
  const hasAnyDoc =
    story.prd || story.technical_design || story.detailed_design;

  // Two-phase logic: stage AI running → show console; otherwise if has doc → show doc+chat
  const showAiConsole = isDocChatStage && story.ai_stage_running;
  const showDocChat = isDocChatStage && !story.ai_stage_running && hasAnyDoc;

  // Rollback: stages before current that can be rolled back to
  const currentIdx = DOC_CHAT_STAGES.indexOf(story.status);
  const rollbackTargets =
    isDocChatStage && currentIdx > 0
      ? DOC_CHAT_STAGES.slice(0, currentIdx)
      : [];

  const handleConfirm = async () => {
    try {
      await confirmStage(story.id);
      message.success("已确认，进入下一阶段");
      refresh();
    } catch {
      message.error("操作失败");
    }
  };

  const handleIterate = async () => {
    try {
      await iterateStory(story.id);
      message.success("已迭代");
      refresh();
    } catch {
      message.error("操作失败");
    }
  };

  const handleRestart = async () => {
    try {
      await restartStory(story.id);
      message.success("已重启新轮次");
      refresh();
    } catch {
      message.error("操作失败");
    }
  };

  const handleStop = async () => {
    try {
      await stopStory(story.id);
      message.success("已停止");
      refresh();
    } catch {
      message.error("操作失败");
    }
  };

  const handleSaveDoc = async (docKey: string, content: string) => {
    const meta = DOC_META[docKey];
    if (!meta) return;
    setSaving(true);
    try {
      await saveStoryDoc(story.id, meta.filename, content);
      message.success(`${meta.label} 已保存`);
      refresh();
    } catch {
      message.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleChatSend = async (text: string) => {
    try {
      await sendChatMessage(story.id, text);
    } catch {
      message.error("发送失败");
    }
  };

  const handleDocUpdated = (content: string, filename: string) => {
    // Find which doc key matches the filename
    for (const [key, meta] of Object.entries(DOC_META)) {
      if (meta.filename === filename) {
        setLocalDocs((prev) => ({ ...prev, [key]: content }));
        break;
      }
    }
    refresh();
  };

  const handleRollback = async (targetStage: string) => {
    try {
      await rollbackStory(story.id, targetStage);
      message.success(`已回退到${STAGE_LABELS[targetStage] || targetStage}`);
      refresh();
    } catch {
      message.error("回退失败");
    }
  };

  const handleAnswersSubmitted = () => {
    refresh();
    setRightPanelTab("chat");
  };

  // Build tab items — only show tabs that have content or are the primary doc
  const docTabItems = Object.entries(DOC_META)
    .filter(([key]) => {
      const content = localDocs[key as keyof LocalDocs];
      return content || key === primaryDoc;
    })
    .map(([key, meta]) => {
      const isEditable = isDocChatStage && key === primaryDoc;
      const content = localDocs[key as keyof LocalDocs];
      return {
        key,
        label: meta.label,
        children: (
          <PrdEditor
            value={content}
            onChange={(v) => setLocalDocs((prev) => ({ ...prev, [key]: v }))}
            onSave={(v) => handleSaveDoc(key, v)}
            saving={saving}
            readOnly={!isEditable}
          />
        ),
      };
    });

  return (
    <>
      <Space
        style={{
          marginBottom: 16,
          justifyContent: "space-between",
          width: "100%",
        }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          {story.title}
        </Typography.Title>
        <Space>
          {story.status === "verifying" && (
            <>
              <Button type="primary" onClick={handleConfirm}>
                确认完成
              </Button>
              <Button onClick={handleIterate}>迭代</Button>
              <Button onClick={handleRestart}>重启</Button>
            </>
          )}
          {showDocChat && (
            <Button type="primary" onClick={handleConfirm}>
              {story.status === "clarifying" ? "确认定稿" : "确认 & 下一步"}
            </Button>
          )}
          {showDocChat && rollbackTargets.length > 0 && (
            <Dropdown
              menu={{
                items: rollbackTargets.map((stage) => ({
                  key: stage,
                  label: `回退到${STAGE_LABELS[stage] || stage}`,
                })),
                onClick: ({ key }) => handleRollback(key),
              }}
            >
              <Button>回退</Button>
            </Dropdown>
          )}
          {isAiStage && (
            <Button danger onClick={handleStop}>
              停止
            </Button>
          )}
        </Space>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <StageStepper status={story.status} />
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="状态">
            <Tag>{story.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="轮次">
            {story.current_round}
          </Descriptions.Item>
          <Descriptions.Item label="需求" span={2}>
            {story.raw_input}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Phase 1: AI running → show AI Console */}
      {showAiConsole && (
        <Card title="AI Console" style={{ marginBottom: 16 }}>
          <AIConsole storyId={story.id} active={true} onDone={refresh} />
        </Card>
      )}

      {/* Phase 2: AI done + has doc → doc tabs + right panel */}
      {showDocChat && (
        <div
          style={{
            display: "flex",
            gap: 16,
            marginBottom: 16,
            height: "calc(100vh - 300px)",
            minHeight: 500,
          }}
        >
          <Card
            style={{
              flex: 1,
              minWidth: 0,
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
            }}
            styles={{
              body: {
                flex: 1,
                overflow: "hidden",
                display: "flex",
                flexDirection: "column",
              },
            }}
          >
            <Tabs
              activeKey={activeDocTab}
              onChange={setActiveDocTab}
              items={docTabItems}
              size="small"
              destroyInactiveTabPane
            />
          </Card>
          <Card
            style={{
              flex: 1,
              minWidth: 0,
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
            styles={{
              body: {
                flex: 1,
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
                minHeight: 0,
              },
            }}
          >
            <div
              style={{
                display: "flex",
                gap: 8,
                marginBottom: 8,
                flexShrink: 0,
              }}
            >
              {story.status === "clarifying" &&
                story.clarifications.length > 0 && (
                  <Button
                    size="small"
                    type={rightPanelTab === "qa" ? "primary" : "default"}
                    onClick={() => setRightPanelTab("qa")}
                  >
                    问题回答 (
                    {story.clarifications.filter((c) => !c.answer).length}/
                    {story.clarifications.length})
                  </Button>
                )}
              <Button
                size="small"
                type={rightPanelTab === "chat" ? "primary" : "default"}
                onClick={() => setRightPanelTab("chat")}
              >
                {story.ai_running && (
                  <LoadingOutlined style={{ marginRight: 4 }} />
                )}
                讨论
              </Button>
            </div>
            {story.status === "clarifying" &&
              story.clarifications.length > 0 && (
                <div
                  style={{
                    flex: 1,
                    display: rightPanelTab === "qa" ? "flex" : "none",
                    flexDirection: "column",
                    minHeight: 0,
                  }}
                >
                  <ClarifyQA
                    storyId={story.id}
                    clarifications={story.clarifications}
                    onSubmitted={handleAnswersSubmitted}
                  />
                </div>
              )}
            <div
              style={{
                flex: 1,
                display: rightPanelTab === "chat" ? "flex" : "none",
                flexDirection: "column",
                minHeight: 0,
              }}
            >
              <ChatPanel
                storyId={story.id}
                active={true}
                onSend={handleChatSend}
                onDocUpdated={handleDocUpdated}
                onDone={refresh}
              />
            </div>
          </Card>
        </div>
      )}

      {/* Read-only doc tabs for non-editable stages */}
      {!isDocChatStage && hasAnyDoc && (
        <Card style={{ marginBottom: 16, overflow: "hidden" }}>
          <Tabs
            activeKey={activeDocTab}
            onChange={setActiveDocTab}
            items={docTabItems}
            size="small"
            destroyInactiveTabPane
          />
        </Card>
      )}

      {story.tasks.length > 0 && (
        <Card title="任务列表" style={{ marginBottom: 16 }}>
          <Table
            rowKey="id"
            dataSource={story.tasks}
            pagination={false}
            size="small"
            columns={[
              { title: "#", dataIndex: "order", width: 50 },
              { title: "任务", dataIndex: "title" },
              { title: "描述", dataIndex: "description", ellipsis: true },
            ]}
          />
        </Card>
      )}

      {story.rounds.length > 0 && (
        <Card title="轮次记录" style={{ marginBottom: 16 }}>
          {story.rounds.map((r) => (
            <div key={r.id} style={{ marginBottom: 8 }}>
              <Tag>{r.type}</Tag>
              Round {r.round_number} — {r.status}
              {r.branch_name && (
                <span style={{ marginLeft: 8, color: "#888" }}>
                  {r.branch_name}
                </span>
              )}
              {r.pull_requests.map((pr) => (
                <a
                  key={pr.pr_number}
                  href={pr.pr_url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ marginLeft: 8 }}
                >
                  PR #{pr.pr_number}
                </a>
              ))}
            </div>
          ))}
        </Card>
      )}

      {story.clarifications.length > 0 && story.status !== "clarifying" && (
        <Card title="澄清问答" style={{ marginBottom: 16 }}>
          {story.clarifications.map((c) => (
            <div key={c.id} style={{ marginBottom: 8 }}>
              <div>
                <strong>Q:</strong> {c.question}
              </div>
              <div>
                <strong>A:</strong>{" "}
                {c.answer || <Tag color="warning">待回答</Tag>}
              </div>
              <Divider style={{ margin: "8px 0" }} />
            </div>
          ))}
        </Card>
      )}

      {/* AI Console for coding stage */}
      {story.status === "coding" && (
        <Card title="AI Console">
          <AIConsole storyId={story.id} active={true} onDone={refresh} />
        </Card>
      )}
    </>
  );
}
