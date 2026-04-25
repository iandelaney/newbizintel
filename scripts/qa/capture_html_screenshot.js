const { pathToFileURL } = require("node:url");
const path = require("node:path");
const { chromium } = require("playwright");

function argValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) {
    return fallback;
  }
  return process.argv[index + 1];
}

async function main() {
  const html = argValue("--html");
  if (!html) {
    throw new Error("Missing --html path");
  }
  const out = argValue("--out", path.join(path.dirname(html), "visual-check.png"));
  const anchor = argValue("--anchor", "");
  const selector = argValue("--selector", "");
  const width = Number(argValue("--width", "1200"));
  const height = Number(argValue("--height", "900"));

  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(path.resolve(html)).href, { waitUntil: "networkidle" });
    if (selector) {
      await page.locator(selector).first().scrollIntoViewIfNeeded();
    } else if (anchor) {
      await page.getByText(anchor, { exact: false }).first().scrollIntoViewIfNeeded();
    }
    await page.waitForFunction(() => {
      const visibleImages = Array.from(document.images).filter((image) => {
        const rect = image.getBoundingClientRect();
        return rect.bottom >= 0 && rect.top <= window.innerHeight && rect.right >= 0 && rect.left <= window.innerWidth;
      });
      return visibleImages.every((image) => image.complete && image.naturalWidth > 0);
    }, null, { timeout: 10000 }).catch(() => {});
    await page.screenshot({ path: out, fullPage: false });
    console.log(JSON.stringify({ ok: true, html: path.resolve(html), screenshot: path.resolve(out) }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: String(error && error.message ? error.message : error) }, null, 2));
  process.exit(1);
});
