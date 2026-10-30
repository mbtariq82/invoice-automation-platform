import { GoogleOAuthProvider } from "@react-oauth/google";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "../styles.css";

declare global {
  interface Window { __APP_CONFIG__?: {googleClientId?: string}; }
}

const clientId = window.__APP_CONFIG__?.googleClientId ?? import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <GoogleOAuthProvider clientId={clientId}><App /></GoogleOAuthProvider>
  </StrictMode>
);
