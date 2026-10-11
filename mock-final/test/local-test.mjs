// node mock-final/test/local-test.mjs : every listed test-customer answer, compared exactly (status and body).
import assert from "node:assert/strict";
import fs from "node:fs";
import { buildIndex, route } from "../core.js";

const data = JSON.parse(fs.readFileSync(new URL("../test-customers.json", import.meta.url), "utf8"));
const index = buildIndex(data);
const call = (service, d, path) => route(index, { method: "POST", path: path || `/voice/v1/${service}`, body: { data: d, call: { ani: "x", lang: "tr" } } });
let checked = 0;
const same = (label, got, status, body, delay = 0) => {
  assert.equal(got.status, status, label + " status");
  assert.deepEqual(got.body, body, label + " body");
  assert.equal(got.delay, delay * 1000, label + " delay");
  checked++;
};

for (const c of data.customers) {
  const no = c.customerNo;
  for (const [service, entry] of Object.entries(c.services)) {
    if (service === "cards.list" || service === "contact.email.get" || service === "statement.pdf.send") {
      const base = { customerNo: no, aiFlow: "CardOps", intAddressInfoType: "E", cardNumber: "540000******1234", currencyType: "TL", statementDate: "05.10.2026", emailAddress: "a@b.example" };
      same(`${no} ${service}`, call(service, base), entry.http, entry.response, entry.delaySeconds || 0);
      same(`${no} ${service} (number)`, call(service, { ...base, customerNo: Number(no) }), entry.http, entry.response);
    } else if (service === "cards.balance" || service === "statement.week.get") {
      for (const [card, e] of Object.entries(entry)) same(`${no} ${service} ${card}`, call(service, { cardNumber: card }), e.http, e.response, e.delaySeconds || 0);
    } else {
      for (const [card, weeks] of Object.entries(entry)) for (const [week, e] of Object.entries(weeks)) {
        same(`${no} ${service} ${card} w${week}`, call(service, { cardNumber: card, newStatementWeek: week, statementDay: 5 }), e.http, e.response);
        same(`${no} ${service} ${card} w${week} (number)`, call(service, { cardNumber: card, newStatementWeek: Number(week), statementDay: "5" }), e.http, e.response);
      }
    }
  }
}
console.log("ok   " + checked + " listed answers equal, status included");

const code = (r) => r.body.result && r.body.result.code;
// unknown customer / card / week
assert.equal(call("cards.list", { customerNo: "11111111" }).status, 404);
assert.equal(code(call("cards.list", { customerNo: "11111111" })), "FB_IVR_CHANNEL_102");
assert.equal(code(call("cards.balance", { cardNumber: "999999******9999" })), "FB_IVR_CHANNEL_120");
assert.equal(code(call("statement.week.get", { cardNumber: "999999******9999" })), "FB_IVR_CHANNEL_121");
assert.equal(code(call("statement.pdf.send", { customerNo: "94907600", cardNumber: "x", currencyType: "TL", statementDate: "d", emailAddress: "e" })), "FB_IVR_CHANNEL_107"); // listed customer without an entry
assert.equal(call("statement.pdf.send", { customerNo: "94907600", cardNumber: "x", currencyType: "TL", statementDate: "d", emailAddress: "e" }).status, 404);
const bad = call("statement.week.decide", { cardNumber: "540000******1234", newStatementWeek: 1, statementDay: 5 }); // the current week has no entry
assert.equal(bad.status, 400); assert.equal(code(bad), "INVALID_ARGUMENTS_ERROR"); assert.equal(bad.body.data, undefined);
assert.equal(call("contact.email.get", { customerNo: "11111111", intAddressInfoType: "E" }).status, 400);
console.log("ok   unknown customer, card and week answers");

// 400 for empty required fields
for (const [service, d, label] of [["cards.list", {}, "customerNo"], ["cards.balance", { cardNumber: " " }, "card number"], ["contact.email.get", { customerNo: "90000001", intAddressInfoType: "" }, "intAddressInfoType"], ["statement.week.change", { cardNumber: "540000******1234", newStatementWeek: 2 }, "statementDay"]]) {
  const r = call(service, d);
  assert.equal(r.status, 400); assert.equal(r.body.result.message, `${label} cannot be empty`);
  assert.equal(r.body.result.returnCode, r.body.result.code); assert.equal(r.body.result.messageText, r.body.result.message);
}
console.log("ok   400 INVALID_ARGUMENTS_ERROR");

// template variable: a valid record, not an error
assert.equal(call("cards.list", { customerNo: "{{customerNumber}}" }).status, 200);
assert.equal(call("cards.balance", { cardNumber: "{{card}}" }).status, 200);
console.log("ok   template variables");

// paths
for (const p of ["/voice/v1/cards.list", "/v1/cards.list", "/cards.list"]) assert.equal(call("cards.list", { customerNo: "90000001" }, p).status, 200);
assert.equal(route(index, { method: "GET", path: "/voice/v1/cards.list", body: null }).status, 404);
console.log("ok   paths");
