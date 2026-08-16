import { AppShell } from "./AppShell";

document.addEventListener("DOMContentLoaded", () => {
  const appElement = document.getElementById("app");
  if (appElement) {
    const app = new AppShell(appElement);
    app.init();
  }
});
