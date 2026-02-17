/* TS types matching backend API responses */

export interface ProjectSummary {
  id: number;
  name: string;
  repo_url: string;
  story_count: number;
  workspace_status: "pending" | "cloning" | "ready" | "error";
}

export interface Rule {
  id: number;
  category: string;
  content: string;
  enabled: boolean;
}

export interface Skill {
  id: number;
  name: string;
  trigger: string;
}

export interface StorySummary {
  id: number;
  title: string;
  status: string;
}

export interface Project {
  id: number;
  name: string;
  repo_url: string;
  description: string;
  tech_stack: string;
  architecture: string;
  workspace_dir: string;
  workspace_status: "pending" | "cloning" | "ready" | "error";
  workspace_error: string;
  rules: Rule[];
  skills: Skill[];
  stories: StorySummary[];
}

export interface TaskItem {
  id: number;
  title: string;
  description: string;
  order: number;
  depends_on: number | null;
}

export interface PullRequest {
  pr_number: number;
  pr_url: string;
  status: string;
}

export interface RoundItem {
  id: number;
  round_number: number;
  type: string;
  status: string;
  branch_name: string | null;
  pull_requests: PullRequest[];
}

export interface ClarificationItem {
  id: number;
  question: string;
  answer: string | null;
}

export interface Story {
  id: number;
  title: string;
  status: string;
  feature_tag: string | null;
  raw_input: string;
  prd: string | null;
  confirmed_prd: string | null;
  technical_design: string | null;
  detailed_design: string | null;
  current_round: number;
  tasks: TaskItem[];
  rounds: RoundItem[];
  clarifications: ClarificationItem[];
  active_round_id: number | null;
}

export interface CapabilityProvider {
  name: string;
  config_schema: ConfigField[];
}

export interface ConfigField {
  name: string;
  label: string;
  type: "text" | "password" | "select";
  required?: boolean;
  options?: string[];
}

export interface CapabilityItem {
  capability: string;
  providers: CapabilityProvider[];
  saved: {
    enabled: boolean;
    provider_override: string | null;
    config_override: Record<string, string>;
  };
}

export const STAGE_ORDER = [
  "preparing",
  "clarifying",
  "planning",
  "designing",
  "coding",
  "verifying",
  "done",
] as const;

export const STAGE_LABELS: Record<string, string> = {
  preparing: "需求分析",
  clarifying: "需求澄清",
  planning: "技术方案",
  designing: "详细设计",
  coding: "AI 编码",
  verifying: "人工验证",
  done: "完成",
};

export const CAPABILITY_LABELS: Record<string, string> = {
  ai: "AI 编码",
  scm: "代码管理",
  ci: "持续集成",
  doc: "文档管理",
  sandbox: "沙箱环境",
  notification: "通知推送",
  requirement: "需求管理",
};
