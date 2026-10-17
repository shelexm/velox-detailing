// Clients screen: show the full visit history on demand.
document.querySelector("[data-show-extra]")?.addEventListener("click", (event) => {
  document.querySelectorAll(".timeline__item.is-extra").forEach((item) => (item.hidden = false));
  event.currentTarget.remove();
});
