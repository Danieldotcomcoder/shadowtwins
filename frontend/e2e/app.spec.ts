import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const errorsOf = (page: Page) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  return errors;
};

async function createRun(page: Page, model: string, mode = "quick_check", concurrency = 4) {
  const res = await page.request.post("/api/runs", {
    data: { model_id: model, profile_id: "standard", mode, spend_limit_usd: 5, concurrency },
  });
  expect(res.status()).toBe(201);
  return (await res.json()).run_id as string;
}

async function waitForState(page: Page, runId: string, state: string) {
  await expect.poll(async () => (await (await page.request.get(`/api/runs/${runId}`)).json()).state,
    { timeout: 60_000 }).toBe(state);
}

test("evaluate flow: pick a model, see the cost preview, start, watch it finish live", async ({ page }) => {
  const errors = errorsOf(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Evaluate a model" })).toBeVisible();
  await page.getByPlaceholder(/Search \d+ models/).fill("mock/optimal");
  await page.locator("[cmdk-item]").filter({ hasText: "mock/optimal" }).first().click();
  await expect(page.getByText("Unranked run")).toBeVisible();
  await expect(page.getByText("mock provider (test double)").first()).toBeVisible();
  await expect(page.locator(".stat").filter({ hasText: "Calls" })).toContainText("9");
  await page.getByRole("button", { name: "Start evaluation" }).click();
  await expect(page).toHaveURL(/\/runs\/run_/);
  await expect(page.locator("h1 .badge").filter({ hasText: "Completed" })).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".score-big")).toContainText("100.0");
  await expect(page.getByText("✓ official")).toBeVisible();
  await expect(page.locator(".feed-item").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("instance inspection: synchronized views, pairs, silhouettes, 2D fallback toggle", async ({ page }) => {
  const errors = errorsOf(page);
  const runId = await createRun(page, "mock/random", "standard", 8);
  await waitForState(page, runId, "completed");
  const items = await (await page.request.get(`/api/runs/${runId}/items`)).json();
  const item = items.find((i: { valid: boolean; score: number }) => i.valid && i.score > 0) ?? items[0];
  await page.goto(`/runs/${runId}/items/${item.job_id}`);
  await expect(page.locator(".voxel-stage canvas")).toHaveCount(3);
  await expect(page.getByRole("heading", { name: "Exact silhouettes" })).toBeVisible();
  await expect(page.locator(".sil svg")).toHaveCount(9);
  const pair = page.locator("button.pm-cell").first();
  await pair.click();
  await expect(pair).toHaveAttribute("aria-pressed", "true");
  const stage = page.locator(".voxel-stage").first();
  await stage.focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("r");
  await page.getByRole("button", { name: "2D layers" }).click();
  await expect(page.locator(".lc")).toHaveCount(64 * 3);
  await page.getByRole("button", { name: "3D", exact: true }).click();
  await expect(page.locator(".voxel-stage canvas")).toHaveCount(3);
  await expect(page.getByText("Score arithmetic")).toBeVisible();
  await expect(page.getByText(/independently verified/).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("invalid answers show their violation and never appear as legal results", async ({ page }) => {
  const runId = await createRun(page, "mock/invalid");
  await waitForState(page, runId, "completed");
  const items = await (await page.request.get(`/api/runs/${runId}/items`)).json();
  await page.goto(`/runs/${runId}/items/${items[0].job_id}`);
  await expect(page.locator("h1 .badge.bad")).toContainText("Malformed");
  await expect(page.getByText("No object could be built from this answer.")).toBeVisible();
  await expect(page.getByText("Invalid answers score")).toBeVisible();
  await page.goto(`/runs/${runId}`);
  await expect(page.locator(".cat-list")).toContainText("Malformed or ambiguous JSON · 9");
});

test("run controls: pause stops dispatch, resume finishes", async ({ page }) => {
  const runId = await createRun(page, "mock/slow", "quick_check", 1);
  await page.goto(`/runs/${runId}`);
  await page.getByRole("button", { name: "❚❚ Pause" }).click();
  await expect(page.locator("h1 .badge").filter({ hasText: "Paused" })).toBeVisible();
  await page.getByRole("button", { name: "▶ Resume" }).click();
  await expect(page.locator("h1 .badge").filter({ hasText: "Completed" })).toBeVisible({ timeout: 60_000 });
});

test("practice: a human answer is scored exactly by the server and compared with the optimum", async ({ page }) => {
  const errors = errorsOf(page);
  await page.goto("/practice");
  await expect(page.locator(".practice-card")).toHaveCount(9);
  await page.locator(".practice-card").first().click();
  const solid = page.locator(".lc.clickable.editable.solid").first();
  const empty = page.locator(".lc.clickable.editable.empty").first();
  await solid.click();
  await empty.click();
  await expect(page.locator("code").filter({ hasText: '"remove":[' })).not.toContainText('"remove":[]');
  await page.getByRole("button", { name: "Submit for exact scoring" }).click();
  await expect(page.locator(".banner[role=status]")).toContainText(/Valid|Invalid/);
  await expect(page.getByRole("heading", { name: "You", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Optimal", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("reduced motion disables route animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/fixtures");
  await page.locator("button.pm-cell").first().click();
  await expect(page.getByRole("button", { name: /route animation/ })).toBeDisabled();
});

test("without WebGL the 2D layer view is used", async ({ page }) => {
  await page.addInitScript(() => {
    const orig = HTMLCanvasElement.prototype.getContext;
    Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
      value(this: HTMLCanvasElement, type: string, ...args: unknown[]) {
        if (type.startsWith("webgl")) return null;
        return (orig as (...a: unknown[]) => unknown).call(this, type, ...args);
      },
    });
  });
  await page.goto("/fixtures");
  await expect(page.getByText(/WebGL is unavailable/)).toBeVisible();
  await expect(page.locator(".voxel-stage canvas")).toHaveCount(0);
  await expect(page.locator(".lc").first()).toBeVisible();
});

test("leaderboard empty state explains eligibility; fixtures are labelled as non-results", async ({ page }) => {
  await page.goto("/leaderboard");
  await expect(page.getByText("No eligible ranked runs yet")).toBeVisible();
  await page.goto("/fixtures");
  await expect(page.getByText(/not model results/)).toBeVisible();
  await expect(page.getByText(/Not a model result/)).toBeVisible();
});

test("no serious accessibility violations on key pages", async ({ page }) => {
  const runId = await createRun(page, "mock/optimal");
  await waitForState(page, runId, "completed");
  const items = await (await page.request.get(`/api/runs/${runId}/items`)).json();
  for (const path of ["/", "/runs", `/runs/${runId}`, `/runs/${runId}/items/${items[0].job_id}`, "/leaderboard",
    "/practice", "/about", "/fixtures"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const res = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
    const serious = res.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${path}: ${v.id} (${v.nodes.length})`)).toEqual([]);
  }
});

test("mobile layout uses tabs and never scrolls sideways @mobile", async ({ page }) => {
  const runId = await createRun(page, "mock/optimal");
  await waitForState(page, runId, "completed");
  const items = await (await page.request.get(`/api/runs/${runId}/items`)).json();
  for (const path of ["/", "/runs", `/runs/${runId}`, "/leaderboard", "/practice", "/about"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, path).toBeLessThanOrEqual(1);
  }
  await page.goto(`/runs/${runId}/items/${items[0].job_id}`);
  await expect(page.getByRole("tab", { name: "Original" })).toBeVisible();
  await page.getByRole("tab", { name: "Optimal" }).click();
  await expect(page.locator(".voxel-stage canvas")).toHaveCount(1);
});
