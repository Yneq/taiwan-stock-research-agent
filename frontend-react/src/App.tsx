import { useEffect, useState } from "react";
import { demoLogin, getSession, logout } from "./api/research";
import { ResearchForm } from "./components/ResearchForm";
import { ResearchResult } from "./components/ResearchResult";
import { useResearch } from "./hooks/useResearch";
import type { MemberProfile } from "./types/research";

export function App() {
  const [member, setMember] = useState<MemberProfile | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError, setSessionError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const { state, run, busy } = useResearch();

  useEffect(() => {
    const controller = new AbortController();
    getSession(controller.signal)
      .then(setMember)
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setSessionError(error instanceof Error ? error.message : "登入狀態查詢失敗。");
      })
      .finally(() => {
        if (!controller.signal.aborted) setSessionLoading(false);
      });
    return () => controller.abort();
  }, []);

  async function signIn() {
    if (authBusy) return;
    setAuthBusy(true);
    setSessionError("");
    try {
      const profile = await demoLogin();
      setMember(profile);
      if (pendingQuestion) {
        const question = pendingQuestion;
        setPendingQuestion("");
        await run(question);
      }
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "體驗登入失敗，請稍後再試。");
    } finally {
      setAuthBusy(false);
    }
  }

  async function signOut() {
    setAuthBusy(true);
    setSessionError("");
    try {
      await logout();
      setMember(null);
    } catch (error) {
      setSessionError(error instanceof Error ? error.message : "登出失敗，請稍後再試。");
    } finally {
      setAuthBusy(false);
    }
  }

  function handleResearch(question: string) {
    if (!member) {
      setPendingQuestion(question);
      return;
    }
    void run(question);
  }

  return (
    <div className="site-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="FinScope TW 首頁">
          <span className="brand-mark">FS<span>.</span></span>
          <span>FinScope <em>TW</em></span>
        </a>
        <div className="topbar-right">
          <span className="edition">REACT + TYPESCRIPT EDITION</span>
          {sessionLoading ? (
            <span className="session-label">確認登入狀態…</span>
          ) : member ? (
            <button className="account-button" type="button" onClick={() => void signOut()} disabled={authBusy}>
              {member.username} · 登出
            </button>
          ) : (
            <button className="account-button" type="button" onClick={() => void signIn()} disabled={authBusy}>
              {authBusy ? "登入中…" : "一鍵體驗登入"}
            </button>
          )}
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="eyebrow"><span /> TAIWAN MARKET RESEARCH TERMINAL</div>
          <h1>每個數字，<br /><em>都有查詢軌跡。</em></h1>
          <p>以公開資料研究台股，保留工具結果與來源。查不到的地方，也會清楚告訴你。</p>
        </section>

        {sessionError && <div className="notice error-notice" role="alert">{sessionError}</div>}
        {pendingQuestion && !member && !sessionLoading && (
          <div className="notice" role="status">
            問題已暫存。請先登入體驗帳號，登入後會自動開始研究。
            <button type="button" onClick={() => void signIn()} disabled={authBusy}>
              {authBusy ? "登入中…" : "一鍵登入並繼續"}
            </button>
          </div>
        )}

        <ResearchForm busy={busy || authBusy || sessionLoading} onSubmit={handleResearch} />

        <div className="result-area" aria-live="polite">
          {state.status === "idle" && (
            <div className="empty-state">
              <span>01 — AWAITING REQUEST</span>
              <p>研究結果、工具軌跡與引用來源會顯示在這裡。</p>
            </div>
          )}
          {state.status === "loading" && (
            <div className="loading-state" role="status">
              <span className="loading-orbit" aria-hidden="true" />
              <div><strong>正在整理研究資料</strong><p>實際查詢可能需要一些時間，請保留此頁面。</p></div>
            </div>
          )}
          {state.status === "error" && (
            <div className="notice error-notice" role="alert">
              <strong>研究未完成</strong><p>{state.message}</p>
              {state.needsLogin && <button type="button" onClick={() => void signIn()}>重新登入</button>}
            </div>
          )}
          {state.status === "success" && <ResearchResult result={state.result} />}
        </div>
      </main>

      <footer>FINScope TW <span>·</span> 公開資訊研究輔助工具 <span>·</span> 非投資建議</footer>
    </div>
  );
}
