import { request } from "./client";

export interface ConfigSchemaField {
  name: string;
  label: string;
  type: "text" | "password" | "select";
  required?: boolean;
  options?: string[];
}

export interface GlobalCapabilityItem {
  id: number;
  capability: string;
  provider: string;
  provider_label: string;
  label: string;
  config_schema: ConfigSchemaField[];
  enabled: boolean;
  config: Record<string, string>;
}

export interface AvailableCapability {
  capability: string;
  label: string;
  provider: string;
  provider_label: string;
  config_schema: ConfigSchemaField[];
}

export const getGlobalCapabilities = () =>
  request<GlobalCapabilityItem[]>("/api/settings/capabilities");

export const getAvailableCapabilities = () =>
  request<AvailableCapability[]>("/api/settings/capabilities/available");

export const createGlobalCapability = (data: {
  capability: string;
  provider: string;
  enabled?: boolean;
  label?: string;
  config?: Record<string, string>;
}) =>
  request<{ ok: boolean; id: number }>("/api/settings/capabilities", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const saveGlobalCapability = (
  id: number,
  data: {
    enabled: boolean;
    config_override?: Record<string, string>;
    label?: string;
  },
) =>
  request(`/api/settings/capabilities/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const deleteGlobalCapability = (id: number) =>
  request(`/api/settings/capabilities/${id}`, { method: "DELETE" });

export const testGlobalCapability = (
  id: number,
  data: { config: Record<string, string> },
) =>
  request<{ healthy: boolean; message: string }>(
    `/api/settings/capabilities/${id}/test`,
    { method: "POST", body: JSON.stringify(data) },
  );

export const verifyAllCapabilities = () =>
  request<Record<number, { healthy: boolean; message: string }>>(
    "/api/settings/capabilities/verify-all",
    { method: "POST" },
  );

export interface ExportCapabilityItem {
  capability: string;
  provider: string;
  enabled: boolean;
  label: string | null;
  config: Record<string, string> | null;
}

export const exportCapabilities = () =>
  request<ExportCapabilityItem[]>("/api/settings/capabilities/export");

export const importCapabilities = (data: {
  configs: ExportCapabilityItem[];
  skip_existing?: boolean;
}) =>
  request<{ ok: boolean; created: number; skipped: number }>(
    "/api/settings/capabilities/import",
    { method: "POST", body: JSON.stringify(data) },
  );
