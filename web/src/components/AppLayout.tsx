import { type ReactNode } from "react";
import { Layout, Typography, Button, Tooltip } from "antd";
import { SettingOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

const { Header, Content } = Layout;

export default function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "#001529",
          padding: "0 24px",
        }}
      >
        <Typography.Text
          strong
          style={{ color: "#fff", fontSize: 18, cursor: "pointer" }}
          onClick={() => navigate("/")}
        >
          OPD v2
        </Typography.Text>
        <Tooltip title="全局设置">
          <Button
            type="text"
            icon={<SettingOutlined style={{ fontSize: 18, color: "#ffffffd9" }} />}
            onClick={() => navigate("/settings")}
          />
        </Tooltip>
      </Header>
      <Content style={{ padding: 24, background: "#f5f5f5" }}>
        {children}
      </Content>
    </Layout>
  );
}
