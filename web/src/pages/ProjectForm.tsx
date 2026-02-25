import { useEffect, useRef, useState } from "react";
import {
  Table,
  Form,
  Input,
  Button,
  message,
  Typography,
  Alert,
  Spin,
  Divider,
  Space,
  Row,
  Col,
  Tag,
  Modal,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  LockOutlined,
  UnlockOutlined,
  PlusOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import {
  createProject,
  getProject,
  updateProject,
  getWorkspaceStatus,
  verifyRepo,
} from "../api/projects";
import {
  getCapabilityCatalog,
  batchSaveCapabilities,
  type CatalogItem,
} from "../api/capabilities";
import type { Project } from "../types";

interface RepoVerify {
  status: "idle" | "loading" | "ok" | "error";
  message?: string;
}

export default function ProjectForm() {
  const { id } = useParams();
  const isEdit = !!id;
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  /** Selected keys as "capability/provider" strings */
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [addCapOpen, setAddCapOpen] = useState(false);
  const [repoVerify, setRepoVerify] = useState<RepoVerify>({ status: "idle" });
  const [cloneStatus, setCloneStatus] = useState<{
    polling: boolean;
    status?: string;
    error?: string;
  }>({ polling: false });
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  // Lock state for edit mode
  const [repoLocked, setRepoLocked] = useState(true);
  const [workspaceLocked, setWorkspaceLocked] = useState(true);
  const [originalProject, setOriginalProject] = useState<Project | null>(null);

  const catKey = (c: CatalogItem) => `${c.capability}/${c.provider}`;

  useEffect(() => {
    getCapabilityCatalog().then((data) => {
      setCatalog(data);
      if (!isEdit) {
        // Default: select all enabled items from global config
        setSelectedKeys(data.filter((c) => c.enabled).map(catKey));
      }
    });

    if (isEdit) {
      getProject(Number(id)).then((p) => {
        form.setFieldsValue(p);
        setOriginalProject(p);
        // Load enabled capabilities as "cap/provider" keys
        const enabled = (p.capability_configs || [])
          .filter((c) => c.enabled)
          .map((c) => `${c.capability}/${c.provider}`);
        setSelectedKeys(enabled);
      });
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [id, isEdit, form]);

  const handleUnlock = (field: "repo" | "workspace") => {
    Modal.confirm({
      title: field === "repo" ? "解锁仓库地址" : "解锁工作空间目录",
      content:
        field === "repo"
          ? "修改仓库地址将触发重新克隆，当前工作区数据会被覆盖。确定要解锁？"
          : "修改工作空间目录可能导致路径不一致，请确认操作。",
      okText: "解锁",
      cancelText: "取消",
      onOk: () => {
        if (field === "repo") setRepoLocked(false);
        else setWorkspaceLocked(false);
      },
    });
  };

  const handleVerifyRepo = async () => {
    const url = form.getFieldValue("repo_url")?.trim();
    if (!url) {
      message.warning("请先输入仓库地址");
      return;
    }
    setRepoVerify({ status: "loading" });
    try {
      const res = await verifyRepo(url);
      setRepoVerify({
        status: res.healthy ? "ok" : "error",
        message: res.message,
      });
    } catch {
      setRepoVerify({ status: "error", message: "验证请求失败" });
    }
  };

  const pollWorkspace = (projectId: number) => {
    setCloneStatus({ polling: true, status: "cloning" });
    let attempts = 0;
    const maxAttempts = 90;
    timerRef.current = setInterval(async () => {
      attempts++;
      try {
        const res = await getWorkspaceStatus(projectId);
        setCloneStatus({ polling: true, status: res.status, error: res.error });
        if (res.status === "ready") {
          clearInterval(timerRef.current);
          message.success("工作区初始化完成");
          navigate(`/projects/${projectId}`);
        } else if (res.status === "error") {
          clearInterval(timerRef.current);
          setCloneStatus({ polling: false, status: "error", error: res.error });
        }
      } catch {
        /* ignore */
      }
      if (attempts >= maxAttempts) {
        clearInterval(timerRef.current);
        setCloneStatus({ polling: false, status: "timeout" });
        message.warning("初始化超时，可稍后在项目详情页重试");
        navigate(`/projects/${projectId}`);
      }
    }, 2000);
  };

  const onFinish = async (values: Record<string, string>) => {
    setLoading(true);
    try {
      if (isEdit) {
        const data: Record<string, unknown> = {
          name: values.name,
          description: values.description,
          tech_stack: values.tech_stack,
          architecture: values.architecture,
        };
        // Only send repo_url if unlocked and changed
        if (!repoLocked && values.repo_url !== originalProject?.repo_url) {
          data.repo_url = values.repo_url;
        }
        // Only send workspace_dir if unlocked
        if (
          !workspaceLocked &&
          values.workspace_dir !== originalProject?.workspace_dir
        ) {
          data.workspace_dir = values.workspace_dir;
        }
        // Send capability toggles: selected → enabled, rest → disabled
        data.capabilities = catalog.map((c) => ({
          capability: c.capability,
          provider: c.provider,
          enabled: selectedKeys.includes(catKey(c)),
        }));
        const res = await updateProject(
          Number(id),
          data as Parameters<typeof updateProject>[1],
        );
        if (res.workspace_reclone) {
          message.success("仓库地址已更新，正在重新克隆...");
          setLoading(false);
          pollWorkspace(Number(id));
        } else {
          message.success("项目已更新");
          navigate(`/projects/${id}`);
        }
      } else {
        const res = await createProject({
          name: values.name,
          repo_url: values.repo_url,
          description: values.description,
          tech_stack: values.tech_stack,
          architecture: values.architecture,
          workspace_dir: values.workspace_dir,
        });
        const items = selectedKeys.map((key) => {
          const catItem = catalog.find((c) => catKey(c) === key);
          return {
            capability: catItem?.capability || key.split("/")[0],
            enabled: true,
            provider_override: catItem?.provider || key.split("/")[1] || null,
          };
        });
        await batchSaveCapabilities(res.id, items);
        message.success("项目已创建，正在初始化工作区...");
        setLoading(false);
        pollWorkspace(res.id);
      }
    } catch {
      message.error("操作失败");
      setLoading(false);
    }
  };

  const repoSuffix = (() => {
    if (repoVerify.status === "loading")
      return <LoadingOutlined style={{ color: "#1677ff" }} />;
    if (repoVerify.status === "ok")
      return <CheckCircleOutlined style={{ color: "#52c41a" }} />;
    if (repoVerify.status === "error")
      return <CloseCircleOutlined style={{ color: "#ff4d4f" }} />;
    return null;
  })();

  // Capabilities selected for this project
  const selectedCatalog = catalog.filter((c) =>
    selectedKeys.includes(catKey(c)),
  );
  const availableToAdd = catalog.filter(
    (c) => !selectedKeys.includes(catKey(c)),
  );

  const capColumns = [
    {
      title: "能力名称",
      dataIndex: "label",
      key: "label",
      render: (_: string, r: CatalogItem) => (
        <Space>
          <span>{r.label}</span>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {r.capability}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: "服务提供方",
      key: "provider",
      width: 140,
      render: (_: unknown, r: CatalogItem) => <Tag>{r.provider_label}</Tag>,
    },
    {
      title: "操作",
      key: "actions",
      width: 70,
      render: (_: unknown, r: CatalogItem) => (
        <Button
          type="text"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() =>
            setSelectedKeys((prev) => prev.filter((k) => k !== catKey(r)))
          }
        />
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <Typography.Title level={4}>
        {isEdit ? "编辑项目" : "新建项目"}
      </Typography.Title>

      {cloneStatus.polling && (
        <Alert
          type="info"
          showIcon
          icon={<Spin size="small" />}
          message="正在克隆仓库，请稍候..."
          style={{ marginBottom: 16 }}
        />
      )}
      {cloneStatus.status === "error" && (
        <Alert
          type="error"
          showIcon
          message="工作区初始化失败"
          description={cloneStatus.error}
          style={{ marginBottom: 16 }}
        />
      )}

      <Form form={form} layout="vertical" onFinish={onFinish}>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="name"
              label="项目名称"
              rules={[{ required: true }]}
            >
              <Input placeholder="My Project" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="workspace_dir"
              label={
                <Space size={4}>
                  工作空间目录
                  {isEdit && (
                    <Button
                      type="text"
                      size="small"
                      icon={
                        workspaceLocked ? <LockOutlined /> : <UnlockOutlined />
                      }
                      onClick={() =>
                        workspaceLocked
                          ? handleUnlock("workspace")
                          : setWorkspaceLocked(true)
                      }
                      style={{ color: workspaceLocked ? "#999" : "#1677ff" }}
                    />
                  )}
                </Space>
              }
              tooltip="AI 编码时代码存放的目录，留空则默认 ./workspace"
            >
              <Input
                placeholder="./workspace"
                disabled={isEdit && workspaceLocked}
              />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          name="repo_url"
          label={
            <Space size={4}>
              仓库地址
              {isEdit && (
                <Button
                  type="text"
                  size="small"
                  icon={repoLocked ? <LockOutlined /> : <UnlockOutlined />}
                  onClick={() =>
                    repoLocked ? handleUnlock("repo") : setRepoLocked(true)
                  }
                  style={{ color: repoLocked ? "#999" : "#1677ff" }}
                />
              )}
            </Space>
          }
          rules={[
            { required: true, message: "请输入仓库地址" },
            {
              pattern: /^(https?:\/\/|git@|ssh:\/\/)/,
              message: "请输入有效的 Git 仓库地址",
            },
          ]}
          extra={
            repoVerify.message && (
              <Typography.Text
                type={repoVerify.status === "ok" ? "success" : "danger"}
                style={{ fontSize: 12 }}
              >
                {repoVerify.message}
              </Typography.Text>
            )
          }
        >
          {isEdit && repoLocked ? (
            <Input disabled />
          ) : (
            <Space.Compact style={{ width: "100%" }}>
              <Input
                placeholder="https://github.com/org/repo"
                suffix={repoSuffix}
                onChange={() => setRepoVerify({ status: "idle" })}
              />
              <Button
                onClick={handleVerifyRepo}
                loading={repoVerify.status === "loading"}
              >
                验证权限
              </Button>
            </Space.Compact>
          )}
        </Form.Item>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item name="tech_stack" label="技术栈">
              <Input.TextArea rows={2} placeholder="Python, React, MySQL..." />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="description" label="项目描述">
              <Input.TextArea rows={2} placeholder="简要描述项目功能" />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item name="architecture" label="架构说明">
          <Input.TextArea rows={3} placeholder="系统架构、模块划分等（可选）" />
        </Form.Item>

        {catalog.length > 0 && (
          <>
            <Divider orientation="left" plain style={{ margin: "8px 0 16px" }}>
              启用能力
            </Divider>
            <Table<CatalogItem>
              rowKey={(r) => catKey(r)}
              columns={capColumns}
              dataSource={selectedCatalog}
              pagination={false}
              size="small"
              footer={() => (
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() => setAddCapOpen(true)}
                  disabled={availableToAdd.length === 0}
                  block
                >
                  添加能力
                </Button>
              )}
            />
            <Modal
              title="添加能力"
              open={addCapOpen}
              onCancel={() => setAddCapOpen(false)}
              footer={null}
              width={480}
            >
              {availableToAdd.length === 0 ? (
                <Typography.Text type="secondary">
                  所有可用能力已添加
                </Typography.Text>
              ) : (
                <Space direction="vertical" style={{ width: "100%" }}>
                  {availableToAdd.map((c) => (
                    <Button
                      key={catKey(c)}
                      block
                      onClick={() => {
                        setSelectedKeys((prev) => [...prev, catKey(c)]);
                        setAddCapOpen(false);
                      }}
                      style={{ textAlign: "left" }}
                    >
                      <Space>
                        <span>{c.label}</span>
                        <Typography.Text
                          type="secondary"
                          style={{ fontSize: 12 }}
                        >
                          {c.capability}
                        </Typography.Text>
                        <Tag>{c.provider_label}</Tag>
                      </Space>
                    </Button>
                  ))}
                </Space>
              )}
            </Modal>
          </>
        )}

        <Form.Item style={{ marginTop: 24 }}>
          <Space>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              disabled={cloneStatus.polling}
              size="large"
            >
              {isEdit ? "保存" : "创建项目"}
            </Button>
            <Button onClick={() => navigate(-1)} disabled={cloneStatus.polling}>
              取消
            </Button>
          </Space>
        </Form.Item>
      </Form>
    </div>
  );
}
