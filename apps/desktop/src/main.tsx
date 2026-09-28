import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { AvatarBoot, isAvatarWindow } from "./avatar/boot";
import "./styles/app.css";

const container = document.getElementById("root");
if (!container) throw new Error("missing #root");
const root = createRoot(container);
void isAvatarWindow().then((avatar) => {
  root.render(<React.StrictMode>{avatar ? <AvatarBoot /> : <App />}</React.StrictMode>);
});
