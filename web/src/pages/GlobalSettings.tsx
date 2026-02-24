import { useEffect, useState } from "react";
import {
  Table,
  Switch,
  Select,
  Input,
  Button,
  Space,
  Typography,
  message,
  Spin,
  Form,
  Tag,
  Modal,
  Popconfirm,
  Tooltip,
} from "antd";
import {
  ApiOutlined,
  PlusOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  getGlobalCapabilities,
  getAvailableCapabilities,
  createGlobalCapability,
  saveGlobalCapability,
  testGlobalCapability,
  deleteGlobalCapability,
  verifyAllCapabilities,
  type GlobalCapabilityItem,
  type AvailableCapability,
  type ConfigSchemaField,
} from "../api/settings";

interface CapEdit {
  enabled: boolean;
  config: Record<string, string>;
  label: string;
}

export default function GlobalSettings() {
  const [caps, setCaps] = useState<GlobalCapabilityItem[]>([]);
  const [available, setAvailable] = useState<AvailableCapability[]>([]);
  const [loading, setLoading] = useState(true);
  const [edits, setEdits] = useState<Record<number, CapEdit>>({});
  const [testing, setTesting] = useState<Record<number, boolean>>({});
  const [saving, setSaving] = useState<Record<number, boolean>>({});
  const [addOpen, setAddOpen] = useState(false);
  const [addCap, setAddCap] = useState<string | undefined>();
  const [addProvider, setAddProvider] = useState<string | undefined>();
  const [addLabel, setAddLabel] = useState<string>("");
  const [healthMap, setHealthMap] = useState<
    Record<number, { healthy: boolean; message: string }>
  >({});
  const [verifying, setVerifying] = useState(false);

  const loadCaps = () => {
    setLoading(true);
    Promise.all([getGlobalCapabilities(), getAvailableCapabilities()])
      .then(([data, avail]) => {
        setCaps(data);
        setAvailable(avail);
        const init: Record<number, CapEdit> = {};
        data.forEach((c) => {
          init[c.id] = {
            enabled: c.enabled,
            config: c.config || {},
            label: c.label,
          };
        });
        setEdits(init);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadCaps();
  }, []);

  const getEdit = (id: number): CapEdit =>
    edits[id] || { enabled: false, config: {}, label: "" };

  const updateEdit = (id: number, patch: Partial<CapEdit>) => {
    setEdits((prev) => ({ ...prev, [id]: { ...getEdit(id), ...patch } }));
  };

  const updateConfigField = (id: number, field: string, value: string) => {
    const current = getEdit(id);
    updateEdit(id, { config: { ...current.config, [field]: value } });
  };

  const handleSave = async (record: GlobalCapabilityItem) => {
    setSaving((prev) => ({ ...prev, [record.id]: true }));
    try {
      const edit = getEdit(record.id);
      await saveGlobalCapability(record.id, {
        enabled: edit.enabled,
        config_override: edit.config,
        label: edit.label || undefined,
      });
      message.success("配置已保存");
    } catch {
      message.error("保存失败");
    } finally {
      setSaving((prev) => ({ ...prev, [record.id]: false }));
    }
  };

  const handleTest = async (record: GlobalCapabilityItem) => {
    const edit = getEdit(record.id);
    setTesting((prev) => ({ ...prev, [record.id]: true }));
    try {
      const res = await testGlobalCapability(record.id, {
        config: edit.config,
      });
      if (res.healthy)
        message.success(
          `${record.label}/${record.provider}: ${res.message || "连接成功"}`,
        );
      else
        message.error(
          `${record.label}/${record.provider}: ${res.message || "连接失败"}`,
        );
    } catch {
      message.error("测试失败");
    } finally {
      setTesting((prev) => ({ ...prev, [record.id]: false }));
    }
  };

  const handleAdd = async () => {
    if (!addCap || !addProvider) {
      message.warning("请选择能力类型和 Provider");
      return;
    }
    try {
      await createGlobalCapability({
        capability: addCap,
        provider: addProvider,
        enabled: true,
        label: addLabel || undefined,
      });
      message.success("能力已添加");
      setAddOpen(false);
      setAddCap(undefined);
      setAddProvider(undefined);
      setAddLabel("");
      loadCaps();
    } catch {
      message.error("添加失败");
    }
  };

  const handleDelete = async (record: GlobalCapabilityItem) => {
    try {
      await deleteGlobalCapability(record.id);
      message.success("配置已删除");
      loadCaps();
    } catch {
      message.error("删除失败");
    }
  };

  const handleVerifyAll = async () => {
    setVerifying(true);
    setHealthMap({});
    try {
      const results = await verifyAllCapabilities();
      setHealthMap(results);
      const total = Object.keys(results).length;
      const healthy = Object.values(results).filter((r) => r.healthy).length;
      if (healthy === total) message.success(`全部 ${total} 项验证通过`);
      else message.warning(`${healthy}/${total} 项验证通过`);
    } catch {
      message.error("批量验证失败");
    } finally {
      setVerifying(false);
    }
  };

  // Available capability types for the add modal
  const capOptions = [...new Set(available.map((a) => a.capability))];
  const providerOptionsForCap = (cap: string) =>
    available.filter((a) => a.capability === cap).map((a) => a.provider);

  const expandedRowRender = (record: GlobalCapabilityItem) => {
    const edit = getEdit(record.id);
    const schema: ConfigSchemaField[] = record.config_schema || [];
    return (
      <Form
        labelCol={{ span: 4 }}
        wrapperCol={{ span: 16 }}
        colon={false}
        style={{ padding: "8px 0" }}
      >
        <Form.Item label="显示名称">
          <Input
            value={edit.label}
            onChange={(e) => updateEdit(record.id, { label: e.target.value })}
            style={{ maxWidth: 320 }}
            placeholder="自定义显示名称"
          />
        </Form.Item>
        {schema.map((field) => (
          <Form.Item
            key={field.name}
            label={field.label}
            required={field.required}
          >
            {field.type === "select" ? (
              <Select
                value={edit.config[field.name] || undefined}
                onChange={(v) => updateConfigField(record.id, field.name, v)}
                style={{ maxWidth: 320 }}
                placeholder="请选择"
                options={(field.options || []).map((o) => ({
                  label: o,
                  value: o,
                }))}
              />
            ) : (
              <Input
                type={field.type === "password" ? "password" : "text"}
                value={edit.config[field.name] || ""}
                onChange={(e) =>
                  updateConfigField(record.id, field.name, e.target.value)
                }
                style={{ maxWidth: 320 }}
                placeholder={field.required ? "必填" : "可选"}
              />
            )}
          </Form.Item>
        ))}
        {schema.length === 0 && (
          <Form.Item wrapperCol={{ offset: 4 }}>
            <Typography.Text type="secondary">
              该能力无需额外配置
            </Typography.Text>
          </Form.Item>
        )}
        <Form.Item wrapperCol={{ offset: 4 }}>
          <Space>
            <Button
              type="primary"
              icon={<CheckCircleOutlined />}
              loading={saving[record.id]}
              onClick={() => handleSave(record)}
            >
              保存配置
            </Button>
            {schema.length > 0 && (
              <Button
                icon={<ApiOutlined />}
                loading={testing[record.id]}
                onClick={() => handleTest(record)}
              >
                测试连接
              </Button>
            )}
          </Space>
        </Form.Item>
      </Form>
    );
  };

  const columns = [
    {
      title: "能力名称",
      key: "label",
      render: (_: unknown, r: GlobalCapabilityItem) => {
        const edit = getEdit(r.id);
        return (
          <Space>
            <span>{edit.label || r.label}</span>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {r.capability}
            </Typography.Text>
          </Space>
        );
      },
    },
    {
      title: "Provider",
      key: "provider",
      width: 160,
      render: (_: unknown, r: GlobalCapabilityItem) => <Tag>{r.provider}</Tag>,
    },
    {
      title: "状态",
      key: "enabled",
      width: 100,
      render: (_: unknown, r: GlobalCapabilityItem) => (
        <Switch
          checked={getEdit(r.id).enabled}
          onChange={(v) => updateEdit(r.id, { enabled: v })}
        />
      ),
    },
    {
      title: "健康",
      key: "health",
      width: 100,
      render: (_: unknown, r: GlobalCapabilityItem) => {
        const h = healthMap[r.id];
        if (!h) return <Typography.Text type="secondary">—</Typography.Text>;
        return (
          <Tooltip title={h.message}>
            <Tag color={h.healthy ? "success" : "error"}>
              {h.healthy ? "正常" : "异常"}
            </Tag>
          </Tooltip>
        );
      },
    },
    {
      title: "操作",
      key: "actions",
      width: 80,
      render: (_: unknown, r: GlobalCapabilityItem) => (
        <Popconfirm
          title="确定删除该配置？"
          onConfirm={() => handleDelete(r)}
          okText="删除"
          cancelText="取消"
        >
          <Button type="text" size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  if (loading)
    return (
      <Spin size="large" style={{ display: "block", margin: "100px auto" }} />
    );

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 8,
        }}
      >
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            全局能力配置
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
            配置全局可用的能力和服务提供方，所有项目共享这些配置。
          </Typography.Paragraph>
        </div>
        <Space>
          <Button
            icon={<SyncOutlined spin={verifying} />}
            loading={verifying}
            onClick={handleVerifyAll}
            disabled={caps.length === 0}
          >
            验证全部
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setAddOpen(true)}
          >
            新增能力
          </Button>
        </Space>
      </div>

      <Table<GlobalCapabilityItem>
        rowKey="id"
        columns={columns}
        dataSource={caps}
        pagination={false}
        expandable={{ expandedRowRender }}
      />

      <Modal
        title="新增能力"
        open={addOpen}
        onOk={handleAdd}
        onCancel={() => {
          setAddOpen(false);
          setAddCap(undefined);
          setAddProvider(undefined);
          setAddLabel("");
        }}
        okText="添加"
        cancelText="取消"
      >
        <Form layout="vertical">
          <Form.Item label="显示名称">
            <Input
              value={addLabel}
              onChange={(e) => setAddLabel(e.target.value)}
              placeholder="用于区分同类型的多个实例"
            />
          </Form.Item>
          <Form.Item label="能力类型">
            <Select
              value={addCap}
              onChange={(v) => {
                setAddCap(v);
                setAddProvider(undefined);
              }}
              placeholder="选择能力类型"
              options={capOptions.map((c) => ({ label: c, value: c }))}
            />
          </Form.Item>
          <Form.Item label="Provider">
            <Select
              value={addProvider}
              onChange={setAddProvider}
              placeholder="选择 Provider"
              disabled={!addCap}
              options={
                addCap
                  ? providerOptionsForCap(addCap).map((p) => ({
                      label: p,
                      value: p,
                    }))
                  : []
              }
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
