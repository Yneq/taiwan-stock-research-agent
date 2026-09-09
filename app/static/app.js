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
const tickerTrack = document.querySelector("#ticker-track");
const preflightLedger = document.querySelector("#preflight-ledger");
const memberButton = document.querySelector("#member-button");
const memberButtonLabel = document.querySelector("#member-button-label");
const authDialog = document.querySelector("#auth-dialog");
const memberDialog = document.querySelector("#member-dialog");
const loginForm = document.querySelector("#login-form");
const registerForm = document.querySelector("#register-form");
const loginTab = document.querySelector("#login-tab");
const registerTab = document.querySelector("#register-tab");
const demoLoginButton = document.querySelector("#demo-login-button");
const authReason = document.querySelector("#auth-reason");
const memberWatchlist = document.querySelector("#member-watchlist");

let lastQuestion = "";
let pendingQuestion = "";
let currentUser = null;
let loadingTimer;
let tickerRefreshTimer;

// Start the Java data service as soon as the public homepage is opened.
// This does not send a Gemini request or consume model tokens.
void warmDataService();
void loadMarketTicker();
const sessionReady = loadCurrentUser();

async function warmDataService() {
  try {
    const response = await fetch("/api/warmup", {
      method: "POST",
      keepalive: true,
    });
    if (!response.ok) return;

    const payload = await response.json();
    if (
      typeof payload.wake_url !== "string" ||
      !payload.wake_url.startsWith("https://")
    ) return;

    // A direct browser request reliably triggers Render's free-tier wake-up
    // while Python prepares the reusable MCP session in parallel. Private
    // Docker hostnames stay server-side and are never requested by the browser.
    void fetch(payload.wake_url, {
      method: "GET",
      mode: "no-cors",
      cache: "no-store",
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Warm-up is best effort; a real research request still performs retries.
  }
}

async function loadMarketTicker(allowRetry = true) {
  window.clearTimeout(tickerRefreshTimer);
  try {
    const response = await fetch("/api/market-ticker", { cache: "no-store" });
    if (!response.ok) throw new Error("Ticker request failed");
    const payload = await response.json();
    const items = Array.isArray(payload.items) ? payload.items : [];
    if (!items.length) throw new Error("Ticker data unavailable");
    renderMarketTicker(items);
    tickerRefreshTimer = window.setTimeout(() => void loadMarketTicker(false), 300000);
  } catch {
    renderTickerMessage("行情資料準備中 · 研究功能仍可使用");
    if (allowRetry) {
      tickerRefreshTimer = window.setTimeout(() => void loadMarketTicker(false), 30000);
    }
  }
}

function renderMarketTicker(items) {
  const nodes = [...items, ...items].map((item) => {
    const wrapper = document.createElement("span");
    wrapper.className = "ticker-item";
    const identity = document.createTextNode(
      `${item.stockCode || ""} ${item.stockName || "台股"} `,
    );
    const price = document.createElement("b");
    price.textContent = formatNumber(item.currentPrice);
    const changeValue = Number(item.changePercent);
    const change = document.createElement("b");
    change.className = `ticker-change ${changeValue > 0 ? "up" : changeValue < 0 ? "down" : "flat"}`;
    change.textContent = Number.isFinite(changeValue)
      ? `${changeValue > 0 ? "▲" : changeValue < 0 ? "▼" : "•"}${Math.abs(changeValue).toFixed(2)}%`
      : "—";
    wrapper.append(identity, price, change);
    return wrapper;
  });
  tickerTrack.replaceChildren(...nodes);
}

function renderTickerMessage(message) {
  const nodes = [message, message].map((text) => {
    const item = document.createElement("span");
    item.className = "ticker-message";
    const label = document.createElement("b");
    label.textContent = "TWSE";
    item.append(label, document.createTextNode(` ${text}`));
    return item;
  });
  tickerTrack.replaceChildren(...nodes);
}

question.addEventListener("input", () => {
  count.textContent = `${question.value.length} / 500`;
  question.style.height = "auto";
  question.style.height = `${Math.min(question.scrollHeight, 220)}px`;
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

memberButton.addEventListener("click", async () => {
  await sessionReady;
  if (!currentUser) {
    openAuthDialog("login", false);
    return;
  }
  openMemberDialog();
});

loginTab.addEventListener("click", () => setAuthMode("login"));
registerTab.addEventListener("click", () => setAuthMode("register"));

document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector(`#${button.dataset.closeDialog}`).close();
  });
});

[authDialog, memberDialog].forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitAuth("login", loginForm);
});

registerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void submitAuth("register", registerForm);
});

demoLoginButton.addEventListener("click", () => {
  void submitDemoAuth();
});

document.querySelector("#logout-button").addEventListener("click", () => {
  void logoutMember();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = question.value.trim();
  if (value.length < 3) return;
  lastQuestion = value;
  await sessionReady;
  if (!currentUser) {
    pendingQuestion = value;
    openAuthDialog("login", true);
    return;
  }
  void runResearch(value);
});

async function runResearch(value) {
  setLoading(true);

  try {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/x-ndjson" },
      body: JSON.stringify({ question: value }),
    });
    if (response.ok && response.headers.get("content-type")?.includes("application/x-ndjson")) {
      await readResearchProgress(response);
      return;
    }
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401) {
      setCurrentUser(null);
      pendingQuestion = value;
      openAuthDialog("login", true);
      return;
    }
    if (!response.ok) {
      const message = apiMessage(payload, "服務暫時無法完成研究，請稍後再試。");
      throw new Error(message);
    }
    renderResult(payload);
  } catch (error) {
    showError(error.message);
  } finally {
    setLoading(false);
  }
}

async function loadCurrentUser() {
  try {
    const response = await fetch("/api/session/status", { cache: "no-store" });
    if (!response.ok) {
      setCurrentUser(null);
      return;
    }
    const user = await response.json();
    setCurrentUser(user && typeof user === "object" ? user : null);
  } catch {
    setCurrentUser(null);
  }
}

function setCurrentUser(user) {
  currentUser = user;
  const avatar = memberButton.querySelector(".member-avatar");
  if (user) {
    memberButton.classList.add("authenticated");
    memberButtonLabel.textContent = user.username;
    avatar.textContent = firstCharacter(user.username, "會");
  } else {
    memberButton.classList.remove("authenticated");
    memberButtonLabel.textContent = "登入";
    avatar.textContent = "人";
  }
}

function openAuthDialog(mode = "login", fromResearch = false) {
  setAuthMode(mode);
  authReason.hidden = !fromResearch;
  document.querySelector("#login-submit-label").textContent = fromResearch
    ? "登入並繼續研究"
    : "登入會員";
  document.querySelector("#register-submit-label").textContent = fromResearch
    ? "建立會員並開始研究"
    : "建立會員";
  clearAuthMessages();
  if (!authDialog.open) authDialog.showModal();
  window.setTimeout(() => {
    const activeForm = mode === "register" ? registerForm : loginForm;
    activeForm.querySelector("input")?.focus();
  }, 0);
}

function setAuthMode(mode) {
  const registering = mode === "register";
  loginForm.hidden = registering;
  registerForm.hidden = !registering;
  loginTab.classList.toggle("active", !registering);
  registerTab.classList.toggle("active", registering);
  loginTab.setAttribute("aria-selected", String(!registering));
  registerTab.setAttribute("aria-selected", String(registering));
  document.querySelector("#auth-dialog-title").textContent = registering
    ? "建立查證終端會員"
    : "登入查證終端";
  clearAuthMessages();
}

async function submitAuth(mode, activeForm) {
  const formData = new FormData(activeForm);
  const payload = Object.fromEntries(formData.entries());
  const submitButton = activeForm.querySelector("button[type='submit']");
  const message = activeForm.querySelector("[data-auth-message]");
  submitButton.disabled = true;
  message.textContent = mode === "register" ? "正在建立會員…" : "正在驗證會員…";
  message.classList.remove("success");

  try {
    const response = await fetch(`/api/session/${mode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(apiMessage(data, "會員操作暫時無法完成"));

    finishAuthentication(data, activeForm);
  } catch (error) {
    message.textContent = error.message;
  } finally {
    submitButton.disabled = false;
  }
}

async function submitDemoAuth() {
  const message = document.querySelector("#demo-message");
  demoLoginButton.disabled = true;
  message.textContent = "正在準備 Demo 帳號…";

  try {
    const response = await fetch("/api/session/demo", { method: "POST" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(apiMessage(data, "Demo 帳號暫時無法登入"));
    finishAuthentication(data);
  } catch (error) {
    message.textContent = error.message;
  } finally {
    demoLoginButton.disabled = false;
  }
}

function finishAuthentication(data, activeForm = null) {
  setCurrentUser(data);
  activeForm?.reset();
  authDialog.close();

  const queuedQuestion = pendingQuestion;
  pendingQuestion = "";
  if (queuedQuestion) {
    lastQuestion = queuedQuestion;
    void runResearch(queuedQuestion);
  } else {
    openMemberDialog();
  }
}

async function openMemberDialog() {
  if (!currentUser) {
    openAuthDialog("login", false);
    return;
  }
  document.querySelector("#profile-username").textContent = currentUser.username;
  document.querySelector("#profile-email").textContent = currentUser.email || "尚未設定 Email";
  document.querySelector("#profile-avatar").textContent = firstCharacter(currentUser.username, "會");
  memberWatchlist.innerHTML = '<p class="watchlist-state">正在讀取自選股…</p>';
  document.querySelector("#watchlist-count").textContent = "— stocks";
  if (!memberDialog.open) memberDialog.showModal();

  try {
    const response = await fetch("/api/member/watchlist", { cache: "no-store" });
    const payload = await response.json().catch(() => ([]));
    if (response.status === 401) {
      memberDialog.close();
      setCurrentUser(null);
      openAuthDialog("login", false);
      return;
    }
    if (!response.ok) throw new Error(apiMessage(payload, "自選股暫時無法讀取"));
    renderMemberWatchlist(payload);
  } catch (error) {
    memberWatchlist.replaceChildren(createWatchlistState(error.message));
  }
}

function renderMemberWatchlist(items) {
  memberWatchlist.replaceChildren();
  document.querySelector("#watchlist-count").textContent = `${items.length} stocks`;
  if (!items.length) {
    memberWatchlist.append(createWatchlistState("尚未加入自選股，可回到 StockTracker 建立清單。"));
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "watchlist-item";
    const code = document.createElement("strong");
    code.textContent = item.stockCode || "—";
    const market = document.createElement("span");
    market.textContent = item.market || "TW";
    row.append(code, market);
    memberWatchlist.append(row);
  });
}

function createWatchlistState(text) {
  const state = document.createElement("p");
  state.className = "watchlist-state";
  state.textContent = text;
  return state;
}

async function logoutMember() {
  const button = document.querySelector("#logout-button");
  button.disabled = true;
  try {
    await fetch("/api/session/logout", { method: "POST" });
  } finally {
    setCurrentUser(null);
    memberDialog.close();
    button.disabled = false;
  }
}

function clearAuthMessages() {
  document.querySelector("#demo-message").textContent = "";
  document.querySelectorAll("[data-auth-message]").forEach((message) => {
    message.textContent = "";
    message.classList.remove("success");
  });
}

function apiMessage(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail) && payload.detail.length) {
    return payload.detail.map((item) => item.msg || "輸入資料格式不正確").join("；");
  }
  if (typeof payload?.error === "string") return payload.error;
  return fallback;
}

function firstCharacter(value, fallback) {
  return Array.from(String(value || "").trim())[0] || fallback;
}

async function readResearchProgress(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let complete = false;
  try {
    while (true) {
      const {value, done} = await reader.read();
      buffer += decoder.decode(value, {stream: !done});
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "error") throw new Error(event.detail);
        if (event.type === "result") {
          renderResult(event.data);
          complete = true;
        }
        if (event.type === "progress") {
          const seconds = (event.elapsed_ms / 1000).toFixed(1);
          const status = {started:"開始", completed:"完成", error:"失敗", retry:"等待重試"}[event.status] || event.status;
          const duration = event.duration_ms == null ? "" : ` · 耗時 ${(event.duration_ms / 1000).toFixed(1)} 秒`;
          const wait = event.wait_seconds == null ? "" : ` · 等待 ${event.wait_seconds} 秒`;
          const row = document.createElement("li");
          row.textContent = `${seconds}s · ${event.stage} · ${status}${duration}${wait}`;
          document.querySelector("#research-timing-list").append(row);
          loadingTitle.textContent = `${event.stage}：${status}${wait}`;
        }
      }
      if (done) break;
    }
    if (!complete) throw new Error("研究連線中斷，請重試；已收到的階段紀錄保留於下方。");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function setLoading(active) {
  submit.disabled = active;
  document.querySelectorAll("[data-question]").forEach((button) => {
    button.disabled = active;
  });
  loadingPanel.hidden = !active;
  if (active) {
    errorPanel.hidden = true;
    preflightLedger.hidden = true;
    results.hidden = true;
    loadingTitle.textContent = "正在連線，等待研究服務回報…";
    let timing = document.querySelector("#research-timing");
    if (!timing) {
      timing = document.createElement("details");
      timing.id = "research-timing";
      timing.open = true;
      timing.innerHTML = '<summary>研究階段與耗時</summary><p>由服務實際回報。行情、營收與新聞會先平行查詢，再由 Gemini 進行一次最終整理；平行耗時不可直接相加。</p><ol id="research-timing-list"></ol>';
      loadingPanel.after(timing);
    }
    document.querySelector("#research-timing-list").replaceChildren();
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
  preflightLedger.hidden = true;
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
    link.append(title);
    citations.append(link);
  });
}
