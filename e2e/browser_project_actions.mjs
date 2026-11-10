import { chromium } from "playwright-core";
const b = await chromium.launch({ executablePath: "/usr/bin/google-chrome", args: ["--no-sandbox"] });
const p = await (await b.newContext({ viewport: { width: 1400, height: 850 } })).newPage(); const errs = [];
p.on("console", m => m.type() === "error" && errs.push(m.text())); p.on("pageerror", e => errs.push("PAGEERR " + e.message));
await p.goto("http://localhost:8000/");
await p.getByRole("button", { name: "New here? Create an account" }).click();
await p.getByLabel("Email").fill(`u${Date.now()}@example.com`); await p.getByLabel(/^Password/).fill("password123");
await p.getByRole("button", { name: "Create account" }).click(); await p.waitForSelector("text=Welcome");
await p.getByRole("button", { name: "+ New project" }).click(); await p.getByLabel("Project name").fill("Alpha"); await p.getByRole("button", { name: "Save" }).click();
await p.waitForSelector("text=Tell me what you want to build");
// attachment + consent
await p.locator('input[type=file]').first().setInputFiles("/tmp/notes.txt");
await p.waitForSelector("text=notes.txt");
await p.getByLabel("Message").fill("see attached"); await p.getByRole("button", { name: "Send" }).click();
await p.waitForSelector("role=dialog"); console.log("CONSENT:", (await p.getByRole("dialog").innerText()).replace(/\n+/g, " | ").slice(0, 300));
await p.getByRole("button", { name: "Confirm and send" }).click();
await p.waitForSelector(".msg.assistant .txt", { timeout: 20000 }); console.log("attach reply ok");
// project actions
await p.getByRole("button", { name: "Actions for Alpha" }).click(); await p.getByRole("menuitem", { name: "Rename / details" }).click();
await p.getByLabel("Project name").fill("Alpha renamed"); await p.getByRole("button", { name: "Save" }).click(); await p.waitForSelector("text=Alpha renamed");
await p.getByRole("button", { name: /Actions for Alpha renamed/ }).click(); await p.getByRole("menuitem", { name: "Duplicate" }).click(); await p.waitForSelector("text=Alpha renamed (copy)");
await p.getByLabel("Search projects").fill("copy"); await p.waitForTimeout(600); console.log("SEARCH list:", await p.locator(".pitem strong").allInnerTexts());
await p.getByLabel("Search projects").fill("attached"); await p.waitForTimeout(600); console.log("CHAT SEARCH list:", await p.locator(".pitem strong").allInnerTexts());
await p.getByLabel("Search projects").fill("");
await p.getByRole("button", { name: /Actions for Alpha renamed \(copy\)/ }).click(); await p.getByRole("menuitem", { name: "Archive" }).click(); await p.waitForTimeout(600);
await p.getByRole("tab", { name: "Archived" }).click(); await p.waitForSelector("text=Alpha renamed (copy)");
await p.getByRole("button", { name: /Actions for/ }).click(); await p.getByRole("menuitem", { name: "Delete…" }).click(); await p.getByRole("button", { name: "Delete permanently" }).click(); await p.waitForSelector("text=No archived projects.");
// branding
await p.getByRole("button", { name: /Branding & account/ }).click(); await p.getByLabel("Firm / studio name").fill("Kunal Design Studio");
await p.getByRole("button", { name: "Save", exact: true }).click(); await p.waitForSelector("text=Saved."); await p.keyboard.press("Escape");
// keyboard nav: tab order reaches composer
console.log("ERRS", errs); await b.close();
