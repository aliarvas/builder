// Cloudflare Worker: the bank mock. One Durable Object (SQLite-backed, free plan) per customer_id keeps
// that customer's data and ledger. Logic is in core.js; names and rules are in config.json.
import config from "./config.json";
import customers from "./customers.json";
import cases from "./cases.json";
import { handle, customerIdOf, customerFromCase } from "./core.js";

const JSON_HEADERS = { "content-type": "application/json" };
const send = (status, json) => new Response(JSON.stringify(json), { status, headers: JSON_HEADERS });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let body = null;
    if (request.method === "POST") {
      try { body = await request.json(); } catch { body = {}; }
    }
    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
      return send(200, { ok: true, service: "bank-mock", customers: Object.keys(customers).length });
    }
    let id = customerIdOf(request.method, url.pathname, body);
    let newId = null;
    if (id === null && /\/practice\/sessions$/.test(url.pathname)) {
      newId = "c_" + crypto.randomUUID().slice(0, 12);
      id = newId;
    }
    if (id === null) return send(200, { ok: false, error: config.errors.missing + ": customer_id" });
    const stub = env.LEDGER.get(env.LEDGER.idFromName(id));
    const inner = new Request("https://do/", {
      method: "POST",
      headers: { ...JSON_HEADERS, "x-team-key": request.headers.get("x-team-key") || "" },
      body: JSON.stringify({ method: request.method, path: url.pathname, body: body || {}, customerId: id, newId }),
    });
    return stub.fetch(inner);
  },
};

export class Ledger {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request) {
    const input = await request.json();
    let stored = (await this.state.storage.get("state")) || null;
    if (!stored && customers[input.customerId]) {
      const customer = JSON.parse(JSON.stringify(customers[input.customerId]));
      stored = null;
      // build the ledger through core by replaying nothing: handle() needs {customer, ledger}
      const seeded = handle({ method: "POST", path: "/admin/customers", body: customer, state: null, config, cases, env: { ...this.env, TEAM_KEY: "" } });
      stored = seeded.state;
    }
    const result = handle({
      method: input.method, path: input.path, body: input.body,
      headers: { "x-team-key": request.headers.get("x-team-key") || "" },
      state: stored, config, cases, env: this.env, newId: input.newId,
    });
    if (result.state && result.state !== stored) await this.state.storage.put("state", result.state);
    return new Response(JSON.stringify(result.json), { status: result.status, headers: JSON_HEADERS });
  }
}
