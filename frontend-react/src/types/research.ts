export type MemberProfile = {
  id?: number | null;
  username: string;
  email: string;
};

export type ToolTrace = {
  tool: string;
  arguments: Record<string, unknown>;
  status: string;
  duration_ms: number;
  error: string | null;
  data: Record<string, unknown> | null;
};

export type Citation = {
  title: string;
  url: string;
  cited_text: string | null;
};

export type ResearchResponse = {
  answer: string;
  tool_calls: ToolTrace[];
  citations: Citation[];
  model: string;
  disclaimer: string;
};
