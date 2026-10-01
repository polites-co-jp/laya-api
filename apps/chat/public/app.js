"use strict";

const STORAGE_KEY = "laya-chat.v1";

const CRITERIA_HINT = {
  noul: "任意。1行目に true の意味、2行目に false の意味を書きます（空欄なら criteria を送りません）",
  choice: "1行に1つ「ラベル: 説明」で書きます（2〜255個）",
  score: "1行に1つ、低い→高い順にラベルを書きます（2〜10個）"
};

const DEFAULT_STATE = {
  model: "laya-multilingual",
  session: "",
  user: "",
  questions: [
    { id: "urgent", type: "noul", instructions: "今日中の対応が必要か？", criteria: "当日中の返信が必要\n通常の順番で問題ない" },
    { id: "queue", type: "choice", instructions: "どの窓口が担当すべきか？", criteria: "returns: 返品・破損\ndelivery: 配送状況\nother: その他" },
    { id: "intensity", type: "score", instructions: "どのくらい急ぎか？", criteria: "Routine\nSoon\nToday\nImmediate" }
  ]
};

const $ = (sel) => document.querySelector(sel);
const log = $("#log");
const questionsEl = $("#questions");
const modelEl = $("#model");

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...structuredClone(DEFAULT_STATE), ...JSON.parse(raw) };
  } catch { /* 保存領域が使えなくても既定値で動かす */ }
  return structuredClone(DEFAULT_STATE);
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
  node.querySelector(".q-id").value = q.id;
  node.querySelector(".q-type").textContent = q.type;
  node.querySelector(".q-instructions").value = q.instructions;
  const criteria = node.querySelector(".q-criteria");
  criteria.value = q.criteria;
  criteria.placeholder = q.type === "noul" ? "true の意味\nfalse の意味" : "criteria";
  node.querySelector(".q-hint").textContent = CRITERIA_HINT[q.type];
  node.querySelector(".q-remove").addEventListener("click", () => {
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
    model: modelEl.value || state.model,
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
    else if (ls.length === 1) throw new Error(`${q.id}: noul の criteria は true と false の2行で書いてください`);
  } else if (q.type === "choice") {
    if (ls.length < 2) throw new Error(`${q.id}: choice の選択肢は2つ以上必要です`);
    out.criteria = Object.fromEntries(
      ls.map((l) => {
        const i = l.indexOf(":");
        return i < 0 ? [l, l] : [l.slice(0, i).trim(), l.slice(i + 1).trim()];
      })
    );
  } else if (q.type === "score") {
    if (ls.length < 2 || ls.length > 10) throw new Error(`${q.id}: score のラベルは2〜10個です`);
    out.criteria = ls;
  }
  return out;
}

function buildRequest(text) {
  const s = collect();
  if (s.questions.length === 0) throw new Error("質問を1つ以上追加してください");
  const questions = {};
  for (const q of s.questions) {
    if (!/^[A-Za-z0-9_.-]{1,64}$/.test(q.id)) throw new Error(`質問ID「${q.id}」は英数字と _ . - で64文字以内にしてください`);
    if (questions[q.id]) throw new Error(`質問ID「${q.id}」が重複しています`);
    if (!q.instructions) throw new Error(`${q.id}: instructions が空です`);
    questions[q.id] = toLayaQuestion(q);
  }
  let parsedState = text;
  const trimmed = text.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try { parsedState = JSON.parse(trimmed); } catch { /* JSON でなければ文章として送る */ }
  }
  const req = { model: s.model, state: parsedState, questions };
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
      el("div", { class: "value" }, p >= 0.5 ? "はい" : "いいえ", el("span", { class: "conf" }, `true の確率 ${pct(p)}`)),
      bars({ true: p, false: 1 - p }, p >= 0.5 ? "true" : "false"));
  }
  if (a.type === "score" || "score" in a) {
    const named = a.legend && a.legend[a.score] !== undefined ? a.legend[a.score] : undefined;
    const label = named !== undefined ? `${a.score}（${named}）` : String(a.score);
    return el("div", { class: "answer" }, head, el("div", { class: "value" }, label, conf), bars(a.probabilities, named ?? a.score));
  }
  return el("div", { class: "answer" }, head, el("div", { class: "value" }, String(a.choice), conf), bars(a.probabilities, a.choice));
}

function responseNode(status, body, headers, ms) {
  const box = el("div", { class: `msg bot${status >= 400 ? " error" : ""}` });
  if (status < 400 && body && body.answers) {
    for (const [id, a] of Object.entries(body.answers)) box.append(answerNode(id, a));
  } else {
    box.append(el("div", { class: "value" }, `エラー ${status}`), el("pre", {}, JSON.stringify(body, null, 2)));
  }
  const meta = [`${ms} ms`];
  if (body && body.model) meta.unshift(body.model);
  if (body && body.usage) meta.push(`input ${body.usage.input_tokens ?? "?"} / output ${body.usage.output_tokens ?? "?"} tokens`);
  for (const [k, v] of Object.entries(headers)) meta.push(`${k}: ${v}`);
  box.append(el("div", { class: "meta-line" }, meta.join(" ・ ")));
  box.append(el("details", {}, el("summary", { class: "meta-line" }, "生のJSON"), el("pre", {}, JSON.stringify(body, null, 2))));
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
  res.headers.forEach((v, k) => { if (k.startsWith("x-laya-") || k === "retry-after") headers[k] = v; });
  const raw = await res.text();
  let body;
  try { body = JSON.parse(raw); } catch { body = raw; }
  push(responseNode(res.status, body, headers, ms));
}

async function loadModels() {
  const fallback = ["laya-english", "laya-multilingual", "jev-latest", "jev-preview", "mercury-decide"];
  let names = fallback;
  try {
    const res = await fetch("/api/models");
    if (res.ok) {
      const data = await res.json();
      const got = (data.models ?? []).map((m) => (typeof m === "string" ? m : m.name)).filter(Boolean);
      if (got.length) names = got;
    }
  } catch { /* 取得できなければ既知の一覧を出す */ }
  if (!names.includes(state.model)) names = [state.model, ...names];
  modelEl.replaceChildren(...names.map((n) => el("option", { value: n }, n)));
  modelEl.value = state.model;
}

async function loadStatus() {
  const s = $("#status");
  try {
    const res = await fetch("/api/status");
    const data = await res.json().catch(() => ({}));
    const ready = res.ok && data.ready !== false;
    s.className = `status ${ready ? "ok" : "ng"}`;
    s.textContent = res.ok ? (ready ? "Laya ready" : `Laya not ready: ${data.reason ?? ""}`) : `API ${res.status}`;
  } catch {
    s.className = "status ng";
    s.textContent = "API に接続できません";
  }
}

// ---------- 起動 ----------

$("#session").value = state.session;
$("#user").value = state.user;
renderQuestions();
loadModels();
loadStatus();

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
  state = { ...collect(), questions: structuredClone(DEFAULT_STATE.questions) };
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
    push(el("div", { class: "msg bot error" }, `送信に失敗しました: ${err.message}`));
  } finally {
    btn.disabled = false;
    input.focus();
  }
});

$("#state").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("#composer").requestSubmit();
});
