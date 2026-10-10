# Submission check

For each final brief, submit these two files from the same normal builder run:

- `submission/<slot>.workflow.json`
- `traces/<slot>.log`

Also retain the generated spec in the repository as reproducibility evidence and for the offline check:

- `traces/<slot>.spec.json`

Run the builder with the official contract; self-tests are enabled by default:

```text
python3 builder/build.py <brief_path> <tool_api_path>
```

Before committing or filling the submission form, run the offline compliance check in a shell where the keys are loaded (`source env.sh`), so the check can also look for the exact key values:

```text
python3 tools/submission_check.py \
  traces/<slot>.log \
  submission/<slot>.workflow.json \
  --spec traces/<slot>.spec.json \
  --verify-inputs --require-env
```

Every item and the final summary must print `PASS`. A `WARN` keeps the item passing but must be read: a self-test case that did not pass, or a key value scan that was skipped because an env variable is unset (`--require-env` turns that into `FAIL`). `--verify-inputs` re-hashes the brief and tool files named in the trace and compares them.

The check validates required trace evidence, the 30-minute limit, secret absence, the sent definition (`sent_agent_config: absent`, `sent_nulls: 0` in the trace), export structure, workflow ID and step-count agreement, and the extracted-spec artifact. It does not contact Freya. The exported file itself carries a platform-filled `agent_config` and `null` defaults; that is expected and not checked.

The submission form also needs `team`, `repo`, `commit`, the exact `run_command`, and the workflow/trace path for each final brief. Do not edit an exported agent after the traced run.
