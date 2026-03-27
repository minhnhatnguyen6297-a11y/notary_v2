/* global jsQR */
importScripts('https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js');

function toGray(src) {
  const out = new Uint8ClampedArray(src.length);
  for (let i = 0; i < src.length; i += 4) {
    const r = src[i];
    const g = src[i + 1];
    const b = src[i + 2];
    const y = Math.max(0, Math.min(255, Math.round(0.299 * r + 0.587 * g + 0.114 * b)));
    out[i] = y;
    out[i + 1] = y;
    out[i + 2] = y;
    out[i + 3] = 255;
  }
  return out;
}

function applyLinearContrast(src, gain = 1.35, bias = -20) {
  const out = new Uint8ClampedArray(src.length);
  for (let i = 0; i < src.length; i += 4) {
    const v = Math.max(0, Math.min(255, Math.round(src[i] * gain + bias)));
    out[i] = v;
    out[i + 1] = v;
    out[i + 2] = v;
    out[i + 3] = 255;
  }
  return out;
}

function threshold(src, value = 130) {
  const out = new Uint8ClampedArray(src.length);
  for (let i = 0; i < src.length; i += 4) {
    const v = src[i] >= value ? 255 : 0;
    out[i] = v;
    out[i + 1] = v;
    out[i + 2] = v;
    out[i + 3] = 255;
  }
  return out;
}

function rotateImageData(data, width, height, angle) {
  if (angle === 0) {
    return { data, width, height };
  }
  let dstW = width;
  let dstH = height;
  if (angle === 90 || angle === 270) {
    dstW = height;
    dstH = width;
  }
  const out = new Uint8ClampedArray(dstW * dstH * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const srcIdx = (y * width + x) * 4;
      let nx = x;
      let ny = y;
      if (angle === 90) {
        nx = height - 1 - y;
        ny = x;
      } else if (angle === 180) {
        nx = width - 1 - x;
        ny = height - 1 - y;
      } else if (angle === 270) {
        nx = y;
        ny = width - 1 - x;
      }
      const dstIdx = (ny * dstW + nx) * 4;
      out[dstIdx] = data[srcIdx];
      out[dstIdx + 1] = data[srcIdx + 1];
      out[dstIdx + 2] = data[srcIdx + 2];
      out[dstIdx + 3] = 255;
    }
  }
  return { data: out, width: dstW, height: dstH };
}

function tryDecode(data, width, height) {
  const qr = jsQR(data, width, height, { inversionAttempts: 'attemptBoth' });
  return qr && qr.data ? qr.data : null;
}

self.onmessage = async (e) => {
  const { id, dataUrl } = e.data || {};
  if (!dataUrl) {
    self.postMessage({ id, data: null });
    return;
  }

  try {
    const res = await fetch(dataUrl);
    const blob = await res.blob();
    const bitmap = await createImageBitmap(blob);
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(bitmap, 0, 0);
    const imgData = ctx.getImageData(0, 0, bitmap.width, bitmap.height);

    const gray = toGray(imgData.data);
    const highContrast = applyLinearContrast(gray, 1.45, -18);
    const bw = threshold(highContrast, 132);
    const variants = [imgData.data, gray, highContrast, bw];

    for (const variant of variants) {
      for (const angle of [0, 90, 180, 270]) {
        const rotated = rotateImageData(variant, bitmap.width, bitmap.height, angle);
        const decoded = tryDecode(rotated.data, rotated.width, rotated.height);
        if (decoded) {
          self.postMessage({ id, data: decoded });
          return;
        }
      }
    }

    self.postMessage({ id, data: null });
  } catch (_) {
    self.postMessage({ id, data: null });
  }
};

