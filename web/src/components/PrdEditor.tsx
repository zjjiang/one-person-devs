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
  return (
    <div data-color-mode="light">
      {!readOnly && (
        <Space style={{ marginBottom: 8, justifyContent: "flex-end", width: "100%" }}>
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
        <MDEditor.Markdown
          source={value || ""}
          style={{ padding: 16, minHeight: 300 }}
        />
      ) : (
        <MDEditor
          value={value}
          onChange={(v) => onChange(v || "")}
          height={500}
          preview="live"
        />
      )}
    </div>
  );
}
