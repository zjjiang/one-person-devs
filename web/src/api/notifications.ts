import { request } from "./client";

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  message: string;
  link: string;
  read: boolean;
  story_id: number | null;
  project_id: number | null;
  created_at: string | null;
}

export function fetchNotifications(
  unreadOnly = false,
  limit = 20,
): Promise<NotificationItem[]> {
  const qs = new URLSearchParams();
  if (unreadOnly) qs.set("unread_only", "true");
  qs.set("limit", String(limit));
  return request<NotificationItem[]>(`/api/notifications?${qs}`);
}

export function fetchUnreadCount(): Promise<{ count: number }> {
  return request<{ count: number }>("/api/notifications/unread-count");
}

export function markRead(id: number): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/notifications/${id}/read`, {
    method: "POST",
  });
}

export function markAllRead(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/notifications/read-all", {
    method: "POST",
  });
}
