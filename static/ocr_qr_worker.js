/* global jsQR */
importScripts('https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js');

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
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0);
    const imgData = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
    const code = jsQR(imgData.data, bitmap.width, bitmap.height, { inversionAttempts: 'attemptBoth' });
    self.postMessage({ id, data: code ? code.data : null });
  } catch (err) {
    self.postMessage({ id, data: null });
  }
};
