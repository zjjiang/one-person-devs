import { useCallback, useEffect, useState } from "react";
import {
  Card,
  Button,
  Space,
  Typography,
  Tag,
  Descriptions,
  Table,
  message,
  Divider,
} from "antd";
import { useParams } from "react-router-dom";
import {
  getStory,
  confirmStage,
  iterateStory,
  restartStory,
  stopStory,
  sendChatMessage,
  saveStoryDoc,
} from "../api/stories";
import type { Story } from "../types";
import MDEditor from "@uiw/react-md-editor";
import StageStepper from "../components/StageStepper";
import AIConsole from "../components/AIConsole";
import PrdEditor from "../components/PrdEditor";
import ChatPanel from "../components/ChatPanel";

const AI_STAGES = [
  "preparing",
  "clarifying",
  "planning",
  "designing",
  "coding",
];
const PRD_EDIT_STAGES = ["preparing", "clarifying"];

export default function StoryDetail() {
  const { id } = useParams();
  const [story, setStory] = useState<Story | null>(null);
  const [localPrd, setLocalPrd] = useState("");
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(() => {
    getStory(Number(id)).then(setStory);
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Sync localPrd when story loads/refreshes
  useEffect(() => {
    if (story?.prd) setLocalPrd(story.prd);
  }, [story?.prd]);

  if (!story) return null;

  const isAiStage = AI_STAGES.includes(story.status);
  const isPrdEditStage = PRD_EDIT_STAGES.includes(story.status);

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

  const handleSavePrd = async (prd: string) => {
    setSaving(true);
    try {
      await saveStoryDoc(story.id, "prd.md", prd);
      message.success("PRD 已保存");
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
          {["preparing", "clarifying", "planning", "designing"].includes(
            story.status,
          ) && (
            <Button type="primary" onClick={handleConfirm}>
              {story.status === "clarifying" ? "确认定稿" : "确认 & 下一步"}
            </Button>
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

      {/* PRD edit + chat for preparing/clarifying stages */}
      {isPrdEditStage && story.prd && (
        <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
          <Card title="PRD" style={{ flex: 1 }}>
            <PrdEditor
              value={localPrd}
              onChange={setLocalPrd}
              onSave={handleSavePrd}
              saving={saving}
            />
          </Card>
          <Card title="讨论" style={{ flex: 1 }}>
            <ChatPanel
              storyId={story.id}
              active={true}
              onSend={handleChatSend}
              onPrdUpdated={(newPrd) => {
                setLocalPrd(newPrd);
                refresh();
              }}
              onDone={refresh}
            />
          </Card>
        </div>
      )}

      {/* Read-only PRD for other stages */}
      {!isPrdEditStage && story.prd && (
        <Card title="PRD" style={{ marginBottom: 16 }} data-color-mode="light">
          <MDEditor.Markdown source={story.prd} />
        </Card>
      )}

      {/* AI console for initial PRD generation (preparing without prd yet) */}
      {isPrdEditStage && !story.prd && (
        <Card title="AI Console" style={{ marginBottom: 16 }}>
          <AIConsole storyId={story.id} active={true} onDone={refresh} />
        </Card>
      )}

      {story.technical_design && (
        <Card
          title="技术方案"
          style={{ marginBottom: 16 }}
          data-color-mode="light"
        >
          <MDEditor.Markdown source={story.technical_design} />
        </Card>
      )}

      {story.detailed_design && (
        <Card
          title="详细设计"
          style={{ marginBottom: 16 }}
          data-color-mode="light"
        >
          <MDEditor.Markdown source={story.detailed_design} />
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

      {story.clarifications.length > 0 && (
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

      {/* AI Console for non-PRD-edit AI stages */}
      {!isPrdEditStage && isAiStage && (
        <Card title="AI Console">
          <AIConsole storyId={story.id} active={true} onDone={refresh} />
        </Card>
      )}
    </>
  );
}
