import { useState } from "react";
import {
  Card,
  Form,
  Input,
  Button,
  message,
  Typography,
  Segmented,
} from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { createStory } from "../api/stories";

export default function StoryForm() {
  const { id: projectId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"full" | "light">("light");

  const onFinish = async (values: {
    title: string;
    raw_input: string;
    feature_tag?: string;
  }) => {
    setLoading(true);
    try {
      const res = await createStory(Number(projectId), { ...values, mode });
      message.success("Story 已创建");
      navigate(`/projects/${projectId}/stories/${res.id}`);
    } catch {
      message.error("创建失败");
    } finally {
      setLoading(false);
    }
  };

  const modeDescriptions: Record<string, string> = {
    full: "完整的软件工程流程，适合复杂功能开发",
    light: "精简流程，适合 Bug 修复、配置变更等小任务",
  };

  return (
    <div>
      <Typography.Title level={4}>新建 Story</Typography.Title>
      <Card>
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item label="模式">
            <Segmented
              value={mode}
              onChange={(v) => setMode(v as "full" | "light")}
              options={[
                { label: "完整流程", value: "full" },
                { label: "轻量模式", value: "light" },
              ]}
            />
            <div style={{ marginTop: 4, color: "#888", fontSize: 12 }}>
              {modeDescriptions[mode]}
            </div>
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="raw_input"
            label="需求描述"
            rules={[{ required: true }]}
          >
            <Input.TextArea rows={6} placeholder="描述你想要实现的功能..." />
          </Form.Item>
          <Form.Item name="feature_tag" label="Feature Tag">
            <Input placeholder="可选，如 auth、payment" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              创建
            </Button>
            <Button style={{ marginLeft: 8 }} onClick={() => navigate(-1)}>
              取消
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
