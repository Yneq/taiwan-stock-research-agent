import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import type { ResearchResponse } from "../src/types/research";

const result: ResearchResponse = {
  answer: "## 摘要\n台積電的**公開資訊**已整理。",
  tool_calls: [{
    tool: "get_stock_snapshot",
    arguments: { stock_code: "2330" },
    status: "success",
    duration_ms: 250,
    error: null,
    data: { currentPrice: 1000 },
  }],
  citations: [{
    title: "交易所公告",
    url: "https://example.com/news",
    cited_text: null,
  }],
  model: "gemini-test",
  disclaimer: "僅供研究參考",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("FinScope React research flow", () => {
  it("holds a submitted question for demo login, then renders answer, trace, and citation", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/session/status") return jsonResponse(null);
      if (path === "/api/session/demo") return jsonResponse({ username: "demo", email: "" });
      if (path === "/api/research") {
        expect(init?.credentials).toBe("same-origin");
        expect(JSON.parse(String(init?.body))).toEqual({ question: "台積電 2330 今天股價如何？" });
        return jsonResponse(result);
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "一鍵體驗登入" });
    await user.click(screen.getByRole("button", { name: "台積電 2330 今天股價如何？" }));
    await user.click(screen.getByRole("button", { name: "開始研究 ↗" }));
    expect(screen.getByText(/問題已暫存/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "一鍵登入並繼續" }));
    expect(await screen.findByRole("heading", { name: "摘要" })).toBeInTheDocument();
    expect(screen.getByText("公開資訊", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("即時行情核對")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /交易所公告/ })).toHaveAttribute("href", "https://example.com/news");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("shows loading and blocks repeat submissions until research completes", async () => {
    let finish!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => { finish = resolve; });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input) === "/api/session/status") {
        return Promise.resolve(jsonResponse({ username: "demo", email: "" }));
      }
      if (String(input) === "/api/research") return pending;
      throw new Error("Unexpected request");
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "demo · 登出" });
    await user.type(screen.getByRole("textbox", { name: "研究問題" }), "2330 今天股價");
    await user.click(screen.getByRole("button", { name: "開始研究 ↗" }));
    expect(screen.getByRole("status")).toHaveTextContent("正在整理研究資料");
    expect(screen.getByRole("button", { name: "研究中…" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(2);

    finish(jsonResponse(result));
    expect(await screen.findByText("即時行情核對")).toBeInTheDocument();
  });

  it("shows the API error detail when research fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/session/status") {
        return jsonResponse({ username: "demo", email: "" });
      }
      return jsonResponse({ detail: "上游資料來源暫時不可用" }, 502);
    }));

    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "demo · 登出" });
    await user.type(screen.getByRole("textbox", { name: "研究問題" }), "2330 今天股價");
    await user.click(screen.getByRole("button", { name: "開始研究 ↗" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("上游資料來源暫時不可用");
    expect(screen.queryByText("即時行情核對")).not.toBeInTheDocument();
  });

  it("asks for login again if the research session has expired", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/session/status") {
        return jsonResponse({ username: "demo", email: "" });
      }
      return jsonResponse({ detail: "Not authenticated" }, 401);
    }));

    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "demo · 登出" });
    await user.type(screen.getByRole("textbox", { name: "研究問題" }), "2330 今天股價");
    await user.click(screen.getByRole("button", { name: "開始研究 ↗" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("登入已失效"));
    expect(screen.getByRole("button", { name: "重新登入" })).toBeInTheDocument();
  });
});
