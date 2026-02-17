import { useEffect, useState } from "react";
import { Card, Row, Col, Tag, Typography, Spin } from "antd";
import { PlusOutlined, ProjectOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { listProjects } from "../api/projects";
import type { ProjectSummary } from "../types";

const wsStatusMap: Record<string, { color: string; text: string }> = {
  ready: { color: "green", text: "就绪" },
  cloning: { color: "blue", text: "初始化中" },
  error: { color: "red", text: "异常" },
  pending: { color: "default", text: "待初始化" },
};

export default function ProjectList() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return <Spin size="large" style={{ display: "block", margin: "100px auto" }} />;

  return (
    <Row gutter={[16, 16]}>
      {projects.map((p) => {
        const ws = wsStatusMap[p.workspace_status] || wsStatusMap.pending;
        return (
          <Col key={p.id} xs={24} sm={12} md={8} lg={6}>
            <Card
              hoverable
              onClick={() => navigate(`/projects/${p.id}`)}
              style={{ height: "100%" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <ProjectOutlined style={{ fontSize: 20, color: "#1677ff" }} />
                <Typography.Text strong ellipsis style={{ flex: 1, fontSize: 15 }}>
                  {p.name}
                </Typography.Text>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {p.story_count} Stories
                </Typography.Text>
                <Tag color={ws.color}>{ws.text}</Tag>
              </div>
            </Card>
          </Col>
        );
      })}
      <Col xs={24} sm={12} md={8} lg={6}>
        <Card
          hoverable
          onClick={() => navigate("/projects/new")}
          style={{
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minHeight: 120,
            borderStyle: "dashed",
          }}
        >
          <div style={{ textAlign: "center", color: "#999" }}>
            <PlusOutlined style={{ fontSize: 28, display: "block", marginBottom: 8 }} />
            <span>新建项目</span>
          </div>
        </Card>
      </Col>
    </Row>
  );
}
