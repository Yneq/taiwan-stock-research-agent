import type { MemberProfile, ResearchResponse } from "../types/research";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function readError(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null);
  const detail =
    body && typeof body === "object" && "detail" in body &&
    typeof body.detail === "string"
      ? body.detail
      : "服務暫時無法完成請求，請稍後再試。";
  return new ApiError(response.status, detail);
}

export async function getSession(signal?: AbortSignal): Promise<MemberProfile | null> {
  const response = await fetch("/api/session/status", {
    credentials: "same-origin",
    cache: "no-store",
    signal,
  });
  if (!response.ok) throw await readError(response);
  return response.json() as Promise<MemberProfile | null>;
}

export async function demoLogin(): Promise<MemberProfile> {
  const response = await fetch("/api/session/demo", {
    method: "POST",
    credentials: "same-origin",
  });
  if (!response.ok) throw await readError(response);
  return response.json() as Promise<MemberProfile>;
}

export async function logout(): Promise<void> {
  const response = await fetch("/api/session/logout", {
    method: "POST",
    credentials: "same-origin",
  });
  if (!response.ok) throw await readError(response);
}

export async function submitResearch(question: string): Promise<ResearchResponse> {
  const response = await fetch("/api/research", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ question }),
  });
  if (!response.ok) throw await readError(response);
  return response.json() as Promise<ResearchResponse>;
}
