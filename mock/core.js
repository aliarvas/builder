// Bank mock logic. No Cloudflare APIs here: the worker (worker.js) and the node test both call handle().
// Names of tools, fields, enums and error texts come from config.json; customers from customers.json.
//
// handle({method, path, body, headers, state, config, cases, env, newId}) -> {status, json, state}
//   state: {customer, ledger} of ONE customer (null when none yet); the caller stores the returned state.

const DAY = 24 * 3600 * 1000;

export function normalizePath(path) {
  let p = String(path || "/").split("?")[0].replace(/\/+$/, "") || "/";
  if (p.startsWith("/v1/")) p = p.slice(3);
  return p;
}

// Which customer a request belongs to (so the worker can pick the right Durable Object).
export function customerIdOf(method, path, body) {
  const p = normalizePath(path);
  let m = p.match(/^\/(?:practice\/ledger|ledger|admin\/reset)\/(.+)$/);
  if (m) return decodeURIComponent(m[1]);
  if (p === "/admin/customers") return body && body.customer_id ? String(body.customer_id) : null;
  if (p === "/practice/sessions") return null; // the worker mints an id
  return body && body.customer_id !== undefined ? String(body.customer_id) : null;
}

function newLedger(customer, env, config) {
  const fields = Object.fromEntries(Object.keys(config.identity.fields).map((f) => [f, false]));
  return {
    ok: true,
    case: customer.case || null,
    team: (env && env.TEAM) || "",
    now: (customer.variables && customer.variables.now) || null,
    verified: fields,
    wrong: 0,
    hinted: false,
    promises: [],
    notes: [],
    callbacks: [],
    transfers: [],
    outcome: null,
    reason: null,
    failures: {},
    calls: [],
    closed: false,
    last_at: 0,
  };
}

export function customerFromCase(c, id, config) {
  const products = (c.products || []).map((p, i) => ({ [config.product_fields.id]: "p" + (i + 1), ...p }));
  return {
    customer_id: id,
    case: c.id || null,
    variables: { ...(c.variables || {}), customer_id: id, now: (c.variables && c.variables.now) || config.default_now },
    identity: { ...(c.identity || {}) },
    products,
    faults: (c.faults || []).map((f) => ({ ...f })),
  };
}

function publicLedger(ledger) {
  const { closed, ...rest } = ledger;
  return rest;
}

const pad = (n) => String(n).padStart(2, "0");

function parseDate(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(text || "").trim());
  if (!m) return null;
  const [y, mo, d] = [+m[1], +m[2], +m[3]];
  const t = new Date(Date.UTC(y, mo - 1, d));
  if (t.getUTCFullYear() !== y || t.getUTCMonth() !== mo - 1 || t.getUTCDate() !== d) return null;
  return { y, mo, d, text: `${y}-${pad(mo)}-${pad(d)}` };
}

function parseTime(text) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(text || "").trim());
  if (!m || +m[1] > 23 || +m[2] > 59) return null;
  return `${pad(+m[1])}:${m[2]}`;
}

export function handle({ method, path, body, headers = {}, state, config, cases = [], env = {}, newId }) {
  const p = normalizePath(path);
  const E = config.errors;
  body = body && typeof body === "object" ? body : {};
  const reply = (status, json, next = state) => ({ status, json, state: next });
  const adminOk = !env.TEAM_KEY || headers["x-team-key"] === env.TEAM_KEY;

  // ---- our own endpoints -------------------------------------------------------------------------
  if (method === "GET" && (p.startsWith("/ledger/") || p.startsWith("/practice/ledger/"))) {
    if (!state || !state.customer) return reply(404, { ok: false, error: E.unknown_customer });
    return reply(200, publicLedger(state.ledger));
  }
  if (method === "POST" && p === "/practice/sessions") {
    if (!adminOk) return reply(401, { ok: false, error: "x-team-key required" });
    const wanted = body.case;
    const source = typeof wanted === "object" && wanted ? wanted : cases.find((c) => c.id === wanted);
    if (!source) return reply(404, { ok: false, error: "unknown case" });
    const customer = customerFromCase(source, newId, config);
    return reply(200, { ok: true, variables: customer.variables }, { customer, ledger: newLedger(customer, env, config) });
  }
  if (method === "POST" && p === "/admin/customers") {
    if (!adminOk) return reply(401, { ok: false, error: "x-team-key required" });
    if (!body.customer_id) return reply(400, { ok: false, error: E.missing + ": customer_id" });
    const customer = customerFromCase(body, String(body.customer_id), config);
    customer.case = body.case || body.id || null;
    return reply(200, { ok: true, customer_id: customer.customer_id }, { customer, ledger: newLedger(customer, env, config) });
  }
  if (method === "POST" && p.startsWith("/admin/reset/")) {
    if (!adminOk) return reply(401, { ok: false, error: "x-team-key required" });
    if (!state || !state.customer) return reply(404, { ok: false, error: E.unknown_customer });
    return reply(200, { ok: true }, { customer: state.customer, ledger: newLedger(state.customer, env, config) });
  }

  // ---- the bank tools ----------------------------------------------------------------------------
  const tool = p.slice(1);
  const spec = config.tools[tool];
  if (method !== "POST" || !spec) return reply(404, { ok: false, error: "not found" });
  if (!state || !state.customer) return reply(200, { ok: false, error: E.unknown_customer });

  const next = { customer: state.customer, ledger: state.ledger };
  const L = next.ledger;
  const C = next.customer;
  const A = spec.args;
  const arg = (logical) => body[A[logical]];

  const answer = (status, json) => {
    L.calls.push({ n: L.calls.length + 1, tool, args: Object.fromEntries(Object.entries(body).filter(([k]) => k !== A.customer)), status, result: json });
    L.last_at = Date.now();
    return reply(status, json, next);
  };
  const fail = (error) => answer(200, { ok: false, error });

  if (L.closed) return fail(E.closed);

  // Faults for the tool-failure cases: the first N calls fail with 500 and record nothing.
  const fault = (C.faults || []).find((f) => f.tool === tool);
  if (fault && (L.failures[tool] || 0) < (fault.fail_first_n || 0)) {
    L.failures[tool] = (L.failures[tool] || 0) + 1;
    return answer(500, { ok: false, error: E.service });
  }

  for (const key of Object.keys(A)) {
    if (key === "text" || key === "reason" && tool === "close_call") continue; // optional
    if (key === "customer") continue;
    if (arg(key) === undefined || arg(key) === null || arg(key) === "") return fail(`${E.missing}: ${A[key]}`);
  }

  const fieldNames = Object.keys(config.identity.fields);
  const allVerified = () => fieldNames.every((f) => L.verified[f] === true);
  if (spec.requires_verified && !allVerified()) return fail(E.not_verified);
  const R = config.response_fields;
  const productOf = (id) => (C.products || []).find((x) => String(x[config.product_fields.id]) === String(id));

  switch (tool) {
    case "verify_identity": {
      const field = String(arg("field"));
      const rule = config.identity.fields[field];
      if (!rule) return fail(E.unknown_field);
      if (L.wrong >= config.wrong_limit) return fail(E.locked);
      const truth = String((C.identity || {})[field] ?? "");
      let given = String(arg("answer")).trim();
      let hint;
      if (rule.kind === "date") {
        const d = parseDate(given);
        if (!d) return fail(E.bad_date);
        given = d.text;
        const t = parseDate(truth);
        if (t && given !== t.text && d.y === t.y && d.mo === t.d && d.d === t.mo && t.mo !== t.d) hint = config.identity.swapped_hint;
      } else {
        given = given.replace(/[\s-]/g, "");
        if (!new RegExp(`^\\d{${rule.length || 4}}$`).test(given)) return fail(E.bad_digits);
      }
      const right = given === truth;
      if (right) L.verified[field] = true;
      else if (hint) L.hinted = true; // a swapped day and month is a retry, not a wrong answer
      else L.wrong += 1;
      const out = { ok: true, [R.verified]: right, [R.wrong_left]: config.wrong_limit - L.wrong, [R.all_verified]: allVerified() };
      if (!right && hint) out[R.hint] = hint;
      return answer(200, out);
    }
    case "get_account": {
      return answer(200, { ok: true, [R.products]: (C.products || []).map((x) => ({ ...x })) });
    }
    case "create_promise": {
      const product = productOf(arg("product"));
      if (!product) return fail(E.unknown_product);
      const amount = Number(arg("amount"));
      if (!(amount > 0) || !Number.isFinite(amount)) return fail(E.bad_amount);
      const date = parseDate(arg("date"));
      if (!date) return fail(E.bad_date);
      if (spec.one_per_product && L.promises.some((x) => String(x.product_id) === String(arg("product")))) return fail(E.duplicate_promise);
      const promise = { [R.promise_id]: "pr" + (L.promises.length + 1), product_id: product[config.product_fields.id], type: product.type, amount, date: date.text };
      L.promises.push(promise);
      return answer(200, { ok: true, [R.promise_id]: promise[R.promise_id] });
    }
    case "add_note": {
      const product = productOf(arg("product"));
      if (!product) return fail(E.unknown_product);
      if (!spec.reasons.includes(arg("reason"))) return fail(E.bad_value + ": " + A.reason);
      L.notes.push({ product_id: product[config.product_fields.id], reason: arg("reason"), text: String(arg("text") ?? "") });
      return answer(200, { ok: true });
    }
    case "schedule_callback": {
      const date = parseDate(arg("date"));
      if (!date) return fail(E.bad_date);
      const time = parseTime(arg("time"));
      if (!time) return fail(E.bad_time);
      L.callbacks.push({ date: date.text, time });
      return answer(200, { ok: true });
    }
    case "transfer_to_agent": {
      if (!spec.queues.includes(arg("queue"))) return fail(E.bad_value + ": " + A.queue);
      L.transfers.push({ queue: arg("queue") });
      return answer(200, { ok: true });
    }
    case "close_call": {
      const outcome = arg("outcome");
      if (!spec.outcomes.includes(outcome)) return fail(E.bad_value + ": " + A.outcome);
      const reason = arg("reason");
      const needed = !spec.reason_not_required_for.includes(outcome);
      if (needed && (reason === undefined || reason === null || reason === "")) return fail(E.reason_required);
      L.outcome = outcome;
      L.reason = needed ? String(reason) : null;
      const out = answer(200, { ok: true });
      L.closed = true;
      return out;
    }
  }
  return reply(404, { ok: false, error: "not found" });
}
