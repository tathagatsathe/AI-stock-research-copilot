import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const outPath =
  process.env.DEMO_UI_OUT ||
  path.join(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'), 'Demo-UI.png');
const url = process.env.DEMO_UI_URL || 'http://127.0.0.1:5173/';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });

await page.goto(url, { waitUntil: 'networkidle' });
await page.getByRole('button', { name: /AAPL/i }).first().click();
await page.getByRole('heading', { name: 'Market News' }).waitFor({ timeout: 120000 });
await page.getByRole('heading', { name: 'Fundamentals' }).waitFor({ timeout: 120000 });

await page.evaluate(() => {
  const shell = document.querySelector('.min-h-screen');
  if (shell) {
    shell.style.height = 'auto';
    shell.style.minHeight = '0';
    shell.style.overflow = 'visible';
  }

  const row = document.querySelector('.flex.flex-col.md\\:flex-row');
  if (row) {
    row.style.height = 'auto';
    row.style.overflow = 'visible';
    row.style.alignItems = 'flex-start';
  }

  document.querySelectorAll('.glass-panel').forEach((panel) => {
    panel.style.overflow = 'visible';
    panel.style.height = 'auto';
    panel.style.maxHeight = 'none';
  });

  document.querySelectorAll('.overflow-y-auto, .overflow-hidden').forEach((el) => {
    el.style.overflow = 'visible';
    el.style.height = 'auto';
    el.style.maxHeight = 'none';
  });

  const heightLocked = document.querySelector('.h-\\[calc\\(100vh-4rem\\)\\]');
  if (heightLocked) {
    heightLocked.style.height = 'auto';
    heightLocked.style.overflow = 'visible';
  }

  document.documentElement.style.height = 'auto';
  document.body.style.height = 'auto';
  document.body.style.overflow = 'visible';
});

await page.waitForTimeout(800);

const app = page.locator('.min-h-screen');
const height = await app.evaluate((el) => el.scrollHeight);
if (height < 2500) {
  throw new Error(`Expanded capture height looks too small: ${height}px`);
}

await app.screenshot({ path: outPath, animations: 'disabled' });
await browser.close();

console.log(`Saved ${outPath} (${height}px tall)`);
