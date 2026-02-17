import { request } from "./client";

export interface GlobalCapabilityItem {
  capability: string;
  label: string;
  providers: { name: string; config_schema: ConfigSchemaField[] }[];
  saved: {
    enabled: boolean;
    provider: string | null;
    config: Record<string, string>;
  };
}

export interface ConfigSchemaField {
  name: string;
  label: string;
  type: "text" | "password" | "select";
  required?: boolean;
  options?: string[];
}

export const getGlobalCapabilities = () =>
  request<GlobalCapabilityItem[]>("/api/settings/capabilities");

export const saveGlobalCapability = (
  capability: string,
  data: {
    enabled: boolean;
    provider_override?: string | null;
    config_override?: Record<string, string>;
  },
) =>
  request(`/api/settings/capabilities/${capability}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const testGlobalCapability = (
  capability: string,
  data: { provider: string; config: Record<string, string> },
) =>
  request<{ healthy: boolean; message: string }>(
    `/api/settings/capabilities/${capability}/test`,
    { method: "POST", body: JSON.stringify(data) },
  );
