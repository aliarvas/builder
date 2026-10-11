// node test/remote-test.mjs <base url> : every listed answer against the deployed Worker (exact body and status).
import assert from "node:assert/strict";
import fs from "node:fs";
const base = process.argv[2].replace(/\/$/, "");
const data = JSON.parse(fs.readFileSync(new URL("../test-customers.json", import.meta.url), "utf8"));
const jobs = [];
const add = (service, d, e) => jobs.push({ service, d, e });
for (const c of data.customers) for (const [s, v] of Object.entries(c.services)) {
  const base1 = { customerNo: c.customerNo, aiFlow: "CardOps", intAddressInfoType: "E", cardNumber: "540000******1234", currencyType: "TL", statementDate: "05.10.2026", emailAddress: "a@b.example" };
  if (["cards.list", "contact.email.get", "statement.pdf.send"].includes(s)) add(s, base1, v);
  else if (["cards.balance", "statement.week.get"].includes(s)) for (const [card, e] of Object.entries(v)) add(s, { cardNumber: card }, e);
  else for (const [card, ws] of Object.entries(v)) for (const [w, e] of Object.entries(ws)) add(s, { cardNumber: card, newStatementWeek: Number(w), statementDay: 5 }, e);
}
let bad = 0, i = 0;
async function worker() {
  while (i < jobs.length) {
    const j = jobs[i++];
    const r = await fetch(`${base}/voice/v1/${j.service}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ data: j.d, call: { ani: "x", lang: "tr" } }) });
    const body = await r.json();
    try { assert.equal(r.status, j.e.http); assert.deepEqual(body, j.e.response); } catch (e) { bad++; console.log("MISMATCH", j.service, JSON.stringify(j.d), r.status); }
  }
}
await Promise.all(Array.from({ length: 12 }, worker));
console.log(jobs.length + " requests, " + bad + " mismatches");
process.exit(bad ? 1 : 0);
