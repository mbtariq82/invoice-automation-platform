import express from "express";
import {GoogleAuth} from "google-auth-library";
import path from "node:path";
import {fileURLToPath} from "node:url";

const apiBaseUrl = (process.env.API_BASE_URL ?? "").replace(/\/$/, "");
const googleClientId = process.env.GOOGLE_CLIENT_ID ?? "";
const port = Number(process.env.PORT ?? 8080);
if (!apiBaseUrl || !googleClientId) throw new Error("API_BASE_URL and GOOGLE_CLIENT_ID are required");

const app = express();
const auth = new GoogleAuth();
let apiClientPromise;
const getApiClient = () => apiClientPromise ??= auth.getIdTokenClient(apiBaseUrl);
const root = path.dirname(fileURLToPath(import.meta.url));

app.use((_request, response, next) => {
  response.set({
    "Content-Security-Policy": "default-src 'self'; script-src 'self' https://accounts.google.com/gsi/client; frame-src https://accounts.google.com/gsi/; connect-src 'self' https://accounts.google.com/gsi/; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://lh3.googleusercontent.com",
    "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY"
  });
  next();
});

app.get("/health", (_request, response) => response.json({status: "ok"}));
app.get("/config.js", (_request, response) => {
  response.type("application/javascript").send(`window.__APP_CONFIG__=${JSON.stringify({googleClientId})};`);
});

app.use("/api", express.raw({type: () => true, limit: "11mb"}), async (request, response) => {
  const userAuthorization = request.get("authorization") ?? "";
  if (!userAuthorization.toLowerCase().startsWith("bearer ")) {
    return response.status(401).json({detail: "Sign in before calling the API"});
  }
  try {
    const apiClient = await getApiClient();
    const serviceHeaders = await apiClient.getRequestHeaders(apiBaseUrl);
    const upstream = await fetch(`${apiBaseUrl}${request.url}`, {
      method: request.method,
      headers: {
        "Authorization": serviceHeaders.get("authorization") ?? "",
        "X-API-Authorization": userAuthorization,
        ...(request.get("content-type") ? {"Content-Type": request.get("content-type")} : {})
      },
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "manual"
    });
    response.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    if (contentType) response.type(contentType);
    response.send(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    console.error("API proxy failed", error);
    response.status(502).json({detail: "The invoice API is temporarily unavailable"});
  }
});

app.use(express.static(path.join(root, "dist"), {index: false, maxAge: "1h"}));
app.get("/{*path}", (_request, response) => response.sendFile(path.join(root, "dist", "index.html")));
app.listen(port, "0.0.0.0", () => console.log(`Frontend listening on ${port}`));
