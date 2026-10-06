"use strict";

const STORAGE_KEY = "laya-chat.v2";
const LANG_KEY = "laya-chat.lang";

/** 画面の文言。index.html の data-i18n / data-i18n-placeholder がキーを参照する */
const I18N = {
  ja: {
    title: "Laya 判断チャット",
    switchTo: "English",
    statusChecking: "確認中…",
    empty: "右の欄で質問を決め、下の入力欄に判断させたい文章（state）を書いて送信します。",
    statePlaceholder: "判断対象の文章（state）。JSON を書くと JSON として送ります。Ctrl+Enter で送信",
    send: "送信",
    model: "モデル",
    modelAuto: "自動（言語で振り分け）",
    questions: "質問",
    metadata: "メタデータ（任意）",
    reset: "質問を初期状態に戻す",
    qIdPlaceholder: "質問ID",
    qInstructionsPlaceholder: "instructions（何を判断させるか）",
    qRemove: "削除",
    noulCriteriaPlaceholder: "true の意味\nfalse の意味",
    hint: {
      noul: "任意。1行目に true の意味、2行目に false の意味を書きます（空欄なら criteria を送りません）",
      choice: "1行に1つ「ラベル: 説明」で書きます（2〜100個）",
      score: "1行に1つ、低い→高い順にラベルを書きます（2〜32個）"
    },
    errNoulCriteria: (id) => `${id}: noul の criteria は true と false の2行で書いてください`,
    errChoiceCount: (id) => `${id}: choice の選択肢は2つ以上必要です`,
    errScoreCount: (id) => `${id}: score のラベルは2〜32個です`,
    errNoQuestions: "質問を1つ以上追加してください",
    errBadId: (id) => `質問ID「${id}」は英数字と _ . - で64文字以内にしてください`,
    errDupId: (id) => `質問ID「${id}」が重複しています`,
    errNoInstructions: (id) => `${id}: instructions が空です`,
    yes: "はい",
    no: "いいえ",
    trueProbability: "true の確率",
    error: "エラー",
    rawJson: "生のJSON",
    inference: "推論",
    sendFailed: "送信に失敗しました",
    notLoaded: "未ロード",
    layaUnreachable: "Laya に接続できません（起動中かもしれません）",
    apiUnreachable: "API に接続できません",
    defaultQuestions: [
      { id: "urgent", type: "noul", instructions: "今日中の対応が必要か？", criteria: "当日中の返信が必要\n通常の順番で問題ない" },
      { id: "queue", type: "choice", instructions: "どの窓口が担当すべきか？", criteria: "returns: 返品・破損\ndelivery: 配送状況\nother: その他" },
      { id: "intensity", type: "score", instructions: "どのくらい急ぎか？", criteria: "Routine\nSoon\nToday\nImmediate" }
    ]
  },
  en: {
    title: "Laya Decision Chat",
    switchTo: "日本語",
    statusChecking: "Checking…",
    empty: "Set up questions in the right panel, then type the text to judge (state) below and send it.",
    statePlaceholder: "Text to judge (state). JSON is sent as JSON. Ctrl+Enter to send",
    send: "Send",
    model: "Model",
    modelAuto: "Auto (route by language)",
    questions: "Questions",
    metadata: "Metadata (optional)",
    reset: "Reset questions to defaults",
    qIdPlaceholder: "Question ID",
    qInstructionsPlaceholder: "instructions (what to decide)",
    qRemove: "Remove",
    noulCriteriaPlaceholder: "Meaning of true\nMeaning of false",
    hint: {
      noul: "Optional. Line 1 is the meaning of true, line 2 the meaning of false (leave empty to omit criteria)",
      choice: "One \"label: description\" per line (2-100 options)",
      score: "One label per line, from low to high (2-32 labels)"
    },
    errNoulCriteria: (id) => `${id}: noul criteria needs two lines, true then false`,
    errChoiceCount: (id) => `${id}: choice needs at least two options`,
    errScoreCount: (id) => `${id}: score needs 2-32 labels`,
    errNoQuestions: "Add at least one question",
    errBadId: (id) => `Question ID "${id}" must be up to 64 characters of letters, digits, _ . -`,
    errDupId: (id) => `Question ID "${id}" is duplicated`,
    errNoInstructions: (id) => `${id}: instructions is empty`,
    yes: "Yes",
    no: "No",
    trueProbability: "P(true)",
    error: "Error",
    rawJson: "Raw JSON",
    inference: "inference",
    sendFailed: "Failed to send",
    notLoaded: "not loaded",
    layaUnreachable: "Cannot reach Laya (it may still be starting)",
    apiUnreachable: "Cannot reach the API",
    defaultQuestions: [
      { id: "urgent", type: "noul", instructions: "Does this need a response today?", criteria: "A same-day reply is needed\nThe normal queue is fine" },
      { id: "queue", type: "choice", instructions: "Which team should handle this?", criteria: "returns: Returns or damaged items\ndelivery: Delivery status\nother: Other" },
      { id: "intensity", type: "score", instructions: "How urgent is this?", criteria: "Routine\nSoon\nToday\nImmediate" }
    ]
  }
};

function initialLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved && saved in I18N) return saved;
  } catch { /* noop */ }
  return (navigator.language ?? "").toLowerCase().startsWith("ja") ? "ja" : "en";
}

let lang = initialLang();
const t = () => I18N[lang];

/** laya-serve が持つチェックポイント。空文字は「言語を見て自動で振り分け」 */
const MODELS = ["", "english", "multilingual", "typed-decisions"];

const defaultState = () => ({ model: "", session: "", user: "", questions: structuredClone(t().defaultQuestions) });

const $ = (sel) => document.querySelector(sel);
const log = $("#log");
const questionsEl = $("#questions");
const modelEl = $("#model");

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...defaultState(), ...JSON.parse(raw) };
  } catch { /* 保存領域が使えなくても既定値で動かす */ }
  return defaultState();
}

function save() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(collect())); } catch { /* noop */ }
}

let state = load();

// ---------- 質問エディタ ----------

function renderQuestions() {
  questionsEl.replaceChildren(...state.questions.map(questionNode));
}

function questionNode(q) {
  const node = $("#q-template").content.firstElementChild.cloneNode(true);
  node.dataset.type = q.type;
  const id = node.querySelector(".q-id");
  id.value = q.id;
  id.placeholder = t().qIdPlaceholder;
  node.querySelector(".q-type").textContent = q.type;
  const instructions = node.querySelector(".q-instructions");
  instructions.value = q.instructions;
  instructions.placeholder = t().qInstructionsPlaceholder;
  const criteria = node.querySelector(".q-criteria");
  criteria.value = q.criteria;
  criteria.placeholder = q.type === "noul" ? t().noulCriteriaPlaceholder : "criteria";
  node.querySelector(".q-hint").textContent = t().hint[q.type];
  const remove = node.querySelector(".q-remove");
  remove.title = t().qRemove;
  remove.setAttribute("aria-label", t().qRemove);
  remove.addEventListener("click", () => {
    state = collect();
    state.questions = state.questions.filter((_, i) => i !== [...questionsEl.children].indexOf(node));
    renderQuestions();
    save();
  });
  node.addEventListener("input", save);
  return node;
}

function collect() {
  return {
    model: modelEl.value,
    session: $("#session").value,
    user: $("#user").value,
    questions: [...questionsEl.children].map((n) => ({
      id: n.querySelector(".q-id").value.trim(),
      type: n.dataset.type,
      instructions: n.querySelector(".q-instructions").value.trim(),
      criteria: n.querySelector(".q-criteria").value
    }))
  };
}

function lines(text) {
  return text.split("\n").map((s) => s.trim()).filter(Boolean);
}

function toLayaQuestion(q) {
  const out = { type: q.type, instructions: q.instructions };
  const ls = lines(q.criteria);
  if (q.type === "noul") {
    if (ls.length >= 2) out.criteria = { true: ls[0], false: ls[1] };
    else if (ls.length === 1) throw new Error(t().errNoulCriteria(q.id));
  } else if (q.type === "choice") {
    if (ls.length < 2) throw new Error(t().errChoiceCount(q.id));
    out.criteria = Object.fromEntries(
      ls.map((l) => {
        const i = l.indexOf(":");
        return i < 0 ? [l, l] : [l.slice(0, i).trim(), l.slice(i + 1).trim()];
      })
    );
  } else if (q.type === "score") {
    if (ls.length < 2 || ls.length > 32) throw new Error(t().errScoreCount(q.id));
    out.criteria = ls;
  }
  return out;
}

function buildRequest(text) {
  const s = collect();
  if (s.questions.length === 0) throw new Error(t().errNoQuestions);
  const questions = {};
  for (const q of s.questions) {
    if (!/^[A-Za-z0-9_.-]{1,64}$/.test(q.id)) throw new Error(t().errBadId(q.id));
    if (questions[q.id]) throw new Error(t().errDupId(q.id));
    if (!q.instructions) throw new Error(t().errNoInstructions(q.id));
    questions[q.id] = toLayaQuestion(q);
  }
  let parsedState = text;
  const trimmed = text.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try { parsedState = JSON.parse(trimmed); } catch { /* JSON でなければ文章として送る */ }
  }
  const req = { state: parsedState, questions };
  if (s.model) req.model = s.model;
  if (s.session) req.session_id = s.session;
  if (s.user) req.user = s.user;
  return req;
}

// ---------- 表示 ----------

function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else n.setAttribute(k, v);
  }
  for (const c of children) if (c != null) n.append(c);
  return n;
}

function push(node) {
  $("#empty")?.remove();
  log.append(node);
  log.scrollTop = log.scrollHeight;
}

const pct = (v) => `${(v * 100).toFixed(1)}%`;

function bars(probabilities, top) {
  const entries = Object.entries(probabilities ?? {});
  if (entries.length === 0) return null;
  const grid = el("div", { class: "bars" });
  for (const [label, p] of entries) {
    const cls = label === String(top) ? "top" : "";
    grid.append(
      el("span", { class: cls }, label),
      el("div", { class: "bar" }, el("span", { style: `width:${Math.max(0, Math.min(1, p)) * 100}%` })),
      el("span", { class: `pct ${cls}` }, pct(p))
    );
  }
  return grid;
}

function answerNode(id, a) {
  const conf = typeof a.confidence === "number" ? el("span", { class: "conf" }, `confidence ${pct(a.confidence)}`) : null;
  const head = el("h3", {}, id, el("span", { class: "type" }, a.type ?? ""));
  if (a.type === "noul" || typeof a.noul === "number") {
    const p = Number(a.noul);
    return el("div", { class: "answer" }, head,
      el("div", { class: "value" }, p >= 0.5 ? t().yes : t().no, el("span", { class: "conf" }, `${t().trueProbability} ${pct(p)}`)),
      bars({ true: p, false: 1 - p }, p >= 0.5 ? "true" : "false"));
  }
  if (a.type === "score" || "score" in a) {
    // score は段階の期待値（小数）、probabilities のキーは段階の番号、legend が番号→ラベル名
    const legend = a.legend ?? {};
    const named = Object.fromEntries(Object.entries(a.probabilities ?? {}).map(([k, p]) => [legend[k] ?? k, p]));
    const top = Object.entries(named).sort((x, y) => y[1] - x[1])[0]?.[0];
    const score = typeof a.score === "number" ? a.score.toFixed(2) : String(a.score);
    return el("div", { class: "answer" }, head,
      el("div", { class: "value" }, top ?? score, el("span", { class: "conf" }, `score ${score}`), conf),
      bars(named, top));
  }
  return el("div", { class: "answer" }, head, el("div", { class: "value" }, String(a.choice), conf), bars(a.probabilities, a.choice));
}

function responseNode(status, body, headers, ms) {
  const box = el("div", { class: `msg bot${status >= 400 ? " error" : ""}` });
  if (status < 400 && body && body.answers) {
    for (const [id, a] of Object.entries(body.answers)) box.append(answerNode(id, a));
  } else {
    box.append(el("div", { class: "value" }, `${t().error} ${status}`), el("pre", {}, JSON.stringify(body, null, 2)));
  }
  const meta = [`${ms} ms`];
  if (body && body.routing && body.routing.model) meta.unshift(`model: ${body.routing.model}`);
  if (body && body.usage) meta.push(`input ${body.usage.input_tokens ?? "?"} / output ${body.usage.output_tokens ?? "?"} tokens`);
  for (const [k, v] of Object.entries(headers)) meta.push(`${k}: ${v}`);
  box.append(el("div", { class: "meta-line" }, meta.join(" ・ ")));
  box.append(el("details", {}, el("summary", { class: "meta-line" }, t().rawJson), el("pre", {}, JSON.stringify(body, null, 2))));
  return box;
}

// ---------- 通信 ----------

async function send(text) {
  let req;
  try {
    req = buildRequest(text);
  } catch (e) {
    push(el("div", { class: "msg bot error" }, e.message));
    return;
  }
  push(el("div", { class: "msg user" }, text));
  const started = performance.now();
  const res = await fetch("/api/systemone", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req)
  });
  const ms = Math.round(performance.now() - started);
  const headers = {};
  const inference = res.headers.get("x-inference-time-ms");
  if (inference) headers[t().inference] = `${inference} ms`;
  const retry = res.headers.get("retry-after");
  if (retry) headers["retry-after"] = retry;
  const raw = await res.text();
  let body;
  try { body = JSON.parse(raw); } catch { body = raw; }
  push(responseNode(res.status, body, headers, ms));
}

function renderModels() {
  modelEl.replaceChildren(...MODELS.map((value) => el("option", { value }, value || t().modelAuto)));
  modelEl.value = MODELS.includes(state.model) ? state.model : "";
}

/** 直近の /health の結果。言語を切り替えたときに表示し直す */
let health;

function renderStatus() {
  const s = $("#status");
  if (!health) {
    s.className = "status";
    s.textContent = t().statusChecking;
  } else if (health.ok) {
    s.className = "status ok";
    const loaded = (health.data.loaded ?? []).join(", ") || t().notLoaded;
    s.textContent = `Laya ready ・ ${health.data.device ?? "?"} ・ ${loaded}`;
  } else {
    s.className = "status ng";
    s.textContent = health.status === 502 ? t().layaUnreachable : health.status ? `API ${health.status}` : t().apiUnreachable;
  }
}

async function loadStatus() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json().catch(() => ({}));
    health = { ok: res.ok && data.status === "ok", status: res.status, data };
  } catch {
    health = { ok: false, status: 0, data: {} };
  }
  renderStatus();
}

function renderStatic() {
  document.documentElement.lang = lang;
  document.title = t().title;
  document.querySelectorAll("[data-i18n]").forEach((n) => (n.textContent = t()[n.dataset.i18n]));
  document.querySelectorAll("[data-i18n-placeholder]").forEach((n) => (n.placeholder = t()[n.dataset.i18nPlaceholder]));
  const btn = $("#lang");
  btn.textContent = t().switchTo;
  btn.lang = lang === "ja" ? "en" : "ja";
}

function setLang(next) {
  const prev = lang;
  state = collect();
  // 質問が既定の例題のままなら、例題も切り替え先の言語にする
  if (JSON.stringify(state.questions) === JSON.stringify(I18N[prev].defaultQuestions)) {
    state.questions = structuredClone(I18N[next].defaultQuestions);
  }
  lang = next;
  try { localStorage.setItem(LANG_KEY, lang); } catch { /* noop */ }
  renderStatic();
  renderQuestions();
  renderModels();
  renderStatus();
  save();
}

// ---------- 起動 ----------

$("#session").value = state.session;
$("#user").value = state.user;
renderStatic();
renderQuestions();
renderModels();
loadStatus();

$("#lang").addEventListener("click", () => setLang(lang === "ja" ? "en" : "ja"));

modelEl.addEventListener("change", save);
$("#session").addEventListener("input", save);
$("#user").addEventListener("input", save);

document.querySelectorAll("[data-add]").forEach((b) =>
  b.addEventListener("click", () => {
    state = collect();
    const type = b.dataset.add;
    state.questions.push({ id: `${type}_${state.questions.length + 1}`, type, instructions: "", criteria: "" });
    renderQuestions();
    save();
  })
);

$("#reset").addEventListener("click", () => {
  state = { ...collect(), questions: structuredClone(t().defaultQuestions) };
  renderQuestions();
  save();
});

$("#composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#state");
  const text = input.value;
  if (!text.trim()) return;
  const btn = $("#send");
  btn.disabled = true;
  try {
    await send(text);
    input.value = "";
  } catch (err) {
    push(el("div", { class: "msg bot error" }, `${t().sendFailed}: ${err.message}`));
  } finally {
    btn.disabled = false;
    input.focus();
  }
});

$("#state").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("#composer").requestSubmit();
});
