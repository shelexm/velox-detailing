// Phone photos are 3 to 12 MB and 12 to 50 MP. They are shrunk in the browser before the upload: the server
// takes up to 5 MB, and a mobile connection and a small VPS both do better with a 0.5 to 1.5 MB file.
// What the browser cannot decode (HEIC outside Safari, a broken file) goes as it is: the server explains why.

const MAX_SIDE = 2400;
const KEEP_BELOW = 1.5 * 1024 * 1024;
const SERVER_TYPES = ["image/jpeg", "image/png", "image/webp", "image/avif"];

// Some Android pickers give an empty type, so the extension decides then.
export function isImageFile(file) {
  return file.type.startsWith("image/") || (!file.type && /\.(jpe?g|png|webp|avif|heic|heif)$/i.test(file.name));
}

function decode(file) {
  const url = URL.createObjectURL(file);
  const img = new Image();
  return new Promise((resolve, reject) => {
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("decode"));
    };
    img.src = url;
  });
}

export async function prepareImage(file) {
  let img;
  try {
    img = await decode(file);
  } catch {
    return file;
  }
  const longest = Math.max(img.naturalWidth, img.naturalHeight);
  const acceptable = SERVER_TYPES.includes(file.type);
  if (acceptable && file.size <= KEEP_BELOW && longest <= MAX_SIDE) return file;

  const ratio = Math.min(1, MAX_SIDE / longest);
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(img.naturalWidth * ratio));
  canvas.height = Math.max(1, Math.round(img.naturalHeight * ratio));
  const context = canvas.getContext("2d");
  if (!context) return file;
  context.fillStyle = "#070708"; // transparency is flattened onto the dark site background, as on the server
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.imageSmoothingQuality = "high";
  context.drawImage(img, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.88));
  if (!blob || (acceptable && blob.size >= file.size)) return file;
  const base = file.name.replace(/\.[^.]+$/, "") || "photo";
  return new File([blob], `${base}.jpg`, { type: "image/jpeg" });
}
