// Image field for panel forms: pick a photo from the studio library or upload a new one.
// Markup: [data-media-field] with a hidden input (the image id), a preview and buttons
// [data-media-pick] / [data-media-clear]. One shared <dialog data-media-dialog> lists the library.

import { api, panel, toast } from "./panel.js";

const dialog = document.querySelector("[data-media-dialog]");
let target = null;
let library = null;

function setField(field, asset) {
  const input = field.querySelector("input[type=hidden]");
  const preview = field.querySelector("[data-media-preview]");
  input.value = asset ? String(asset.id) : "";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  preview.replaceChildren();
  if (asset) {
    const img = document.createElement("img");
    img.src = asset.thumb;
    img.alt = asset.alt || "";
    preview.append(img);
  } else {
    const empty = document.createElement("span");
    empty.className = "media-field__empty";
    empty.textContent = "Нет фото";
    preview.append(empty);
  }
  field.classList.toggle("has-image", Boolean(asset));
}

async function loadLibrary(force = false) {
  if (library && !force) return library;
  const result = await api(`${panel.api}/media`);
  library = result.ok ? result.data : [];
  return library;
}

function renderGrid(items) {
  const grid = dialog.querySelector("[data-media-grid]");
  const current = target?.querySelector("input[type=hidden]")?.value;
  grid.replaceChildren(
    ...items.map((asset) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "media-tile";
      button.setAttribute("aria-pressed", String(String(asset.id) === current));
      button.title = asset.alt || asset.original_name || "";
      const img = document.createElement("img");
      img.src = asset.thumb;
      img.alt = "";
      img.loading = "lazy";
      button.append(img);
      if (asset.is_example) {
        const tag = document.createElement("span");
        tag.className = "media-tile__tag mono";
        tag.textContent = "ПРИМЕР";
        button.append(tag);
      }
      button.addEventListener("click", () => {
        setField(target, asset);
        dialog.close();
      });
      return button;
    }),
  );
  dialog.querySelector("[data-media-empty]").hidden = items.length > 0;
}

async function open(field) {
  target = field;
  dialog.showModal();
  renderGrid(await loadLibrary());
}

if (dialog) {
  document.addEventListener("click", (event) => {
    const pick = event.target.closest("[data-media-pick]");
    if (pick) {
      event.preventDefault();
      open(pick.closest("[data-media-field]"));
    }
    const clear = event.target.closest("[data-media-clear]");
    if (clear) {
      event.preventDefault();
      setField(clear.closest("[data-media-field]"), null);
    }
  });

  const upload = dialog.querySelector("[data-media-upload]");
  upload?.addEventListener("change", async () => {
    const file = upload.files[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("alt", dialog.querySelector("[data-media-alt]")?.value || "");
    const label = dialog.querySelector("[data-media-upload-label]");
    label.setAttribute("aria-busy", "true");
    const result = await api(`${panel.api}/media`, { method: "POST", formData: form });
    label.removeAttribute("aria-busy");
    upload.value = "";
    if (!result.ok) {
      toast(result.error?.details?.[0]?.message || result.error?.message || "Не удалось загрузить", "error");
      return;
    }
    toast("Фото загружено");
    library = [result.data, ...(library || [])];
    setField(target, result.data);
    dialog.close();
  });
}

export { setField, loadLibrary };
