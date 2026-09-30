/**
 * Development-only verification fixture for the + menu's Advanced submenu (adv-fixture.html).
 * Not part of the shell or the packaged app - it mounts the real App with FakeCoreClient so the
 * composer pill and the Advanced submenu can be screenshotted without a live Core.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles/app.css";
import { App } from "../App";
import { FakeCoreClient } from "../test/fakeClient";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App client={new FakeCoreClient()} />
  </StrictMode>,
);
