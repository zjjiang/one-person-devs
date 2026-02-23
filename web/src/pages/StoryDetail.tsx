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
  Drawer,
  FloatButton,
  Badge,
  Alert,
  Modal,
  Input,
  Radio,
  Tooltip,
  Breadcrumb,
} from "antd";
import {
  LoadingOutlined,
  CommentOutlined,
  InfoCircleOutlined,
  QuestionCircleOutlined,
  CodeOutlined,
  BranchesOutlined,
  HomeOutlined,
} from "@ant-design/icons";
import { useParams, Link } from "react-router-dom";
import {
  getStory,
  confirmStage,
  rejectStage,
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
  coding: "coding_report",
  verifying: "coding_report",
};

// Document key → (filename, tab label)
const DOC_META: Record<string, { filename: string; label: string }> = {
  prd: { filename: "prd.md", label: "需求文档" },
  technical_design: { filename: "technical_design.md", label: "技术方案" },
  detailed_design: { filename: "detailed_design.md", label: "详细设计" },
  coding_report: { filename: "coding_report.md", label: "编码报告" },
  test_guide: { filename: "test_guide.md", label: "测试指南" },
};

interface LocalDocs {
  prd: string;
  technical_design: string;
  detailed_design: string;
  coding_report: string;
  test_guide: string;
}

export default function StoryDetail() {
  const { id } = useParams();
  const [story, setStory] = useState<Story | null>(null);
  const [localDocs, setLocalDocs] = useState<LocalDocs>({
    prd: "",
    technical_design: "",
    detailed_design: "",
    coding_report: "",
    test_guide: "",
  });
  const [activeDocTab, setActiveDocTab] = useState("prd");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<
    "qa" | "chat" | "info" | "console"
  >("chat");
  const [saving, setSaving] = useState(false);
  const [iterateModal, setIterateModal] = useState<{
    open: boolean;
    action: "iterate" | "restart";
  }>({ open: false, action: "iterate" });
  const [iterateMode, setIterateMode] = useState<"cr" | "manual">("manual");
  const [iterateFeedback, setIterateFeedback] = useState("");

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
      coding_report: story.coding_report || "",
      test_guide: story.test_guide || "",
    });
  }, [
    story?.prd,
    story?.technical_design,
    story?.detailed_design,
    story?.coding_report,
    story?.test_guide,
  ]);

  // Set default active tab based on stage
  useEffect(() => {
    if (!story) return;
    const primary = STAGE_PRIMARY_DOC[story.status];
    if (primary) setActiveDocTab(primary);
    // Auto-open drawer with Q&A tab if clarifying with unanswered questions
    if (
      story.status === "clarifying" &&
      story.clarifications.some((c) => !c.answer)
    ) {
      setDrawerTab("qa");
      setDrawerOpen(true);
    }
    // Auto-open Console drawer when entering coding stage
    if (story.status === "coding") {
      setDrawerTab("console");
      setDrawerOpen(true);
    }
  }, [story?.status]);

  if (!story) return null;

  const isAiStage = AI_STAGES.includes(story.status);
  const isDocChatStage = DOC_CHAT_STAGES.includes(story.status);
  const primaryDoc = STAGE_PRIMARY_DOC[story.status] || "prd";
  const hasAnyDoc =
    story.prd ||
    story.technical_design ||
    story.detailed_design ||
    story.coding_report ||
    story.test_guide;

  // Doc is editable only in doc stages when AI is not running
  const isDocEditable = isDocChatStage && !story.ai_stage_running;
  // Show confirm/rollback buttons when doc is editable and has content
  const showDocActions = isDocEditable && hasAnyDoc;
  // AI Console available in drawer when AI is actively running
  const showConsole =
    story.ai_running || story.ai_stage_running || story.status === "coding";

  // Rollback: stages before current that can be rolled back to
  const currentIdx = DOC_CHAT_STAGES.indexOf(story.status);
  const rollbackTargets =
    isDocChatStage && currentIdx > 0
      ? DOC_CHAT_STAGES.slice(0, currentIdx)
      : [];

  const handleConfirm = async () => {
    try {
      const res = await confirmStage(story.id);
      if (res.skipped_ai) {
        message.info("输入未变化，保留现有文档");
      } else {
        message.success("已确认，进入下一阶段");
      }
      refresh();
    } catch {
      message.error("操作失败");
    }
  };

  const handleIterate = () => {
    setIterateMode("manual");
    setIterateFeedback("");
    setIterateModal({ open: true, action: "iterate" });
  };

  const handleRestart = () => {
    setIterateMode("manual");
    setIterateFeedback("");
    setIterateModal({ open: true, action: "restart" });
  };

  const handleIterateConfirm = async () => {
    const { action } = iterateModal;
    setIterateModal({ open: false, action: "iterate" });
    try {
      if (action === "iterate") {
        await iterateStory(story.id, iterateFeedback);
        message.success("已开始迭代编码");
      } else {
        await restartStory(story.id, iterateFeedback);
        message.success("已回退重写，进入详细设计");
      }
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

  const handleRegenerate = async () => {
    try {
      await rejectStage(story.id);
      message.success("已触发重新生成");
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
    setDrawerTab("chat");
  };

  // Unanswered clarification count for badge
  const unansweredCount = story.clarifications.filter((c) => !c.answer).length;
  const hasClarifyQuestions =
    story.status === "clarifying" && story.clarifications.length > 0;

  // Coding/verifying stages show both coding_report and test_guide tabs
  const codingDocs = new Set(
    story.status === "coding" || story.status === "verifying"
      ? ["coding_report", "test_guide"]
      : [],
  );

  // Build tab items — only show tabs that have content or are the primary doc
  const docTabItems = Object.entries(DOC_META)
    .filter(([key]) => {
      const content = localDocs[key as keyof LocalDocs];
      return content || key === primaryDoc || codingDocs.has(key);
    })
    .map(([key, meta]) => {
      const isEditable = isDocEditable && key === primaryDoc;
      const content = localDocs[key as keyof LocalDocs];
      const isEmpty = !content && (key === primaryDoc || codingDocs.has(key));
      return {
        key,
        label: meta.label,
        children: isEmpty ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              minHeight: 200,
              color: "#999",
            }}
          >
            {story.ai_running || story.ai_stage_running ? (
              <Space direction="vertical" align="center">
                <LoadingOutlined style={{ fontSize: 28 }} />
                <span>{meta.label}生成中...</span>
              </Space>
            ) : codingDocs.has(key) ? (
              <Space direction="vertical" align="center">
                <span>编码未完成，请点击「迭代」重新触发</span>
              </Space>
            ) : (
              <span>暂无{meta.label}</span>
            )}
          </div>
        ) : (
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

  const drawerTitle =
    drawerTab === "qa"
      ? "问题回答"
      : drawerTab === "chat"
        ? "AI 对话"
        : drawerTab === "console"
          ? "编码日志"
          : "基本信息";

  // Branch link for coding/verifying stages
  const activeRound = story.rounds.find((r) => r.status === "active");
  const branchName = activeRound?.branch_name;
  const branchUrl =
    branchName && story.repo_url
      ? `${story.repo_url.replace(/\.git$/, "")}/tree/${branchName}`
      : null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "calc(100vh - 112px)",
      }}
    >
      {/* Breadcrumb navigation */}
      <Breadcrumb
        style={{ marginBottom: 8, flexShrink: 0 }}
        items={[
          {
            title: (
              <Link to="/">
                <HomeOutlined /> 首页
              </Link>
            ),
          },
          {
            title: (
              <Link to={`/projects/${story.project_id}`}>
                {story.project_name}
              </Link>
            ),
          },
          { title: story.title },
        ]}
      />

      {/* Compact header: title + status + actions */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 8,
          flexShrink: 0,
        }}
      >
        <Space>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {story.title}
          </Typography.Title>
          <Tag>{story.status}</Tag>
          <span style={{ color: "#888", fontSize: 12 }}>
            轮次 {story.current_round}
          </span>
          {branchName &&
            (branchUrl ? (
              <a
                href={branchUrl}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: 12 }}
              >
                <BranchesOutlined style={{ marginRight: 4 }} />
                {branchName}
              </a>
            ) : (
              <span style={{ fontSize: 12, color: "#888" }}>
                <BranchesOutlined style={{ marginRight: 4 }} />
                {branchName}
              </span>
            ))}
        </Space>
        <Space>
          {(story.status === "verifying" || story.status === "coding") && (
            <>
              {story.status === "verifying" && (
                <Button type="primary" onClick={handleConfirm}>
                  确认完成
                </Button>
              )}
              <Tooltip title="代码大体 OK，给 AI 提修改意见再改">
                <Button
                  onClick={handleIterate}
                  disabled={story.ai_stage_running}
                >
                  迭代
                </Button>
              </Tooltip>
              <Tooltip title="编码结果不行，回到详细设计重来">
                <Button
                  onClick={handleRestart}
                  disabled={story.ai_stage_running}
                >
                  重写
                </Button>
              </Tooltip>
            </>
          )}
          {showDocActions && (
            <Button type="primary" onClick={handleConfirm}>
              {story.status === "clarifying" ? "确认定稿" : "确认 & 下一步"}
            </Button>
          )}
          {isDocChatStage && !story.ai_stage_running && !story.ai_running && (
            <Button onClick={handleRegenerate}>重新生成</Button>
          )}
          {showDocActions && rollbackTargets.length > 0 && (
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
      </div>

      {/* Stage stepper — compact, no Card */}
      <div style={{ marginBottom: 8, flexShrink: 0 }}>
        <StageStepper status={story.status} />
      </div>

      {/* Main content area — docs always primary */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Coding stage banner */}
        {story.status === "coding" && story.ai_running && (
          <Alert
            type="info"
            showIcon
            icon={<LoadingOutlined />}
            message={
              <Space>
                <span>AI 正在编码中，可在右侧编码日志查看实时进度</span>
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0 }}
                  onClick={() => {
                    setDrawerTab("console");
                    setDrawerOpen(true);
                  }}
                >
                  打开编码日志
                </Button>
              </Space>
            }
            style={{ marginBottom: 8, flexShrink: 0 }}
          />
        )}
        {hasAnyDoc ? (
          <Card
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
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
              className="flex-tabs"
              activeKey={activeDocTab}
              onChange={setActiveDocTab}
              items={docTabItems}
              size="small"
              destroyInactiveTabPane
            />
          </Card>
        ) : showConsole ? (
          <Card
            title="编码日志"
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
            styles={{ body: { flex: 1, overflow: "auto" } }}
          >
            <AIConsole storyId={story.id} active={true} onDone={refresh} />
          </Card>
        ) : (
          <Card
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            styles={{
              body: {
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: "100%",
              },
            }}
          >
            <div style={{ textAlign: "center", color: "#999" }}>
              {story.ai_running || story.ai_stage_running ? (
                <>
                  <LoadingOutlined style={{ fontSize: 32, marginBottom: 16 }} />
                  <div style={{ fontSize: 16 }}>AI 正在生成文档...</div>
                  <div style={{ fontSize: 13, marginTop: 8 }}>
                    {story.status === "preparing" && "正在生成需求文档"}
                    {story.status === "clarifying" && "正在整理澄清问题"}
                    {story.status === "planning" && "正在生成技术方案"}
                    {story.status === "designing" && "正在生成详细设计"}
                    {story.status === "coding" && "正在编写代码"}
                  </div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 32, marginBottom: 16 }}>📄</div>
                  <div style={{ fontSize: 16 }}>暂无文档</div>
                  <div style={{ fontSize: 13, marginTop: 8 }}>
                    文档将在 AI 处理后自动生成
                  </div>
                </>
              )}
            </div>
          </Card>
        )}
      </div>

      {/* Floating action buttons */}
      <FloatButton.Group shape="square" style={{ insetInlineEnd: 24 }}>
        {hasClarifyQuestions && (
          <Badge count={unansweredCount} offset={[-4, 4]} size="small">
            <FloatButton
              icon={<QuestionCircleOutlined />}
              tooltip="问题回答"
              type={drawerOpen && drawerTab === "qa" ? "primary" : "default"}
              onClick={() => {
                setDrawerTab("qa");
                setDrawerOpen(true);
              }}
            />
          </Badge>
        )}
        {isDocChatStage && (
          <FloatButton
            icon={story.ai_running ? <LoadingOutlined /> : <CommentOutlined />}
            tooltip="AI 对话"
            type={drawerOpen && drawerTab === "chat" ? "primary" : "default"}
            onClick={() => {
              setDrawerTab("chat");
              setDrawerOpen(true);
            }}
          />
        )}
        <FloatButton
          icon={<InfoCircleOutlined />}
          tooltip="基本信息"
          type={drawerOpen && drawerTab === "info" ? "primary" : "default"}
          onClick={() => {
            setDrawerTab("info");
            setDrawerOpen(true);
          }}
        />
        {showConsole && hasAnyDoc && (
          <FloatButton
            icon={<CodeOutlined />}
            tooltip="编码日志"
            type={drawerOpen && drawerTab === "console" ? "primary" : "default"}
            onClick={() => {
              setDrawerTab("console");
              setDrawerOpen(true);
            }}
          />
        )}
      </FloatButton.Group>

      {/* Floating Drawer — always available */}
      <Drawer
        title={drawerTitle}
        placement="right"
        width={480}
        mask={false}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        styles={{
          body: {
            padding: 0,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          },
        }}
      >
        <div
          style={{
            display: "flex",
            gap: 8,
            padding: "8px 16px",
            flexShrink: 0,
            borderBottom: "1px solid #f0f0f0",
          }}
        >
          {hasClarifyQuestions && (
            <Button
              size="small"
              type={drawerTab === "qa" ? "primary" : "default"}
              onClick={() => setDrawerTab("qa")}
            >
              问题回答 ({unansweredCount}/{story.clarifications.length})
            </Button>
          )}
          {isDocChatStage && (
            <Button
              size="small"
              type={drawerTab === "chat" ? "primary" : "default"}
              onClick={() => setDrawerTab("chat")}
            >
              {story.ai_running && (
                <LoadingOutlined style={{ marginRight: 4 }} />
              )}
              AI 对话
            </Button>
          )}
          <Button
            size="small"
            type={drawerTab === "info" ? "primary" : "default"}
            onClick={() => setDrawerTab("info")}
          >
            基本信息
          </Button>
          {showConsole && hasAnyDoc && (
            <Button
              size="small"
              type={drawerTab === "console" ? "primary" : "default"}
              onClick={() => setDrawerTab("console")}
            >
              {story.ai_running && (
                <LoadingOutlined style={{ marginRight: 4 }} />
              )}
              编码日志
            </Button>
          )}
        </div>

        {/* Q&A tab */}
        {hasClarifyQuestions && (
          <div
            style={{
              flex: 1,
              display: drawerTab === "qa" ? "flex" : "none",
              flexDirection: "column",
              minHeight: 0,
              padding: "0 16px 16px",
            }}
          >
            <ClarifyQA
              storyId={story.id}
              clarifications={story.clarifications}
              onSubmitted={handleAnswersSubmitted}
            />
          </div>
        )}

        {/* Chat tab */}
        {isDocChatStage && (
          <div
            style={{
              flex: 1,
              display: drawerTab === "chat" ? "flex" : "none",
              flexDirection: "column",
              minHeight: 0,
              padding: "0 16px 16px",
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
        )}

        {/* Info tab */}
        <div
          style={{
            flex: 1,
            display: drawerTab === "info" ? "block" : "none",
            overflow: "auto",
            padding: "16px",
          }}
        >
          <Descriptions column={1} size="small">
            <Descriptions.Item label="需求">
              {story.raw_input}
            </Descriptions.Item>
            {branchName && (
              <Descriptions.Item label="代码分支">
                {branchUrl ? (
                  <a href={branchUrl} target="_blank" rel="noreferrer">
                    <BranchesOutlined style={{ marginRight: 4 }} />
                    {branchName}
                  </a>
                ) : (
                  <span>
                    <BranchesOutlined style={{ marginRight: 4 }} />
                    {branchName}
                  </span>
                )}
              </Descriptions.Item>
            )}
          </Descriptions>

          {story.tasks.length > 0 && (
            <>
              <Divider style={{ margin: "12px 0" }} />
              <Typography.Text strong>任务列表</Typography.Text>
              <Table
                rowKey="id"
                dataSource={story.tasks}
                pagination={false}
                size="small"
                style={{ marginTop: 8 }}
                columns={[
                  { title: "#", dataIndex: "order", width: 50 },
                  { title: "任务", dataIndex: "title" },
                  { title: "描述", dataIndex: "description", ellipsis: true },
                ]}
              />
            </>
          )}

          {story.rounds.length > 0 && (
            <>
              <Divider style={{ margin: "12px 0" }} />
              <Typography.Text strong>轮次记录</Typography.Text>
              <div style={{ marginTop: 8 }}>
                {story.rounds.map((r) => (
                  <div key={r.id} style={{ marginBottom: 8 }}>
                    <Tag>
                      {{ initial: "初始", iterate: "迭代", restart: "重启" }[
                        r.type
                      ] || r.type}
                    </Tag>
                    轮次 {r.round_number} —{" "}
                    {{ active: "进行中", closed: "已关闭" }[r.status] ||
                      r.status}
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
              </div>
            </>
          )}

          {story.clarifications.length > 0 && story.status !== "clarifying" && (
            <>
              <Divider style={{ margin: "12px 0" }} />
              <Typography.Text strong>澄清问答</Typography.Text>
              <div style={{ marginTop: 8 }}>
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
              </div>
            </>
          )}
        </div>

        {/* Console tab */}
        {showConsole && hasAnyDoc && (
          <div
            style={{
              flex: 1,
              display: drawerTab === "console" ? "flex" : "none",
              flexDirection: "column",
              minHeight: 0,
              padding: "0 16px 16px",
            }}
          >
            <AIConsole storyId={story.id} active={true} onDone={refresh} />
          </div>
        )}
      </Drawer>

      {/* Iterate / Restart modal */}
      <Modal
        title={iterateModal.action === "iterate" ? "迭代编码" : "回退重写"}
        open={iterateModal.open}
        onCancel={() => setIterateModal({ open: false, action: "iterate" })}
        onOk={handleIterateConfirm}
        okText="确认"
        cancelText="取消"
      >
        <div style={{ marginBottom: 16 }}>
          <Radio.Group
            value={iterateMode}
            onChange={(e) => setIterateMode(e.target.value)}
          >
            <Radio value="cr">基于 CR 反馈</Radio>
            <Radio value="manual">手动输入</Radio>
          </Radio.Group>
        </div>
        <Input.TextArea
          rows={6}
          value={iterateFeedback}
          onChange={(e) => setIterateFeedback(e.target.value)}
          placeholder={
            iterateMode === "cr"
              ? "粘贴 Code Review 反馈意见..."
              : "输入修改意见或补充说明..."
          }
        />
      </Modal>
    </div>
  );
}
