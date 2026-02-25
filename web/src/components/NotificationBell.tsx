import { useCallback, useEffect, useState } from "react";
import { Badge, Button, List, Popover, Typography } from "antd";
import { BellOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import {
  fetchNotifications,
  fetchUnreadCount,
  markAllRead,
  markRead,
  type NotificationItem,
} from "../api/notifications";

const POLL_INTERVAL = 30_000;

export default function NotificationBell() {
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const refreshCount = useCallback(() => {
    fetchUnreadCount()
      .then((r) => setUnread(r.count))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshCount();
    const timer = setInterval(refreshCount, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [refreshCount]);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchNotifications(false, 20);
      setItems(data);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleOpenChange = (visible: boolean) => {
    setOpen(visible);
    if (visible) loadItems();
  };

  const handleClick = async (item: NotificationItem) => {
    if (!item.read) {
      await markRead(item.id);
      setItems((prev) =>
        prev.map((n) => (n.id === item.id ? { ...n, read: true } : n)),
      );
      setUnread((c) => Math.max(0, c - 1));
    }
    setOpen(false);
    if (item.link) navigate(item.link);
  };

  const handleReadAll = async () => {
    await markAllRead();
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    setUnread(0);
  };

  const formatTime = (iso: string | null) => {
    if (!iso) return "";
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 60_000) return "刚刚";
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
    return d.toLocaleDateString();
  };

  const content = (
    <div style={{ width: 340 }}>
      <List
        loading={loading}
        dataSource={items}
        locale={{ emptyText: "暂无通知" }}
        renderItem={(item) => (
          <List.Item
            style={{
              cursor: "pointer",
              padding: "10px 12px",
              background: item.read ? undefined : "#f0f5ff",
            }}
            onClick={() => handleClick(item)}
          >
            <List.Item.Meta
              title={
                <Typography.Text strong={!item.read} style={{ fontSize: 13 }}>
                  {item.title}
                </Typography.Text>
              }
              description={
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {formatTime(item.created_at)}
                </Typography.Text>
              }
            />
          </List.Item>
        )}
      />
      {items.length > 0 && (
        <div style={{ textAlign: "center", padding: "8px 0" }}>
          <Button type="link" size="small" onClick={handleReadAll}>
            全部已读
          </Button>
        </div>
      )}
    </div>
  );

  return (
    <Popover
      content={content}
      trigger="click"
      open={open}
      onOpenChange={handleOpenChange}
      placement="bottomRight"
      title="通知"
    >
      <Badge count={unread} size="small" offset={[-2, 4]}>
        <BellOutlined
          style={{ fontSize: 18, color: "#ffffffd9", cursor: "pointer" }}
        />
      </Badge>
    </Popover>
  );
}
