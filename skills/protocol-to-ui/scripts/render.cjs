// One local batch; no shell interpolation, external images or remote fonts.
'use strict';
const fs = require('node:fs');
const { Resvg } = require('@resvg/resvg-js');

function renderBatch(batch) {
  const results = [];
  for (const job of batch.jobs) {
    const renderer = new Resvg(fs.readFileSync(job.svg), {
      fitTo: { mode: 'zoom', value: batch.scale },
      font: { loadSystemFonts: true, defaultFontFamily: batch.font_family },
    });
    const image = renderer.render();
    if (image.width !== job.pixel_width || image.height !== job.pixel_height) {
      throw new Error(`导出像素尺寸错误：${job.svg}`);
    }
    if (job.kind === 'asset') {
      const pixels = image.pixels;
      const w = image.width, h = image.height;
      let visible = false;
      let touchesEdge = false;
      for (let i = 3; i < pixels.length; i += 4) {
        if (pixels[i] > 0) { visible = true; break; }
      }
      if (!visible) throw new Error(`资源完全透明，请检查内容或字体：${job.svg}`);
      if (job.padding > 0) {
        for (let x = 0; x < w; x++) {
          if (pixels[x * 4 + 3] || pixels[((h - 1) * w + x) * 4 + 3]) touchesEdge = true;
        }
        for (let y = 0; y < h; y++) {
          if (pixels[y * w * 4 + 3] || pixels[(y * w + w - 1) * 4 + 3]) touchesEdge = true;
        }
        if (touchesEdge) throw new Error(`资源内容触及导出边界，请增加 padding 或修正布局：${job.svg}`);
      }
    }
    fs.writeFileSync(job.png, image.asPng());
    results.push({ path: job.png, width: image.width, height: image.height });
  }
  return results;
}

try {
  const batch = JSON.parse(fs.readFileSync(0, 'utf8'));
  process.stdout.write(JSON.stringify(renderBatch(batch)));
} catch (error) {
  process.stderr.write(String(error.message) + '\n');
  process.exitCode = 1;
}
