// Browser integration: all examples offline, all downloads, controls and loop endpoints.
import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';
import { readFile, readdir, mkdtemp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const chrome = [process.env.CHROME_PATH, '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/chromium'].filter(Boolean).find(existsSync);
assert(chrome, 'Set CHROME_PATH to Chrome/Chromium');
const temp = await mkdtemp(join(tmpdir(), 'flowchart-browser-'));
const browser = await chromium.launch({ executablePath: chrome });
let checks = 0;
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const requests = [];
  await context.route(/^https?:/, route => { requests.push(route.request().url()); return route.abort(); });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const name of (await readdir(join(root, 'examples'))).filter(name => name.endsWith('.html'))) {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto(pathToFileURL(join(root, 'examples', name)).href);
    await page.evaluate(() => document.fonts.ready);
    await page.locator('img').evaluateAll(images => Promise.all(images.map(image => {
      image.loading = 'eager';
      return image.decode();
    })));
    assert.equal(await page.locator('img').evaluateAll(images => images.filter(i => !i.complete || !i.naturalWidth).length), 0, `${name}: broken images`);
    const canvas = page.locator('.canvas');
    if (await canvas.count()) {
      const geometry = await page.evaluate(() => {
        const svg = document.querySelector('.canvas svg');
        const box = svg.viewBox.baseVal;
        return { width: box.width, height: box.height, title: !!svg.querySelector('title'), desc: !!svg.querySelector('desc'),
          outside: [...svg.querySelectorAll('text')].filter(t => {
            const b = t.getBoundingClientRect(), r = svg.getBoundingClientRect();
            return b.left < r.left - 1 || b.right > r.right + 1 || b.top < r.top - 1 || b.bottom > r.bottom + 1;
          }).map(t => t.textContent) };
      });
      assert(geometry.title && geometry.desc, `${name}: accessible SVG`);
      assert.deepEqual(geometry.outside, [], `${name}: clipped text`);
      await page.setViewportSize({ width: geometry.width, height: geometry.height });
      await page.evaluate(() => document.getAnimations().forEach(a => { a.pause(); a.currentTime = 0; }));
      const start = await canvas.screenshot();
      await page.evaluate(() => {
        const value = getComputedStyle(document.documentElement).getPropertyValue('--loop').trim();
        const loop = parseFloat(value) * (value.endsWith('ms') ? 1 : 1000);
        document.getAnimations().forEach(a => { a.currentTime = loop; });
      });
      assert(start.equals(await canvas.screenshot()), `${name}: loop endpoint differs`);
      if (await page.locator('#motion').count()) {
        await page.locator('#motion').click();
        assert.equal(await page.locator('#motion').getAttribute('aria-pressed'), 'true');
        await page.locator('#motion').click();
        assert.equal(await page.locator('#motion').getAttribute('aria-pressed'), 'false');
      }
      await page.emulateMedia({ reducedMotion: 'reduce' });
      assert.equal(await page.evaluate(() => document.getAnimations().length), 0, `${name}: reduced motion`);
    }
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}: horizontal overflow at ${width}`);
    }
    console.log(`PASS offline, images, geometry, motion and responsive: ${name}`);
    checks++;
  }
  await page.goto(pathToFileURL(join(root, 'examples/material-library.html')).href);
  const cards = page.locator('.asset');
  assert.equal(await cards.count(), 24);
  for (let i = 0; i < await cards.count(); i++) {
    // Chromium limits rapid successive downloads; keep this batch below 10/second.
    if (i > 0 && i % 8 === 0) await page.waitForTimeout(1100);
    const card = cards.nth(i);
    const id = await card.getAttribute('data-id');
    const format = await card.getAttribute('data-format');
    console.log(`Checking download: ${id}.${format}`);
    const pending = page.waitForEvent('download');
    await card.locator('button.download').click();
    const download = await pending;
    assert.equal(download.suggestedFilename(), `${id}.${format}`);
    const path = join(temp, download.suggestedFilename());
    await download.saveAs(path);
    const data = await readFile(path);
    if (format === 'png') {
      assert(data.equals(await readFile(join(root, 'assets/raster', `${id}.png`))), `${id}: download differs`);
    } else {
      // Parse downloaded standalone SVG, then render it as an image without page CSS/defs.
      assert(await page.evaluate(text => !new DOMParser().parseFromString(text, 'image/svg+xml').querySelector('parsererror'), data.toString()), id);
      const standalone = await context.newPage();
      await standalone.goto(pathToFileURL(path).href);
      assert(await standalone.locator('svg').count(), `${id}: SVG root`);
      assert(await standalone.locator('path,rect,circle').count(), `${id}: drawable content`);
      await standalone.close();
    }
    checks++;
  }
  await page.getByLabel('查找素材').fill('权限');
  assert.equal(await page.locator('.asset:visible').count(), 1);
  await page.getByLabel('查找素材').fill('');
  await page.getByRole('button', { name: '基础组件', exact: true }).click();
  assert.equal(await page.locator('.asset:visible').count(), 8);
  await page.getByRole('button', { name: '全部', exact: true }).click();
  await page.getByLabel('查找素材').fill('no-such-material');
  assert(await page.locator('#empty').isVisible());
  assert.equal(await page.locator('.asset:visible').count(), 0);
  assert.deepEqual(errors, []);
  assert.deepEqual(requests, [], 'Examples must not request online assets');
  console.log(`PASS ${checks} example/download checks; search, filter, empty state; no JS errors or network requests`);
} finally {
  await browser.close();
  await rm(temp, { recursive: true, force: true });
}
