import type { ResearchResponse } from "../types/research";
import Markdown from "react-markdown";

type Props = { result: ResearchResponse };

const toolNames: Record<string, string> = {
  get_stock_snapshot: "即時行情核對",
  get_revenue_history: "月營收查詢",
  search_news: "近期新聞搜尋",
};

export function ResearchResult({ result }: Props) {
  return (
    <section className="result-grid" aria-label="研究結果">
      <article className="panel answer-panel">
        <div className="panel-heading">
          <div>
            <div className="section-kicker">RESEARCH BRIEF / 研究摘要</div>
            <h2>查詢結果</h2>
          </div>
          <span className="stamp">已查證</span>
        </div>
        <div className="answer-text"><Markdown>{result.answer}</Markdown></div>
        <div className="disclaimer">{result.disclaimer}</div>
        <div className="model-name">整理模型 · {result.model}</div>
      </article>

      <div className="evidence-column">
        <section className="panel" aria-labelledby="trace-title">
          <div className="section-kicker">AUDIT TRAIL / 查詢軌跡</div>
          <h2 id="trace-title">研究軌跡 <small>{result.tool_calls.length} tools</small></h2>
          {result.tool_calls.length === 0 ? (
            <p className="muted">這次沒有使用外部查詢工具。</p>
          ) : (
            <ol className="trace-list">
              {result.tool_calls.map((trace, index) => (
                <li key={`${trace.tool}-${index}`}>
                  <span className={trace.status === "success" ? "status-dot success" : "status-dot error"} aria-hidden="true" />
                  <div>
                    <strong>{toolNames[trace.tool] ?? trace.tool}</strong>
                    <span className="trace-meta">
                      {String(trace.arguments.stock_code ?? trace.arguments.query ?? "")}
                      {" · "}{trace.duration_ms} ms
                    </span>
                    {trace.error && <span className="trace-error">{trace.error}</span>}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="panel" aria-labelledby="citation-title">
          <div className="section-kicker">SOURCES / 公開來源</div>
          <h2 id="citation-title">引用來源 <small>{result.citations.length} sources</small></h2>
          {result.citations.length === 0 ? (
            <p className="muted">這次沒有外部新聞來源。</p>
          ) : (
            <ol className="citation-list">
              {result.citations.map((citation, index) => {
                const safeUrl = /^https?:\/\//i.test(citation.url) ? citation.url : null;
                return (
                  <li key={`${citation.url}-${index}`}>
                    <span className="citation-index">{String(index + 1).padStart(2, "0")}</span>
                    {safeUrl ? (
                      <a href={safeUrl} target="_blank" rel="noopener noreferrer">
                        {citation.title} <span aria-hidden="true">↗</span>
                      </a>
                    ) : (
                      <span>{citation.title}</span>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      </div>
    </section>
  );
}
