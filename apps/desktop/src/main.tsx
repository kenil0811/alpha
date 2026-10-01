import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AvatarBoot, isAvatarWindow } from "./avatar/boot";
import "./styles/app.css";
import { applyAppearance, readAppearance } from "./shell/appearance";

applyAppearance(readAppearance());

/** A window that went blank tells nobody anything. Any error that escapes rendering is shown
 *  in the window with a way back, and the same for errors thrown outside React. */
class Guard extends React.Component<{ children: React.ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(error: unknown) {
    return { error: error instanceof Error ? `${error.message}\n${error.stack ?? ""}` : String(error) };
  }
  componentDidMount() {
    window.addEventListener("error", (event) => this.setState({ error: `${event.message}\n${event.error?.stack ?? ""}` }));
    window.addEventListener("unhandledrejection", (event) => this.setState({ error: `Unhandled: ${String((event as PromiseRejectionEvent).reason)}` }));
  }
  render() {
    if (this.state.error) {
      return (
        <section className="page" role="alert" style={{ padding: 24 }}>
          <h2>Alpha's window hit a problem</h2>
          <p className="panel__hint">Reload to carry on; nothing you saved is affected.</p>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, userSelect: "text" }}>{this.state.error}</pre>
          <button type="button" className="btn btn--primary" onClick={() => window.location.reload()}>
            Reload
          </button>
        </section>
      );
    }
    return this.props.children;
  }
}

const container = document.getElementById("root");
if (!container) throw new Error("missing #root");
const root = createRoot(container);
void isAvatarWindow().then((avatar) => {
  root.render(
    <React.StrictMode>
      <Guard>{avatar ? <AvatarBoot /> : <App />}</Guard>
    </React.StrictMode>,
  );
});
