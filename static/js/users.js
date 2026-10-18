// Access screen: shows a temporary password once (after adding a person or resetting a password).

const dialog = document.querySelector("[data-password-dialog]");
const value = dialog?.querySelector("[data-password-value]");

function show(detail) {
  if (!detail?.temporary_password) {
    // An existing account was added to the studio: nothing to show, just refresh the list.
    window.location.reload();
    return;
  }
  value.textContent = detail.temporary_password;
  dialog.showModal();
}

document.addEventListener("panel:done", (event) => {
  if (event.target.closest("[data-show-password]")) show(event.detail);
});
document.addEventListener("panel:saved", (event) => {
  if (event.target.closest("[data-show-password-form]")) show(event.detail);
});

dialog?.querySelector("[data-password-copy]").addEventListener("click", async (event) => {
  try {
    await navigator.clipboard.writeText(value.textContent);
    event.currentTarget.textContent = "Скопировано";
  } catch {
    window.getSelection().selectAllChildren(value);
  }
});
dialog?.querySelector("[data-password-close]").addEventListener("click", () => dialog.close());
// The password is never kept: closing the dialog reloads the page and drops it from the DOM.
dialog?.addEventListener("close", () => window.location.reload());
