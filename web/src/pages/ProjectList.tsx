import { useEffect, useState } from 'react';
import { Card, Table, Button, Space, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { listProjects } from '../api/projects';
import type { ProjectSummary } from '../types';

export default function ProjectList() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>项目列表</Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/projects/new')}>
          新建项目
        </Button>
      </Space>
      <Card>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={projects}
          onRow={(record) => ({ onClick: () => navigate(`/projects/${record.id}`), style: { cursor: 'pointer' } })}
          columns={[
            { title: '项目名称', dataIndex: 'name' },
            { title: '仓库地址', dataIndex: 'repo_url', ellipsis: true },
            { title: 'Stories', dataIndex: 'story_count', width: 100 },
          ]}
          pagination={false}
        />
      </Card>
    </>
  );
}
