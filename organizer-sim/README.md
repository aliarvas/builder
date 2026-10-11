# Organizer Simulation: Two Unseen Briefs

These inputs imitate the final format described in starter-kit v3. They are
synthetic rehearsal material written locally; they are not official Freya
briefs and are not connected to the organizer's bank ledger.

## Package 1: clean specification

```bash
python3 builder/build.py \
  organizer-sim/hidden-01-clean/brief.md \
  organizer-sim/hidden-01-clean/openapi.json
```

## Package 2: raw bank material

Pass every source document, in the order below, followed by the OpenAPI file:

```bash
python3 builder/build.py \
  organizer-sim/hidden-02-raw/01-email-thread.md \
  organizer-sim/hidden-02-raw/02-policy-extract.md \
  organizer-sim/hidden-02-raw/03-outcome-codes.csv \
  organizer-sim/hidden-02-raw/04-calendar.txt \
  organizer-sim/hidden-02-raw/05-override-memo.md \
  organizer-sim/hidden-02-raw/openapi.json
```

For an offline render that does not save, publish, chat with, or simulate a
Freya workflow, add `--print`. Spec extraction still uses the configured
builder model:

```bash
python3 builder/build.py --print --slot rehearsal-clean \
  organizer-sim/hidden-01-clean/brief.md \
  organizer-sim/hidden-01-clean/openapi.json > /tmp/rehearsal-clean.workflow.json
```

The OpenAPI servers deliberately use the reserved `.invalid` domain. The
workflow can be built and inspected, but its tools cannot create real bank
records. Do not use these packages for a live Freya case run. Their purpose is
to test whether the builder extracts unfamiliar rules, tool fields, enums,
calendars, precedence and multi-product behavior without hardcoding.

No reference spec, expected workflow or case answer key is included. After a
run, inspect the generated trace spec and workflow as if this were a final
submission.
