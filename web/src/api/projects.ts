import { request } from "./client";
import type { ProjectSummary, Project } from "../types";

export const listProjects = () => request<ProjectSummary[]>("/api/projects");

export const getProject = (id: number) =>
  request<Project>(`/api/projects/${id}`);

export const createProject = (data: {
  name: string;
  repo_url: string;
  description?: string;
  tech_stack?: string;
  architecture?: string;
  workspace_dir?: string;
}) =>
  request<{ id: number }>("/api/projects", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateProject = (
  id: number,
  data: {
    name: string;
    repo_url: string;
    description?: string;
    tech_stack?: string;
    architecture?: string;
    workspace_dir?: string;
  },
) =>
  request<{ id: number }>(`/api/projects/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });

export const initWorkspace = (id: number) =>
  request<{ status: string; message: string }>(
    `/api/projects/${id}/init-workspace`,
    {
      method: "POST",
    },
  );

export const getWorkspaceStatus = (id: number) =>
  request<{ status: string; error: string }>(
    `/api/projects/${id}/workspace-status`,
  );

export const verifyRepo = (repo_url: string) =>
  request<{ healthy: boolean; message: string }>("/api/projects/verify-repo", {
    method: "POST",
    body: JSON.stringify({ repo_url }),
  });
