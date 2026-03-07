import { useCallback, useEffect, useState } from "react";
import {
  Card,
  Descriptions,
  Table,
  Tag,
  Button,
  Space,
  Typography,
  Tabs,
  message,
  Breadcrumb,
  Drawer,
  FloatButton,
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  ReloadOutlined,
  SyncOutlined,
  HomeOutlined,
  LoadingOutlined,
  CodeOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams, Link } from "react-router-dom";
import { getProject, initWorkspace, syncContext } from "../api/projects";
import type { Project } from "../types";
import { STAGE_LABELS } from "../types";
import SyncConsole from "../components/SyncConsole";

const statusColor: Record<string, string> = {
  preparing: "default",
  clarifying: "processing",
  planning: "processing",
  designing: "processing",
  coding: "warning",
  verifying: "success",
  done: "success",
};

const wsStatusConfig: Record<string, { color: string; label: string }> = {
  pending: { color: "default", label: "待初始化" },
  cloning: { color: "processing", label: "克隆中..." },
  ready: { color: "success", label: "就绪" },
  error: { color: "error", label: "失败" },
};

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const refresh = () => getProject(Number(id)).then(setProject);

  useEffect(() => {
    refresh();
  }, [id]);

  const handleInitWorkspace = async () => {
    try {
      await initWorkspace(Number(id));
      message.success("工作区初始化已触发");
      refresh();
    } catch {
      message.error("操作失败");
    }
  };

  const handleSyncContext = async () => {
    setSyncing(true);
    setDrawerOpen(true);
    try {
      await syncContext(Number(id));
    } catch {
      message.error("同步上下文启动失败");
      setSyncing(false);
    }
  };

  const handleSyncDone = useCallback((msg: string) => {
    setSyncing(false);
    message.success(msg || "同步完成");
  }, []);

  const handleSyncError = useCallback((msg: string) => {
    setSyncing(false);
    message.error(msg || "同步失败");
  }, []);

  if (!project) return null;

  return (
    <>
      <Breadcrumb
        style={{ marginBottom: 12 }}
        items={[
          {
            title: (
              <Link to="/">
                <HomeOutlined /> 首页
              </Link>
            ),
          },
          { title: project.name },
        ]}
      />

      <Space
        style={{
          marginBottom: 16,
          justifyContent: "space-between",
          width: "100%",
        }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          {project.name}
        </Typography.Title>
        <Space>
          <Button
            icon={<SyncOutlined spin={syncing} />}
            onClick={handleSyncContext}
            loading={syncing}
            disabled={project.workspace_status !== "ready"}
          >
            同步上下文
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleInitWorkspace}
            disabled={syncing}
          >
            初始化工作区
          </Button>
          <Button
            icon={<EditOutlined />}
            onClick={() => navigate(`/projects/${id}/edit`)}
          >
            编辑
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate(`/projects/${id}/stories/new`)}
          >
            新建 Story
          </Button>
        </Space>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="仓库">{project.repo_url}</Descriptions.Item>
          <Descriptions.Item label="描述">
            {project.description || "-"}
          </Descriptions.Item>
          <Descriptions.Item label="技术栈">
            {project.tech_stack || "-"}
          </Descriptions.Item>
          <Descriptions.Item label="已启用能力">
            {project.capability_configs.filter((c) => c.enabled).length > 0 ? (
              <Space size={[4, 4]} wrap>
                {project.capability_configs
                  .filter((c) => c.enabled)
                  .map((c) => (
                    <Tag key={c.capability} color="blue">
                      {c.capability_label}
                      {c.provider_label ? ` · ${c.provider_label}` : ""}
                    </Tag>
                  ))}
              </Space>
            ) : (
              <Typography.Text type="secondary">未配置</Typography.Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="工作区">
            <Tag
              color={
                wsStatusConfig[project.workspace_status]?.color || "default"
              }
            >
              {wsStatusConfig[project.workspace_status]?.label ||
                project.workspace_status}
            </Tag>
            {project.workspace_path && (
              <Typography.Text
                code
                copyable
                style={{ marginLeft: 8, fontSize: 12 }}
              >
                {project.workspace_path}
              </Typography.Text>
            )}
            {project.workspace_status === "error" && (
              <Typography.Text
                type="danger"
                style={{ marginLeft: 8, fontSize: 12 }}
              >
                {project.workspace_error}
              </Typography.Text>
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card>
        <Tabs
          items={[
            {
              key: "stories",
              label: `用户故事 (${project.stories.length})`,
              children: (
                <Table
                  rowKey="id"
                  dataSource={project.stories}
                  pagination={false}
                  onRow={(r) => ({
                    onClick: () => navigate(`/projects/${id}/stories/${r.id}`),
                    style: { cursor: "pointer" },
                  })}
                  columns={[
                    { title: "标题", dataIndex: "title" },
                    {
                      title: "状态",
                      dataIndex: "status",
                      width: 120,
                      render: (s: string) => (
                        <Tag color={statusColor[s]}>{STAGE_LABELS[s] || s}</Tag>
                      ),
                    },
                  ]}
                />
              ),
            },
            // {
            //   key: "rules",
            //   label: `规则 (${project.rules.length})`,
            //   children: (
            //     <Table
            //       rowKey="id"
            //       dataSource={project.rules}
            //       pagination={false}
            //       columns={[
            //         { title: "类别", dataIndex: "category", width: 120 },
            //         { title: "内容", dataIndex: "content", ellipsis: true },
            //         {
            //           title: "启用",
            //           dataIndex: "enabled",
            //           width: 80,
            //           render: (v: boolean) => (v ? "是" : "否"),
            //         },
            //       ]}
            //     />
            //   ),
            // },
            // {
            //   key: "skills",
            //   label: `技能 (${project.skills.length})`,
            //   children: (
            //     <Table
            //       rowKey="id"
            //       dataSource={project.skills}
            //       pagination={false}
            //       columns={[
            //         { title: "名称", dataIndex: "name" },
            //         { title: "触发方式", dataIndex: "trigger", width: 160 },
            //       ]}
            //     />
            //   ),
            // },
          ]}
        />
      </Card>

      {/* Floating action button — sync log */}
      <FloatButton.Group shape="square" style={{ insetInlineEnd: 24 }}>
        <FloatButton
          icon={syncing ? <LoadingOutlined /> : <CodeOutlined />}
          tooltip="编码日志"
          type={drawerOpen ? "primary" : "default"}
          onClick={() => setDrawerOpen(true)}
        />
      </FloatButton.Group>

      <Drawer
        title="编码日志"
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
          <Button size="small" type="primary">
            {syncing && <LoadingOutlined style={{ marginRight: 4 }} />}
            编码日志
          </Button>
        </div>
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
          }}
        >
          {drawerOpen && (
            <SyncConsole
              projectId={Number(id)}
              active={true}
              onDone={handleSyncDone}
              onError={handleSyncError}
            />
          )}
        </div>
      </Drawer>
    </>
  );
}
