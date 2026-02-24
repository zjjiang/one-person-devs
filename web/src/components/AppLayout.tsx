import { type ReactNode, useState } from "react";
import { Layout, Menu, Typography, Avatar, Dropdown, Space } from "antd";
import {
  ProjectOutlined,
  FileTextOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
  LogoutOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router-dom";

const { Sider, Header, Content } = Layout;

const NAV_ITEMS = [
  { key: "/", icon: <ProjectOutlined />, label: "项目" },
  { key: "/logs", icon: <FileTextOutlined />, label: "日志" },
  { key: "/settings", icon: <SettingOutlined />, label: "设置" },
];

function resolveSelectedKey(pathname: string): string {
  if (pathname.startsWith("/logs")) return "/logs";
  if (pathname.startsWith("/settings")) return "/settings";
  return "/";
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(true);

  const userMenuItems = [
    { key: "profile", icon: <UserOutlined />, label: "个人信息" },
    { type: "divider" as const },
    {
      key: "logout",
      icon: <LogoutOutlined />,
      label: "退出登录",
      danger: true,
    },
  ];

  return (
    <Layout style={{ height: "100vh" }}>
      {/* Unified top bar: logo left, user right */}
      <Header
        style={{
          height: 56,
          lineHeight: "56px",
          padding: "0 20px 0 24px",
          background: "#001529",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Typography.Text
          strong
          style={{
            color: "#fff",
            fontSize: 18,
            letterSpacing: 2,
            cursor: "pointer",
          }}
          onClick={() => navigate("/")}
        >
          SoloForge
        </Typography.Text>

        <Dropdown
          menu={{
            items: userMenuItems,
            onClick: ({ key }) => {
              if (key === "logout") {
                // TODO: implement logout
              }
            },
          }}
          placement="bottomRight"
        >
          <Space style={{ cursor: "pointer" }}>
            <Avatar
              size={28}
              icon={<UserOutlined />}
              style={{ backgroundColor: "#1677ff" }}
            />
            <span style={{ fontSize: 13, color: "#ffffffd9" }}>开发者</span>
          </Space>
        </Dropdown>
      </Header>

      <Layout>
        <Sider
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          trigger={null}
          width={180}
          collapsedWidth={60}
          style={{
            background: "#001529",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[resolveSelectedKey(location.pathname)]}
            items={NAV_ITEMS}
            onClick={({ key }) => navigate(key)}
            style={{ borderRight: 0, flex: 1 }}
          />

          {/* Collapse trigger at bottom */}
          <div
            style={{
              padding: "12px 0",
              textAlign: "center",
              borderTop: "1px solid #ffffff12",
              cursor: "pointer",
              color: "#ffffffa6",
              fontSize: 14,
            }}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </div>
        </Sider>

        <Content
          style={{
            padding: "20px 24px 24px",
            background: "#f5f5f5",
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}
