import { useState } from "react";
import { ApiError, submitResearch } from "../api/research";
import type { ResearchResponse } from "../types/research";

type ResearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: ResearchResponse }
  | { status: "error"; message: string; needsLogin: boolean };

export function useResearch() {
  const [state, setState] = useState<ResearchState>({ status: "idle" });
  const [busy, setBusy] = useState(false);

  async function run(question: string) {
    if (busy) return;
    setBusy(true);
    setState({ status: "loading" });
    try {
      const result = await submitResearch(question);
      setState({ status: "success", result });
    } catch (error) {
      const needsLogin = error instanceof ApiError && error.status === 401;
      setState({
        status: "error",
        needsLogin,
        message: needsLogin
          ? "登入已失效，請重新使用體驗帳號登入。"
          : error instanceof Error
            ? error.message
            : "網路連線失敗，請稍後再試。",
      });
    } finally {
      setBusy(false);
    }
  }

  return { state, run, busy };
}
