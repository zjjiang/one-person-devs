import { request } from "./client";

export interface LogEntry {
  ts: string;
  level: string;
  name: string;
  msg: string;
}

export interface LogHistoryResponse {
  items: LogEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface LogHistoryParams {
  page?: number;
  page_size?: number;
  level?: string;
  search?: string;
}

export function fetchLogHistory(params: LogHistoryParams = {}): Promise<LogHistoryResponse> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.level) qs.set("level", params.level);
  if (params.search) qs.set("search", params.search);
  const query = qs.toString();
  return request<LogHistoryResponse>(`/api/logs/history${query ? `?${query}` : ""}`);
}
