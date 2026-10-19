// Temporary diagnostics: which picture files this browser picks on the real page and which variants it can show.
const $ = (id) => document.getElementById(id);
const report = [];
const line = (parent, ok, text) => {
  report.push(`${ok ? "OK" : "FAIL"} ${text}`);
  const d = document.createElement("div");
  d.className = ok ? "ok" : "fail";
  d.textContent = `${ok ? "OK" : "НЕ ГРУЗИТСЯ"}  ${text}`;
  parent.append(d);
};
const load = (src) =>
  new Promise((resolve) => {
    const img = new Image();
    const t = setTimeout(() => resolve({ ok: false, why: "таймаут 15 с" }), 15000);
    img.onload = () => { clearTimeout(t); resolve({ ok: true, size: `${img.naturalWidth}x${img.naturalHeight}` }); };
    img.onerror = () => { clearTimeout(t); resolve({ ok: false, why: "ошибка" }); };
    img.src = src;
  });

const support = async () => {
  const avif = "data:image/avif;base64,AAAAIGZ0eXBhdmlmAAAAAGF2aWZtaWYxbWlhZk1BMUIAAADybWV0YQAAAAAAAAAoaGRscgAAAAAAAAAAcGljdAAAAAAAAAAAAAAAAGxpYmF2aWYAAAAADnBpdG0AAAAAAAEAAAAeaWxvYwAAAABEAAABAAEAAAABAAABGgAAAB0AAAAoaWluZgAAAAAAAQAAABppbmZlAgAAAAABAABhdjAxQ29sb3IAAAAAamlwcnAAAABLaXBjbwAAABRpc3BlAAAAAAAAAAIAAAACAAAAEHBpeGkAAAAAAwgICAAAAAxhdjFDgQ0MAAAAABNjb2xybmNseAACAAIAAYAAAAAXaXBtYQAAAAAAAAABAAEEAQKDBAAAACVtZGF0EgAKCBgANogQEAwgMg8f8D///8WfhwB8+ErK42A=";
  const webp = "data:image/webp;base64,UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA==";
  return { avif: (await load(avif)).ok, webp: (await load(webp)).ok };
};

(async () => {
  const s = await support();
  $("env").textContent =
    `Экран: ${innerWidth} px, плотность ${devicePixelRatio}\nAVIF: ${s.avif ? "да" : "нет"}, WebP: ${s.webp ? "да" : "нет"}\n${navigator.userAgent}`;

  // 1. The pictures of the real landing page, taken from its HTML and put on this page.
  const html = await (await fetch("/", { credentials: "same-origin" })).text();
  const doc = new DOMParser().parseFromString(html, "text/html");
  const pictures = [...doc.querySelectorAll("picture")].slice(0, 12);
  const holder = $("page");
  for (const [index, picture] of pictures.entries()) {
    const box = document.createElement("div");
    box.className = "box";
    box.append(document.importNode(picture, true));
    holder.append(box);
    const img = box.querySelector("img");
    const done = () => {
      const src = (img.currentSrc || img.src).replace(location.origin, "");
      line(box, img.naturalWidth > 0, `${index + 1}: ${src.split("/").pop()} (${img.naturalWidth}x${img.naturalHeight})`);
    };
    if (img.complete) done();
    else { img.addEventListener("load", done); img.addEventListener("error", done); }
  }

  // 2. Every size and format of the first picture, one by one.
  const first = pictures[0]?.querySelector("img");
  const base = (first?.getAttribute("src") || "").replace(/\/[^/]+$/, "");
  const box = $("variants");
  for (const ext of ["jpg", "webp", "avif"]) {
    for (const width of [480, 960, 1600, 2400]) {
      const name = `w${width}.${ext}`;
      const result = await load(`${base}/${name}?diag=${Date.now()}`);
      line(box, result.ok, `${name} ${result.ok ? result.size : result.why}`);
    }
  }
  // The result goes to the server as the query of a request: it is visible in the access log.
  const text = `${$("env").textContent}
${report.join("
")}`;
  new Image().src = `/static/diag/report.gif?${encodeURIComponent(text)}`;
  $("sent").textContent = "Готово, результат отправлен. Скриншот не нужен, напишите в чат «готово».";
})().catch((error) => {
  new Image().src = `/static/diag/report.gif?${encodeURIComponent(`SCRIPT ERROR ${error}
${report.join("
")}`)}`;
  $("sent").textContent = `Ошибка: ${error}. Напишите в чат «ошибка».`;
});
