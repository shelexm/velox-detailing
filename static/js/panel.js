// VÉLOX studio panel: one small module for every page.
// Pages are rendered on the server; this script sends changes to the admin JSON API with the CSRF token,
// shows field errors from 422 responses and refreshes the page when the server state changed.

const CSRF_COOKIE = "velox_csrf";
const body = document.body;
export const panel = { api: body.dataset.panelApi || "", url: body.dataset.panelUrl || "", tz: body.dataset.tz || "" };

function csrfToken() {
  const row = document.cookie.split("; ").find((c) => c.startsWith(`${CSRF_COOKIE}=`));
  return row ? decodeURIComponent(row.slice(CSRF_COOKIE.length + 1)) : "";
}

export async function api(url, { method = "GET", data, formData } = {}) {
  const headers = { Accept: "application/json" };
  let payload;
  if (formData) payload = formData;
  else if (data !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(data);
  }
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  let response;
  try {
    response = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
  } catch {
    return { ok: false, status: 0, error: { message: "Нет связи с сервером. Проверьте подключение." } };
  }
  if (response.status === 401 && !url.endsWith("/auth/login")) {
    window.location.href = `/admin/login?next=${encodeURIComponent(location.pathname + location.search)}`;
    return { ok: false, status: 401, error: { message: "Требуется вход" } };
  }
  let json = null;
  if (response.status !== 204) json = await response.json().catch(() => null);
  if (!response.ok) {
    // A proxy answers 413 or 502/504 with HTML, not JSON: say what happened instead of a generic error.
    const fallback =
      response.status === 413
        ? "Файл слишком большой для загрузки"
        : response.status === 502 || response.status === 504
          ? "Сервер не успел ответить. Попробуйте ещё раз или выберите файл поменьше"
          : "Ошибка сервера";
    return { ok: false, status: response.status, error: json?.error || { message: fallback } };
  }
  return { ok: true, status: response.status, data: json };
}

// ---------- toasts and confirm ----------
export function toast(message, kind = "ok") {
  const zone = document.querySelector("[data-toasts]");
  if (!zone || !message) return;
  const node = document.createElement("div");
  node.className = `toast${kind === "error" ? " toast--error" : ""}`;
  node.setAttribute("role", kind === "error" ? "alert" : "status");
  node.textContent = message;
  zone.append(node);
  setTimeout(() => node.remove(), kind === "error" ? 7000 : 3500);
}

// After a reload the message survives in sessionStorage, so "Сохранено" is still visible.
function toastAfterReload(message) {
  try {
    sessionStorage.setItem("velox:toast", message);
  } catch {}
}
try {
  const pending = sessionStorage.getItem("velox:toast");
  if (pending) {
    sessionStorage.removeItem("velox:toast");
    toast(pending);
  }
} catch {}

export function confirmAction({ title, text = "", ok = "Да", danger = true }) {
  // Own data-confirm-dialog-* hooks: buttons use data-confirm/data-confirm-ok for their texts.
  const dialog = document.querySelector("[data-confirm-dialog]");
  if (!dialog?.showModal) return Promise.resolve(window.confirm(title));
  dialog.querySelector("[data-confirm-dialog-title]").textContent = title;
  dialog.querySelector("[data-confirm-dialog-text]").textContent = text;
  const button = dialog.querySelector("[data-confirm-dialog-ok]");
  button.textContent = ok;
  button.className = `btn ${danger ? "btn--danger" : "btn--primary"}`;
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) => dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok"), { once: true }));
}

function finish(element, message) {
  const { reload, redirect } = element.dataset;
  if (redirect) {
    if (message) toastAfterReload(message);
    window.location.href = redirect;
  } else if (reload !== undefined) {
    if (message) toastAfterReload(message);
    window.location.reload();
  } else if (message) toast(message);
}

// ---------- forms ----------
function setPath(target, path, value) {
  const keys = path.split(".");
  let node = target;
  keys.forEach((key, i) => {
    const last = i === keys.length - 1;
    const nextIsIndex = !last && /^\d+$/.test(keys[i + 1]);
    if (last) node[key] = value;
    else {
      node[key] ??= nextIsIndex ? [] : {};
      node = node[key];
    }
  });
}

function compact(value) {
  // Lists built from indexed names may have holes when rows were removed.
  if (Array.isArray(value)) return value.filter((v) => v !== undefined).map(compact);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, compact(v)]));
  return value;
}

function readField(el) {
  const type = el.dataset.type || (el.type === "number" ? "int" : "text");
  if (type === "bool") return el.checked;
  const raw = el.value;
  if (type === "int") return raw.trim() === "" ? null : Number(raw.replace(/\s/g, ""));
  if (type === "lines") return raw.split("\n").map((s) => s.trim()).filter(Boolean);
  if (type === "list") return raw.split(",").map((s) => s.trim()).filter(Boolean);
  if (type === "json") return raw.trim() ? JSON.parse(raw) : null;
  if (type === "nullable") return raw.trim() === "" ? null : raw.trim();
  return raw.trim();
}

export function serialize(form) {
  const data = {};
  const groups = new Map();
  for (const el of form.elements) {
    if (!el.name || el.disabled || el.dataset.ignore !== undefined) continue;
    if (el.type === "radio") {
      if (el.checked) setPath(data, el.name, el.dataset.type === "int" ? Number(el.value) : el.value);
      continue;
    }
    if (el.type === "checkbox" && el.dataset.type !== "bool") {
      // A group of checkboxes with the same name is a list of ids/values.
      if (!groups.has(el.name)) groups.set(el.name, []);
      if (el.checked) groups.get(el.name).push(el.dataset.type === "ids" || /^\d+$/.test(el.value) ? Number(el.value) : el.value);
      continue;
    }
    if (el.type === "file" || el.type === "submit" || el.type === "button") continue;
    const value = readField(el);
    if (value === null && el.dataset.skipEmpty !== undefined) continue;
    setPath(data, el.name, value);
  }
  for (const [name, values] of groups) setPath(data, name, values);
  return compact(data);
}

function clearErrors(form) {
  form.querySelectorAll("[data-error-for]").forEach((n) => {
    n.hidden = true;
    n.textContent = "";
  });
  form.querySelectorAll("[aria-invalid]").forEach((n) => n.removeAttribute("aria-invalid"));
  const alert = form.querySelector("[data-form-alert]");
  if (alert) alert.hidden = true;
}

export function showErrors(form, error) {
  let shown = false;
  for (const detail of error?.details || []) {
    const field = String(detail.field || "").replace(/^body\./, "");
    const slot = form.querySelector(`[data-error-for="${CSS.escape(field)}"]`) || form.querySelector(`[data-error-for="${CSS.escape(field.split(".")[0])}"]`);
    const input = form.querySelector(`[name="${CSS.escape(field)}"]`);
    if (input) input.setAttribute("aria-invalid", "true");
    if (slot) {
      slot.textContent = detail.message;
      slot.hidden = false;
      shown = true;
    }
  }
  const alert = form.querySelector("[data-form-alert]");
  if (!shown) {
    if (alert) {
      alert.querySelector("[data-form-alert-text]").textContent = error?.message || "Не удалось сохранить";
      alert.hidden = false;
    } else toast(error?.message || "Не удалось сохранить", "error");
  }
  form.querySelector('[aria-invalid="true"]')?.focus();
}

async function submitForm(form, submitter) {
  clearErrors(form);
  if (form.dataset.confirm && !(await confirmAction({ title: form.dataset.confirm, ok: form.dataset.confirmOk || "Да" }))) return;
  let data;
  try {
    data = serialize(form);
  } catch {
    toast("Проверьте формат данных", "error");
    return;
  }
  const extra = form.dataset.extra ? JSON.parse(form.dataset.extra) : {};
  const button = submitter || form.querySelector('[type="submit"]');
  button?.setAttribute("aria-busy", "true");
  const method = submitter?.dataset.method || form.dataset.method || "POST";
  const action = submitter?.dataset.action || form.dataset.action;
  const result = await api(action, { method, data: { ...data, ...extra } });
  button?.removeAttribute("aria-busy");
  if (!result.ok) {
    showErrors(form, result.error);
    return;
  }
  form.dispatchEvent(new CustomEvent("panel:saved", { detail: result.data, bubbles: true }));
  if (form.dataset.reset !== undefined) form.reset();
  form.querySelectorAll("[data-dirty-note]").forEach((n) => (n.hidden = true));
  if (form.id) document.querySelectorAll(`[data-dirty-for="${form.id}"]`).forEach((n) => (n.hidden = true));
  // A saved form can still warn, e.g. "в эти дни у мастера 2 записи": data-warn-key + data-warn-text with {n}.
  const warnValue = form.dataset.warnKey ? result.data?.[form.dataset.warnKey] : 0;
  const message = warnValue ? form.dataset.warnText.replace("{n}", warnValue) : form.dataset.success || "Сохранено";
  const target = submitter?.dataset.redirect ? submitter : form;
  if (target.dataset.redirect?.includes("{id}") && result.data?.id) target.dataset.redirect = target.dataset.redirect.replace("{id}", result.data.id);
  finish(target, message);
}

document.addEventListener("submit", (event) => {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  submitForm(form, event.submitter);
});

// "Есть несохранённые изменения" inside the form or linked to it by id (data-dirty-for).
function markDirty(form) {
  if (!form) return;
  form.querySelectorAll("[data-dirty-note]").forEach((n) => (n.hidden = false));
  if (form.id) document.querySelectorAll(`[data-dirty-for="${form.id}"]`).forEach((n) => (n.hidden = false));
}

document.addEventListener("input", (event) => {
  const form = event.target.closest("form[data-form]");
  markDirty(form);
  const el = event.target;
  if (el.matches("[aria-invalid]")) el.removeAttribute("aria-invalid");
  const counter = el.id && document.querySelector(`[data-count-for="${CSS.escape(el.id)}"]`);
  if (counter) counter.textContent = `${el.value.length} / ${el.maxLength}`;
});

// ---------- one-click API actions ----------
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-api]");
  if (!button) return;
  event.preventDefault();
  if (button.dataset.confirm && !(await confirmAction({ title: button.dataset.confirm, text: button.dataset.confirmText || "", ok: button.dataset.confirmOk || "Да", danger: button.dataset.confirmSafe === undefined }))) return;
  button.setAttribute("aria-busy", "true");
  const data = button.dataset.body ? JSON.parse(button.dataset.body) : undefined;
  const result = await api(button.dataset.api, { method: button.dataset.method || "POST", data });
  button.removeAttribute("aria-busy");
  if (!result.ok) {
    toast(result.error?.message || "Не получилось", "error");
    return;
  }
  button.dispatchEvent(new CustomEvent("panel:done", { detail: result.data, bubbles: true }));
  finish(button, button.dataset.done || "Готово");
});

// Switches that save immediately: <input type="checkbox" data-toggle="/api/..." data-field="online_booking">.
document.addEventListener("change", async (event) => {
  const input = event.target.closest("input[data-toggle]");
  if (!input) return;
  input.disabled = true;
  const result = await api(input.dataset.toggle, { method: "PATCH", data: { [input.dataset.field]: input.checked } });
  input.disabled = false;
  if (!result.ok) {
    input.checked = !input.checked;
    toast(result.error?.details?.[0]?.message || result.error?.message || "Не сохранилось", "error");
    return;
  }
  toast(input.checked ? input.dataset.on || "Включено" : input.dataset.off || "Выключено");
});

// Ordering with up/down buttons inside [data-sortable data-order-api]; children carry data-id.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-move]");
  if (!button) return;
  const item = button.closest("[data-id], [data-repeat-row]");
  const list = item?.parentElement;
  if (!item || !list) return;
  const sameKind = (n) => n && (item.dataset.id ? n.dataset.id : n.matches("[data-repeat-row]"));
  const sibling = button.dataset.move === "up" ? item.previousElementSibling : item.nextElementSibling;
  if (!sameKind(sibling)) return;
  if (button.dataset.move === "up") sibling.before(item);
  else sibling.after(item);
  button.focus();
  if (list.matches("[data-repeat]")) {
    renumber(list);
    markDirty(list.closest("form"));
    return;
  }
  if (!list.dataset.orderApi) return;
  // Most lists are ordered by numeric ids; landing blocks by their keys (data-order-field="keys").
  const field = list.dataset.orderField || "ids";
  const values = [...list.children].filter((n) => n.dataset.id).map((n) => (field === "ids" ? Number(n.dataset.id) : n.dataset.id));
  const result = await api(list.dataset.orderApi, { method: "POST", data: { [field]: values } });
  toast(result.ok ? "Порядок сохранён" : result.error?.message || "Порядок не сохранился", result.ok ? "ok" : "error");
});

// Repeated rows (gallery items, list entries): [data-repeat] holds rows, a <template data-repeat-template>,
// buttons [data-repeat-add] and [data-repeat-remove]; names use __i__ for the row index.
// data-repeat-prefix="days.0.breaks" renumbers only that level, so nested lists keep their parent index.
function renumber(box) {
  const prefix = box.dataset.repeatPrefix;
  const pattern = prefix ? new RegExp(`^${prefix.replace(/\./g, "\\.")}\\.\\d+\\.`) : /\.\d+\./;
  [...box.querySelectorAll(":scope > [data-repeat-row]")].forEach((row, index) => {
    row.querySelectorAll("[name]").forEach((el) => (el.name = el.name.replace(pattern, prefix ? `${prefix}.${index}.` : `.${index}.`)));
  });
}
document.addEventListener("click", (event) => {
  const add = event.target.closest("[data-repeat-add]");
  if (add) {
    const box = document.querySelector(add.dataset.repeatAdd);
    const template = box?.querySelector("template[data-repeat-template]");
    if (!template) return;
    const index = box.querySelectorAll(":scope > [data-repeat-row]").length;
    const html = template.innerHTML.replaceAll("__i__", String(index));
    template.insertAdjacentHTML("beforebegin", html);
    markDirty(box.closest("form"));
    box.querySelectorAll(":scope > [data-repeat-row]")[index]?.querySelector("input, textarea, button")?.focus();
    return;
  }
  const remove = event.target.closest("[data-repeat-remove]");
  if (remove) {
    const row = remove.closest("[data-repeat-row]");
    const box = row.parentElement;
    row.remove();
    renumber(box);
    markDirty(box.closest("form"));
  }
});

// Filter forms (form[data-autosubmit]) reload the page as soon as a field changes.
document.addEventListener("change", (event) => {
  const form = event.target.closest("form[data-autosubmit]");
  if (form && event.target.matches("select, input")) form.submit();
});

// Whole table rows open their record; links and controls inside keep working.
document.addEventListener("click", (event) => {
  const row = event.target.closest("[data-href]");
  if (!row || event.target.closest("a, button, input, select, textarea, label")) return;
  window.location.href = row.dataset.href;
});

// ---------- sign in / out ----------
const login = document.querySelector("[data-login]");
if (login) {
  login.addEventListener("submit", async (event) => {
    event.preventDefault();
    const alert = login.querySelector("[data-form-alert]");
    alert.hidden = true;
    const button = login.querySelector('[type="submit"]');
    button.setAttribute("aria-busy", "true");
    const result = await api("/api/v1/auth/login", { method: "POST", data: { email: login.email.value.trim(), password: login.password.value } });
    button.removeAttribute("aria-busy");
    if (result.ok) {
      window.location.href = login.dataset.next || "/admin";
      return;
    }
    alert.querySelector("[data-form-alert-text]").textContent = result.status === 422 ? "Введите e-mail и пароль" : result.error.message;
    alert.hidden = false;
    login.password.value = "";
    login.password.focus();
  });
}

document.querySelectorAll("[data-logout]").forEach((button) =>
  button.addEventListener("click", async () => {
    await api("/api/v1/auth/logout", { method: "POST" });
    window.location.href = "/admin/login";
  }),
);

// Character counters for fields with a limit.
document.querySelectorAll("[data-count-for]").forEach((counter) => {
  const field = document.getElementById(counter.dataset.countFor);
  if (field) counter.textContent = `${field.value.length} / ${field.maxLength}`;
});
