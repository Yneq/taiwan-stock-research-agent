import { useState, type FormEvent } from "react";

type Props = {
  busy: boolean;
  onSubmit: (question: string) => void;
};

const suggestions = [
  "台積電 2330 今天股價如何？",
  "聯發科 2454 近期有哪些重要消息？",
  "光洋科 1785 最近月營收表現？",
];

export function ResearchForm({ busy, onSubmit }: Props) {
  const [question, setQuestion] = useState("");
  const valid = question.trim().length >= 3;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid || busy) return;
    onSubmit(question.trim());
  }

  return (
    <section className="research-card" aria-labelledby="form-title">
      <div className="section-kicker">RESEARCH REQUEST / 研究申請</div>
      <h2 id="form-title">提出一個台股問題</h2>
      <p className="muted">系統會先查詢可用資料，再整理成附有軌跡的研究摘要。</p>
      <form onSubmit={handleSubmit}>
        <label htmlFor="question">研究問題</label>
        <textarea
          id="question"
          name="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={500}
          rows={4}
          placeholder="例如：台積電 2330 今天股價如何？"
        />
        <div className="form-footer">
          <span className="counter">{question.length} / 500</span>
          <button type="submit" disabled={!valid || busy}>
            {busy ? "研究中…" : "開始研究 ↗"}
          </button>
        </div>
      </form>
      <div className="suggestions" aria-label="快速提問">
        {suggestions.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            disabled={busy}
            onClick={() => setQuestion(suggestion)}
          >
            {suggestion}
          </button>
        ))}
      </div>
    </section>
  );
}
