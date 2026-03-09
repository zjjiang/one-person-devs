import { request } from "./client";
import type { Story } from "../types";

export const getStory = (id: number) => request<Story>(`/api/stories/${id}`);

export const createStory = (
  projectId: number,
  data: {
    title: string;
    raw_input: string;
    feature_tag?: string;
  },
) =>
  request<{ id: number }>(`/api/projects/${projectId}/stories`, {
    method: "POST",
    body: JSON.stringify(data),
  });

export const confirmStage = (id: number) =>
  request<{ id: number; status: string; skipped_ai: boolean }>(
    `/api/stories/${id}/confirm`,
    {
      method: "POST",
    },
  );

export const rejectStage = (id: number) =>
  request<{ id: number }>(`/api/stories/${id}/reject`, { method: "POST" });

export const answerQuestions = (
  id: number,
  answers: { id: number; question: string; answer: string }[],
) =>
  request(`/api/stories/${id}/answer`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });

export const iterateStory = (id: number, feedback?: string) =>
  request(`/api/stories/${id}/iterate`, {
    method: "POST",
    body: JSON.stringify({ feedback: feedback || "" }),
  });

export const restartStory = (id: number, feedback?: string) =>
  request(`/api/stories/${id}/restart`, {
    method: "POST",
    body: JSON.stringify({ feedback: feedback || "" }),
  });

export const stopStory = (id: number) =>
  request(`/api/stories/${id}/stop`, { method: "POST" });

export const rollbackStory = (id: number, targetStage: string) =>
  request<{ id: number; status: string }>(`/api/stories/${id}/rollback`, {
    method: "POST",
    body: JSON.stringify({ target_stage: targetStage }),
  });

export const preflightCheck = (id: number) =>
  request<{ ok: boolean; errors: string[]; warnings: string[] }>(
    `/api/stories/${id}/preflight`,
  );

export const updatePrd = (id: number, prd: string) =>
  request<{ id: number; prd: string }>(`/api/stories/${id}/prd`, {
    method: "PUT",
    body: JSON.stringify({ prd }),
  });

export const sendChatMessage = (id: number, message: string) =>
  request<{ status: string }>(`/api/stories/${id}/chat`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });

export const listStoryDocs = (id: number) =>
  request<{ files: string[] }>(`/api/stories/${id}/docs`);

export const getStoryDoc = (id: number, filename: string) =>
  request<{ filename: string; content: string }>(
    `/api/stories/${id}/docs/${filename}`,
  );

export const saveStoryDoc = (id: number, filename: string, content: string) =>
  request<{ filename: string; path: string }>(
    `/api/stories/${id}/docs/${filename}`,
    {
      method: "PUT",
      body: JSON.stringify({ content }),
    },
  );

export const mergeStoryPR = (id: number) =>
  request<{ id: number; pr_number: number; status: string }>(
    `/api/stories/${id}/merge`,
    { method: "POST" },
  );

export const createStoryPR = (id: number) =>
  request<{ id: number; pr_number: number; pr_url: string }>(
    `/api/stories/${id}/create-pr`,
    { method: "POST" },
  );

export const getStoryDocDownloadUrl = (id: number, filename: string) =>
  `/api/stories/${id}/docs/${filename}/download`;

export const uploadStoryDoc = async (id: number, file: File) => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/stories/${id}/docs/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<{ filename: string; path: string }>;
};
