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
const dataDashboard = document.querySelector("#data-dashboard");
const metricGrid = document.querySelector("#metric-grid");
const chartGrid = document.querySelector("#chart-grid");

let lastQuestion = "";
let loadingTimer;

// Start the Java data service as soon as the public homepage is opened.
// This does not send a Gemini request or consume model tokens.
void fetch("/api/warmup", { method: "POST", keepalive: true }).catch(() => {});

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
  renderDataDashboard(payload.tool_calls || []);
  results.hidden = false;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

function formatAnswer(text) {
  const fragment = document.createDocumentFragment();
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  let paragraphLines = [];
  let list = null;

  const flushParagraph = () => {
    if (!paragraphLines.length) return;
    fragment.append(createParagraph(paragraphLines.join(" ")));
    paragraphLines = [];
  };

  const flushList = () => {
    if (!list) return;
    fragment.append(list);
    list = null;
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      return;
    }

    if (/^_{3,}$|^-{3,}$/.test(line)) {
      flushParagraph();
      flushList();
      fragment.append(document.createElement("hr"));
      return;
    }

    const heading = parseHeading(line);
    if (heading) {
      flushParagraph();
      flushList();
      const element = document.createElement(heading.level === 2 ? "h2" : "h3");
      appendInlineMarkdown(element, heading.title);
      fragment.append(element);
      if (heading.trailing) fragment.append(createParagraph(heading.trailing));
      return;
    }

    const unorderedItem = line.match(/^[-*•]\s+(.+)$/);
    const orderedItem = line.match(/^\d+[.)、]\s*(.+)$/);
    if (unorderedItem || orderedItem) {
      flushParagraph();
      const type = orderedItem ? "ol" : "ul";
      if (!list || list.tagName.toLowerCase() !== type) {
        flushList();
        list = document.createElement(type);
      }
      const item = document.createElement("li");
      appendInlineMarkdown(item, (orderedItem || unorderedItem)[1]);
      list.append(item);
      return;
    }

    flushList();
    paragraphLines.push(line);
  });

  flushParagraph();
  flushList();
  return Array.from(fragment.childNodes);
}

function parseHeading(line) {
  const markdownHeading = line.match(/^(#{1,4})\s+(.+)$/);
  if (markdownHeading) {
    return {
      level: markdownHeading[1].length <= 2 ? 2 : 3,
      title: normalizeHeading(markdownHeading[2]),
      trailing: "",
    };
  }

  const sectionHeading = line.match(
    /^(?:[一二三四五六七八九十]+[、.．]\s*)?(摘要|關鍵數據(?:與事實)?|可能影響因素|資料限制|結論)[:：]?\s*(.*)$/,
  );
  if (!sectionHeading) return null;
  return {
    level: 3,
    title: sectionHeading[1],
    trailing: sectionHeading[2],
  };
}

function normalizeHeading(text) {
  return text
    .replace(/^(?:[一二三四五六七八九十]+[、.．]\s*)/, "")
    .replace(/[:：]\s*$/, "");
}

function appendInlineMarkdown(parent, text) {
  const pattern = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*]+\*)/g;
  let cursor = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      parent.append(document.createTextNode(text.slice(cursor, match.index)));
    }
    const token = match[0];
    let element;
    if (token.startsWith("**") || token.startsWith("__")) {
      element = document.createElement("strong");
      element.textContent = token.slice(2, -2);
    } else if (token.startsWith("`")) {
      element = document.createElement("code");
      element.textContent = token.slice(1, -1);
    } else {
      element = document.createElement("em");
      element.textContent = token.slice(1, -1);
    }
    parent.append(element);
    cursor = pattern.lastIndex;
  }
  if (cursor < text.length) {
    parent.append(document.createTextNode(text.slice(cursor)));
  }
}

function createParagraph(text) {
  const paragraph = document.createElement("p");
  appendInlineMarkdown(paragraph, text);
  return paragraph;
}

function renderDataDashboard(items) {
  metricGrid.replaceChildren();
  chartGrid.replaceChildren();

  const snapshots = deduplicateToolData(items, "get_stock_snapshot");
  const revenues = deduplicateToolData(items, "get_revenue_history");

  snapshots.forEach((snapshot) => renderSnapshotMetrics(snapshot));
  snapshots.slice(0, 2).forEach((snapshot) => {
    const rows = [
      { label: "昨收", value: Number(snapshot.previousClose) },
      { label: "開盤", value: Number(snapshot.openPrice) },
      { label: "現價", value: Number(snapshot.currentPrice) },
    ].filter((row) => Number.isFinite(row.value));
    if (rows.length) {
      chartGrid.append(
        createChartCard(
          `${snapshot.stockCode || ""} 價格基準`,
          snapshot.stockName || "即時行情",
          rows,
          (value) => formatNumber(value),
          "price",
        ),
      );
    }
  });

  revenues.forEach((revenue) => {
    const rows = (revenue.data || [])
      .map((point) => ({
        label: formatMonth(point.date),
        value: Number(point.revenue),
      }))
      .filter((row) => Number.isFinite(row.value))
      .sort((a, b) => a.label.localeCompare(b.label))
      .slice(-12);
    if (rows.length) {
      chartGrid.append(
        createChartCard(
          `${revenue.stockCode || ""} 月營收趨勢`,
          `最近 ${rows.length} 個月 · TWD`,
          rows,
          formatCompactNumber,
          "revenue",
        ),
      );
    }
  });

  dataDashboard.hidden = metricGrid.childElementCount === 0 && chartGrid.childElementCount === 0;
}

function deduplicateToolData(items, toolName) {
  const unique = new Map();
  items
    .filter((item) => item.tool === toolName && item.status === "success" && item.data)
    .forEach((item) => {
      const key = item.data.stockCode || JSON.stringify(item.arguments);
      unique.set(key, item.data);
    });
  return Array.from(unique.values());
}

function renderSnapshotMetrics(snapshot) {
  const code = snapshot.stockCode || "台股";
  const name = snapshot.stockName || "即時行情";
  const change = Number(snapshot.changePercent);
  const changeTone = Number.isFinite(change) ? (change >= 0 ? "positive" : "negative") : "";
  metricGrid.append(
    createMetricCard(`${code} ${name}`, "即時成交", formatMoney(snapshot.currentPrice, snapshot.currency), "primary"),
    createMetricCard("今日漲跌", "相較昨收", formatPercent(change), changeTone),
    createMetricCard("今日開盤", code, formatMoney(snapshot.openPrice, snapshot.currency)),
    createMetricCard("昨日收盤", code, formatMoney(snapshot.previousClose, snapshot.currency)),
  );
}

function createMetricCard(title, caption, value, tone = "") {
  const card = document.createElement("article");
  card.className = `metric-card ${tone}`.trim();
  const top = document.createElement("div");
  const label = document.createElement("span");
  label.textContent = title;
  const detail = document.createElement("small");
  detail.textContent = caption;
  top.append(label, detail);
  const metric = document.createElement("strong");
  metric.textContent = value;
  card.append(top, metric);
  return card;
}

function createChartCard(title, subtitle, rows, formatter, tone) {
  const card = document.createElement("article");
  card.className = "chart-card";
  const heading = document.createElement("div");
  heading.className = "chart-heading";
  const text = document.createElement("div");
  const headingTitle = document.createElement("h3");
  headingTitle.textContent = title;
  const headingSubtitle = document.createElement("p");
  headingSubtitle.textContent = subtitle;
  text.append(headingTitle, headingSubtitle);
  const badge = document.createElement("span");
  badge.textContent = tone === "revenue" ? "REVENUE" : "PRICE";
  heading.append(text, badge);

  const plot = document.createElement("div");
  plot.className = `bar-chart ${tone}`;
  plot.setAttribute("role", "img");
  plot.setAttribute("aria-label", `${title}長條圖`);
  const maximum = Math.max(...rows.map((row) => row.value), 1);
  rows.forEach((row) => {
    const column = document.createElement("div");
    column.className = "bar-column";
    column.title = `${row.label}: ${formatter(row.value)}`;
    const value = document.createElement("span");
    value.className = "bar-value";
    value.textContent = formatter(row.value);
    const track = document.createElement("div");
    track.className = "bar-track";
    const bar = document.createElement("i");
    bar.style.height = `${Math.max(8, (row.value / maximum) * 100)}%`;
    track.append(bar);
    const label = document.createElement("span");
    label.className = "bar-label";
    label.textContent = row.label;
    column.append(value, track, label);
    plot.append(column);
  });
  card.append(heading, plot);
  return card;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 2 }).format(number);
}

function formatCompactNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("zh-TW", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(number);
}

function formatMoney(value, currency = "TWD") {
  const formatted = formatNumber(value);
  return formatted === "—" ? formatted : `${formatted} ${currency || "TWD"}`;
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatMonth(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})/);
  return match ? `${match[1]}/${match[2]}` : String(value || "");
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
