// Laya のモデルファイルのサイズと、1回の問い合わせで使ったメモリを表示する。
//   npm run stats                         既定の例文（日本語・3問）で1回問い合わせて測る
//   npm run stats -- --state "判断させたい文章"
//
// 1回分のメモリは、Laya プロセスのピーク RSS（/proc/<pid>/status の VmHWM）を問い合わせ直前にリセットし、
// 問い合わせ後に読んだピークと直前の RSS の差で求める。docker stats は約1秒間隔で、0.1秒前後の推論のピークを拾えないため。
// VRAM は Docker Desktop（WSL2）ではプロセスごとに取れないので、GPU 全体の使用量を 50ms 間隔で計測した差で示す。
import { execFileSync, spawn } from "node:child_process";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";

const PROJECT = "laya-api";
const HF_HUB = "/home/laya/.cache/huggingface/hub";
const envFile = new URL("../.env", import.meta.url);

function sh(args, opts = {}) {
  return execFileSync("docker", args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], ...opts }).trim();
}

function readEnv() {
  const env = {};
  for (const line of readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m) env[m[1]] = m[2];
  }
  return env;
}

function mb(bytes) {
  return `${(bytes / 1e6).toFixed(1)} MB`;
}

function signedRequest(baseUrl, secret, method, path, body) {
  // 署名方式は docs/ja/auth.md と apps/chat/src/layaClient.ts と同じ
  const timestamp = String(Date.now());
  const nonce = randomBytes(18).toString("base64url");
  const canonical = ["v1", timestamp, nonce, method, path, createHash("sha256").update(body).digest("hex")].join("\n");
  return fetch(baseUrl + path, {
    method,
    headers: {
      "content-type": "application/json",
      "x-auth-timestamp": timestamp,
      "x-auth-nonce": nonce,
      "x-auth-signature": createHmac("sha256", secret).update(canonical).digest("hex")
    },
    body
  });
}

/** GPU 全体の VRAM 使用量（MiB）を 50ms 間隔で記録する。nvidia-smi が無ければ undefined */
function startVramSampler() {
  let proc;
  try {
    proc = spawn("nvidia-smi", ["--query-gpu=memory.used", "--format=csv,noheader,nounits", "-lms", "50"]);
  } catch {
    return undefined;
  }
  const samples = [];
  let failed = false;
  proc.on("error", () => (failed = true));
  proc.stdout.on("data", (d) => {
    for (const l of String(d).split("\n")) if (l.trim()) samples.push({ t: Date.now(), mib: Number(l.split(",")[0]) });
  });
  return {
    samples,
    get failed() {
      return failed;
    },
    stop: () => proc.kill()
  };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- laya コンテナと Laya プロセス ----------

const container = sh([
  "ps", "-q",
  "--filter", `label=com.docker.compose.project=${PROJECT}`,
  "--filter", "label=com.docker.compose.service=laya"
]);
if (!container) {
  console.error("laya コンテナが起動していません（npm run dev:gpu または npm run dev:cpu で起動してください）");
  process.exit(1);
}

const device = sh(["inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", container])
  .split("\n")
  .find((e) => e.startsWith("LAYA_DEVICE="))
  ?.slice("LAYA_DEVICE=".length);

const procList = sh([
  "exec", "-u", "0", container, "sh", "-c",
  'for d in /proc/[0-9]*; do printf "%s\\t" "${d#/proc/}"; tr "\\0" " " < "$d/cmdline"; echo; done'
]);
const pid = procList
  .split("\n")
  .map((l) => l.split("\t"))
  .find(([, cmd]) => cmd && /python/.test(cmd) && /\/bin\/laya-serve/.test(cmd))?.[0];
if (!pid) {
  console.error("laya-serve のプロセスが見つかりません");
  process.exit(1);
}

function procMem() {
  const status = sh(["exec", "-u", "0", container, "cat", `/proc/${pid}/status`]);
  const kb = (key) => Number(status.match(new RegExp(`${key}:\\s+(\\d+) kB`))?.[1] ?? NaN) * 1024;
  return { rss: kb("VmRSS"), hwm: kb("VmHWM") };
}

// ---------- モデルファイル ----------

const files = sh([
  "exec", container, "sh", "-c",
  `find -L ${HF_HUB} -path '*/snapshots/*' -type f -exec stat -L -c '%s %n' {} +`
])
  .split("\n")
  .filter(Boolean)
  .map((l) => {
    const i = l.indexOf(" ");
    return { size: Number(l.slice(0, i)), path: l.slice(i + 1) };
  });

// snapshots/<sha>/model.safetensors は english、snapshots/<sha>/<名前>/model.safetensors はその名前のチェックポイント
const checkpoints = new Map();
for (const f of files) {
  const m = f.path.match(/models--([^/]+)\/snapshots\/[^/]+\/(.*)$/);
  if (!m) continue;
  const parts = m[2].split("/");
  const isSub = parts.length > 1 && !["tokenizer"].includes(parts[0]);
  const name = isSub ? parts[0] : m[1] === "convaiinnovations--laya" ? "english" : m[1].replace(/^.*--/, "");
  const entry = checkpoints.get(name) ?? { weights: 0, other: 0 };
  if (f.path.endsWith(".safetensors") || f.path.endsWith(".bin")) entry.weights += f.size;
  else entry.other += f.size;
  checkpoints.set(name, entry);
}
const cacheTotal = Number(sh(["exec", container, "du", "-sb", HF_HUB]).split(/\s+/)[0]);

console.log("■ モデルファイル（Hugging Face キャッシュ内）");
// 重みを持たないもの（共有の設定ファイルだけのフォルダ）は表に出さない。キャッシュ全体には含まれる
for (const [name, e] of [...checkpoints].filter(([, e]) => e.weights > 0).sort()) {
  console.log(`  ${name.padEnd(16)} 重み ${mb(e.weights).padStart(10)}   トークナイザ等 ${mb(e.other).padStart(9)}`);
}
console.log(`  キャッシュ全体   ${mb(cacheTotal).padStart(10)}`);

// ---------- 1回の問い合わせ ----------

const env = readEnv();
if (!env.API_AUTH_SECRET) {
  console.error(".env に API_AUTH_SECRET がありません");
  process.exit(1);
}
const stateArg = process.argv.indexOf("--state");
const state = stateArg > 0 ? process.argv[stateArg + 1] : "届いた商品が割れていました。今日中に交換してください！";
const body = JSON.stringify({
  state,
  questions: {
    urgent: { type: "noul", instructions: "今日中の対応が必要か？" },
    queue: { type: "choice", instructions: "どの窓口が担当すべきか？", criteria: { returns: "返品・破損", delivery: "配送状況", other: "その他" } },
    intensity: { type: "score", instructions: "どのくらい急ぎか？", criteria: ["Routine", "Soon", "Today", "Immediate"] }
  }
});
const apiUrl = `http://127.0.0.1:${env.API_HOST_PORT || 22300}`;

const vram = device === "cuda" ? startVramSampler() : undefined;
if (vram) await sleep(300);

sh(["exec", "-u", "0", container, "sh", "-c", `echo 5 > /proc/${pid}/clear_refs`]);
const before = procMem();
const sentAt = Date.now();
const res = await signedRequest(apiUrl, env.API_AUTH_SECRET, "POST", "/v1/systemone", body);
const text = await res.text();
const doneAt = Date.now();
const after = procMem();
if (vram) {
  await sleep(300);
  vram.stop();
}

console.log(`\n■ 1回の問い合わせ（${device === "cuda" ? "GPU" : device === "cpu" ? "CPU" : device ?? "?"} モード）`);
if (!res.ok) {
  console.log(`  失敗しました: HTTP ${res.status} ${text}`);
  process.exit(1);
}
const json = JSON.parse(text);
console.log(`  内容     : ${Object.keys(json.answers ?? {}).length}問、チェックポイント ${json.routing?.model ?? "?"}、入力 ${json.usage?.input_tokens ?? "?"} トークン`);
console.log(`  時間     : 推論 ${res.headers.get("x-inference-time-ms") ?? "?"} ms ／ 応答まで ${doneAt - sentAt} ms`);
console.log(
  `  RAM      : 直前 ${mb(before.rss)} → 処理中のピーク ${mb(after.hwm)}（この1回で +${mb(Math.max(0, after.hwm - before.rss))}）→ 直後 ${mb(after.rss)}`
);
if (vram && !vram.failed && vram.samples.length > 0) {
  const pre = vram.samples.filter((s) => s.t < sentAt);
  const during = vram.samples.filter((s) => s.t >= sentAt && s.t <= doneAt + 100);
  const base = pre.length ? pre[pre.length - 1].mib : vram.samples[0].mib;
  const peak = Math.max(base, ...during.map((s) => s.mib));
  console.log(`  VRAM     : 直前 ${base} MiB → 処理中のピーク ${peak} MiB（+${peak - base} MiB、GPU 全体の値）`);
  console.log("             torch は確保した VRAM を解放せず使い回すため、2回目以降の問い合わせでは増えにくい");
}
console.log("  ※ 起動後の最初の問い合わせは初期化を含むため、2回目以降より大きく出る");
