# T-053: api_call body as one `default` object (the call never started)

**Constraints and tests:** no commit, no env.sh, no Freya. `python3 -m unittest`: **724 OK** (3 new tests in `tests/test_t046_generic.py`, class `T053Tests`; the leak test passes, using the `dict(type=...)` form).

## Cause

In the live final workflow, **all 7 of 7** `api_call` tools had a body (and headers) written as `{"type": "object", "default": {...nested object...}}`. The kit reads only `body.properties.<field>.default`, so the pre_action never ran.

## Fix (`builder/generic.py`)

1. **`clean()` calls `_api_properties()`** on every `api_call` tool, whether it sits in `pre_actions`, in `tools`, or in the workflow's `tools`:
   - `body` and `headers` given as a `default` object become `{type: object, properties: {field: {type, default}}}`;
   - nested objects become nested `properties`;
   - the leaf type is `string` / `number` / `boolean` (and `array` for a list);
   - a leaf the model wrote under `properties` (with a description or enum) keeps those, plus the value as its `default`.
   - **Checked on `submission/final.workflow.json`:** all 7 tools were rewritten. `load_cards` now sends `call.ani`, `call.lang`, `data.aiFlow` and `data.customerNo={{customerNumber}}` as leaves.
2. **`validate()`:** an `api_call` tool whose `body` or `headers` is one `default` object is reported as "api_call body/headers must use properties …". This only fires when `clean()` did not run first, because `clean()` already fixes it.

## Tests

- default-object body and headers, in a pre_action and in a global node's tools, with nested objects and string, number and boolean leaves;
- a written leaf keeps its description;
- `validate` names both body and headers.
