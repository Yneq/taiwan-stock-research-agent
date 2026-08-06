const form = document.querySelector("#research-form");
const question = document.querySelector("#question");
const count = document.querySelector("#character-count");
const submit = document.querySelector("#submit-button");
const loadingPanel = document.querySelector("#loading-panel");
const loadingTitle = document.querySelector("#loading-title");
const errorPanel = document.querySelector("#error-panel");
const errorMessage = document.querySelector("#error-message");
const results = document.querySelector("#results");
const answerContent = document.querySelector("#answer-content");
const traces = document.querySelector("#tool-traces");
const citations = document.querySelector("#citations");

let lastQuestion = "";
let loadingTimer;

question.addEventListener("input", () => {
  count.textContent = `${question.value.length} / 500`;
});

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    question.value = button.dataset.question;
    question.dispatchEvent(new Event("input"));
    form.requestSubmit();
  });
});

document.querySelector("#retry-button").addEventListener("click", () => {
  question.value = lastQuestion;
  form.requestSubmit();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = question.value.trim();
  if (value.length < 3) return;
  lastQuestion = value;
  setLoading(true);

  try {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: value }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = payload.detail || "服務暫時無法完成研究，請稍後再試。";
      throw new Error(message);
    }
    renderResult(payload);
  } catch (error) {
    showError(error.message);
  } finally {
    setLoading(false);
  }
});

function setLoading(active) {
  submit.disabled = active;
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.disabled = active;
  });
  loadingPanel.hidden = !active;
  errorPanel.hidden = true;
  if (active) {
    results.hidden = true;
    const messages = [
      "正在判斷需要查詢哪些資料…",
      "正在核對即時行情與公開來源…",
      "正在整理事實、事件與資料限制…",
    ];
    let index = 0;
    loadingTitle.textContent = messages[index];
    loadingTimer = window.setInterval(() => {
      index = Math.min(index + 1, messages.length - 1);
      loadingTitle.textContent = messages[index];
    }, 4500);
    loadingPanel.scrollIntoView({ behavior: "smooth", block: "center" });
  } else {
    window.clearInterval(loadingTimer);
  }
}

function showError(message) {
  errorMessage.textContent = message;
  errorPanel.hidden = false;
  errorPanel.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderResult(payload) {
  answerContent.replaceChildren(...formatAnswer(payload.answer));
  document.querySelector("#disclaimer").textContent = payload.disclaimer;
  document.querySelector("#model-badge").textContent = payload.model;
  renderTraces(payload.tool_calls || []);
  renderCitations(payload.citations || []);
  results.hidden = false;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

function formatAnswer(text) {
  const fragment = document.createDocumentFragment();
  const blocks = text.split(/\n{2,}/).filter(Boolean);
  blocks.forEach((block) => {
    const cleaned = block.trim();
    const headingMatch = cleaned.match(/^(?:#{1,3}\s*)?(摘要|關鍵數據|可能影響因素|資料限制|結論)[:：]?\s*(.*)$/s);
    if (headingMatch) {
      const heading = document.createElement("h3");
      heading.textContent = headingMatch[1];
      fragment.append(heading);
      if (headingMatch[2]) fragment.append(createParagraph(headingMatch[2]));
    } else {
      fragment.append(createParagraph(cleaned.replace(/^[-*]\s+/gm, "• ")));
    }
  });
  return Array.from(fragment.childNodes);
}

function createParagraph(text) {
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  paragraph.style.whiteSpace = "pre-line";
  return paragraph;
}

function renderTraces(items) {
  traces.replaceChildren();
  document.querySelector("#tool-count").textContent = `${items.length} tools`;
  items.forEach((item) => {
    const row = document.createElement("li");
    if (item.status !== "success") row.classList.add("error");
    const name = document.createElement("span");
    name.className = "trace-name";
    name.textContent = humanToolName(item.tool);
    const detail = document.createElement("span");
    detail.className = "trace-detail";
    detail.textContent = traceDetail(item);
    row.append(name, detail);
    traces.append(row);
  });
}

function humanToolName(name) {
  return {
    get_stock_snapshot: "即時行情核對",
    get_revenue_history: "月營收查詢",
    google_search: "公開新聞搜尋",
    search_news: "即時新聞搜尋",
  }[name] || name;
}

function traceDetail(item) {
  if (item.error) return item.error;
  if (item.tool === "google_search" || item.tool === "search_news") {
    return item.arguments.query || (item.arguments.queries || []).join(" · ");
  }
  const code = item.arguments.stock_code || "";
  const duration = item.duration_ms ? ` · ${item.duration_ms} ms` : "";
  return `${code}${duration}` || "完成";
}

function renderCitations(items) {
  citations.replaceChildren();
  document.querySelector("#citation-count").textContent = `${items.length} sources`;
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "這次回答未使用網路新聞來源。即時數據仍由 StockTracker 工具核對。";
    citations.append(empty);
    return;
  }
  items.forEach((item, index) => {
    const link = document.createElement("a");
    link.className = "citation-link";
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const title = document.createElement("strong");
    title.textContent = `${String(index + 1).padStart(2, "0")} · ${item.title}`;
    const arrow = document.createElement("span");
    arrow.textContent = "↗";
    title.append(arrow);
    const url = document.createElement("small");
    url.textContent = item.url;
    link.append(title, url);
    citations.append(link);
  });
}
