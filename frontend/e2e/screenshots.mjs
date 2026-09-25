// Visual evidence capture (not a test): `node e2e/screenshots.mjs http://127.0.0.1:8777 ../docs/screenshots`
// Reference device: Playwright Chromium headless shell (SwiftShader WebGL), 1440x900 desktop and Pixel 7.
import { chromium, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";

const [base = "http://127.0.0.1:8777", out = "../docs/screenshots"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const runs = await (await fetch(`${base}/api/runs`)).json();
const rnd = runs.find((r) => r.model_id === "mock/random");
const items = await (await fetch(`${base}/api/runs/${rnd.run_id}/items`)).json();
const partial = items.find((i) => i.valid && i.score > 0 && i.score < 100);
const invalid = items.find((i) => i.valid === false);

const desk = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await desk.newPage();
async function shot(name, path, prep, full = true) {
  await page.goto(base + path, { waitUntil: "networkidle" });
  await page.waitForTimeout(900);
  if (prep) await prep(page);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: full });
  console.log(name);
}
await shot("01-evaluate", "/", async (p) => {
  await p.getByPlaceholder(/Search/).fill("llama-3.1-8b");
  await p.waitForTimeout(400);
}, false);
await shot("02-run", `/runs/${rnd.run_id}`);
await shot("03-inspect-partial-route", `/runs/${rnd.run_id}/items/${partial.job_id}`, async (p) => {
  await p.locator("button.pm-cell.pm-opened").first().click();
  await p.waitForTimeout(700);
});
await shot("04-inspect-invalid", `/runs/${rnd.run_id}/items/${invalid.job_id}`);
await shot("05-inspect-2d-fallback", `/runs/${rnd.run_id}/items/${partial.job_id}`, async (p) => {
  await p.getByRole("button", { name: "2D layers" }).click();
  await p.waitForTimeout(300);
}, false);
await shot("06-leaderboard-empty", "/leaderboard", null, false);
await shot("07-practice", "/practice/" + (await (await fetch(`${base}/api/practice`)).json())[4].instance_id, null, false);
await shot("08-method", "/about", null, false);

const mob = await browser.newContext({ ...devices["Pixel 7"] });
const m = await mob.newPage();
await m.goto(`${base}/runs/${rnd.run_id}/items/${partial.job_id}`, { waitUntil: "networkidle" });
await m.waitForTimeout(900);
await m.screenshot({ path: `${out}/09-mobile-inspect.png` });
await m.goto(`${base}/runs/${rnd.run_id}`, { waitUntil: "networkidle" });
await m.waitForTimeout(600);
await m.screenshot({ path: `${out}/10-mobile-run.png` });
console.log("mobile");
await browser.close();
