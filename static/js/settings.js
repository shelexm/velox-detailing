// Settings: show the one-time code for linking the admins' Telegram chat.
document.addEventListener("panel:done", (event) => {
  if (!event.target.closest("[data-link-code]")) return;
  const box = document.querySelector("[data-link-code-value]");
  box.textContent = event.detail.command;
  box.hidden = false;
  event.target.closest("[data-link-code]").hidden = true;
});
