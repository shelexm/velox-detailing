// Telegram Mini App calendar: free days and times from the public API; the chosen time is held on the server
// (signed initData proves who the user is) and its id is handed back to the chat with sendData().

const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const root = document.querySelector("[data-tg-app]");
const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
const WEEKDAYS = ["воскресенье", "понедельник", "вторник", "среду", "четверг", "пятницу", "субботу"];
const SHORT = ["ВС", "ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ"];
const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parse = (s) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
};

if (root && root.querySelector("[data-day-grid]")) {
  const slug = root.dataset.studio;
  const horizon = Number(root.dataset.horizon || 30);
  const serviceSelect = root.querySelector("[data-service]");
  const daysBox = root.querySelector("[data-day-grid]");
  const timesBox = root.querySelector("[data-times]");
  const timesLabel = root.querySelector("[data-times-label]");
  const note = root.querySelector("[data-note]");
  const error = root.querySelector("[data-error]");
  const choose = root.querySelector("[data-choose]");
  const title = root.querySelector("[data-month-title]");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const last = new Date(today);
  last.setDate(last.getDate() + horizon);
  let month = new Date(today.getFullYear(), today.getMonth(), 1);
  let days = new Map();
  let day = null;
  let start = null;

  const option = () => serviceSelect.selectedOptions[0];
  function showPrice() {
    const o = option();
    const price = o.dataset.price ? `от ${Number(o.dataset.price).toLocaleString("ru-RU")} ₽` : "";
    root.querySelector("[data-price-label]").textContent = price;
  }

  async function load() {
    days = new Map();
    day = start = null;
    timesLabel.textContent = "Загружаем свободное время…";
    timesBox.replaceChildren();
    for (let offset = 0; offset <= horizon; offset += 14) {
      const from = new Date(today);
      from.setDate(from.getDate() + offset);
      const params = new URLSearchParams({ service_id: serviceSelect.value, date_from: iso(from), days: "14" });
      const response = await fetch(`/api/v1/public/studios/${slug}/availability?${params}`, { headers: { Accept: "application/json" } });
      if (!response.ok) break;
      const data = await response.json();
      for (const d of data.days) days.set(d.date, d.slots.filter((s) => s.available));
      if (!data.days.length) break;
    }
    const first = [...days.entries()].find(([, slots]) => slots.length);
    if (first) {
      day = first[0];
      month = new Date(parse(day).getFullYear(), parse(day).getMonth(), 1);
    }
    render();
  }

  function render() {
    title.textContent = `${MONTHS[month.getMonth()]} ${month.getFullYear()}`;
    root.querySelector("[data-month-prev]").disabled = month <= new Date(today.getFullYear(), today.getMonth(), 1);
    root.querySelector("[data-month-next]").disabled = new Date(month.getFullYear(), month.getMonth() + 1, 1) > last;
    const cells = [];
    const lead = (month.getDay() + 6) % 7;
    for (let i = 0; i < lead; i++) {
      const empty = document.createElement("span");
      empty.className = "tga__day is-empty";
      cells.push(empty);
    }
    const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
    for (let n = 1; n <= count; n++) {
      const d = new Date(month.getFullYear(), month.getMonth(), n);
      const key = iso(d);
      const free = (days.get(key) || []).length > 0;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `tga__day${key === iso(today) ? " is-today" : ""}`;
      button.textContent = String(n);
      button.disabled = !free;
      button.setAttribute("aria-pressed", String(key === day));
      button.setAttribute("aria-label", `${n} ${MONTHS_GEN[d.getMonth()]}${free ? "" : ", мест нет"}`);
      button.addEventListener("click", () => {
        day = key;
        start = null;
        render();
      });
      cells.push(button);
    }
    daysBox.replaceChildren(...cells);
    renderTimes();
  }

  function renderTimes() {
    const slots = day ? days.get(day) || [] : [];
    if (!day) {
      timesLabel.textContent = days.size ? "Свободных дат нет. Напишите администратору в чате." : "Не удалось загрузить время.";
      timesBox.replaceChildren();
    } else {
      const d = parse(day);
      timesLabel.textContent = `Свободно в ${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
      timesBox.replaceChildren(
        ...slots.map((slot) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "tga__time";
          button.textContent = slot.start.slice(11, 16);
          button.setAttribute("aria-pressed", String(slot.start === start));
          button.addEventListener("click", () => {
            start = slot.start;
            renderTimes();
          });
          return button;
        }),
      );
    }
    const multiDay = option().dataset.days;
    note.hidden = !multiDay;
    if (multiDay) note.textContent = `Автомобиль останется в студии: ${option().dataset.label || `${multiDay} дн.`}.`;
    choose.disabled = !start;
    if (start) {
      const d = parse(day);
      choose.textContent = `Выбрать · ${SHORT[d.getDay()]} ${d.getDate()} ${MONTHS_GEN[d.getMonth()].slice(0, 3)}, ${start.slice(11, 16)}`;
    } else choose.textContent = "Выберите дату и время";
  }

  root.querySelector("[data-month-prev]").addEventListener("click", () => {
    month = new Date(month.getFullYear(), month.getMonth() - 1, 1);
    render();
  });
  root.querySelector("[data-month-next]").addEventListener("click", () => {
    month = new Date(month.getFullYear(), month.getMonth() + 1, 1);
    render();
  });
  serviceSelect.addEventListener("change", () => {
    showPrice();
    load();
  });

  choose.addEventListener("click", async () => {
    error.hidden = true;
    if (!tg?.initData) {
      error.textContent = "Откройте календарь из чата с ботом: кнопка «Выбрать дату в календаре».";
      error.hidden = false;
      return;
    }
    choose.disabled = true;
    const response = await fetch(`/api/v1/tg/studios/${slug}/hold`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ init_data: tg.initData, service_id: Number(serviceSelect.value), starts_at: start }),
    });
    if (response.ok) {
      const data = await response.json();
      tg.sendData(String(data.hold_id)); // closes the Mini App; the chat continues with the name and phone
      return;
    }
    const body = await response.json().catch(() => null);
    error.textContent = body?.error?.message || "Не получилось. Попробуйте ещё раз.";
    error.hidden = false;
    if (response.status === 409) await load();
    else choose.disabled = false;
  });

  showPrice();
  load();
}
