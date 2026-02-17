import { request } from "./client";
import type { CapabilityItem } from "../types";

export interface CatalogItem {
  capability: string;
  label: string;
  providers: { name: string }[];
}

export const getCapabilityCatalog = () =>
  request<CatalogItem[]>("/api/capabilities/catalog");

export const getCapabilities = (projectId: number) =>
  request<CapabilityItem[]>(`/api/projects/${projectId}/capabilities`);

export const saveCapability = (
  projectId: number,
  capability: string,
  data: {
    enabled: boolean;
    provider_override?: string | null;
    config_override?: Record<string, string>;
  },
) =>
  request(`/api/projects/${projectId}/capabilities/${capability}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const batchSaveCapabilities = (
  projectId: number,
  items: {
    capability: string;
    enabled: boolean;
    provider_override?: string | null;
  }[],
) =>
  request(`/api/projects/${projectId}/capabilities/batch`, {
    method: "POST",
    body: JSON.stringify(items),
  });

export const testCapability = (
  projectId: number,
  capability: string,
  data: {
    provider: string;
    config: Record<string, string>;
  },
) =>
  request<{ healthy: boolean; message: string }>(
    `/api/projects/${projectId}/capabilities/${capability}/test`,
    { method: "POST", body: JSON.stringify(data) },
  );
