import { useEffect, useState } from 'react';
import { Card, Descriptions, Table, Tag, Button, Space, Typography, Tabs } from 'antd';
import { PlusOutlined, SettingOutlined, EditOutlined } from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { getProject } from '../api/projects';
import type { Project } from '../types';

const statusColor: Record<string, string> = {
  preparing: 'default', clarifying: 'processing', planning: 'processing',
  designing: 'processing', coding: 'warning', verifying: 'success', done: 'success',
};

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);

  useEffect(() => {
    getProject(Number(id)).then(setProject);
  }, [id]);

  if (!project) return null;

  return (
    <>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>{project.name}</Typography.Title>
        <Space>
          <Button icon={<EditOutlined />} onClick={() => navigate(`/projects/${id}/edit`)}>编辑</Button>
          <Button icon={<SettingOutlined />} onClick={() => navigate(`/projects/${id}/settings`)}>能力配置</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate(`/projects/${id}/stories/new`)}>新建 Story</Button>
        </Space>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="仓库">{project.repo_url}</Descriptions.Item>
          <Descriptions.Item label="描述">{project.description || '-'}</Descriptions.Item>
          <Descriptions.Item label="技术栈">{project.tech_stack || '-'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card>
        <Tabs items={[
          {
            key: 'stories',
            label: `Stories (${project.stories.length})`,
            children: (
              <Table
                rowKey="id"
                dataSource={project.stories}
                pagination={false}
                onRow={(r) => ({ onClick: () => navigate(`/stories/${r.id}`), style: { cursor: 'pointer' } })}
                columns={[
                  { title: '标题', dataIndex: 'title' },
                  { title: '状态', dataIndex: 'status', width: 120, render: (s: string) => <Tag color={statusColor[s]}>{s}</Tag> },
                ]}
              />
            ),
          },
          {
            key: 'rules',
            label: `规则 (${project.rules.length})`,
            children: (
              <Table
                rowKey="id"
                dataSource={project.rules}
                pagination={false}
                columns={[
                  { title: '类别', dataIndex: 'category', width: 120 },
                  { title: '内容', dataIndex: 'content', ellipsis: true },
                  { title: '启用', dataIndex: 'enabled', width: 80, render: (v: boolean) => v ? '是' : '否' },
                ]}
              />
            ),
          },
          {
            key: 'skills',
            label: `技能 (${project.skills.length})`,
            children: (
              <Table
                rowKey="id"
                dataSource={project.skills}
                pagination={false}
                columns={[
                  { title: '名称', dataIndex: 'name' },
                  { title: '触发方式', dataIndex: 'trigger', width: 160 },
                ]}
              />
            ),
          },
        ]} />
      </Card>
    </>
  );
}
