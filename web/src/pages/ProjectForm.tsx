import { useEffect, useState } from 'react';
import { Card, Form, Input, Button, message, Typography } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { createProject, getProject, updateProject } from '../api/projects';

export default function ProjectForm() {
  const { id } = useParams();
  const isEdit = !!id;
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isEdit) {
      getProject(Number(id)).then((p) => form.setFieldsValue(p));
    }
  }, [id, isEdit, form]);

  const onFinish = async (values: Record<string, string>) => {
    setLoading(true);
    try {
      const data = { name: values.name, repo_url: values.repo_url, description: values.description, tech_stack: values.tech_stack, architecture: values.architecture };
      if (isEdit) {
        await updateProject(Number(id), data);
        message.success('项目已更新');
      } else {
        const res = await createProject(data);
        message.success('项目已创建');
        navigate(`/projects/${res.id}`);
        return;
      }
      navigate(`/projects/${id}`);
    } catch {
      message.error('操作失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Typography.Title level={4}>{isEdit ? '编辑项目' : '新建项目'}</Typography.Title>
      <Card style={{ maxWidth: 640 }}>
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="repo_url" label="仓库地址" rules={[{ required: true }]}>
            <Input placeholder="https://github.com/org/repo" />
          </Form.Item>
          <Form.Item name="description" label="项目描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="tech_stack" label="技术栈">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="architecture" label="架构说明">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              {isEdit ? '保存' : '创建'}
            </Button>
            <Button style={{ marginLeft: 8 }} onClick={() => navigate(-1)}>取消</Button>
          </Form.Item>
        </Form>
      </Card>
    </>
  );
}
