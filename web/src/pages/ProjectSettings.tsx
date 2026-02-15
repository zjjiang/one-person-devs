import { useEffect, useState } from 'react';
import { Card, Switch, Select, Input, Button, Space, Typography, message, Spin, Form, Divider } from 'antd';
import { ApiOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import { getCapabilities, saveCapability, testCapability } from '../api/capabilities';
import type { CapabilityItem, ConfigField } from '../types';
import { CAPABILITY_LABELS } from '../types';

const LABEL_COL = { span: 5 };
const WRAPPER_COL = { span: 16 };

export default function ProjectSettings() {
  const { id } = useParams();
  const projectId = Number(id);
  const [caps, setCaps] = useState<CapabilityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [edits, setEdits] = useState<Record<string, CapabilityItem['saved']>>({});

  useEffect(() => {
    getCapabilities(projectId)
      .then((data) => {
        setCaps(data);
        const init: Record<string, CapabilityItem['saved']> = {};
        data.forEach((c) => { init[c.capability] = { ...c.saved }; });
        setEdits(init);
      })
      .finally(() => setLoading(false));
  }, [projectId]);

  const getEdit = (cap: string) =>
    edits[cap] || { enabled: true, provider_override: null, config_override: {} };

  const updateEdit = (cap: string, patch: Partial<CapabilityItem['saved']>) => {
    setEdits((prev) => ({ ...prev, [cap]: { ...getEdit(cap), ...patch } }));
  };

  const updateConfigField = (cap: string, field: string, value: string) => {
    const current = getEdit(cap);
    updateEdit(cap, { config_override: { ...current.config_override, [field]: value } });
  };

  const getSchema = (cap: CapabilityItem): ConfigField[] => {
    const providerName = getEdit(cap.capability).provider_override || cap.providers[0]?.name;
    const provider = cap.providers.find((p) => p.name === providerName) || cap.providers[0];
    return provider?.config_schema || [];
  };

  const handleSave = async (cap: string) => {
    try {
      await saveCapability(projectId, cap, getEdit(cap));
      message.success(`${CAPABILITY_LABELS[cap] || cap} 配置已保存`);
    } catch { message.error('保存失败'); }
  };

  const handleTest = async (cap: CapabilityItem) => {
    const edit = getEdit(cap.capability);
    const provider = edit.provider_override || cap.providers[0]?.name;
    if (!provider) return;
    try {
      const res = await testCapability(projectId, cap.capability, {
        provider,
        config: edit.config_override,
      });
      const name = CAPABILITY_LABELS[cap.capability] || cap.capability;
      if (res.healthy) message.success(`${name}: ${res.message || '连接成功'}`);
      else message.error(`${name}: ${res.message || '连接失败'}`);
    } catch { message.error('测试失败'); }
  };

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <>
      <Typography.Title level={4}>能力配置</Typography.Title>
      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        {caps.map((cap) => {
          const edit = getEdit(cap.capability);
          const schema = getSchema(cap);
          const label = CAPABILITY_LABELS[cap.capability] || cap.capability;
          return (
            <Card
              key={cap.capability}
              title={
                <Space>
                  <ApiOutlined />
                  <span>{label}</span>
                  <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
                    {cap.capability}
                  </Typography.Text>
                </Space>
              }
              extra={
                <Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {edit.enabled ? '已启用' : '已禁用'}
                  </Typography.Text>
                  <Switch checked={edit.enabled} onChange={(v) => updateEdit(cap.capability, { enabled: v })} />
                </Space>
              }
            >
              <Form labelCol={LABEL_COL} wrapperCol={WRAPPER_COL} colon={false}>
                {cap.providers.length > 1 && (
                  <Form.Item label="服务提供方">
                    <Select
                      value={edit.provider_override || cap.providers[0]?.name}
                      onChange={(v) => updateEdit(cap.capability, { provider_override: v })}
                      style={{ maxWidth: 320 }}
                      options={cap.providers.map((p) => ({ label: p.name, value: p.name }))}
                    />
                  </Form.Item>
                )}
                {schema.map((field) => (
                  <Form.Item key={field.name} label={field.label} required={field.required}>
                    {field.type === 'select' ? (
                      <Select
                        value={edit.config_override[field.name] || undefined}
                        onChange={(v) => updateConfigField(cap.capability, field.name, v)}
                        style={{ maxWidth: 320 }}
                        placeholder="请选择"
                        options={(field.options || []).map((o) => ({ label: o, value: o }))}
                      />
                    ) : (
                      <Input
                        type={field.type === 'password' ? 'password' : 'text'}
                        value={edit.config_override[field.name] || ''}
                        onChange={(e) => updateConfigField(cap.capability, field.name, e.target.value)}
                        style={{ maxWidth: 320 }}
                        placeholder={field.required ? '必填' : '可选'}
                      />
                    )}
                  </Form.Item>
                ))}
                {schema.length === 0 && (
                  <Form.Item wrapperCol={{ offset: 5 }}>
                    <Typography.Text type="secondary">该能力无需额外配置</Typography.Text>
                  </Form.Item>
                )}
                <Divider style={{ margin: '12px 0' }} />
                <Form.Item wrapperCol={{ offset: 5 }}>
                  <Space>
                    <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => handleSave(cap.capability)}>
                      保存配置
                    </Button>
                    <Button icon={<ApiOutlined />} onClick={() => handleTest(cap)}>
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
