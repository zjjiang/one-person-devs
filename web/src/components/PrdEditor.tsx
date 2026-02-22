import { useRef, useEffect, useState } from "react";
import MDEditor from "@uiw/react-md-editor";
import { Button, Space } from "antd";
import { SaveOutlined } from "@ant-design/icons";

interface Props {
  value: string;
  onChange: (prd: string) => void;
  onSave: (prd: string) => void;
  saving?: boolean;
  readOnly?: boolean;
}

export default function PrdEditor({
  value,
  onChange,
  onSave,
  saving,
  readOnly,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [editorHeight, setEditorHeight] = useState(500);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const h = entries[0]?.contentRect.height;
      if (h && h > 0) setEditorHeight(h);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div
      data-color-mode="light"
      style={{
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        flex: 1,
      }}
    >
      {!readOnly && (
        <Space
          style={{
            marginBottom: 8,
            justifyContent: "flex-end",
            width: "100%",
            flexShrink: 0,
          }}
        >
          <Button
            type="primary"
            size="small"
            icon={<SaveOutlined />}
            loading={saving}
            onClick={() => onSave(value)}
          >
            保存
          </Button>
        </Space>
      )}

      {readOnly ? (
        <div style={{ flex: 1, overflow: "auto" }}>
          <MDEditor.Markdown
            source={value || ""}
            style={{ padding: 16, minHeight: 300 }}
          />
        </div>
      ) : (
        <div ref={containerRef} style={{ flex: 1, minHeight: 0 }}>
          <MDEditor
            value={value}
            onChange={(v) => onChange(v || "")}
            height={editorHeight}
            preview="preview"
          />
        </div>
      )}
    </div>
  );
}
