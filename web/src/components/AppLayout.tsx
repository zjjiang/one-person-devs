import { useState, useEffect, type ReactNode } from 'react';
import { Layout, Menu, Typography } from 'antd';
import {
  ProjectOutlined,
  PlusOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { listProjects } from '../api/projects';
import type { ProjectSummary } from '../types';

const { Sider, Content } = Layout;

export default function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    listProjects().then(setProjects).catch(() => {});
  }, [location.pathname]);

  const menuItems = [
    {
      key: '/',
      icon: <AppstoreOutlined />,
      label: '所有项目',
    },
    {
      key: '/projects/new',
      icon: <PlusOutlined />,
      label: '新建项目',
    },
    ...projects.map((p) => ({
      key: `/projects/${p.id}`,
      icon: <ProjectOutlined />,
      label: p.name,
    })),
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
        width={220}
      >
        <div
          style={{
            height: 48,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: '1px solid rgba(255,255,255,0.1)',
          }}
        >
          <Typography.Text
            strong
            style={{ color: '#fff', fontSize: collapsed ? 14 : 18 }}
          >
            {collapsed ? 'OPD' : 'OPD v2'}
          </Typography.Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Content style={{ padding: 24, background: '#f5f5f5' }}>
        {children}
      </Content>
    </Layout>
  );
}
