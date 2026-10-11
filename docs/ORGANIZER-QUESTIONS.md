# Platform Questions for the Organizers

These questions come from our live chat tests and from two unresolved differences between the hackathon page and starter kit. We want to confirm the intended platform contract so the builder can produce workflows that behave consistently in organizer-run tests.

## 1. F-043 Default language when agent config is omitted

**Context.** The starter kit says to omit `agent_config`, so our workflow cannot set `sttConfig.language` or `ttsConfig.language`. Our calls and prompts were in English, but a slow transition through API and code steps caused a platform-generated wait message in Turkish.

**Observed.** On 10 October, Brief A PUB-01 version 10, customer `c_de6c4d55-76e`, the transcript inserted “Bir saniye lütfen.” between identity verification and the English account discussion; it appeared again in a version 13 slow turn on 11 October.

**Question.** When `agent_config` is omitted, how is the language of platform-generated filler selected, and will hidden-brief runs use an English default or another supported workflow-level language setting?

**Our assumption.** We should continue to omit `agent_config`, and platform-generated speech should follow the call or workflow language rather than a workspace default.

## 2. F-049 State and side effects after a 5xx response

**Context.** A chat turn can invoke external tools before the Freya request returns a 5xx. We need to know whether node and variable updates are transactional with the response, and how a client can safely determine whether to retry.

**Observed.** On 11 October, Brief A PUB-07 version 11 returned 502 after identity calls and `get_account` appeared in the bank ledger, but the next message resumed at the previous identity node with the old variables.

**Question.** Is this rollback-with-committed-tool-effects expected, and is there a supported idempotency key, durable turn status, or call-record field that tells a client whether the state transition committed?

**Our assumption.** After a 5xx, we must treat external tool side effects as possibly committed but conversation state as possibly rolled back, inspect the call state and ledger, and replay only idempotent workflow logic.

## 3. F-057 End-of-call hook after a branched resume

**Context.** Our `end_of_call` hook uses call variables to avoid a duplicate `close_call`. If a post-goodbye message resumes from a branch whose variable table predates the close, that guard is lost and the hook can send a second close.

**Observed.** On 11 October, Brief A PUB-02 and PUB-09 version 13 (`traces/live-runs/pub02v13.json` and `pub09v13.json`) each recorded a successful `close_call`, then a later message resumed from older state and the end-of-call hook attempted another `close_call`; the bank refused it as already closed.

**Question.** Can organizer simulations or judge customers send a message after the agent has ended the call, and should `end_of_call` hooks execute exactly once across `isBranch` resumes and state rollbacks?

**Our assumption.** Ending a call should be terminal for new customer input, and lifecycle hooks should have exactly-once semantics for that call even if a branch is resumed.

## 4. F-058 Global path exclusions on global-step resumes

**Context.** We use `excluded_nodes` to prevent a global path from matching while another global path is active. The published workflow included the expected exclusion, but a branched resume appeared to bypass it.

**Observed.** On 11 October, Brief A PUB-09 version 13 (`traces/live-runs/pub09v13.json`), a message resumed in the restructuring global step and matched the human-request global path even though that restructuring step was listed in the path's `excluded_nodes`.

**Question.** Does `excluded_nodes` apply when the current node is a global step and when the call resumes with `isBranch`, or are exclusions evaluated only for ordinary workflow nodes?

**Our assumption.** Exact node names in `excluded_nodes` should suppress a global path uniformly for ordinary nodes, global nodes, and resumed branches.

## 5. F-031 Chat behavior after end call

**Context.** The chat endpoint continued to accept messages after the workflow reached `end_call`. Those messages resumed at the last speaking node, so the closing chain ran again unless guarded by workflow state.

**Observed.** On 10 October, Brief A PUB-07 version 8, workflow `b0bdd6e6`, customer `c_27bca007-28e`, post-goodbye messages caused 17 ledger entries for `close_call`—one successful and 16 refused—and several turns returned 504.

**Question.** Is `end_call` intentionally deferred or non-terminal in `/api/v2/chat/message`, and what response or call field should a test driver use to know that it must stop sending messages?

**Our assumption.** Chat clients should stop after the agent ends the call, while the platform should reject later messages or expose an unambiguous terminal status.

## 6. Workflow limit per workspace TO-CONFIRM

**Context.** The hackathon page states a limit of 10 workflows per workspace, while the newer starter-kit README states 200. We update a stable workflow in place, but need the authoritative cap for recovery and test planning.

**Observed.** `docs/STARTER-KIT-FACTS.md` records this as an unresolved source conflict and gives the newer kit precedence without confirming the live workspace limit.

**Question.** What workflow limit will apply in competition workspaces, and do updates or published versions count toward that limit, or only distinct workflow IDs?

**Our assumption.** The current limit is 200 distinct workflows as stated by the newer kit, and updating an existing workflow does not consume another slot.

## 7. Final command shape for cumulative briefs TO-CONFIRM

**Context.** The official run contract is shown as `python3 builder/build.py {brief_path} {tool_api_path}`, one brief and one OpenAPI file per final run. The public Brief B builds on Brief A, however, and the sample builder accepts multiple brief files.

**Observed.** `docs/STARTER-KIT-FACTS.md` marks it `[TO-CONFIRM]` whether a Brief-B-style final input will be self-contained or supplied as cumulative documents such as `brief-a.md brief-b.md openapi.json`.

**Question.** For each final agent, will the exact run command always receive one self-contained brief plus one OpenAPI file, or may a cumulative brief require multiple brief paths before the OpenAPI path?

**Our assumption.** Each final run will receive one self-contained brief and its OpenAPI file; support for multiple briefs is useful for the public kit but is not required by the final invocation contract.
