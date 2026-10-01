import { fileURLToPath } from "node:url";
import { LayaApiClient } from "./layaClient.js";
import { buildChatServer } from "./server.js";

const secret = process.env.API_AUTH_SECRET ?? "";
if (secret.length < 32) throw new Error("API_AUTH_SECRET must be set and at least 32 characters");
const apiUrl = process.env.LAYA_API_URL ?? "http://api:8080";
const port = Number(process.env.PORT ?? 3000);
const publicDir = fileURLToPath(new URL("../public", import.meta.url));

const server = buildChatServer(new LayaApiClient(apiUrl, secret), publicDir);
server.listen(port, "0.0.0.0", () => console.log(`laya-chat listening on ${port} -> ${apiUrl}`));

for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
