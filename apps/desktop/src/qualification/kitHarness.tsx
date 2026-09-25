/**
 * Development-only qualification page for the F06 compositions (kit-fixture.html). It is not part
 * of the shell or the packaged app: the shell's CSP is inherited by srcdoc frames, and native App
 * UI serving from sealed Versions arrives with F08. It uses the shell's own Core client and bridge
 * host code against the Core named by VITE_ALPHA_CORE_URL / VITE_ALPHA_CORE_TOKEN.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles/app.css";
import { HttpCoreClient } from "../core/client";
import { KitFixture } from "./KitFixture";

const baseUrl = import.meta.env.VITE_ALPHA_CORE_URL as string | undefined;
const token = import.meta.env.VITE_ALPHA_CORE_TOKEN as string | undefined;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <div className="frame">
      <main className="frame__main frame__main--kit">
        {baseUrl && token ? (
          <KitFixture client={new HttpCoreClient({ baseUrl, token })} />
        ) : (
          <p role="alert">Set VITE_ALPHA_CORE_URL and VITE_ALPHA_CORE_TOKEN to a development Core.</p>
        )}
      </main>
    </div>
  </StrictMode>,
);
