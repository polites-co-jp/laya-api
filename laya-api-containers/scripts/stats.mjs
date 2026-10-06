// laya-api の各コンテナのメモリ使用量を表示する。
//   npm run stats             1回だけ表示
//   npm run stats -- --watch  2秒ごとに表示し続ける（推論中のピークを見るとき。Ctrl+C で終了）
import { execFileSync } from "node:child_process";

const PROJECT = "laya-api";

function run(cmd, args) {
  try {
    return execFileSync(cmd, args, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return undefined;
  }
}

function jsonLines(text) {
  return (text ?? "").split("\n").filter(Boolean).map((l) => JSON.parse(l));
}

function snapshot() {
  const containers = jsonLines(
    run("docker", ["ps", "--filter", `label=com.docker.compose.project=${PROJECT}`, "--format", "{{json .}}"])
  );
  if (containers.length === 0) return "laya-api のコンテナは起動していません";

  const stats = new Map(
    jsonLines(run("docker", ["stats", "--no-stream", "--format", "{{json .}}", ...containers.map((c) => c.ID)])).map(
      (s) => [s.Name, s]
    )
  );

  const rows = containers
    .map((c) => {
      const s = stats.get(c.Names);
      // laya はコンテナに渡された LAYA_DEVICE（cuda / cpu）でモードを示す
      const device = c.Labels.includes("com.docker.compose.service=laya")
        ? run("docker", ["inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", c.ID])
            ?.split("\n")
            .find((e) => e.startsWith("LAYA_DEVICE="))
            ?.slice("LAYA_DEVICE=".length)
        : undefined;
      const mode = device === "cuda" ? "GPU" : device === "cpu" ? "CPU" : "";
      return [c.Names, mode, s?.MemUsage.split(" / ")[0] ?? "?", s?.CPUPerc ?? "?"];
    })
    .sort((a, b) => a[0].localeCompare(b[0]));

  const header = ["コンテナ", "モード", "RAM", "CPU"];
  const widths = header.map((h, i) => Math.max(h.length, ...rows.map((r) => r[i].length)) + 2);
  const line = (cols) => cols.map((c, i) => c.padEnd(widths[i])).join("");
  const out = [line(header), ...rows.map(line)];

  // Docker Desktop（WSL2）ではプロセスごとの VRAM が取れないため、GPU 全体の使用量だけ出す
  const gpu = run("nvidia-smi", ["--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"]);
  if (gpu) {
    for (const g of gpu.split("\n")) {
      const [name, used, total] = g.split(",").map((s) => s.trim());
      out.push(`GPU ${name}: VRAM ${used} / ${total} MiB（他のアプリの使用分を含む）`);
    }
  }
  return out.join("\n");
}

if (process.argv.includes("--watch")) {
  const tick = () => {
    process.stdout.write(`\x1b[2J\x1b[H${new Date().toLocaleTimeString()}\n${snapshot()}\n`);
  };
  tick();
  setInterval(tick, 2000);
} else {
  console.log(snapshot());
}
