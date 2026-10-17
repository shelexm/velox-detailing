// Booking form: services, masters, free slots and the request, all through the public API.
// One class drives both the inline form (#booking) and the mobile step-by-step sheet.

const WEEKDAYS = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
const MONTHS = ["ЯНВАРЬ", "ФЕВРАЛЬ", "МАРТ", "АПРЕЛЬ", "МАЙ", "ИЮНЬ", "ИЮЛЬ", "АВГУСТ", "СЕНТЯБРЬ", "ОКТЯБРЬ", "НОЯБРЬ", "ДЕКАБРЬ"];
const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const DRAFT_KEY = "velox:booking-draft";
const WIZARD_TITLES = { 1: "Что нужно автомобилю?", 2: "Когда вам удобно?", 3: "Как с вами связаться?" };

export const rub = (n) => (n == null ? "" : `от ${n.toLocaleString("ru-RU").replace(/\s/g, " ")} ₽`);
const dateOf = (iso) => iso.slice(0, 10);
const timeOf = (iso) => iso.slice(11, 16);
function parseDay(day) {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d);
}
function addDays(day, n) {
  const date = parseDay(day);
  date.setDate(date.getDate() + n);
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, "0"), String(date.getDate()).padStart(2, "0")].join("-");
}
const dayLabel = (day) => {
  const d = parseDay(day);
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
};
const dayShort = (day) => {
  const d = parseDay(day);
  return `${WEEKDAYS[d.getDay()]}, ${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
};
const phoneDigits = (value) => {
  let digits = (value || "").replace(/\D/g, "");
  if (digits.length === 11 && (digits[0] === "7" || digits[0] === "8")) digits = digits.slice(1);
  return digits;
};
function formatPhone(value) {
  let digits = (value || "").replace(/\D/g, "");
  if (digits[0] === "8") digits = "7" + digits.slice(1);
  if (digits && digits[0] !== "7") digits = "7" + digits;
  digits = digits.slice(0, 11);
  const p = digits.slice(1);
  let out = "+7";
  if (p.length) out += " " + p.slice(0, 3);
  if (p.length > 3) out += " " + p.slice(3, 6);
  if (p.length > 6) out += "-" + p.slice(6, 8);
  if (p.length > 8) out += "-" + p.slice(8, 10);
  return digits.length ? out : "";
}
const el = (tag, attrs = {}, children = []) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of [].concat(children)) if (child) node.append(child);
  return node;
};

let servicesPromise = null;
function loadServices(slug) {
  servicesPromise ??= fetch(`/api/v1/public/studios/${slug}/services`, { headers: { Accept: "application/json" } }).then((r) => {
    if (!r.ok) throw new Error(`services ${r.status}`);
    return r.json();
  });
  return servicesPromise;
}

export class BookingForm {
  constructor(form, { slug, bot, sheet = null }) {
    this.form = form;
    this.slug = slug;
    this.bot = bot;
    this.sheet = sheet;
    this.mode = form.dataset.mode;
    this.done = form.parentElement.querySelector("[data-booking-done]");
    this.q = (sel) => form.querySelector(sel);
    this.state = { serviceId: null, chip: null, staffId: null, day: null, start: null, step: 1, showAll: false, windowStart: null };
    this.days = new Map();
    this.loadedUntil = null;
    this.today = null;
    this.restoreDraft();
    this.bind();
    this.ready = loadServices(slug)
      .then((services) => this.setServices(services))
      .catch(() => this.showAlert("Не удалось загрузить услуги", "Обновите страницу или позвоните в студию."));
  }

  // ---------- setup ----------
  bind() {
    this.form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (this.mode === "wizard" && this.state.step < 3) this.next();
      else this.submit();
    });
    const phone = this.q('input[name="phone"]');
    phone.addEventListener("input", () => {
      const caret = phone.selectionStart === phone.value.length;
      phone.value = formatPhone(phone.value);
      if (caret) phone.setSelectionRange(phone.value.length, phone.value.length);
      this.clearFieldError("phone");
      this.saveDraft();
    });
    for (const name of ["name", "vehicle"]) {
      this.q(`input[name="${name}"]`).addEventListener("input", () => {
        this.clearFieldError(name);
        this.saveDraft();
      });
    }
    this.q("[data-days-prev]").addEventListener("click", () => this.shiftWindow(-7));
    this.q("[data-days-next]").addEventListener("click", () => this.shiftWindow(7));
    this.q("[data-other-day]").addEventListener("click", () => {
      this.q("[data-slot-taken]").hidden = true;
      this.q("[data-days]").querySelector("button:not(:disabled)")?.focus();
    });
    this.q("[data-pick-alternative]").addEventListener("click", (event) => {
      const iso = event.currentTarget.dataset.start;
      if (!iso) return;
      this.q("[data-slot-taken]").hidden = true;
      this.selectDay(dateOf(iso), iso);
    });
    if (this.mode === "wizard") {
      this.q("[data-wizard-back]").addEventListener("click", () => this.goto(this.state.step - 1));
      this.form.querySelectorAll("[data-wizard-goto]").forEach((b) => b.addEventListener("click", () => this.goto(Number(b.dataset.wizardGoto))));
    }
  }

  setServices(services) {
    this.services = services;
    this.byId = new Map(services.map((s) => [s.id, s]));
    this.bySlug = new Map(services.map((s) => [s.slug, s]));
    const chips = [];
    const seen = new Map();
    for (const svc of services) {
      const key = svc.group_slug ? `g:${svc.group_slug}` : `s:${svc.slug}`;
      if (!seen.has(key)) {
        const label = svc.group_title || svc.name;
        const chip = { key, label, short: svc.group_short_title || label, services: [], grouped: Boolean(svc.group_slug) };
        seen.set(key, chip);
        chips.push(chip);
      }
      seen.get(key).services.push(svc);
    }
    // Directions from the landing page first, then the inspection, then everything else behind "Ещё".
    const primary = chips.filter((c) => c.grouped || c.services[0].kind === "inspection");
    const rest = chips.filter((c) => !primary.includes(c));
    this.chips = [...primary, ...rest];
    this.primaryCount = primary.length;
    const pending = this.pendingSlug;
    this.pendingSlug = null;
    this.selectService(pending ? this.bySlug.get(pending) : null) || this.selectService(primary[0]?.services[0] || services[0]);
  }

  // ---------- service and master ----------
  preselect(slug) {
    if (!this.services) {
      this.pendingSlug = slug;
      return;
    }
    const svc = this.bySlug.get(slug);
    if (svc) this.selectService(svc);
  }

  selectService(svc) {
    if (!svc) return false;
    const chip = this.chips.find((c) => c.services.includes(svc));
    if (this.chips.indexOf(chip) >= this.primaryCount) this.state.showAll = true;
    const changed = this.state.serviceId !== svc.id;
    this.state.serviceId = svc.id;
    this.state.chip = chip;
    if (changed) {
      this.state.staffId = null;
      this.state.start = null;
      this.days = new Map();
      this.loadedUntil = null;
      this.state.windowStart = null;
    }
    this.renderServices();
    this.renderMasters();
    this.renderSummary();
    if (changed) this.loadDays();
    return true;
  }

  renderServices() {
    const box = this.q("[data-services]");
    box.removeAttribute("aria-busy");
    const visible = this.state.showAll ? this.chips : this.chips.slice(0, this.primaryCount);
    // Phones get the short direction name ("Керамика"), as in the mobile mockup.
    const buttons = visible.map((chip) =>
      el("button", { type: "button", class: "chip", "aria-pressed": String(chip === this.state.chip) },
        chip.short === chip.label ? chip.label : [el("span", { class: "only-desktop", text: chip.label }), el("span", { class: "only-mobile", text: chip.short })]),
    );
    buttons.forEach((button, i) => button.addEventListener("click", () => this.selectService(visible[i].services[0])));
    if (!this.state.showAll && this.chips.length > this.primaryCount) {
      const more = el("button", { type: "button", class: "chip", "aria-expanded": "false", text: "Ещё услуги" });
      more.addEventListener("click", () => {
        this.state.showAll = true;
        this.renderServices();
      });
      buttons.push(more);
    }
    box.replaceChildren(...buttons);

    const svc = this.service;
    const variants = this.q("[data-variants]");
    const options = this.state.chip.services;
    variants.hidden = options.length < 2;
    variants.replaceChildren(
      ...options.map((option) => {
        const b = el("button", { type: "button", class: "chip chip--sm", "aria-pressed": String(option.id === svc.id) }, [
          option.name,
          el("small", { text: [rub(option.price_from), option.duration_label].filter(Boolean).join(" · ") }),
        ]);
        b.addEventListener("click", () => this.selectService(option));
        return b;
      }),
    );
    this.q("[data-service-meta]").textContent = [rub(svc.price_from), svc.duration_label].filter(Boolean).join(" · ");
  }

  get service() {
    return this.byId?.get(this.state.serviceId);
  }

  renderMasters() {
    const svc = this.service;
    const box = this.q("[data-masters]");
    const note = this.q("[data-no-master]");
    const choosable = svc.staff_selection === "client" && svc.staff.length > 0;
    note.hidden = choosable;
    box.hidden = !choosable;
    if (!choosable) return box.replaceChildren();
    const options = [...svc.staff.map((m) => ({ id: m.id, name: m.short_name, ini: m.initials, spec: m.specializations.join(", ") })),
      { id: null, name: "Любой мастер", ini: "–", spec: "Ближайшее время" }];
    box.replaceChildren(
      ...options.map((m) => {
        const b = el("button", { type: "button", class: "master", "aria-pressed": String(m.id === this.state.staffId) }, [
          el("span", { class: "master__ini", "aria-hidden": "true", text: m.ini }),
          el("span", { class: "master__text" }, [m.name, el("small", { text: m.spec })]),
          el("span", { class: "master__radio", "aria-hidden": "true" }),
        ]);
        b.addEventListener("click", () => {
          if (this.state.staffId === m.id) return;
          this.state.staffId = m.id;
          this.state.start = null;
          this.days = new Map();
          this.loadedUntil = null;
          this.renderMasters();
          this.renderSummary();
          this.loadDays(this.state.windowStart);
        });
        return b;
      }),
    );
  }

  // ---------- days and times ----------
  // seekFree: on the first load keep fetching two-week chunks until a free day shows up (or the horizon ends).
  async loadDays(from = null, seekFree = !from) {
    const svc = this.service;
    const params = new URLSearchParams({ service_id: svc.id, days: "14" });
    if (from) params.set("date_from", from);
    if (this.state.staffId) params.set("staff_id", this.state.staffId);
    const token = (this.loadToken = Symbol("load"));
    this.q("[data-times]").setAttribute("aria-busy", "true");
    try {
      const response = await fetch(`/api/v1/public/studios/${this.slug}/availability?${params}`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      if (token !== this.loadToken) return;
      for (const day of data.days) this.days.set(day.date, day);
      if (data.days.length) {
        this.today ??= data.days[0].date;
        this.loadedUntil = data.days[data.days.length - 1].date;
      }
      this.state.windowStart ??= this.today;
      // Keep the chosen day while it still has free time (e.g. after switching the service), otherwise jump to the first free one.
      if (!this.days.get(this.state.day)?.slots.some((s) => s.available)) {
        const firstFree = data.days.find((d) => d.slots.some((s) => s.available));
        if (!firstFree && seekFree && this.loadedUntil && this.loadedUntil < this.horizonEnd) {
          return this.loadDays(addDays(this.loadedUntil, 1), true);
        }
        this.state.day = firstFree?.date || this.state.day || this.today || null;
        if (firstFree && this.isMobile) this.state.windowStart = this.today;
        else if (firstFree) this.state.windowStart = this.windowFor(firstFree.date);
      }
      this.renderDays();
      this.renderTimes();
    } catch {
      if (token === this.loadToken) this.showAlert("Не удалось загрузить свободное время", "Проверьте подключение и попробуйте ещё раз.");
    } finally {
      this.q("[data-times]").removeAttribute("aria-busy");
    }
  }

  get isMobile() {
    return window.matchMedia("(max-width: 900px)").matches;
  }

  get horizonEnd() {
    return addDays(this.today, Number(document.body.dataset.horizon || 30));
  }

  windowFor(day) {
    let start = this.today;
    while (addDays(start, 7) <= day) start = addDays(start, 7);
    return start;
  }

  async shiftWindow(delta) {
    const next = addDays(this.state.windowStart, delta);
    if (next < this.today) return;
    this.state.windowStart = next;
    if (!this.loadedUntil || addDays(next, 6) > this.loadedUntil) await this.loadDays(addDays(this.loadedUntil || next, 1));
    this.renderDays();
  }

  renderDays() {
    const box = this.q("[data-days]");
    // Phones scroll one strip from today through everything loaded (at least two weeks); desktop pages by week.
    let count = 7;
    if (this.isMobile) for (count = 14; this.loadedUntil && addDays(this.today, count) <= this.loadedUntil; count++);
    const start = this.isMobile ? this.today : this.state.windowStart;
    if (!start) return;
    const buttons = [];
    for (let i = 0; i < count; i++) {
      const day = addDays(start, i);
      const info = this.days.get(day);
      const free = info?.slots.some((s) => s.available);
      const d = parseDay(day);
      const b = el("button", {
        type: "button",
        class: "day",
        disabled: !free,
        "aria-pressed": String(day === this.state.day),
        "aria-label": `${dayLabel(day)}${free ? "" : ", мест нет"}`,
      }, [el("span", { text: WEEKDAYS[d.getDay()] }), el("span", { text: String(d.getDate()) })]);
      b.addEventListener("click", () => this.selectDay(day));
      buttons.push(b);
    }
    box.replaceChildren(...buttons);
    const first = parseDay(start);
    const last = parseDay(addDays(start, count - 1));
    const month = first.getMonth() === last.getMonth() ? MONTHS[first.getMonth()] : `${MONTHS[first.getMonth()]} / ${MONTHS[last.getMonth()]}`;
    this.q("[data-month-legend]").textContent = `3 · ДАТА И ВРЕМЯ · ${month} ${last.getFullYear()}`;
    this.q("[data-days-prev]").hidden = start <= this.today;
    this.q("[data-days-next]").hidden = addDays(start, 7) > this.horizonEnd;
  }

  selectDay(day, start = null) {
    this.state.day = day;
    this.state.start = start;
    if (!this.isMobile) this.state.windowStart = this.windowFor(day);
    this.clearFieldError("starts_at");
    const ensure = this.days.has(day) ? Promise.resolve() : this.loadDays(day);
    ensure.then(() => {
      this.renderDays();
      this.renderTimes();
      this.renderSummary();
    });
  }

  renderTimes() {
    const box = this.q("[data-times]");
    const info = this.days.get(this.state.day);
    const legend = this.q("[data-times-legend]");
    if (this.mode === "wizard" && this.state.day) {
      legend.hidden = false;
      legend.textContent = `СВОБОДНОЕ ВРЕМЯ · ${dayShort(this.state.day).toUpperCase()}`;
    }
    if (!info || !info.slots.length) {
      const anyFree = [...this.days.values()].some((d) => d.slots.some((s) => s.available));
      const text = !anyFree
        ? "Свободных дат пока нет. Выберите другого мастера или услугу, либо свяжитесь со студией."
        : info && !info.open
          ? "Выходной день. Выберите другую дату."
          : "На этот день свободного времени нет.";
      box.replaceChildren(el("p", { class: "times__empty", text }));
    } else {
      box.replaceChildren(
        ...info.slots.map((slot) => {
          const label = timeOf(slot.start);
          const b = el("button", {
            type: "button",
            class: "time",
            disabled: !slot.available,
            "aria-pressed": String(slot.start === this.state.start),
            "aria-label": `${label}${slot.available ? "" : ", занято"}`,
            text: label,
          });
          b.addEventListener("click", () => {
            this.state.start = slot.start;
            this.clearFieldError("starts_at");
            this.renderTimes();
            this.renderSummary();
          });
          return b;
        }),
      );
    }
    const svc = this.service;
    const hint = this.q("[data-time-hint]");
    hint.hidden = !svc?.duration_days;
    if (svc?.duration_days) hint.textContent = `Время указано для начала работ. Автомобиль останется в студии на ${svc.duration_label || `${svc.duration_days} дн.`}.`;
  }

  // ---------- summary and wizard ----------
  get masterName() {
    const svc = this.service;
    if (!svc) return "";
    if (svc.staff_selection !== "client" || !svc.staff.length) return "Назначит студия";
    return svc.staff.find((m) => m.id === this.state.staffId)?.short_name || "Любой мастер";
  }

  renderSummary() {
    const svc = this.service;
    if (!svc) return;
    const parts = [this.state.chip?.services.length > 1 ? svc.name : this.state.chip?.label || svc.name];
    if (svc.staff_selection === "client" && this.state.staffId) parts.push(this.masterName);
    if (this.state.day) parts.push(dayLabel(this.state.day));
    if (this.state.start) parts.push(timeOf(this.state.start));
    this.q("[data-summary]").textContent = parts.join(" · ");
    const picked = this.q("[data-picked-service]");
    if (picked) {
      picked.textContent = svc.name;
      this.q("[data-picked-meta]").textContent = [this.masterName, rub(svc.price_from), svc.duration_label].filter(Boolean).join(" · ");
    }
    if (this.mode === "wizard") this.renderWizard();
  }

  renderWizard() {
    const step = this.state.step;
    this.sheet.dataset.step = String(step);
    this.q("[data-wizard-label]").textContent = `ЗАПИСЬ · ШАГ ${step} ИЗ 3`;
    this.q("[data-wizard-title]").textContent = WIZARD_TITLES[step];
    this.form.querySelectorAll(".bk-wizard__progress span").forEach((s, i) => s.classList.toggle("is-on", i < step));
    this.q("[data-wizard-back]").hidden = step === 1;
    const submit = this.q("[data-submit]");
    if (step === 3) submit.textContent = "ЗАПИСАТЬСЯ";
    else if (step === 2 && this.state.start) {
      const d = parseDay(this.state.day);
      submit.textContent = `ДАЛЕЕ · ${WEEKDAYS[d.getDay()].toUpperCase()} ${d.getDate()}, ${timeOf(this.state.start)}`;
    } else submit.textContent = "ДАЛЕЕ";
  }

  next() {
    if (this.state.step === 2 && !this.state.start) {
      this.showFieldError("starts_at");
      return;
    }
    this.goto(this.state.step + 1);
  }

  goto(step) {
    this.state.step = Math.min(3, Math.max(1, step));
    this.renderWizard();
    if (this.state.step === 2) this.renderDays();
    this.q("[data-wizard-title]").focus({ preventScroll: true });
    this.q(".bk__scroll").scrollTop = 0;
  }

  // ---------- validation and submit ----------
  showFieldError(field, message) {
    const error = this.q(`[data-error="${field}"]`);
    if (error) {
      if (message) error.lastChild.textContent = message;
      error.hidden = false;
    }
    if (field === "starts_at") this.q("[data-times]").classList.add("has-error");
    const input = this.q(`input[name="${field}"]`);
    input?.setAttribute("aria-invalid", "true");
  }

  clearFieldError(field) {
    const error = this.q(`[data-error="${field}"]`);
    if (error) error.hidden = true;
    if (field === "starts_at") this.q("[data-times]").classList.remove("has-error");
    this.q(`input[name="${field}"]`)?.removeAttribute("aria-invalid");
    this.q("[data-form-alert]").hidden = true;
  }

  showAlert(title, text) {
    const alert = this.q("[data-form-alert]");
    this.q("[data-alert-title]").textContent = title;
    this.q("[data-alert-text]").textContent = text;
    alert.hidden = false;
  }

  validate() {
    const problems = [];
    const name = this.q('input[name="name"]').value.trim();
    const digits = phoneDigits(this.q('input[name="phone"]').value);
    if (!name) {
      this.showFieldError("name");
      problems.push("укажите имя");
    }
    if (digits.length !== 10) {
      this.showFieldError("phone");
      problems.push("проверьте телефон");
    }
    if (!this.state.start) {
      this.showFieldError("starts_at");
      problems.push("выберите время");
    }
    if (problems.length) {
      this.showAlert("Не получилось отправить заявку", `Пожалуйста, ${problems.join(", ")}.`);
      if (this.mode === "wizard" && !this.state.start) this.goto(2);
    }
    return problems.length === 0;
  }

  async submit() {
    this.q("[data-offline]").hidden = true;
    this.q("[data-slot-taken]").hidden = true;
    if (!this.validate()) return;
    const button = this.q("[data-submit]");
    button.classList.add("is-loading");
    button.disabled = true;
    const body = {
      service_id: this.state.serviceId,
      starts_at: this.state.start,
      staff_id: this.state.staffId,
      name: this.q('input[name="name"]').value.trim(),
      phone: this.q('input[name="phone"]').value,
      vehicle: this.q('input[name="vehicle"]').value.trim() || null,
      consent: true,
      website: this.q('input[name="website"]').value,
    };
    try {
      const response = await fetch(`/api/v1/public/studios/${this.slug}/bookings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 201) return this.showDone(data, body.name);
      const error = data.error || {};
      if (error.code === "slot_taken") return this.slotTaken(error.details?.alternatives || []);
      if (response.status === 422 && Array.isArray(error.details)) {
        const map = { contact_name: "name", name: "name", phone: "phone", starts_at: "starts_at" };
        for (const item of error.details) if (map[item.field]) this.showFieldError(map[item.field], item.message);
      }
      this.showAlert("Не получилось отправить заявку", error.message || "Попробуйте ещё раз.");
    } catch {
      this.saveDraft();
      this.q("[data-offline]").hidden = false;
      this.showAlert("Нет связи", "Заявка не ушла, данные сохранены.");
    } finally {
      button.classList.remove("is-loading");
      button.disabled = false;
    }
  }

  slotTaken(alternatives) {
    const taken = this.state.start;
    this.state.start = null;
    this.days = new Map();
    this.loadedUntil = null;
    this.loadDays(this.state.windowStart);
    const box = this.q("[data-slot-taken]");
    const pick = this.q("[data-pick-alternative]");
    const alt = alternatives[0];
    let text = `Время ${timeOf(taken)} только что заняли.`;
    if (alt) {
      const sameDay = dateOf(alt) === dateOf(taken);
      text += ` Ближайшее свободное: ${timeOf(alt)} ${sameDay ? "в тот же день" : dayLabel(dateOf(alt))}.`;
      pick.textContent = `ВЫБРАТЬ ${timeOf(alt)}`;
      pick.dataset.start = alt;
    }
    pick.hidden = !alt;
    this.q("[data-slot-taken-text]").textContent = text;
    box.hidden = false;
    if (this.mode === "wizard") this.goto(2);
    box.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  showDone(data, name) {
    try {
      sessionStorage.removeItem(DRAFT_KEY);
    } catch {}
    const token = data.manage_url.split("/").pop();
    const svc = this.service;
    const text = this.done.querySelector("[data-done-text]");
    text.textContent = `${name}, ${text.dataset.template}`;
    const rows = [
      ["Услуга", data.service_name],
      ["Мастер", data.staff_name && svc.staff_selection === "client" ? data.staff_name : "Назначит студия"],
      ["Дата и время", `${dayShort(dateOf(data.starts_at))} · ${timeOf(data.starts_at)}`, true],
      ["Стоимость", [rub(data.price_from), data.duration_label].filter(Boolean).join(" · "), true],
    ];
    this.done.querySelector("[data-done-list]").replaceChildren(
      ...rows.filter((r) => r[1]).map(([label, value, mono]) => el("div", {}, [el("dt", { text: label }), el("dd", { class: mono ? "mono" : null, text: value })])),
    );
    this.done.querySelector("[data-done-calendar]").href = data.calendar_url;
    this.done.querySelector("[data-done-manage]").href = data.manage_url;
    const tg = this.done.querySelector("[data-done-telegram]");
    if (tg && this.bot) tg.href = `https://t.me/${this.bot}?start=booking_${token}`;
    this.form.hidden = true;
    this.form.parentElement.querySelector(".booking-tabs")?.setAttribute("hidden", "");
    this.done.hidden = false;
    this.done.focus();
  }

  // ---------- draft ----------
  saveDraft() {
    try {
      const draft = {};
      for (const name of ["name", "phone", "vehicle"]) draft[name] = this.q(`input[name="${name}"]`).value;
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {}
  }

  restoreDraft() {
    try {
      const draft = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || "{}");
      for (const [name, value] of Object.entries(draft)) {
        const input = this.q(`input[name="${name}"]`);
        if (input && value && !input.value) input.value = value;
      }
    } catch {}
  }
}
