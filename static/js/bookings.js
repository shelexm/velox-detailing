// Bookings screen: the edit panel saves details, reschedules and changes status through the admin API,
// one call after another (each bumps the booking version); the "new booking" panel suggests free times.

import { api, serialize, showErrors, toast } from "./panel.js";

const phone = window.matchMedia("(max-width: 900px)");

// Phones open a booking as a full page instead of the side panel.
document.addEventListener("click", (event) => {
  const link = event.target.closest("[data-phone-href]");
  if (link && phone.matches) {
    event.preventDefault();
    window.location.href = link.dataset.phoneHref;
  }
});

function clear(form) {
  form.querySelectorAll("[data-error-for]").forEach((n) => (n.hidden = true));
  form.querySelectorAll("[aria-invalid]").forEach((n) => n.removeAttribute("aria-invalid"));
  const alert = form.querySelector("[data-form-alert]");
  if (alert) alert.hidden = true;
}

function slotTakenMessage(error) {
  const times = (error.details?.alternatives || []).slice(0, 3).map((iso) => iso.slice(11, 16));
  return times.length ? `${error.message}. Свободно: ${times.join(", ")}` : error.message;
}

// ---------- edit ----------
const editor = document.querySelector("[data-booking-editor]");
const editForm = editor?.querySelector("[data-booking-form]");
if (editForm) {
  const original = JSON.parse(editor.dataset.original);
  const base = editor.dataset.bookingApi;

  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clear(editForm);
    const now = serialize(editForm);
    const button = editForm.querySelector('[type="submit"]');
    let version = original.version;
    const steps = [];

    const detailKeys = ["contact_name", "vehicle", "client_comment", "internal_note"];
    if (detailKeys.some((k) => (now[k] ?? "") !== (original[k] ?? ""))) {
      steps.push(() => ({ url: base, method: "PATCH", data: { ...Object.fromEntries(detailKeys.map((k) => [k, now[k]])), version } }));
    }
    const moved = now.date !== original.date || now.time !== original.time || now.service_id !== original.service_id || (now.staff_id ?? "") !== (original.staff_id || "");
    if (moved) {
      steps.push(() => ({
        url: `${base}/reschedule`,
        method: "POST",
        data: { starts_at: `${now.date}T${now.time}:00`, service_id: now.service_id, staff_id: now.staff_id || null, version },
      }));
    }
    if (now.status && now.status !== original.status) {
      steps.push(() => ({ url: `${base}/status`, method: "POST", data: { status: now.status, version } }));
    }
    if (!steps.length) {
      toast("Изменений нет");
      return;
    }
    button.setAttribute("aria-busy", "true");
    for (const step of steps) {
      const { url, method, data } = step();
      const result = await api(url, { method, data });
      if (!result.ok) {
        button.removeAttribute("aria-busy");
        if (result.error?.code === "slot_taken") result.error.message = slotTakenMessage(result.error);
        showErrors(editForm, result.error);
        return;
      }
      version = result.data.version;
    }
    try {
      sessionStorage.setItem("velox:toast", "Запись сохранена");
    } catch {}
    window.location.reload();
  });
}

// ---------- create ----------
const creator = document.querySelector("[data-booking-create]");
if (creator) {
  const slotsBox = creator.querySelector("[data-free-slots]");
  const timeInput = creator.querySelector('[name="time"]');
  let token = 0;

  async function loadSlots() {
    const service = creator.service_id.value;
    const day = creator.date.value;
    if (!service || !day) return;
    const mine = ++token;
    slotsBox.setAttribute("aria-busy", "true");
    const params = new URLSearchParams({ service_id: service, date_from: day, days: "1" });
    if (creator.staff_id.value) params.set("staff_id", creator.staff_id.value);
    const result = await api(`${creator.dataset.bookingApi}/availability?${params}`);
    if (mine !== token) return;
    slotsBox.removeAttribute("aria-busy");
    const slots = result.ok ? result.data.days[0]?.slots.filter((s) => s.available) : [];
    if (!result.ok) {
      slotsBox.textContent = "Не удалось загрузить свободное время";
      return;
    }
    if (!slots.length) {
      slotsBox.innerHTML = "";
      const note = document.createElement("span");
      note.className = "muted small";
      note.textContent = result.data.days[0]?.open === false ? "Студия в этот день закрыта. Время можно указать вручную." : "Свободных окон нет. Время можно указать вручную, если место есть.";
      slotsBox.append(note);
      return;
    }
    slotsBox.replaceChildren(
      ...slots.map((slot) => {
        const label = slot.start.slice(11, 16);
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip chip--mono";
        chip.textContent = label;
        chip.setAttribute("aria-pressed", String(timeInput.value === label));
        chip.addEventListener("click", () => {
          timeInput.value = label;
          slotsBox.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
        });
        return chip;
      }),
    );
  }

  ["service_id", "staff_id", "date"].forEach((name) => creator[name].addEventListener("change", loadSlots));
  timeInput.addEventListener("input", () => slotsBox.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c.textContent === timeInput.value))));
  loadSlots();

  creator.addEventListener("submit", async (event) => {
    event.preventDefault();
    clear(creator);
    const data = serialize(creator);
    if (!data.time) {
      showErrors(creator, { details: [{ field: "starts_at", message: "Выберите время" }] });
      return;
    }
    const button = creator.querySelector('[type="submit"]');
    button.setAttribute("aria-busy", "true");
    const { date, time, ...rest } = data;
    const result = await api(`${creator.dataset.bookingApi}/bookings`, { method: "POST", data: { ...rest, staff_id: rest.staff_id || null, starts_at: `${date}T${time}:00` } });
    button.removeAttribute("aria-busy");
    if (!result.ok) {
      if (result.error?.code === "slot_taken") result.error.message = slotTakenMessage(result.error);
      showErrors(creator, result.error);
      return;
    }
    try {
      sessionStorage.setItem("velox:toast", `Запись № ${result.data.number} создана`);
    } catch {}
    window.location.href = `${creator.dataset.redirectBase}?view=day&date=${date}&open=${result.data.id}`;
  });
}


// Keep the "now" line moving without a reload.
const nowLine = document.querySelectorAll(".cal__now");
if (nowLine.length) {
  setInterval(() => {
    nowLine.forEach((line) => (line.style.top = `${parseFloat(line.style.top) + 64 / 60}px`));
  }, 60_000);
}
