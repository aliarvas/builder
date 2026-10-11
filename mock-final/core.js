// Freya Bank statement services, test environment. Pure routing: route(data, {method, path, body}) -> {status, body, delay, log}.
// Answers come ONLY from test-customers.json (exact bodies and status codes). Anything not in it gets the 404
// of that service (or a 400 INVALID_ARGUMENTS_ERROR where the contract has no 404). Nothing is made up.

export const SERVICES = ["cards.list", "cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change", "contact.email.get", "statement.pdf.send"];

// Contract section 3/4. Required data fields per service (empty or missing -> 400, message names the field).
const REQUIRED = {
  "cards.list": [["customerNo", "customerNo"]],
  "cards.balance": [["cardNumber", "card number"]],
  "statement.week.get": [["cardNumber", "card number"]],
  "statement.week.decide": [["cardNumber", "card number"], ["newStatementWeek", "newStatementWeek"], ["statementDay", "statementDay"]],
  "statement.week.change": [["cardNumber", "card number"], ["newStatementWeek", "newStatementWeek"], ["statementDay", "statementDay"]],
  "contact.email.get": [["customerNo", "customerNo"], ["intAddressInfoType", "intAddressInfoType"]],
  "statement.pdf.send": [["customerNo", "customerNo"], ["cardNumber", "card number"], ["currencyType", "currencyType"], ["statementDate", "statementDate"], ["emailAddress", "emailAddress"]],
};

// 404 per service (contract section 4). Text for 102 and 107 is from the contract; 120 is the contract's example; 121 is not given there.
const NOT_FOUND = {
  "cards.list": ["FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı."],
  "cards.balance": ["FB_IVR_CHANNEL_120", "Kart bakiye servisi hatası: kart bulunamadı"],
  "statement.week.get": ["FB_IVR_CHANNEL_121", "Kart bulunamadı"],
  "statement.pdf.send": ["FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı"],
};

export function buildIndex(data) {
  const byCustomer = new Map();
  const byCard = new Map(); // service -> card -> entry
  for (const s of SERVICES) byCard.set(s, new Map());
  for (const c of data.customers) {
    byCustomer.set(String(c.customerNo), c);
    for (const s of ["cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change"]) {
      for (const [card, entry] of Object.entries(c.services[s] || {})) {
        if (!byCard.get(s).has(card)) byCard.get(s).set(card, entry);
      }
    }
  }
  return { byCustomer, byCard, first: data.customers[0] };
}

function hex32(text) {
  let h = 0x811c9dc5, out = "";
  for (let round = 0; out.length < 32; round++) {
    for (const ch of text + ":" + round) { h ^= ch.charCodeAt(0); h = Math.imul(h, 0x01000193) >>> 0; }
    out += h.toString(16).padStart(8, "0");
  }
  return out.slice(0, 32);
}

export function errorBody(code, message, type, seed) {
  const guid = hex32(seed + code);
  return { result: { guid, returnCode: code, messageText: message, code, message, type, details: { guid, rootCause: type === "ERROR" ? "InvalidArgumentsException" : "NotFoundException", errorOrigin: "ivr-gateway-test:ivr-channel-v0" } } };
}

const isTemplate = (v) => typeof v === "string" && (v.startsWith("{{") || v.startsWith("%7B%7B"));
const empty = (v) => v === undefined || v === null || (typeof v === "string" && v.trim() === "");
const text = (v) => String(v).trim();

export function normalizePath(path) {
  const p = String(path || "/").split("?")[0].replace(/\/+$/, "") || "/";
  const m = p.match(/^(?:\/voice)?(?:\/v1)?\/([a-z]+\.[a-z.]+)$/);
  return m ? m[1] : p;
}

export function route(index, { method, path, body }) {
  const name = normalizePath(path);
  if (method !== "POST" || !SERVICES.includes(name)) return { status: 404, body: { error: "not found", services: SERVICES } };
  const data = body && typeof body === "object" && body.data && typeof body.data === "object" ? body.data : {};
  const seed = name + JSON.stringify(data);
  const log = { service: name, customerNo: data.customerNo === undefined ? null : text(data.customerNo), cardNumber: data.cardNumber ?? null, week: data.newStatementWeek ?? null };

  // 400: a required field is missing or empty.
  for (const [field, label] of REQUIRED[name]) {
    if (empty(data[field])) {
      return done(400, errorBody("INVALID_ARGUMENTS_ERROR", `${label} cannot be empty`, "ERROR", seed), 0, log);
    }
  }

  const customerNo = data.customerNo !== undefined ? text(data.customerNo) : null;
  const card = data.cardNumber !== undefined ? text(data.cardNumber) : null;
  const week = data.newStatementWeek !== undefined ? text(data.newStatementWeek) : null;

  // The panel's "Test API Request" sends {{variables}} unfilled: answer with a valid record then.
  const templated = [customerNo, card, week].some(isTemplate);
  let entry = null;
  if (name === "cards.list" || name === "contact.email.get" || name === "statement.pdf.send") {
    const customer = templated ? index.first : index.byCustomer.get(customerNo);
    entry = customer ? customer.services[name] : null;
  } else {
    let key = card;
    if (templated) key = Object.keys(index.first.services["cards.balance"])[0];
    const hit = index.byCard.get(name).get(key);
    if (name === "statement.week.decide" || name === "statement.week.change") {
      const wk = templated ? Object.keys(hit || {})[0] : week;
      entry = hit ? hit[wk] : null;
    } else entry = hit;
  }
  if (entry) {
    return done(entry.http, entry.response, (entry.delaySeconds || 0) * 1000, log, entry);
  }
  if (NOT_FOUND[name]) {
    const [code, message] = NOT_FOUND[name];
    return done(404, errorBody(code, message, "WARNING", seed), 0, log);
  }
  // No 404 in the contract for this service: 400 INVALID_ARGUMENTS_ERROR.
  const reason = name === "contact.email.get" ? "customerNo is not valid"
    : card && !index.byCard.get(name).has(card) ? "card number is not valid"
    : "newStatementWeek is not valid for this card";
  return done(400, errorBody("INVALID_ARGUMENTS_ERROR", reason, "ERROR", seed), 0, log);
}

function done(status, body, delay, log, entry) {
  return { status, body, delay, log: { ...log, status } };
}
