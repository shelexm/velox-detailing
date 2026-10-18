// Media library: upload several files (button or drag and drop) and replace a file in place.

import { api, panel, toast } from "./panel.js";

const progress = document.querySelector("[data-upload-progress]");

async function uploadAll(files) {
  const images = [...files].filter((f) => f.type.startsWith("image/"));
  if (!images.length) return;
  let done = 0;
  let failed = 0;
  progress.hidden = false;
  for (const file of images) {
    progress.textContent = `Загружаю ${done + failed + 1} из ${images.length}…`;
    const form = new FormData();
    form.append("file", file);
    const result = await api(`${panel.api}/media`, { method: "POST", formData: form });
    if (result.ok) done += 1;
    else {
      failed += 1;
      toast(`${file.name}: ${result.error?.details?.[0]?.message || result.error?.message || "не загрузилось"}`, "error");
    }
  }
  progress.textContent = `Загружено: ${done}${failed ? `, с ошибкой: ${failed}` : ""}`;
  if (done) {
    try {
      sessionStorage.setItem("velox:toast", `Загружено фото: ${done}. Добавьте описание (alt) каждому.`);
    } catch {}
    setTimeout(() => window.location.assign("?show=unused"), failed ? 2500 : 300);
  }
}

document.querySelector("[data-upload-many]")?.addEventListener("change", (event) => uploadAll(event.target.files));

const zone = document.querySelector("[data-dropzone]");
if (zone) {
  ["dragenter", "dragover"].forEach((type) =>
    window.addEventListener(type, (event) => {
      event.preventDefault();
      zone.classList.add("is-over");
    }),
  );
  ["dragleave", "drop"].forEach((type) => window.addEventListener(type, () => zone.classList.remove("is-over")));
  window.addEventListener("drop", (event) => {
    event.preventDefault();
    uploadAll(event.dataTransfer.files);
  });
}

document.querySelector("[data-replace]")?.addEventListener("change", async (event) => {
  const input = event.target;
  const file = input.files[0];
  if (!file) return;
  const label = input.closest("label");
  label.setAttribute("aria-busy", "true");
  const form = new FormData();
  form.append("file", file);
  const result = await api(input.dataset.replace, { method: "POST", formData: form });
  label.removeAttribute("aria-busy");
  input.value = "";
  if (!result.ok) {
    toast(result.error?.details?.[0]?.message || result.error?.message || "Не удалось заменить", "error");
    return;
  }
  try {
    sessionStorage.setItem("velox:toast", "Файл заменён: на сайте уже новое фото");
  } catch {}
  window.location.reload();
});
