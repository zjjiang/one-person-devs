import { type ReactNode, useEffect, useMemo, useState } from "react";
import {
  Layout,
  Menu,
  Typography,
  Avatar,
  Dropdown,
  Space,
  Tooltip,
} from "antd";
import {
  ProjectOutlined,
  FileTextOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
  LogoutOutlined,
  ArrowLeftOutlined,
  AppstoreOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router-dom";
import NotificationBell from "./NotificationBell";
import { getProject } from "../api/projects";

const { Sider, Header, Content } = Layout;

const GLOBAL_NAV = [
  { key: "/", icon: <ProjectOutlined />, label: "项目" },
  { key: "/logs", icon: <FileTextOutlined />, label: "日志" },
];

function parseProjectId(pathname: string): string | null {
  const m = pathname.match(/^\/projects\/(\d+)/);
  return m ? m[1] : null;
}

function resolveGlobalKey(pathname: string): string {
  if (pathname.startsWith("/logs")) return "/logs";
  return "/";
}

function resolveProjectKey(pathname: string, pid: string): string {
  if (pathname.match(/\/projects\/\d+\/edit/)) return `/projects/${pid}/edit`;
  return `/projects/${pid}`;
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(true);
  const [projectName, setProjectName] = useState("");

  const projectId = useMemo(
    () => parseProjectId(location.pathname),
    [location.pathname],
  );

  useEffect(() => {
    if (projectId) {
      getProject(Number(projectId))
        .then((p) => setProjectName(p.name))
        .catch(() => setProjectName(""));
    } else {
      setProjectName("");
    }
  }, [projectId]);

  const navItems = useMemo(() => {
    if (!projectId) return GLOBAL_NAV;
    return [
      {
        key: `/projects/${projectId}`,
        icon: <AppstoreOutlined />,
        label: "概览",
      },
      {
        key: `/projects/${projectId}/edit`,
        icon: <SettingOutlined />,
        label: "项目设置",
      },
    ];
  }, [projectId]);

  const selectedKey = projectId
    ? resolveProjectKey(location.pathname, projectId)
    : resolveGlobalKey(location.pathname);

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
      <Header
        style={{
          height: 56,
          lineHeight: "56px",
          padding: "10px 20px 0 24px",
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

        <Space size={20}>
          <NotificationBell />
          <Tooltip title="全局设置">
            <SettingOutlined
              style={{ fontSize: 17, color: "#ffffffd9", cursor: "pointer" }}
              onClick={() => navigate("/settings")}
            />
          </Tooltip>
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
        </Space>
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
          {/* Back to project list when in project context */}
          {projectId && (
            <div
              style={{
                padding: collapsed ? "12px 0" : "12px 16px",
                borderBottom: "1px solid #ffffff12",
                cursor: "pointer",
                color: "#ffffffa6",
                fontSize: 13,
                display: "flex",
                alignItems: "center",
                gap: 8,
                justifyContent: collapsed ? "center" : "flex-start",
                whiteSpace: "nowrap",
                overflow: "hidden",
              }}
              onClick={() => navigate("/")}
            >
              <ArrowLeftOutlined />
              {!collapsed && (
                <span
                  style={{
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {projectName || "返回"}
                </span>
              )}
            </div>
          )}

          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selectedKey]}
            items={navItems}
            onClick={({ key }) => navigate(key)}
            style={{ borderRight: 0, flex: 1 }}
          />

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
            overflow: "auto",
          }}
        >
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}
