// freya-final-mock: the bank's statement services (test environment). Answers are exact and static
// (core.js + test-customers.json); a Durable Object only keeps a ledger of the calls and the state changes
// (confirmed week changes, statement e-mails). The answer never waits for the Durable Object.
import customers from "./test-customers.json";
import { buildIndex, route, SERVICES } from "./core.js";

const index = buildIndex(customers);
const JSON_HEADERS = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*" };
const send = (status, body) => new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const ledger = (env) => env.STATE.get(env.STATE.idFromName("ledger"));

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: { ...JSON_HEADERS, "access-control-allow-methods": "GET, POST, OPTIONS", "access-control-allow-headers": "*" } });
    }
    if (request.method === "GET" && (url.pathname === "/health" || url.pathname === "/")) {
      return send(200, { ok: true, service: "freya-final-mock", customers: customers.customers.length, services: SERVICES });
    }
    if (url.pathname.startsWith("/ledger") || url.pathname.startsWith("/admin/")) {
      return ledger(env).fetch(new Request("https://do" + url.pathname + url.search, { method: request.method }));
    }
    if (request.method === "POST" && url.pathname.endsWith("/oauth2/token")) {
      return send(200, { access_token: "test-token", token_type: "Bearer", expires_in: 1800 });
    }
    let body = null;
    if (request.method === "POST") {
      try { body = await request.json(); } catch { body = null; }
    }
    const result = route(index, { method: request.method, path: url.pathname, body });
    if (result.log) {
      const note = { at: new Date().toISOString(), ...result.log, args: body && body.data ? body.data : null };
      // The state: a confirmed week change and a sent statement. Recorded, not applied to later answers.
      if (result.status === 200 && result.log.service === "statement.week.change" && result.body.data && result.body.data.exitState === "OK") note.state = "week_changed";
      if (result.status === 200 && result.log.service === "statement.pdf.send" && result.body.data && result.body.data.exitState === "DONE") note.state = "statement_sent";
      ctx.waitUntil(ledger(env).fetch(new Request("https://do/record", { method: "POST", body: JSON.stringify(note) })).catch(() => {}));
    }
    if (result.delay) await sleep(result.delay);
    return send(result.status, result.body);
  },
};

export class CustomerState {
  constructor(state) { this.state = state; }
  async fetch(request) {
    const url = new URL(request.url);
    let log = (await this.state.storage.get("log")) || [];
    if (url.pathname === "/record") {
      log.push(await request.json());
      if (log.length > 2000) log = log.slice(-2000);
      await this.state.storage.put("log", log);
      return new Response("ok");
    }
    if (url.pathname.startsWith("/admin/reset")) {
      await this.state.storage.delete("log");
      return new Response(JSON.stringify({ ok: true }), { headers: JSON_HEADERS });
    }
    const customerNo = url.searchParams.get("customerNo");
    const rows = customerNo ? log.filter((row) => row.customerNo === customerNo || (row.args && String(row.args.customerNo) === customerNo)) : log;
    return new Response(JSON.stringify({ ok: true, count: rows.length, calls: rows, changes: rows.filter((r) => r.state) }), { headers: JSON_HEADERS });
  }
}
