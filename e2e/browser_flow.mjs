import { chromium } from "playwright-core";
const b = await chromium.launch({ executablePath: "/usr/bin/google-chrome", args: ["--no-sandbox"] });
const mobile = process.argv[2] === "mobile";
const ctx = await b.newContext(mobile ? { viewport: { width: 390, height: 800 }, isMobile: true, hasTouch: true } : { viewport: { width: 1400, height: 850 } });
const p = await ctx.newPage(); const errs = [];
p.on("console", m => m.type() === "error" && errs.push(m.text())); p.on("pageerror", e => errs.push("PAGEERR " + e.message));
const sh = n => p.screenshot({ path: `/tmp/${mobile ? "m" : "d"}-${n}.png` });
const T = async (n) => { if (mobile) await p.getByRole("tab", { name: new RegExp(n) }).click(); else if (n !== "Chat") await p.getByRole("tab", { name: new RegExp(n) }).click(); };
await p.goto("http://localhost:8000/");
await p.getByRole("button", { name: "New here? Create an account" }).click();
await p.getByLabel("Your name").fill("Asha"); await p.getByLabel("Email").fill(`u${Date.now()}@example.com`); await p.getByLabel(/^Password/).fill("password123");
await p.getByRole("button", { name: "Create account" }).click(); await p.waitForSelector("text=Welcome");
if (mobile) await p.getByRole("button", { name: "Open projects" }).click();
await p.getByRole("button", { name: "+ New project" }).click(); await p.getByLabel("Project name").fill("Test plot"); await p.getByRole("button", { name: "Save" }).click();
await p.waitForSelector("text=Tell me what you want to build");
const say = async (t) => { await p.getByLabel("Message").fill(t); await p.getByRole("button", { name: "Send" }).click(); await p.waitForFunction(() => !document.querySelector(".msgs .spinner") && !document.querySelector(".compose-row .btn.danger"), null, { timeout: 30000 }); await p.waitForTimeout(400); };
await say("I have a 30 ft x 50 ft plot, road on the east. 2 bedrooms, open kitchen, parking. front 3 m, rear 1.5 m, sides 0 m.");
console.log("A:", (await p.locator(".msg.assistant").last().innerText()).slice(0, 300));
await T("Drawing"); await p.waitForSelector(".canvas img", { timeout: 40000 }); await p.waitForTimeout(1200); await sh("10-drawing");
// zoom / pan / fit
const before = await p.locator(".canvas img").evaluate(e => e.style.transform);
await p.getByRole("button", { name: "Zoom in" }).click(); await p.getByRole("button", { name: "Zoom in" }).click();
const zoomed = await p.locator(".canvas img").evaluate(e => e.style.transform);
await p.getByRole("button", { name: "Fit page" }).click(); const fit = await p.locator(".canvas img").evaluate(e => e.style.transform);
console.log("ZOOM changed:", before !== zoomed, "fit restores:", fit === before);
// keyboard
await p.locator(".canvas").focus(); await p.keyboard.press("+"); const kz = await p.locator(".canvas img").evaluate(e => e.style.transform); console.log("kbd zoom:", kz !== before);
await p.keyboard.press("0");
// edit via quick edits -> proposal -> confirm
await T("Brief"); await p.getByText("Quick edits").click();
await p.getByLabel("Opening").selectOption({ index: 1 });
const opt = await p.getByLabel("Opening").locator("option:checked").innerText(); console.log("opening:", opt);
await p.getByLabel("New width (mm)").fill("1800");
await p.getByRole("button", { name: "Propose opening change" }).click();
await p.waitForSelector(".proposal", { timeout: 20000 }); if (!mobile) {} else {}
await sh("11-proposal");
console.log("PROPOSAL:", (await p.locator(".proposal").first().innerText()).replace(/\n+/g, " | ").slice(0, 500));
await p.getByRole("button", { name: "Confirm and save revision" }).click();
await p.waitForSelector("text=Rev 2", { timeout: 30000 }).catch(() => {});
await T("Revisions"); await p.waitForSelector("text=Rev 2"); await sh("12-revisions");
await p.getByLabel("From").selectOption({ index: 1 }); await p.getByLabel("To").selectOption({ index: 2 });
await p.getByRole("button", { name: "Compare" }).click(); await p.waitForSelector(".cmp"); await sh("13-compare");
console.log("CMP:", (await p.locator(".cmp").innerText()).replace(/\n+/g, " | ").slice(0, 400));
await p.getByRole("button", { name: "Overlay" }).click(); await p.waitForSelector(".overlay img"); await p.waitForTimeout(800); await sh("14-overlay");
// export
await T("Export"); await p.getByRole("button", { name: "Export PDF" }).click(); await p.waitForSelector("text=/Download/", { timeout: 60000 }); await sh("15-export");
const [dl] = await Promise.all([p.waitForEvent("download"), p.getByRole("button", { name: "Download" }).first().click()]);
await dl.saveAs("/tmp/ui-export.pdf"); console.log("downloaded", dl.suggestedFilename());
console.log("ERRS", errs); await b.close();
