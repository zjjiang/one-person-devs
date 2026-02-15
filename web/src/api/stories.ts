import { request } from './client';
import type { Story } from '../types';

export const getStory = (id: number) => request<Story>(`/api/stories/${id}`);

export const createStory = (projectId: number, data: {
  title: string;
  raw_input: string;
  feature_tag?: string;
}) => request<{ id: number }>(`/api/projects/${projectId}/stories`, {
  method: 'POST',
  body: JSON.stringify(data),
});

export const confirmStage = (id: number) =>
  request<{ id: number; status: string }>(`/api/stories/${id}/confirm`, { method: 'POST' });

export const rejectStage = (id: number) =>
  request<{ id: number }>(`/api/stories/${id}/reject`, { method: 'POST' });

export const answerQuestions = (id: number, answers: { question: string; answer: string }[]) =>
  request(`/api/stories/${id}/answer`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  });

export const iterateStory = (id: number) =>
  request(`/api/stories/${id}/iterate`, { method: 'POST' });

export const restartStory = (id: number) =>
  request(`/api/stories/${id}/restart`, { method: 'POST' });

export const stopStory = (id: number) =>
  request(`/api/stories/${id}/stop`, { method: 'POST' });

export const preflightCheck = (id: number) =>
  request<{ ok: boolean; errors: string[]; warnings: string[] }>(`/api/stories/${id}/preflight`);
