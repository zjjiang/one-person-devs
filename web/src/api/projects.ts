import { request } from './client';
import type { ProjectSummary, Project } from '../types';

export const listProjects = () => request<ProjectSummary[]>('/api/projects');

export const getProject = (id: number) => request<Project>(`/api/projects/${id}`);

export const createProject = (data: {
  name: string;
  repo_url: string;
  description?: string;
  tech_stack?: string;
  architecture?: string;
}) => request<{ id: number }>('/api/projects', {
  method: 'POST',
  body: JSON.stringify(data),
});

export const updateProject = (id: number, data: {
  name: string;
  repo_url: string;
  description?: string;
  tech_stack?: string;
  architecture?: string;
}) => request<{ id: number }>(`/api/projects/${id}`, {
  method: 'PUT',
  body: JSON.stringify(data),
});
