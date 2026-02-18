import { useState } from "react";
import { Input, Button, Space, Tag, message } from "antd";
import { CheckOutlined } from "@ant-design/icons";
import type { ClarificationItem } from "../types";
import { answerQuestions } from "../api/stories";

interface Props {
  storyId: number;
  clarifications: ClarificationItem[];
  onSubmitted: () => void;
}

export default function ClarifyQA({
  storyId,
  clarifications,
  onSubmitted,
}: Props) {
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const unanswered = clarifications.filter((c) => !c.answer);
  const answered = clarifications.filter((c) => c.answer);

  const handleSubmit = async () => {
    const pairs = unanswered
      .map((c) => ({
        id: c.id,
        question: c.question,
        answer: (answers[c.id] || "").trim(),
      }))
      .filter((p) => p.answer);
    if (pairs.length === 0) {
      message.warning("请至少回答一个问题");
      return;
    }
    setSubmitting(true);
    try {
      await answerQuestions(storyId, pairs);
      message.success(`已提交 ${pairs.length} 个回答`);
      setAnswers({});
      onSubmitted();
    } catch {
      message.error("提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
      }}
    >
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          minHeight: 0,
          paddingRight: 4,
        }}
      >
        {unanswered.map((c, i) => (
          <div key={c.id} style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
              <Tag color="blue">{i + 1}</Tag>
              {c.question}
            </div>
            <Input.TextArea
              rows={2}
              value={answers[c.id] || ""}
              onChange={(e) =>
                setAnswers((prev) => ({ ...prev, [c.id]: e.target.value }))
              }
              placeholder="输入你的回答..."
              disabled={submitting}
            />
          </div>
        ))}
        {unanswered.length === 0 && answered.length > 0 && (
          <div style={{ color: "#999", textAlign: "center", marginTop: 20 }}>
            所有问题已回答，可以确认进入下一阶段
          </div>
        )}
        {answered.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 12, color: "#999", marginBottom: 8 }}>
              已回答
            </div>
            {answered.map((c) => (
              <div
                key={c.id}
                style={{
                  marginBottom: 8,
                  padding: "6px 8px",
                  background: "#f5f5f5",
                  borderRadius: 6,
                  fontSize: 12,
                }}
              >
                <div style={{ color: "#666" }}>Q: {c.question}</div>
                <div>A: {c.answer}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      {unanswered.length > 0 && (
        <Space style={{ marginTop: 8 }}>
          <Button
            type="primary"
            icon={<CheckOutlined />}
            onClick={handleSubmit}
            loading={submitting}
          >
            提交回答
          </Button>
          <span style={{ fontSize: 12, color: "#999" }}>
            {Object.values(answers).filter((v) => v.trim()).length}/
            {unanswered.length} 已填写
          </span>
        </Space>
      )}
    </div>
  );
}
