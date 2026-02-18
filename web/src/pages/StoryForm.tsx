import { useState } from "react";
import { Card, Form, Input, Button, message, Typography } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { createStory } from "../api/stories";

export default function StoryForm() {
  const { id: projectId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: {
    title: string;
    raw_input: string;
    feature_tag?: string;
  }) => {
    setLoading(true);
    try {
      const res = await createStory(Number(projectId), values);
      message.success("Story 已创建");
      navigate(`/stories/${res.id}`);
    } catch {
      message.error("创建失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 640, margin: "0 auto" }}>
      <Typography.Title level={4}>新建 Story</Typography.Title>
      <Card>
        <Form layout="vertical" onFinish={onFinish}>
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
