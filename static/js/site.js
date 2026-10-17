// Public site behaviour. Everything degrades gracefully: without JavaScript the content is fully visible
// and the links keep working (anchors, /services/<slug>, tel:, t.me).
import { BookingForm } from "./booking.js";

const root = document.documentElement;
const body = document.body;
const slug = body.dataset.studio;
const bot = body.dataset.bot || null;
const mobileQuery = window.matchMedia("(max-width: 900px)");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
root.classList.add("js");
try {
  if (sessionStorage.getItem("velox:visited")) root.classList.add("is-repeat");
  sessionStorage.setItem("velox:visited", "1");
} catch {}

// ---------- header, sticky bar, parallax ----------
const header = document.querySelector("[data-header]");
const hero = document.querySelector(".hero");
const heroPicture = hero?.querySelector(".hero__media picture");
const stickyBar = document.querySelector("[data-sticky-bar]");
const bookingSection = document.getElementById("booking");
let bookingInView = false;
let ticking = false;

function onScroll() {
  ticking = false;
  const y = window.scrollY;
  header?.classList.toggle("is-compact", y > 40);
  if (stickyBar) {
    const limit = hero ? hero.offsetHeight * 0.8 : 120;
    stickyBar.classList.toggle("is-visible", y > limit && !bookingInView);
  }
  if (heroPicture && !reducedMotion.matches && !mobileQuery.matches && y < (hero?.offsetHeight || 0)) {
    heroPicture.style.transform = `translate3d(0, ${Math.min(y * 0.3, 80)}px, 0)`;
  }
}
window.addEventListener("scroll", () => {
  if (!ticking) {
    ticking = true;
    requestAnimationFrame(onScroll);
  }
}, { passive: true });
onScroll();

if (bookingSection && "IntersectionObserver" in window) {
  new IntersectionObserver(([entry]) => {
    bookingInView = entry.isIntersecting;
    onScroll();
  }, { threshold: 0.05 }).observe(bookingSection);
}

// ---------- reveal on scroll (once) ----------
const revealed = document.querySelectorAll(".reveal");
if ("IntersectionObserver" in window && !reducedMotion.matches) {
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    }
  }, { threshold: 0.15 });
  revealed.forEach((node) => observer.observe(node));
} else {
  revealed.forEach((node) => node.classList.add("is-visible"));
}

// ---------- card tilt that follows the cursor (desktop, up to 6 degrees) ----------
if (window.matchMedia("(hover: hover) and (pointer: fine)").matches && !reducedMotion.matches) {
  document.querySelectorAll(".svc-card").forEach((card) => {
    card.addEventListener("pointermove", (event) => {
      if (mobileQuery.matches) return;
      const rect = card.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      card.style.transform = `perspective(1400px) rotateX(${(-y * 5).toFixed(2)}deg) rotateY(${(x * 6).toFixed(2)}deg) translateY(-6px)`;
    });
    card.addEventListener("pointerleave", () => {
      card.style.transform = "";
    });
  });
}

// ---------- mobile menu ----------
const menu = document.getElementById("mobile-menu");
const menuButton = document.querySelector("[data-menu-open]");
if (menu && menuButton && typeof menu.showModal === "function") {
  menuButton.addEventListener("click", () => {
    menu.showModal();
    menuButton.setAttribute("aria-expanded", "true");
  });
  menu.addEventListener("close", () => menuButton.setAttribute("aria-expanded", "false"));
  menu.querySelector("[data-menu-close]")?.addEventListener("click", () => menu.close());
  menu.querySelectorAll("[data-menu-link]").forEach((link) => link.addEventListener("click", () => menu.close()));
}

// ---------- before / after ----------
const works = document.querySelector("[data-works]");
if (works) {
  const ba = works.querySelector("[data-ba]");
  const range = ba.querySelector("[data-ba-range]");
  const setPos = (value) => {
    ba.style.setProperty("--pos", `${value}%`);
    range.value = String(Math.round(value));
  };
  range.addEventListener("input", () => setPos(Number(range.value)));
  range.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const delta = event.key === "ArrowLeft" ? -5 : 5;
      setPos(Math.min(100, Math.max(0, Number(range.value) + delta)));
    }
  });
  const index = works.querySelector("[data-case-index]");
  const total = works.querySelectorAll("[data-case]").length;
  works.querySelectorAll("[data-case-pick]").forEach((button) => {
    button.addEventListener("click", () => {
      const pick = button.dataset.casePick;
      works.querySelectorAll("[data-case]").forEach((c) => {
        const active = c.dataset.case === pick;
        c.hidden = !active;
        c.classList.toggle("is-active", active);
      });
      works.querySelectorAll("[data-case-info]").forEach((info) => {
        info.hidden = info.dataset.caseInfo !== pick;
      });
      works.querySelectorAll("[data-case-pick]").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      ba.querySelector('[data-ba-label="before"]').textContent = button.dataset.before;
      ba.querySelector('[data-ba-label="after"]').textContent = button.dataset.after;
      const example = ba.querySelector("[data-ba-example]");
      if (example) example.hidden = button.dataset.example !== "true";
      if (index) index.textContent = `${String(Number(pick) + 1).padStart(2, "0")} / ${String(total).padStart(2, "0")}`;
      setPos(50);
    });
  });
  // One gentle nudge of the handle the first time the slider is seen.
  if (!reducedMotion.matches && "IntersectionObserver" in window) {
    const hint = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      hint.disconnect();
      const frames = [[0, 50], [0.3, 42], [0.65, 58], [1, 50]];
      const startedAt = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - startedAt) / 1600);
        let i = 0;
        while (i < frames.length - 2 && t > frames[i + 1][0]) i++;
        const [t0, v0] = frames[i];
        const [t1, v1] = frames[i + 1];
        const k = (t - t0) / (t1 - t0);
        const eased = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
        setPos(v0 + (v1 - v0) * eased);
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }, { threshold: 0.5 });
    hint.observe(ba);
  }
}

// ---------- price accordion: closed on phones, always open on desktop ----------
const priceCats = [...document.querySelectorAll("[data-price-cat]")];
function syncPrices() {
  priceCats.forEach((cat, i) => {
    cat.open = mobileQuery.matches ? i === 0 : true;
  });
}
priceCats.forEach((cat) => {
  cat.querySelector("summary").addEventListener("click", (event) => {
    if (!mobileQuery.matches) event.preventDefault();
  });
});
syncPrices();
mobileQuery.addEventListener("change", syncPrices);

// ---------- gift certificate ----------
const gift = document.querySelector("[data-gift]");
gift?.querySelectorAll("[data-gift-pick]").forEach((button) => {
  button.addEventListener("click", () => {
    gift.querySelectorAll("[data-gift-pick]").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    gift.querySelector("[data-gift-value]").textContent = button.dataset.value;
    gift.querySelector("[data-gift-sub]").textContent = button.dataset.sub;
  });
});

// ---------- reviews dots (mobile carousel) ----------
const reviews = document.querySelector("[data-reviews]");
const dots = document.querySelector("[data-review-dots]");
if (reviews && dots) {
  reviews.addEventListener("scroll", () => {
    const cards = [...reviews.children];
    const left = reviews.scrollLeft;
    let active = 0;
    cards.forEach((card, i) => {
      if (Math.abs(card.offsetLeft - reviews.offsetLeft - 20 - left) < Math.abs(cards[active].offsetLeft - reviews.offsetLeft - 20 - left)) active = i;
    });
    [...dots.children].forEach((dot, i) => dot.classList.toggle("is-active", i === active));
  }, { passive: true });
}

// ---------- booking ----------
const forms = [];
const sheet = document.getElementById("booking-sheet");
document.querySelectorAll("[data-booking-form]").forEach((form) => {
  forms.push(new BookingForm(form, { slug, bot, sheet: form.closest("dialog") }));
});
const inlineForm = forms.find((f) => f.mode === "inline");
const wizardForm = forms.find((f) => f.mode === "wizard");

function openBooking(serviceSlug, trigger) {
  const inBookingSection = trigger?.closest("#booking");
  if (mobileQuery.matches && wizardForm && sheet && !inBookingSection) {
    if (serviceSlug) wizardForm.preselect(serviceSlug);
    wizardForm.goto(1);
    sheet.showModal();
    return true;
  }
  if (serviceSlug && inlineForm) inlineForm.preselect(serviceSlug);
  return false;
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("[data-book]");
  if (!link) return;
  const onLanding = Boolean(bookingSection);
  if (!onLanding) return; // other pages navigate to /#booking normally
  const dialog = link.closest("dialog");
  if (dialog && dialog !== sheet) dialog.close();
  if (openBooking(link.dataset.bookService, link)) {
    event.preventDefault();
    return;
  }
  event.preventDefault();
  bookingSection.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth" });
  history.replaceState(null, "", "#booking");
});

sheet?.querySelectorAll("[data-sheet-close]").forEach((b) => b.addEventListener("click", () => sheet.close()));

// /?service=<slug>#booking preselects a service (links from the bot or other pages).
const preset = new URLSearchParams(location.search).get("service");
if (preset && inlineForm) inlineForm.preselect(preset);

// ---------- service details in a dialog ----------
const serviceDialog = document.getElementById("service-dialog");

function initServiceDetail(scope) {
  const detail = scope.querySelector("[data-service-detail]");
  if (!detail) return;
  detail.querySelectorAll("[data-slide-pick]").forEach((thumb) => {
    thumb.addEventListener("click", () => {
      const pick = thumb.dataset.slidePick;
      detail.querySelectorAll("[data-slide]").forEach((slide) => {
        slide.hidden = slide.dataset.slide !== pick;
      });
      detail.querySelectorAll("[data-slide-pick]").forEach((t) => t.setAttribute("aria-pressed", String(t === thumb)));
    });
  });
  detail.querySelector("[data-gallery-full]")?.addEventListener("click", () => {
    const img = detail.querySelector("[data-slide]:not([hidden]) img");
    if (img?.requestFullscreen) img.requestFullscreen().catch(() => window.open(img.currentSrc || img.src, "_blank", "noopener"));
    else if (img) window.open(img.currentSrc || img.src, "_blank", "noopener");
  });
  const book = detail.querySelector("[data-detail-book]");
  detail.querySelectorAll("[data-variant]").forEach((variant) => {
    variant.addEventListener("click", () => {
      detail.querySelectorAll("[data-variant]").forEach((v) => v.setAttribute("aria-pressed", String(v === variant)));
      if (book && variant.dataset.online === "true") book.dataset.bookService = variant.dataset.variant;
    });
  });
}
initServiceDetail(document);

if (serviceDialog && typeof serviceDialog.showModal === "function") {
  const target = serviceDialog.querySelector("[data-dialog-body]");
  document.addEventListener("click", async (event) => {
    const link = event.target.closest("[data-service-link]");
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    try {
      const response = await fetch(`${link.getAttribute("href")}?fragment=1`, { headers: { Accept: "text/html" } });
      if (!response.ok) throw new Error(String(response.status));
      target.innerHTML = await response.text();
      initServiceDetail(target);
      target.querySelectorAll("[data-sheet-close]").forEach((b) => b.addEventListener("click", () => serviceDialog.close()));
      serviceDialog.showModal();
      target.querySelector("h1")?.focus({ preventScroll: true });
    } catch {
      location.href = link.getAttribute("href");
    }
  });
  serviceDialog.addEventListener("click", (event) => {
    if (event.target === serviceDialog) serviceDialog.close();
  });
}
sheet?.addEventListener("click", (event) => {
  if (event.target === sheet) sheet.close();
});

// ---------- manage page ----------
const manage = document.querySelector("[data-manage]");
if (manage) {
  manage.querySelectorAll("[data-local-datetime]").forEach((node) => {
    const iso = node.dataset.localDatetime;
    const date = new Date(iso);
    node.textContent = date.toLocaleString("ru-RU", {
      timeZone: node.dataset.tz,
      weekday: "short",
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  });
  const cancel = manage.querySelector("[data-manage-cancel]");
  let armed = false;
  cancel?.addEventListener("click", async () => {
    if (!armed) {
      armed = true;
      cancel.textContent = "ПОДТВЕРДИТЬ ОТМЕНУ";
      return;
    }
    cancel.disabled = true;
    const error = manage.querySelector("[data-manage-error]");
    try {
      const response = await fetch(`/api/v1/public/studios/${manage.dataset.studio}/bookings/manage/${manage.dataset.token}/cancel`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error?.message || "Не удалось отменить запись");
      manage.querySelector("[data-manage-status]").textContent = "Отменена";
      manage.querySelector("[data-manage-cancel-box]").replaceChildren(Object.assign(document.createElement("p"), { textContent: "Запись отменена. Будем рады видеть вас снова." }));
    } catch (exc) {
      error.textContent = exc.message;
      error.hidden = false;
      cancel.disabled = false;
    }
  });
}
