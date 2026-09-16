import { expect, test } from '@playwright/test';
import { getGlobeFrame } from '../src/data/globeDemo';

// Keep visual checks still; exercise autoplay separately.
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
});

test('research page fits desktop and small mobile viewports', async ({ page, isMobile }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: /Fault-Aware Fleet Recovery Scheduling/ })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Service-Preserving Active Diagnosis');
  await expect(page.getByRole('heading', { level: 2, name: 'Abstract', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { level: 2, name: 'Optimization Problem', exact: true })).toBeVisible();
  await expect(page.getByText('When is diagnosis worth a contact?')).toHaveCount(0);
  await expect(page.locator('.globe-scene')).toHaveAttribute('data-renderer', 'webgl');
  await expect(page.locator('.globe-scene')).toHaveAttribute('data-texture', 'ready');
  for (const width of isMobile ? [390, 320] : [1440, 768]) {
    await page.setViewportSize({ width, height: isMobile ? 844 : 1000 });
    for (const selector of ['.orbit-figure', '.abstract-section .reading-width', '.formulation-section .reading-width', '.results-figure', '.citation-details']) {
      const element = page.locator(selector);
      await element.scrollIntoViewIfNeeded();
      const bounds = await element.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(-1);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    await page.screenshot({ path: testInfo.outputPath(`page-${width}.png`), fullPage: true });
    for (const section of ['hero', 'orbit-figure', 'results-figure']) {
      await page.locator(`.${section}`).screenshot({ path: testInfo.outputPath(`${section}-${width}.png`) });
    }
  }
  expect(errors).toEqual([]);
});

test('globe has valid contacts and stays still with reduced motion without playback controls', async ({ page }) => {
  await page.goto('/');
  const figure = page.locator('.orbit-figure');
  const scene = page.locator('.globe-scene');
  await figure.scrollIntoViewIfNeeded();
  await expect(scene).toHaveAttribute('data-renderer', 'webgl');
  await expect(scene).toHaveAttribute('data-texture', 'ready');
  await expect(figure.getByRole('button')).toHaveCount(0);
  await expect(figure.locator('select')).toHaveCount(0);
  await expect(figure).not.toContainText('Illustrative passes');
  const expected = getGlobeFrame(0).contacts;
  await expect(page.locator('[data-contact-for]')).toHaveCount(expected.length);
  for (const contact of expected) {
    await expect(page.locator(`[data-station-id="${contact.stationId}"][data-contact-for="${contact.satelliteId}"]`)).toHaveAttribute('data-contact-type', contact.type);
  }
  await page.waitForTimeout(250);
  await expect(scene).toHaveAttribute('data-animation-time', '0.000');
});

test('satellites animate automatically and suspend offscreen and with reduced motion', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 500 });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  const figure = page.locator('.orbit-figure');
  const scene = page.locator('.globe-scene');
  await figure.scrollIntoViewIfNeeded();
  await expect.poll(async () => Number(await scene.getAttribute('data-animation-time'))).toBeGreaterThan(0.15);
  const satellite = page.locator('[data-satellite-id="sat-02"]');
  const position = await satellite.getAttribute('data-position');
  const rotation = await satellite.getAttribute('data-orientation');
  await expect(satellite).not.toHaveAttribute('data-position', position!);
  await expect(satellite).not.toHaveAttribute('data-orientation', rotation!);

  await page.locator('#citation').scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  const offscreen = await scene.getAttribute('data-animation-time');
  await page.waitForTimeout(250);
  await expect(scene).toHaveAttribute('data-animation-time', offscreen!);
  await figure.scrollIntoViewIfNeeded();
  await expect.poll(async () => Number(await scene.getAttribute('data-animation-time'))).toBeGreaterThan(Number(offscreen));

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.waitForTimeout(100);
  const stopped = await scene.getAttribute('data-animation-time');
  await page.waitForTimeout(250);
  await expect(scene).toHaveAttribute('data-animation-time', stopped!);
});

test('3D globe supports dragging and arrow-key rotation with reduced motion', async ({ page }, testInfo) => {
  await page.goto('/');
  const scene = page.locator('.globe-scene');
  await expect(scene).toHaveAttribute('data-renderer', 'webgl');
  await expect(scene).toHaveAttribute('data-texture', 'ready');
  await expect(scene).toHaveAttribute('data-animation-time', '0.000');
  const canvas = page.getByLabel('Interactive 3D Earth and satellite fleet');
  await canvas.scrollIntoViewIfNeeded();
  const initialCamera = await scene.getAttribute('data-camera-position');
  await canvas.focus();
  await canvas.press('ArrowRight');
  await expect(scene).not.toHaveAttribute('data-camera-position', initialCamera!);
  const beforeDrag = await scene.getAttribute('data-camera-position');
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.45, box.y + box.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.65, box.y + box.height * 0.55, { steps: 8 });
  await page.mouse.up();
  await expect(scene).not.toHaveAttribute('data-camera-position', beforeDrag!);
  await expect(scene).toHaveAttribute('data-animation-time', '0.000');
  await page.locator('.orbit-figure').screenshot({ path: testInfo.outputPath('rotated-globe.png') });
});

test('unavailable WebGL keeps an autonomous fallback and contact information', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type: string, ...args: unknown[]) {
      if (type.startsWith('webgl') || type === 'experimental-webgl') return null;
      return original.apply(this, [type, ...args] as Parameters<typeof original>);
    } as typeof original;
  });
  await page.goto('/');
  const figure = page.locator('.orbit-figure');
  const scene = page.locator('.globe-scene');
  await expect(scene).toHaveAttribute('data-renderer', 'fallback');
  await expect(page.locator('#results')).toContainText('SPAR-MPC');
  await figure.scrollIntoViewIfNeeded();
  await expect(figure.getByRole('button')).toHaveCount(0);
  await expect(figure.locator('select')).toHaveCount(0);
  await expect(figure.getByRole('img', { name: /Schematic Earth and satellite fleet/ })).toBeVisible();
  await expect(scene).toHaveAttribute('data-animation-time', '0.000');
  await expect(page.locator('[data-contact-for]')).toHaveCount(getGlobeFrame(0).contacts.length);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await expect.poll(async () => Number(await scene.getAttribute('data-animation-time'))).toBeGreaterThan(0.1);
});

test('result metric switching shows SPAR-MPC and the four baselines', async ({ page }) => {
  await page.goto('/');
  const results = page.locator('#results');
  const ours = results.locator('.chart-row').filter({ hasText: 'SPAR-MPC' });
  const baseline = results.locator('.chart-row').filter({ hasText: 'Certainty equivalent' });
  await expect(results.locator('.chart-row')).toHaveCount(5);
  await expect(results.getByText('Service-only')).toHaveCount(0);
  await expect(results.getByRole('button').first()).toHaveText('Lethal recovery');
  await expect(results.getByRole('button', { name: 'Lethal recovery', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(ours).toContainText('54.2%');
  await expect(baseline).toContainText('14.1%');
  await expect(results.locator('figcaption')).toContainText('before their deadlines');
  await results.getByRole('button', { name: 'Deadline-weighted completion', exact: true }).click();
  await expect(ours).toContainText('35.3%');
  await expect(baseline).toContainText('9.2%');
  await results.getByRole('button', { name: 'Lethal recovery', exact: true }).click();
  await expect(ours).toContainText('54.2%');
});

test('BibTeX is visible by default, can be copied, and is reached from the resource link', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      writeText: async (text: string) => { document.documentElement.dataset.copiedCitation = text; },
    } });
  });
  await page.goto('/');
  const citation = page.locator('#citation');
  await expect(citation.getByRole('heading', { level: 2, name: 'BibTeX', exact: true })).toBeVisible();
  await expect(citation.locator('pre')).toBeVisible();
  const displayed = await citation.locator('pre code').textContent();
  await citation.getByRole('button', { name: 'Copy BibTeX', exact: true }).click();
  await expect(citation.getByRole('status')).toHaveText('BibTeX copied to clipboard.');
  await expect(page.locator('html')).toHaveAttribute('data-copied-citation', displayed!);
  await page.locator('.hero').getByRole('link', { name: 'BibTeX', exact: true }).click();
  await expect(page).toHaveURL(/#citation$/);
  await expect(citation.getByRole('heading', { level: 2, name: 'BibTeX', exact: true })).toBeInViewport();
  await expect(citation.locator('pre')).toBeVisible();
});

test('resource tags link to the solver and BibTeX while arXiv remains unconfigured', async ({ page }) => {
  await page.goto('/');
  const resources = page.getByRole('navigation', { name: 'Research resources' });
  await expect(resources.getByRole('link')).toHaveText(['arXiv', 'Code', 'BibTeX']);
  const arxiv = resources.getByRole('link', { name: 'arXiv', exact: true });
  await expect(arxiv).toHaveAttribute('aria-disabled', 'true');
  await expect(arxiv).not.toHaveAttribute('href');
  const code = resources.getByRole('link', { name: 'Code', exact: true });
  await expect(code).toHaveAttribute('href', 'https://github.com/spar-mpc/spar-mpc.github.io/tree/main/solver');
  await expect(code).not.toHaveAttribute('aria-disabled');
  await expect(code).toHaveAttribute('target', '_blank');
  await resources.getByRole('link', { name: 'BibTeX', exact: true }).click();
  await expect(page).toHaveURL(/#citation$/);
  await expect(page.locator('#citation').getByRole('heading', { level: 2, name: 'BibTeX', exact: true })).toBeInViewport();
  await expect(page.locator('#citation pre')).toBeVisible();
});
