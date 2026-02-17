import { useEffect, useState } from "react";
import {
  Card,
  Switch,
  Select,
  Input,
  Button,
  Space,
  Typography,
  message,
  Spin,
  Form,
  Divider,
} from "antd";
import { ApiOutlined, CheckCircleOutlined } from "@ant-design/icons";
import {
  getGlobalCapabilities,
  saveGlobalCapability,
  testGlobalCapability,
  type GlobalCapabilityItem,
  type ConfigSchemaField,
} from "../api/settings";

interface CapEdit {
  enabled: boolean;
  provider: string | null;
  config: Record<string, string>;
}

const LABEL_COL = { span: 5 };
const WRAPPER_COL = { span: 16 };

export default function GlobalSettings() {
  const [caps, setCaps] = useState<GlobalCapabilityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [edits, setEdits] = useState<Record<string, CapEdit>>({});
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});

  useEffect(() => {
    getGlobalCapabilities()
      .then((data) => {
        setCaps(data);
        const init: Record<string, CapEdit> = {};
        data.forEach((c) => {
          init[c.capability] = { ...c.saved };
        });
        setEdits(init);
      })
      .finally(() => setLoading(false));
  }, []);

  const getEdit = (cap: string): CapEdit =>
    edits[cap] || { enabled: true, provider: null, config: {} };

  const updateEdit = (cap: string, patch: Partial<CapEdit>) => {
    setEdits((prev) => ({ ...prev, [cap]: { ...getEdit(cap), ...patch } }));
  };

  const updateConfigField = (cap: string, field: string, value: string) => {
    const current = getEdit(cap);
    updateEdit(cap, { config: { ...current.config, [field]: value } });
  };

  const getSchema = (cap: GlobalCapabilityItem): ConfigSchemaField[] => {
    const providerName =
      getEdit(cap.capability).provider || cap.providers[0]?.name;
    const provider =
      cap.providers.find((p) => p.name === providerName) || cap.providers[0];
    return provider?.config_schema || [];
  };

  const handleSave = async (cap: string) => {
    setSaving((prev) => ({ ...prev, [cap]: true }));
    try {
      const edit = getEdit(cap);
      const providerOverride =
        edit.provider ||
        caps.find((c) => c.capability === cap)?.providers[0]?.name ||
        null;
      await saveGlobalCapability(cap, {
        enabled: edit.enabled,
        provider_override: providerOverride,
        config_override: edit.config,
      });
      message.success("配置已保存");
    } catch {
      message.error("保存失败");
    } finally {
      setSaving((prev) => ({ ...prev, [cap]: false }));
    }
  };

  const handleTest = async (cap: GlobalCapabilityItem) => {
    const edit = getEdit(cap.capability);
    const provider = edit.provider || cap.providers[0]?.name;
    if (!provider) return;
    setTesting((prev) => ({ ...prev, [cap.capability]: true }));
    try {
      const res = await testGlobalCapability(cap.capability, {
        provider,
        config: edit.config,
      });
      if (res.healthy)
        message.success(`${cap.label}: ${res.message || "连接成功"}`);
      else message.error(`${cap.label}: ${res.message || "连接失败"}`);
    } catch {
      message.error("测试失败");
    } finally {
      setTesting((prev) => ({ ...prev, [cap.capability]: false }));
    }
  };

  if (loading)
    return (
      <Spin size="large" style={{ display: "block", margin: "100px auto" }} />
    );

  return (
    <>
      <Typography.Title level={4}>全局能力配置</Typography.Title>
      <Typography.Paragraph type="secondary">
        配置全局可用的能力和服务提供方，所有项目共享这些配置。
      </Typography.Paragraph>
      <Space
        direction="vertical"
        style={{ width: "100%", maxWidth: 720 }}
        size={16}
      >
        {caps.map((cap) => {
          const edit = getEdit(cap.capability);
          const schema = getSchema(cap);
          return (
            <Card
              key={cap.capability}
              title={
                <Space>
                  <ApiOutlined />
                  <span>{cap.label}</span>
                  <Typography.Text
                    type="secondary"
                    style={{ fontSize: 12, fontWeight: "normal" }}
                  >
                    {cap.capability}
                  </Typography.Text>
                </Space>
              }
              extra={
                <Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {edit.enabled ? "已启用" : "已禁用"}
                  </Typography.Text>
                  <Switch
                    checked={edit.enabled}
                    onChange={(v) => updateEdit(cap.capability, { enabled: v })}
                  />
                </Space>
              }
            >
              <Form labelCol={LABEL_COL} wrapperCol={WRAPPER_COL} colon={false}>
                {cap.providers.length > 1 && (
                  <Form.Item label="服务提供方">
                    <Select
                      value={edit.provider || cap.providers[0]?.name}
                      onChange={(v) =>
                        updateEdit(cap.capability, { provider: v })
                      }
                      style={{ maxWidth: 320 }}
                      options={cap.providers.map((p) => ({
                        label: p.name,
                        value: p.name,
                      }))}
                    />
                  </Form.Item>
                )}
                {schema.map((field) => (
                  <Form.Item
                    key={field.name}
                    label={field.label}
                    required={field.required}
                  >
                    {field.type === "select" ? (
                      <Select
                        value={edit.config[field.name] || undefined}
                        onChange={(v) =>
                          updateConfigField(cap.capability, field.name, v)
                        }
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
                          updateConfigField(
                            cap.capability,
                            field.name,
                            e.target.value,
                          )
                        }
                        style={{ maxWidth: 320 }}
                        placeholder={field.required ? "必填" : "可选"}
                      />
                    )}
                  </Form.Item>
                ))}
                {schema.length === 0 && (
                  <Form.Item wrapperCol={{ offset: 5 }}>
                    <Typography.Text type="secondary">
                      该能力无需额外配置
                    </Typography.Text>
                  </Form.Item>
                )}
                <Divider style={{ margin: "12px 0" }} />
                <Form.Item wrapperCol={{ offset: 5 }}>
                  <Space>
                    <Button
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      loading={saving[cap.capability]}
                      onClick={() => handleSave(cap.capability)}
                    >
                      保存配置
                    </Button>
                    <Button
                      icon={<ApiOutlined />}
                      loading={testing[cap.capability]}
                      onClick={() => handleTest(cap)}
                    >
                      测试连接
                    </Button>
                  </Space>
                </Form.Item>
              </Form>
            </Card>
          );
        })}
      </Space>
    </>
  );
}
