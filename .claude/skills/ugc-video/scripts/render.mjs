// Renders overlay.html frame by frame to transparent PNGs, using clip starts measured from the cut parts.
import { createRequire } from 'module';
const { chromium } = createRequire(import.meta.url)('playwright');
import { readFileSync, mkdirSync, existsSync } from 'fs';
import { execFileSync } from 'child_process';
import path from 'path';

const [tlPath, buildDir, overlay = 'overlay.html'] = process.argv.slice(2);
const tl = JSON.parse(readFileSync(tlPath, 'utf8'));
let start = 0;
// cut_hd.py writes the joined timeline itself (clips overlap during transitions)
const clipsFile = path.join(buildDir, 'clips.json');
const clips = existsSync(clipsFile) ? JSON.parse(readFileSync(clipsFile, 'utf8')) : tl.clips.map((c, i) => {
  const dur = parseFloat(execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v', '-show_entries',
    'format=duration', '-of', 'csv=p=0', path.join(buildDir, `part${String(i).padStart(2, '0')}.mp4`)]).toString());
  const r = { ...c, start, dur }; start += dur; return r;
});
if (existsSync(clipsFile)) start = clips.at(-1).start + clips.at(-1).dur;
const frames = Math.round(start * tl.fps);
const outDir = path.join(buildDir, 'ov'); mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: tl.w, height: tl.h } });
await page.goto('file://' + path.resolve(path.dirname(tlPath), overlay));
await page.evaluate(c => { window.TL = c; }, clips);
await page.evaluate(() => document.fonts.ready);
for (let f = 0; f < frames; f++) {
  await page.evaluate(t => window.renderAt(t), f / tl.fps);
  await page.screenshot({ path: path.join(outDir, `f${String(f).padStart(5, '0')}.png`), omitBackground: true });
}
await browser.close();
console.log(`rendered ${frames} frames`);
