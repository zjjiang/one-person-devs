import { useEffect, useRef, useState } from "react";
import {
  Card,
  Form,
  Input,
  Button,
  message,
  Typography,
  Alert,
  Spin,
  Checkbox,
  Select,
  Divider,
  Space,
  Row,
  Col,
  Tag,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
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

interface CapEdit {
  enabled: boolean;
  provider: string;
}

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
  const [capEdits, setCapEdits] = useState<Record<string, CapEdit>>({});
  const [repoVerify, setRepoVerify] = useState<RepoVerify>({ status: "idle" });
  const [cloneStatus, setCloneStatus] = useState<{
    polling: boolean;
    status?: string;
    error?: string;
  }>({ polling: false });
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    getCapabilityCatalog().then((data) => {
      setCatalog(data);
      const init: Record<string, CapEdit> = {};
      data.forEach((c) => {
        init[c.capability] = {
          enabled: true,
          provider: c.providers[0]?.name || "",
        };
      });
      setCapEdits(init);
    });
    if (isEdit) {
      getProject(Number(id)).then((p) => form.setFieldsValue(p));
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [id, isEdit, form]);

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
      const data = {
        name: values.name,
        repo_url: values.repo_url,
        description: values.description,
        tech_stack: values.tech_stack,
        architecture: values.architecture,
        workspace_dir: values.workspace_dir,
      };
      if (isEdit) {
        await updateProject(Number(id), data);
        message.success("项目已更新");
        navigate(`/projects/${id}`);
      } else {
        const res = await createProject(data);
        const items = Object.entries(capEdits).map(([cap, edit]) => ({
          capability: cap,
          enabled: edit.enabled,
          provider_override: edit.provider || null,
        }));
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

  return (
    <>
      <Typography.Title level={4}>
        {isEdit ? "编辑项目" : "新建项目"}
      </Typography.Title>

      {cloneStatus.polling && (
        <Alert
          type="info"
          showIcon
          icon={<Spin size="small" />}
          message="正在克隆仓库，请稍候..."
          style={{ marginBottom: 16, maxWidth: 720 }}
        />
      )}
      {cloneStatus.status === "error" && (
        <Alert
          type="error"
          showIcon
          message="工作区初始化失败"
          description={cloneStatus.error}
          style={{ marginBottom: 16, maxWidth: 720 }}
        />
      )}

      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        style={{ maxWidth: 720 }}
      >
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
              label="工作空间目录"
              tooltip="AI 编码时代码存放的目录，留空则默认 ./workspace"
            >
              <Input placeholder="./workspace" />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          name="repo_url"
          label="仓库地址"
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

        {!isEdit && catalog.length > 0 && (
          <>
            <Divider orientation="left" plain style={{ margin: "8px 0 16px" }}>
              启用能力
            </Divider>
            <Row gutter={[12, 8]}>
              {catalog.map((cap) => {
                const edit = capEdits[cap.capability];
                if (!edit) return null;
                return (
                  <Col key={cap.capability} xs={12} sm={8}>
                    <Card
                      size="small"
                      hoverable
                      style={{
                        borderColor: edit.enabled ? "#1677ff" : undefined,
                        cursor: "pointer",
                      }}
                      onClick={() =>
                        setCapEdits((prev) => ({
                          ...prev,
                          [cap.capability]: { ...edit, enabled: !edit.enabled },
                        }))
                      }
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                        }}
                      >
                        <Checkbox checked={edit.enabled} />
                        <span style={{ flex: 1 }}>{cap.label}</span>
                        {cap.providers.length > 1 ? (
                          <Select
                            size="small"
                            value={edit.provider}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(v) =>
                              setCapEdits((prev) => ({
                                ...prev,
                                [cap.capability]: { ...edit, provider: v },
                              }))
                            }
                            style={{ width: 110 }}
                            options={cap.providers.map((p) => ({
                              label: p.name,
                              value: p.name,
                            }))}
                          />
                        ) : (
                          <Tag>{cap.providers[0]?.name}</Tag>
                        )}
                      </div>
                    </Card>
                  </Col>
                );
              })}
            </Row>
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
    </>
  );
}
