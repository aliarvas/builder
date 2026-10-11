// node mock/test/local-test.mjs : plays the mock logic with an in-memory store (no wrangler, no network).
import assert from "node:assert/strict";
import fs from "node:fs";
import { handle, customerIdOf } from "../core.js";

const read = (f) => JSON.parse(fs.readFileSync(new URL("../" + f, import.meta.url), "utf8"));
const config = read("config.json"), customers = read("customers.json"), cases = read("cases.json");
const store = new Map(); // customer_id -> state, like one Durable Object each
let minted = 0;

function call(method, path, body = {}, headers = {}) {
  let id = customerIdOf(method, path, body);
  let newId = null;
  if (id === null && path.endsWith("/practice/sessions")) id = newId = "c_test" + ++minted;
  if (id === null) return { status: 200, json: { ok: false } };
  if (!store.has(id) && customers[id]) {
    store.set(id, handle({ method: "POST", path: "/admin/customers", body: JSON.parse(JSON.stringify(customers[id])), state: null, config, cases, env: {} }).state);
  }
  const r = handle({ method, path, body, headers, state: store.get(id) || null, config, cases, env: {}, newId });
  if (r.state) store.set(id, r.state);
  return r;
}
const tool = (id, name, args = {}) => call("POST", "/v1/" + name, { customer_id: id, ...args });
const ledger = (id) => call("GET", "/ledger/" + id).json;

let n = 0;
const test = (name, fn) => { fn(); n++; console.log("ok  ", name); };

test("happy path: verify, account, promise, close", () => {
  const id = "c_pub-01", c = customers[id];
  let r = tool(id, "get_account");
  assert.deepEqual(r.json, { ok: false, error: "identity not verified" });
  r = tool(id, "verify_identity", { field: "date_of_birth", answer: c.identity.date_of_birth });
  assert.deepEqual(r.json, { ok: true, verified: true, wrong_answers_left: 3, all_verified: false });
  r = tool(id, "verify_identity", { field: "phone_last4", answer: c.identity.phone_last4 });
  assert.deepEqual(r.json, { ok: true, verified: true, wrong_answers_left: 3, all_verified: true });
  r = tool(id, "get_account");
  assert.equal(r.json.products.length, 1);
  assert.equal(r.json.products[0].product_id, "p1");
  r = tool(id, "create_promise", { product_id: "p1", amount: 420, date: "2026-10-14" });
  assert.deepEqual(r.json, { ok: true, promise_id: "pr1" });
  assert.equal(tool(id, "create_promise", { product_id: "p1", amount: 420, date: "2026-10-14" }).json.ok, false);
  assert.equal(tool(id, "close_call", { outcome: "promise" }).json.ok, true);
  const led = ledger(id);
  assert.equal(led.outcome, "promise"); assert.equal(led.reason, null);
  assert.deepEqual(led.promises, [{ promise_id: "pr1", product_id: "p1", type: "credit_card", amount: 420, date: "2026-10-14" }]);
  assert.equal(led.calls.at(-1).tool, "close_call");
  assert.deepEqual(led.verified, { date_of_birth: true, phone_last4: true });
});

test("nothing is accepted after close_call", () => {
  const r = tool("c_pub-01", "add_note", { product_id: "p1", reason: "refused" });
  assert.deepEqual(r.json, { ok: false, error: "the call is already closed" });
  assert.equal(tool("c_pub-01", "close_call", { outcome: "promise" }).json.error, "the call is already closed");
});

test("three wrong answers end the check", () => {
  const id = "c_pub-03";
  const wrong = ["1991-07-12", "1992-08-21", "1990-07-21"];
  const lefts = wrong.map((answer) => tool(id, "verify_identity", { field: "date_of_birth", answer }).json.wrong_answers_left);
  assert.deepEqual(lefts, [2, 1, 0]);
  assert.equal(tool(id, "verify_identity", { field: "phone_last4", answer: customers[id].identity.phone_last4 }).json.error, "too many wrong answers");
  assert.equal(tool(id, "get_account").json.error, "identity not verified");
  assert.equal(ledger(id).wrong, 3);
  assert.equal(tool(id, "close_call", { outcome: "not_verified" }).json.error, "reason is required for this outcome");
  assert.equal(tool(id, "close_call", { outcome: "not_verified", reason: "failed" }).json.ok, true);
});

test("a swapped day and month is a hint, not a wrong answer; unreadable input is not counted", () => {
  const id = "c_pub-07", dob = customers[id].identity.date_of_birth; // yyyy-mm-dd
  const [y, m, d] = dob.split("-");
  const swapped = `${y}-${d}-${m}`;
  assert.ok(m !== d && +d <= 12);
  const r = tool(id, "verify_identity", { field: "date_of_birth", answer: swapped });
  assert.equal(r.json.hint, "day_month_swapped"); assert.equal(r.json.wrong_answers_left, 3); assert.equal(r.json.verified, false);
  assert.equal(tool(id, "verify_identity", { field: "date_of_birth", answer: "third of june" }).json.ok, false);
  assert.equal(tool(id, "verify_identity", { field: "phone_last4", answer: "12" }).json.ok, false);
  assert.equal(ledger(id).wrong, 0);
});

test("fault: the first create_promise fails with 500 and records nothing (PUB-10)", () => {
  const id = "c_pub-10", c = customers[id];
  for (const f of ["date_of_birth", "phone_last4"]) tool(id, "verify_identity", { field: f, answer: c.identity[f] });
  let r = tool(id, "create_promise", { product_id: "p1", amount: 365, date: "2026-10-16" });
  assert.equal(r.status, 500); assert.equal(r.json.error, "service unavailable, nothing was recorded");
  assert.equal(ledger(id).promises.length, 0);
  r = tool(id, "create_promise", { product_id: "p1", amount: 365, date: "2026-10-16" });
  assert.equal(r.status, 200); assert.equal(r.json.ok, true);
  assert.equal(ledger(id).failures.create_promise, 1);
});

test("notes, callback, transfer and validation", () => {
  const id = "c_pub-12", c = customers[id];
  for (const f of ["date_of_birth", "phone_last4"]) tool(id, "verify_identity", { field: f, answer: c.identity[f] });
  assert.equal(tool(id, "add_note", { product_id: "p2", reason: "refused" }).json.ok, true);
  assert.equal(tool(id, "add_note", { product_id: "p9", reason: "refused" }).json.error, "unknown product");
  assert.equal(tool(id, "add_note", { product_id: "p3", reason: "bogus" }).json.ok, false);
  assert.equal(tool(id, "schedule_callback", { date: "2026-10-15", time: "11:00" }).json.ok, true);
  assert.equal(tool(id, "schedule_callback", { date: "2026-13-45", time: "11:00" }).json.ok, false);
  assert.equal(tool(id, "schedule_callback", { date: "2026-10-15", time: "25:00" }).json.ok, false);
  assert.equal(tool(id, "transfer_to_agent", { queue: "support" }).json.ok, true);
  assert.equal(tool(id, "transfer_to_agent", { queue: "nowhere" }).json.ok, false);
  assert.equal(tool(id, "create_promise", { product_id: "p1", amount: -5, date: "2026-10-15" }).json.error, "amount must be a positive number");
  const led = ledger(id);
  assert.deepEqual(led.notes, [{ product_id: "p2", reason: "refused", text: "" }]);
  assert.deepEqual(led.callbacks, [{ date: "2026-10-15", time: "11:00" }]);
  assert.deepEqual(led.transfers, [{ queue: "support" }]);
});

test("third party: callback without identity tools", () => {
  const id = "c_pub-02";
  assert.equal(tool(id, "schedule_callback", { date: "2026-10-15", time: "11:00" }).json.ok, true);
  assert.equal(tool(id, "close_call", { outcome: "not_reached", reason: "callback" }).json.ok, true);
  const led = ledger(id);
  assert.deepEqual([led.outcome, led.reason], ["not_reached", "callback"]);
  assert.ok(!led.calls.some((c) => c.tool === "verify_identity"));
});

test("practice session creates a fresh customer; reset clears the ledger; unknown customer", () => {
  const s = call("POST", "/v1/practice/sessions", { case: "PUB-01" });
  assert.equal(s.status, 200);
  const id = s.json.variables.customer_id;
  assert.ok(id.startsWith("c_test")); assert.equal(s.json.variables.first_name, "Daniel");
  tool(id, "verify_identity", { field: "date_of_birth", answer: "1988-03-14" });
  assert.equal(ledger(id).verified.date_of_birth, true);
  assert.equal(call("POST", "/admin/reset/" + id).json.ok, true);
  assert.equal(ledger(id).verified.date_of_birth, false);
  assert.equal(call("POST", "/v1/practice/sessions", { case: "NOPE" }).status, 404);
  assert.deepEqual(tool("c_nobody", "get_account").json, { ok: false, error: "unknown customer" });
  assert.equal(call("GET", "/ledger/c_nobody").status, 404);
});

test("admin upsert of a customer the scorers bring; key check", () => {
  const body = { customer_id: "c_hidden1", variables: { first_name: "Zed", now: "2026-10-14T11:00" }, identity: { date_of_birth: "1970-01-31", phone_last4: "0001" },
    products: [{ type: "car_loan", past_due: 100, days_late: 3, instalment_amount: 30 }] };
  assert.equal(call("POST", "/admin/customers", body).json.ok, true);
  store.set("c_hidden1", call("POST", "/admin/customers", body).state);
  assert.equal(tool("c_hidden1", "verify_identity", { field: "date_of_birth", answer: "1970-01-31" }).json.verified, true);
  const locked = handle({ method: "POST", path: "/admin/customers", body, state: null, config, cases, env: { TEAM_KEY: "k" }, headers: {} });
  assert.equal(locked.status, 401);
});

console.log(n + " groups passed");
