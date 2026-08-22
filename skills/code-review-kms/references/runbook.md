# Code-Review-KMS Driver — Reusable Runbook

> ## Quick path — read this first, then stop
>
> **You do not need to read this file.** It is the driver's source of truth, and it is long because it carries every
> gotcha and server bug found on real runs. The skill (`../SKILL.md`) reads it for you. Run `/code-review-kms <PR>` and
> follow the prompts. Step-by-step walkthrough for a first run: `HOW-TO-USE.md` → *AI code review on a PR*.
>
> **Read this file yourself only when** a run behaves unexpectedly, you are changing the procedure, or you want to know
> *why* a gate exists before approving it.
>
> **The shape in six lines:**
> 1. Resolve the checkout mode — plain repo folder (`main`) or `git worktree` (`worktree`). See `./checkout-modes.md`.
> 2. Start the review; upload the diff; hand the server the checkout path.
> 3. Findings are produced **locally**, by parallel reviewer subagents — one per review lens.
> 4. **GATE 1** — you decide which findings are real and in scope. Nothing has reached the server yet.
> 5. **GATE 2** — you approve each local fix. Loop back to 3 and re-derive findings against the fixed code.
> 6. **GATE 3** — you push, then the server is written to **exactly once**.
>
> The one thing worth internalising: **the loop is local, the server sees only the result.** Everything between step 3
> and the push is on your disk and reversible. That is why the gates are where they are.
>
> **Two hard rules that never bend:** the driver never commits or pushes for you (`.claude/rules/git-safety.md` G11),
> and it never prints the value of `MANAGER_HUB_TEAM_TOKEN` (`.claude/rules/secrets-safety.md`).

**Version:** v1.3 · **stamped:** 2026-08-11 · (originally maintained outside git; the lineage below is reconstructed
from dated notes in this file, not from commits).

| Evidence generation | Run it came from | What it established |
|---|---|---|
| 2026-07-01 | earlier local run (code-lessons 0.4.0 / code-review 0.3.3) | dev-rules gate auto-skip — **superseded, do not follow** |
| 2026-07-30 | PR #371 · GEN-3357 | the bulk of this doc: pre-submit withhold gate, gotchas 1–4, server gaps 1–6, dev-rules gate now live (14 rules) |
| 2026-08-05 | PR #152-era vars refresh · live GEN-3443 run | version stamp; discrepancies below observed against a running execution |
| 2026-08-06 | procedure edit (no run) | STEP 4 executes the Code Review node as an in-thread `Agent` fan-out instead of `claude -p`; the block becomes a prompt carrier, the driving thread becomes the coordinator |
| 2026-08-11 | local loop half-run · rubric decoded from the server's scoring panel | **LOCAL CONVERGENCE LOOP** (STEP 4.6): findings are re-derived locally after each fix and the server is written to exactly once, after the push. Rubric-computed score (never judged). `local-fix-ledger.md` feed-forward. Gates renumbered 1 / 2 / 3. Observed N = 6 specialist lenses (was 5 on PR #371) — count it, never assume. |
| 2026-08-11 | PR #422 · GEN-3426 round 1 · full run to COMPLETED | **v1.3.** The rubric section was wrong and is replaced by the server's own `rubricVersion 1` contract: `critical −2.5`, and **every `STILL_OPEN` entry is charged as carried debt at ½ weight** (the "only new findings are scored" hypothesis is DISPROVEN). Adds the **zero-iteration round** (GATE 1/2/3 collapse), corrects the empty-findings-array rule (`distill_lessons` receives carried findings, so a 0-new-finding round does NOT starve the corpus), records the carried-½-vs-fresh-full weighting that governs the "open a clean PR?" decision, adds server gaps #7–#8 (including a **live bug that stamps `STILL_OPEN` entries `RESOLVED`**), and adds a STEP 1 **base-branch precondition** — the round's 11 out-of-diff findings were traced by the PR author to the PR having been opened against the **wrong base**, not to any server or scoring defect (first misdiagnosed here as a server gap; corrected same day) |
| 2026-08-11 | review of the above (no run) | v1.2 corrections: exit criterion scoped to **`fix now`** high/criticals (follow-up-routed ones are deferred by design and would otherwise make it unsatisfiable — the shape two PR #371 highs actually had); GATE 3 **re-uploads the diff** (STEP 3's upload predates the loop's fixes); mid-loop execution-death recovery; empty-submission case named; `withheld-findings.md` nested per iteration |

**Known discrepancies in this revision** — verified against a live execution on 2026-08-05, not yet reconciled:
1. **STEP 2's stated premise is stale.** It cites a "5-min sweeper"; the server's heartbeat reply returns
   `timeoutMs: 1800000` (**30 min**), so the 45s interval is far more frequent than required. The heartbeat itself is
   still warranted (nodes can outrun 30 min) — only its justification and interval are off. STEP 2 also has no teardown
   step tied to node completion, so the `while true` loop only ever stops via an explicit `TaskStop`.
2. ~~**Specialist count contradicts itself.**~~ **Resolved by v1.1** — the count is no longer something this doc asserts.
   STEP 4 now reads the specialist prompts out of the returned block and dispatches one subagent per lens, so N is
   whatever the block actually carries and you count it first-hand. Observed **5** (PR #371, 2026-07-30) and **6**
   (2026-08-11) — it genuinely varies, so record the observed N in the gate block rather than trusting any number
   written here.

**Bumping this:** a run that changes procedure appends a lineage row and bumps the minor (v1.1, v1.2…); a run that only
resolves a discrepancy strikes it from the list above and re-stamps the date. Bump the major only if the driving
procedure's step order changes.

---

Drive the manager-hub code-review-kms MCP workflow on any PR, end-to-end, stopping at its **three** human gates:
**GATE 1 — pre-submit withhold** (which findings are real, in scope, and how they route), **GATE 2 — local fix**
(what gets changed locally, once per loop iteration), and **GATE 3 — push** (the single point where the server is
written to). Works for a **first review** and a **re-review** (after fixing a prior round).

**The shape in one line: the loop is local, the server sees the result.** Findings are produced on your disk and become
server state only at `mh_submit_result`, so the fix-and-re-review cycle runs entirely locally — fix, recompute the
working-tree diff, re-dispatch the lenses, re-gate — and the server is written to exactly **once**, on the state you
actually push. See **LOCAL CONVERGENCE LOOP** (STEP 4.6).

## How to use

1. Fill in the **VARIABLES** block below for your PR.
2. Either paste this whole file into a fresh session, **or** say:
   *"Run the code-review-kms runbook for PR `<PR_ID>`, workflow `<WORKFLOW_ID>`, checkout `<CHECKOUT>`, branch `<BRANCH>`, base `<BASE_REF>`"* — and I'll read this file.
3. Find the PR's manager-hub CUID with `mh_list_open_prs` (optionally `repoFullName: "FireHawk/FCRM-Web"`); it's the `prId` — NOT the GitHub PR number.

---

## VARIABLES — fill these in

```
PR_ID:        <manager-hub PullRequest CUID>     # e.g. cmqhkubnk1xc0o7omhms0eojq  (from mh_list_open_prs → prId)
PR_LABEL:     <owner/repo #number>               # e.g. FireHawk/FCRM-Web #152      (display only)
WORKFLOW_ID:  <workflow CUID>                     # e.g. cmpayfzt901zbo79shreoy3zy
CHECKOUT:      <path to the checkout>             # the repo folder holding the PR branch. Either a plain
                                                  #   checkout (e.g. ./FCRM-Web) or a worktree
                                                  #   (e.g. .worktrees/gen-2993/FCRM-Web). See CHECKOUT_MODE.
CHECKOUT_MODE: main | worktree                    # resolved by the detection ladder in
                                                  #   ./checkout-modes.md — NEVER assumed. It changes the
                                                  #   STEP 0 preconditions and flips server gap #6.
BRANCH:       <PR head branch>                    # e.g. feat/gen-2993-estimate-template-tab
BASE_REF:     <PR base branch>                    # develop | main
```

## CONSTANTS — rarely change

```
MANAGER_HUB_BASE: http://192.168.59.33:3001
TOKEN_ENV_VAR:    MANAGER_HUB_TEAM_TOKEN          # reference by NAME only; NEVER print the value
```

---

## DRIVING PROCEDURE (the prompt)

> Drive the code-review-kms MCP workflow on PR `{{PR_ID}}` (`{{PR_LABEL}}`) using workflow ID `{{WORKFLOW_ID}}`.
> Drive it end-to-end and STOP at ALL THREE gates: **GATE 1** at STEP 4.5 (pre-submit — validity, scope, routing),
> **GATE 2** at STEP 4.6 (local fix — what gets changed this iteration), and **GATE 3** at STEP 4.7 (push — the one
> outward write). Read ALL notes before starting — this is a long-running, email-sending workflow. baseRef is
> `{{BASE_REF}}`.
>
> **Do not call `mh_submit_result` on the code_review node until the loop has converged and I have pushed.** Everything
> between STEP 4 and STEP 4.7 is local. That is the whole design — see STEP 4.6.
>
> ENV: `MANAGER_HUB_TEAM_TOKEN` is in the shell env (reference by name, NEVER print it). Manager-hub base:
> `http://192.168.59.33:3001`.
>
> **STEP 0 — RESOLVE THE CHECKOUT MODE (do this before any other precondition).**
> Run the detection ladder in `./checkout-modes.md` to set `CHECKOUT_MODE` to `worktree` or `main`. Do NOT assume —
> the mode changes the preconditions immediately below, and it **flips** server gap #6 (the indexed impact reading is trustworthy
> in one mode and contaminated in the other). If the ladder is ambiguous, STOP and ask; do not guess.
>
> **In `main` mode, add these two preconditions** — a plain checkout has no pristine reference copy to fall back on, so
> the safeties the worktree model gives you for free must be checked explicitly:
> - **Right branch.** `git -C {{CHECKOUT}} rev-parse --abbrev-ref HEAD` must equal `{{BRANCH}}`. In worktree mode a wrong
>   branch is merely the wrong worktree; here it means you are about to review — and later fix — the wrong code in the
>   folder the user actually works in.
> - **Tree clean enough to attribute.** `git -C {{CHECKOUT}} status --porcelain`. Pre-existing uncommitted edits are
>   allowed (local-dev dirt is normal), but **list them for me now**, before the loop starts. Once STEP 4.6 begins
>   applying fixes you can no longer tell your edits from the ones that were already there, and GATE 3's explicit-path
>   `git add` depends on that distinction.
>
> **STEP 0.1 — PRECONDITION (the review diff is HEAD-based, not working-tree):**
> The reviewer sees `git diff --merge-base origin/{{BASE_REF}} HEAD` — i.e. COMMITTED state, not unstaged edits.
> - **Re-review:** the prior round's fixes must already be COMMITTED and PUSHED to `origin/{{BRANCH}}` so the PR
>   head SHA reflects them. Run `git -C {{CHECKOUT}} log --oneline -3` and `git -C {{CHECKOUT}} status`. If the
>   fixes are not committed/pushed (or the branch is "ahead of origin"), STOP and tell me to push first — do NOT
>   push/commit for me, and never stage local-dev dirt (`.env*`, `environment*.ts`, `server/package.json`) or the
>   review artifacts (`code-review-*`, `*-prompt.txt`, `local-diff.patch`, `manager-hub-open-comments.json`,
>   `review-artifacts/**` — which now includes `ticket-intent.md`, `withheld-findings.md`, and `local-fix-ledger.md`).
>   Also confirm any
>   previously-rejected findings were posted on RepoWatch (so they return WONT_FIX, not re-raised) — and **read BOTH
>   `./review-artifacts/withheld-findings.md` and `./review-artifacts/local-fix-ledger.md` if they exist**, so this round
>   does not re-derive from scratch what a prior round already investigated or already fixed. Both are **facts, never
>   verdicts** — see the FEED-FORWARD ARTIFACTS section for the phrasing rule and why it is load-bearing. Treat the
>   withheld file as **prior evidence, not a settled verdict**: a finding withheld last round on
>   code this round has since changed must be re-judged, and a prior `INVALID` whose evidence cell no longer holds against
>   current code becomes VALID again. A prior `intent-satisfied` is re-judged the same way — if the criterion it quoted has
>   since changed in the ticket, the withhold lapses. Never carry a withhold forward on its label alone. Read the file's
>   **follow-up table** as well: those findings are still OPEN on the server by design, so they are expected to reappear.
> - **First review:** skip to STEP 1.
> - **Re-opened-as-a-fresh-PR (a first review with history):** when a prior PR was closed and re-opened to clear a board
>   polluted by a wrong base (see that section below), the new PR has a **new `PR_ID`** and an **empty open-comments
>   list** — so there is no
>   `openCommentsResolvedJson` to build and no carried debt. The checkout's artifacts do NOT reset: `review-artifacts/`
>   still holds `withheld-findings.md`, `local-fix-ledger.md`, and `ticket-intent.md` from the closed PR's rounds. **Read
>   them** — they are the same facts about the same code — but expect every in-diff defect the old board carried to be
>   re-raised as a **new** finding at full weight, and do not describe the round as a re-review of the old PR. Record the
>   old `PR_ID` in the new round's `withheld-findings.md` heading so the two histories stay linked.
>
> **STEP 1 —** `mh_start_review({prId, workflowId})` → capture the NEW `executionId` + reported `headSha` + reported
> `baseRef`.
> - Verify `git -C {{CHECKOUT}} rev-parse HEAD` == `headSha`. The checkout may carry known local-dev dirt; a clean
>   HEAD match is the load-bearing precondition — proceed on that.
> - **Verify the base, and verify what it implies.** The server's reported `baseRef` overrides `BASE_REF` above (a
>   default of `develop` was reported as `main` on PR #422). Then run
>   `git -C {{CHECKOUT}} diff --merge-base origin/<reported baseRef> HEAD --stat` and check the file list contains **only
>   this ticket's files**. If another ticket's files appear, STOP and surface it — the PR base is wrong, and reviewing
>   anyway posts findings the PR can never resolve. See "NOT a server gap — a wrong PR base permanently pollutes the
>   board".
>
> **STEP 2 — HEARTBEAT (turn latency exceeds the 5-min sweeper).** Immediately launch a PERSISTENT BACKGROUND
> curl loop (Bash `run_in_background`), every 45s, until the workflow ends (then `TaskStop` it):
> ```
> POST http://192.168.59.33:3001/api/public/code-review-mcp/heartbeat
>   -H "Authorization: Bearer $MANAGER_HUB_TEAM_TOKEN" -H "Content-Type: application/json"
>   --data '{"executionId":"<NEW executionId>"}'
> ```
>
> **STEP 3 — DIFF.** In the checkout: `git fetch origin {{BASE_REF}}`;
> `git diff --merge-base origin/{{BASE_REF}} HEAD > local-diff.patch`; then upload:
> ```
> POST .../api/public/code-review-mcp/diff-upload?executionId=<NEW executionId>
>   (Bearer auth, Content-Type text/plain, --data-binary @local-diff.patch)
> ```
>
> **STEP 3.5 — WRITE THE CONTEXT BRIEF (before checkout, because the next call returns the prompt).** The reviewers cannot
> see why the change was made — the `pr` object carries no `body`. Write `./review-artifacts/ticket-intent.md` from the
> ticket folder `tickets/{KEY}/` **now**: `mh_report_checkout` is what makes the server assemble and hand back the review prompt,
> and the file must already exist on disk before the path you name inside that prompt gets read. Also split
> `local-diff.patch` into the `./review-artifacts/artifact-N.patch` paths the specialist prompts expect (server gap #2).
> Content rules: **CONTEXT BRIEF** section below. Skip only if there is no ticket folder — and say so in
> the report rather than silently omitting it.
>
> **STEP 3.6 — CHECKOUT.** `mh_report_checkout({executionId, localPath:<absolute {{CHECKOUT}} path>, headSha})`
> (omit `localDiff` — uploaded already).
>
> **STEP 4 — DRIVE NODES** in the order the server returns them (typical: send_email → Code Review →
> send_email → Distill Lessons → End). Each node returns a verbatim bash block running `claude -p ... > <outputFile>`.
>
> **On the Code Review node, treat that block as a PROMPT CARRIER, not a command to run.** Do **not** shell out to
> `claude -p`. Lift the prompts out of it and run the review as an **`Agent`-tool fan-out in this thread** — you become
> the coordinator the subprocess used to be. Everything server-side is unchanged: the node still came from
> `mh_poll_next_action`, and its result still goes back through `mh_submit_result` in the same schema.
>
> 1. **Parse the block; run nothing.** Extract, verbatim: the **Team Context**, the **Repo + PR Context**, each
>    **specialist lens prompt**, the **output contract** (finding schema + severity enum), and the **dedup / merge
>    rules**. Count the specialists the block actually defines — that is N (observed 5 on PR #371, **6** on 2026-08-11;
>    it changes, so count it every run and record the number in the gate block). Never paraphrase a lens or a
>    contract; the server's wording is what the submitted findings are graded against.
> 2. **Inject the brief into Team Context** — the one line naming `./review-artifacts/ticket-intent.md` (exact text in
>    the CONTEXT BRIEF section), nothing else. Since you now assemble each specialist prompt yourself, **prepend the
>    Team Context to every dispatch prompt directly** rather than relying on the coordinator prompt's promise to
>    propagate it.
> 3. **Dispatch N subagents in ONE message so they run in parallel.** Default `subagent_type: code-review-depth` — it is
>    read-only *by tool whitelist* and it carries `mcp__code-lesson__get_development_rules`, which closes server
>    gap #3 (the returned block ships no `--allowedTools`, so the old `claude -p` specialists were dev-rules-blind). Use
>    `code-review-breadth` for any lens needing cross-repo reach (RepoSphere). Per `agents-safety.md` A7 each dispatch
>    prompt is **self-contained**: the lens text verbatim + Team Context + Repo/PR context + the **absolute** checkout
>    path + the diff path(s) + `./review-artifacts/ticket-intent.md` + the output contract + "return your findings as a
>    fenced JSON array as the LAST block of your reply" (A4). Name the tools explicitly per the Subagent Protocol —
>    subagents do not inherit tool preferences.
> 4. **You merge.** Apply the block's dedup rules across the N packets yourself, keep every field the output contract
>    demands, and assemble one `codeReviewJson` in the server's schema. Write it to `./review-artifacts/code-review-result.json`
>    as evidence **before** the gate, and keep each raw packet alongside it. A4 applies: a specialist returning prose
>    with no JSON block is a **dispatch failure** — re-dispatch it with the contract restated; do not parse the prose.
>    A3 applies: their findings are hypotheses, and PASS A at STEP 4.5 is where you open the code for every one of them.
> 5. **Other nodes are single-prompt and fast** — keep running their blocks as returned, in the foreground. Those blocks
>    exit non-zero from their heartbeat-subshell `kill`/`wait` even when `claude` succeeded; check the `claude_exit=0`
>    marker / the output file, not the script exit code.
>
> **Why this shape.** Control is the point: the fan-out is visible per-agent, one lens can be re-dispatched without
> re-running the other four, tool access is enforced by whitelist instead of by a flag the server never sends, and the
> findings arrive as structured returns you already hold. It also removes three failure modes wholesale — the
> Write-blocked JSON salvage (gotcha 1), the `claude -p` connection flakiness that cost 3 retries on PR #371 (gap #5),
> and the 10-min foreground cap that forced backgrounding-and-polling.
>
> **What it does NOT remove.** The heartbeat still runs (STEP 2) — the server is still in `AWAIT_RESULT` and the fan-out
> plus the gate can outlast its window. The specialists still need the `artifact-N.patch` split from STEP 3.5 if you pass
> those paths (gap #2); simpler now, since you may hand each subagent the diff path directly. And the pre-submit withhold
> gate is unchanged and still mandatory — running the lenses yourself does not make their findings verified.
>
> **STEP 4.5 — GATE 1 · PRE-SUBMIT WITHHOLD GATE (after the Code Review node finishes; nothing is submitted yet).**
> Findings are produced **locally** by the fan-out and only become server state when you submit them. **Open the real
> code for every single finding — the ones you expect to submit as much as the ones you expect to drop — and classify
> each on what you read there**, then withhold the invalid + out-of-scope ones so they never reach the server. A finding
> you have not read code for is not classified, whichever bucket you were going to put it in. Three ordered passes, never
> collapsed: **PASS A — validity** (first-hand, every finding), **PASS B — scope** (mechanical, VALID only), **PASS C —
> ticket intent + minimum blast radius** (VALID + in-scope only; routes fix-now vs follow-up, and withholds only a
> finding whose alleged defect *is* the acceptance criterion). Full procedure: **PRE-SUBMIT WITHHOLD GATE** section
> below. This gate is a STOP.
>
> **STEP 4.6 — LOCAL CONVERGENCE LOOP (GATE 2 per iteration).** Do **not** submit yet. Fix the surviving findings
> locally, recompute the working-tree diff, re-dispatch the lenses against it, and re-run GATE 1 — iterating until the
> exit criterion holds. Full procedure: **LOCAL CONVERGENCE LOOP** section below.
>
> **STEP 4.7 — GATE 3 · PUSH, THEN SUBMIT ONCE.** Present the commit; I commit and push. Only after the push do you
> `mh_submit_result` the code_review node — once, on the pushed state — and continue with the remaining nodes.

### CRITICAL GOTCHAS

1. **(Applies only to the nodes still run as `claude -p` — since v1.1 that is send_email and distill_lessons, not
   code_review, whose JSON you now assemble yourself at STEP 4.)**
   `claude -p`'s Write tool is **sometimes** blocked — do not assume either way. When blocked, `<outputFile>` is the
   coordinator's MARKDOWN with the real JSON in an inline ` ```json ` salvage block at the END; extract **LINE-BASED**
   (last ` ```json…``` ` fence → last closing fence) — a regex breaks because `suggestion` fields contain ` ``` ` fences.
   **Always try a direct `jq`/`json.load` parse FIRST and fall back to fence extraction.** On PR #371 the code_review
   node's Write succeeded and the file was clean JSON, while `distill-lessons-result.json` in the same run *was*
   fence-wrapped — so both paths occur within a single execution.
2. `manager-hub-open-comments.json` resolutions **DON'T persist** (Write blocked). The server only learns prior findings
   are resolved if you pass a corrected `openCommentsResolvedJson` on the code_review submit — **build it yourself** by
   verifying each prior OPEN finding against the CURRENT code: `RESOLVED`+`CODE_FIX` where the bad pattern is gone;
   leave `WONT_FIX` entries untouched. (Strict enums: `resolution` ∈ {RESOLVED, STILL_OPEN}; `resolutionReason` ∈
   {CODE_FIX, LINE_NOT_IN_DIFF, NO_LONGER_FLAGGED, null}; `evidence` ≤200 chars, required.)
3. Reviewer finding line numbers are **DIFF-GLOBAL offsets**, not file lines (often beyond file length). VERIFY and
   re-locate every finding against the real code before classifying/fixing.
4. `mh_submit_result` sometimes aborts client-side on the FINAL node ("operation was aborted") but usually **landed** —
   confirm with `mh_review_status` (`workflowExecutionStatus: COMPLETED`). Do **NOT** blindly re-submit.

### SUBMIT payloads

- `send_email` → `{nodeType:"send_email", resultJson:<parsed>}`  (reviewId = the node's `jobId`)
- `code_review` → `{codeReviewJson:<**withheld-filtered** extracted>, openCommentsResolvedJson:<your resolved array>}`  (reviewId = the run's `reviewId`)
- `distill_lessons` → `{nodeType:"distill_lessons", resultJson:<parsed array>}`  (reviewId = the node's `jobId`)

`codeReviewJson` is the **post-gate** object, not the raw one `claude -p` wrote — see the PRE-SUBMIT WITHHOLD GATE.
Keep the raw file untouched on disk as evidence; filter a copy.

### PRE-SUBMIT WITHHOLD GATE (run between the Code Review node and `mh_submit_result`)

**The discovery this section exists for:** findings from the Code Review node are produced **locally** — `claude -p` writes
them to `<outputFile>` on your disk — and become server state only when `mh_submit_result` uploads them. So an invalid or
out-of-scope finding does **not** have to be posted and then dismissed. It can simply never be submitted.

For a finding you have **established** is invalid or out-of-scope, that is cleaner than the reject-after-the-fact loop
(`/fix-review-findings` Step 3, `reject_comments`):

| | Withhold before submit | Post then `reject_comments` |
|---|---|---|
| Server state | never created | created, then marked `WONT_FIX` |
| Outward-facing write | none | two (post + dismissal) |
| RepoWatch noise for reviewers | none | a finding + a rejection to read |
| `distill_lessons` input | clean | polluted by a false positive that then needs suppressing |
| Reversible as a *record* | yes — it's a local file | no — dismissal is durable shared state |
| Recoverable if the call was **wrong** | **no — the finding is gone, with no server trace** | yes — the finding is on the board and a human can re-open it |

**Read the last two rows together — they pull in opposite directions, and that is the whole design.** Withholding is
reversible for you (a local file you can edit) but *invisible* to everyone else: nothing on the server, nothing in the
email, nothing in `distill_lessons`, nothing for a later reviewer to notice you got wrong. A `WONT_FIX` at least leaves a
dismissal a human can argue with. So the cheapness of withholding is exactly what makes a wrong withhold expensive — the
error class it creates is *silent*.

That is why this gate is a STOP, and why **validity is judged first-hand before scope, with the heaviest burden of proof
on withholding** (step 4 below). Recall beats precision here: submitting a questionable finding costs one reviewer read;
withholding a real one deletes it. When the two conflict, submit.

**But "when in doubt, submit" is the tie-break, not the workload.** Every finding — submitted or withheld — is read
against real code before it is classified; what the recall bias decides is only which way an *unresolved* read falls. A
gate that submits everything without opening anything satisfies the tie-break and defeats the gate: it emits the same
summary line as a fully verified pass while passing the reviewer exactly the noise this step was built to remove.

**This does not replace `reject_comments`.** That tool is still the only way to dismiss findings **already on the server**
from a *previous* round — re-raised prior findings, or anything a human posted. Withholding governs findings from *this*
run, pre-submit. Both can be in play on a re-review.

#### Procedure

> **The ordering rule that governs the whole gate: validity is judged FIRST, by this main thread, first-hand — and it is
> judged before scope, which is judged before intent.** The three passes (4, 5 and 6) are ordered and must not be collapsed
> into one classification. A finding is not "invalid" because it looks wrong, because the reviewer is often noisy, or
> because withholding it is convenient; it is invalid only when *you* have read the code and can state what refutes it. The
> order matters because each later test is cheaper and more tempting than the one before it: running scope first invites
> labelling a finding out-of-scope and never checking whether it was telling you something true about code you did in fact
> touch, and running intent first invites dismissing a real defect as "not what this ticket is about" — the single easiest
> way to lose a genuine finding. **A pass may only ever narrow the set the pass before it produced; it may never rescue a
> finding an earlier pass withheld, and it may never be used to reach a verdict an earlier pass declined to reach.**
>
> **PASS C is deliberately the weakest of the three.** It exists to answer *how* a surviving finding should be acted on —
> fix inside this PR, or record and fix in a follow-up — because a valid in-scope finding whose minimum fix ripples across
> repos is not automatically this PR's work. It is **not** a third opportunity to make findings disappear: its only
> withhold bucket requires the finding's asserted defect to *be* the acceptance criterion, quoted. See PASS C's forbidden
> reasons; PR #371 is the standing evidence that intent used as a filter silently kills findings worth fixing.
>
> **The completeness rule that makes the ordering rule mean anything: PASS A visits EVERY raw finding and opens real code
> for EVERY one of them — including the ones you are confident are valid.** `VALID` is a *finding*, not a default you fall
> back to when you skipped the work. The distinction is invisible in the output unless you enforce it here: a gate that
> read nothing and submitted all nine findings prints the same "9 SUBMIT · 0 WITHHOLD" line as a gate that read all nine
> and confirmed them. So the deliverable of PASS A is not the bucket — it is the **citation** attached to each finding, and
> a finding with no citation has not been through the gate regardless of where it ended up.
>
> Read the burden-of-proof rule below as *asymmetric in what it takes to be satisfied, not in whether it applies*: every
> finding needs a first-hand read, and what differs is only the strength of what that read must establish. Confirming a
> defect can rest on seeing the flawed line in context; refuting one demands an invariant that makes the defect impossible.
> Uncertainty resolves to VALID **after** you have looked and remain uncertain — never in place of looking. "I defaulted it
> to VALID so I didn't need to check" inverts the rule: it uses recall-over-precision, which exists to protect real
> findings, as a licence to submit unverified ones, and it hands the reviewer noise the gate was built to filter.

1. **Parse the raw findings** out of `<outputFile>` (per gotcha #1 — direct `jq` first, fence-extraction fallback).
   Preserve that file byte-for-byte; do all filtering on a copy.
2. **Re-locate every finding against real code.** Reviewer line numbers are diff-global offsets (gotcha #3), so a
   finding's `line` is not a file line. Never classify on the raw number.
3. **Run the DEVELOPMENT RULES GATE below** — its output is an *input* to the validity pass (step 4), not a shortcut past
   it. A returned rule the change complies with can refute a finding, but only via the same evidence bar as any other
   refutation: name the rule and show the compliance in the real code.
4. **PASS A — VALIDITY (first-hand, main thread, EVERY finding).** Work the raw list in order and do not skip entries.
   For each finding, open the real code at the re-located position (step 2) and establish whether the defect is real.
   This is the pass the whole gate rests on:

   - **Every finding gets opened. No exceptions, no sampling, no "obviously valid" shortcut.** The unit of work is
     `raw_findings_count` reads, and the gate block reports that count so a skipped finding is visible rather than
     inferred. If the volume makes that infeasible, say so at the gate and stop — a partial pass presented as a complete
     one is the one outcome worse than a slow gate.
   - **Do it in this thread.** Do not delegate the validity call to a subagent, and do not fan out. A subagent's
     "not a real issue" is a hypothesis (`.claude/rules/agents-safety.md` A3) — accepting it *is* the failure mode this
     gate exists to prevent. Reading code to answer a bounded question is cheap; being wrong here is not.
   - **Read the surrounding code, not just the cited line.** A finding about a null path needs the guard sites, the
     callers, and the type; reposphere `get_symbol` / `graph_query` (callers) on the symbol where reachability is the question.
   - **VALID needs positive evidence too.** To mark a finding `VALID` you must be able to write one sentence, from code
     you opened, saying what makes the defect real — *"`x.ts:142` dereferences `cfg.channels` and the only caller at
     `y.ts:88` passes the config through unset when the team has no override"*. Reciting the reviewer's own claim back is
     not evidence; neither is "the reviewer flagged it and I could not rule it out **without looking**". A `VALID` whose
     sentence merely paraphrases the finding title marks a finding you did not verify — fix that by reading, not by
     rewording.
   - **The two bars differ in strength, not in whether they exist.** VALID: you saw the flaw in its real context and can
     point at it. INVALID: you can cite a concrete `file:line` or invariant that makes the defect **impossible** — *"the
     guard at `b.ts:81` returns early, so the dereference at `:88` is unreachable"*. Refuting is strictly harder than
     confirming; that asymmetry is the whole point, and it is not a licence to skip the confirming read.
   - **Absence of evidence is never a refutation.** "I could not reproduce the concern", "seems fine", "unlikely in
     practice", "the reviewer probably misread it", and "no test covers this so probably not real" do not move a finding
     to INVALID — they classify as VALID **once you have read the code and still cannot refute it**, and as *unfinished*
     if you have not.
   - **Uncertain-after-reading → VALID.** Recall over precision: submitting a questionable finding costs a reviewer one
     read and stays reversible; withholding a real one deletes it with no server trace, and nothing downstream will ever
     surface it again. Record it as `VALID (uncertain)` with what you read and what remains unresolved, so the reviewer
     inherits your uncertainty instead of a false confirmation.
   - **Ambiguity in the finding's own wording → VALID.** If it is unclear *what* the reviewer meant, you have not refuted
     anything — you have failed to understand it. Submit it and say the wording was ambiguous.

5. **PASS B — SCOPE (mechanical, and only on findings PASS A marked VALID).** An INVALID finding never reaches this pass;
   scope is irrelevant to something that isn't a defect. Compute the change set deterministically, exactly as
   `/fix-review-findings` Step 2 does:
   ```
   git -C {{CHECKOUT}} diff --merge-base origin/{{BASE_REF}} HEAD --unified=0
   ```
   Parse it into `file → [added line ranges]` from the `+++ b/<file>` and `@@ -a,b +c,d @@` headers. Use a
   **TOLERANCE of 3 lines** around each added range — reviewers routinely anchor a finding one or two lines above the
   changed line. Do not widen it silently. Then:

   | PASS A | PASS B — scope test | Bucket | Disposition |
   |---|---|---|---|
   | VALID | `file:line` inside an added range ± TOLERANCE | **VALID + in scope** | → PASS C |
   | VALID | No usable `file`/`line` — repo-wide or architectural | **VALID + in scope** | → PASS C — a human-shaped finding is not out-of-scope for lacking coordinates |
   | VALID | Just outside the window, but about code this branch touched | **VALID + in scope** | → PASS C, and say why in the gate block |
   | VALID | File absent from the change set, or line clearly predates this branch | **VALID but out-of-scope** | **WITHHOLD** → recommend a follow-up ticket |
   | INVALID | — (not evaluated) | **INVALID / false positive** | **WITHHOLD** — requires the PASS A refutation sentence |

   Out-of-scope is the safest of the three withholds: the defect is recorded as real in `withheld-findings.md` with a
   follow-up, so the information survives. `intent-satisfied` (PASS C) also records the defect as real but asserts there is
   nothing to change, so it survives only as a citation someone must re-read. `INVALID` asserts the defect does not exist
   and is the only bucket that destroys information outright — hold it to the highest bar.

   **Out-of-scope is a claim about the diff, so cite the diff.** "File absent from the change set" means you looked at the
   parsed change set and the file is not in it — name that, not a recollection. A line that "predates this branch" is
   established from the `@@` ranges or a `git log`/blame on that line, not from it looking untouched.

6. **PASS C — TICKET INTENT & MINIMUM BLAST RADIUS (only on findings PASS B marked VALID + in scope).** Everything that
   reaches this pass is a real defect in code this branch touched. PASS C therefore decides **how it is acted on**, not
   whether it is real — and its default answer is *submit*. Two independent questions per finding; answer both, in this
   order.

   **C1 — Minimum blast radius (routing; NEVER a withhold).** State the **smallest** fix that resolves the finding: the
   files and symbols it must change. Then measure:
   - If the minimum fix is confined to lines this branch already added or modified, the radius is by construction the
     branch's own — say so and skip the impact call.
   - Otherwise run `mcp__reposphere__graph_query({ template: "callers", function_name: <symbol>, repo: <repo> })` on each symbol the minimum fix
     would change. **Read server gap #6 first — where you run it, and whether you can trust it, depends on
     `CHECKOUT_MODE`:** in `worktree` mode run it from the main checkout and trust it; in `main` mode the registered path
     already carries your fixes, so the reading is contaminated — mark it advisory (or stash first). In both modes
     `git diff` is the change-scope authority; reposphere callers/callees is the only blast-radius authority.
   - If the minimum fix would touch another repo, run the cross-repo recipe (RepoSphere for the seam, then a callers check
     inside the flagged repo for the radius) — RepoSphere never computes a radius.

   | Minimum fix | Route |
   |---|---|
   | Confined to lines this branch added/modified; or `impact` LOW/MEDIUM inside the PR's own change set | **SUBMIT — fix now** |
   | Needs edits to files absent from this PR's change set, changes a shared symbol's signature / API contract / DB or config write, spans another repo, or `impact` returns **HIGH/CRITICAL** | **SUBMIT — fix in follow-up**, carrying the measured radius |

   **A wide radius is a reason to fix it elsewhere, never a reason not to report it.** The CLAUDE.md guardrail "stop on
   HIGH/CRITICAL" governs *making the edit*, not disclosing the defect — a HIGH/CRITICAL finding is the single most
   important thing to put on the server. Both routes SUBMIT; the route is an annotation the human uses at GATE 2.

   **C2 — Ticket intent (the one withhold, and the highest bar in this runbook).** Withhold as **intent-satisfied** only
   when **every** condition holds:
   1. The finding's asserted defect is *that the code does X*, and **X is an acceptance criterion or a BA-confirmed
      decision you can quote verbatim** from the ticket artifacts (`./review-artifacts/ticket-intent.md`, or `rca.md`
      / `spec.md` in `tickets/{KEY}/`). Paste the sentence into the gate block.
   2. The finding names **no separate mechanism failure** — no crash, no null path, no data loss, no security exposure, no
      broken invariant, no regression outside the criterion. It objects to the *specified behaviour itself*.
   3. Severity is **not** `high` or `critical`, and the category is **not** correctness, security, or data integrity. Those
      are never eligible for this bucket whatever intent says.
   4. You can cite the acceptance criterion **and** the code line together, so a later reader can check both.

   **Forbidden reasons to withhold at PASS C — each of these is a SUBMIT:**
   - "Intentional" / "by design" / "BA-confirmed" as a bare label, with no quoted criterion.
   - Design *rationale* from `spec.md` ("we chose this shape because…"). Intent tells the reviewer what to check; rationale
     tells it what to accept, and only the first is admissible here (same split as the CONTEXT BRIEF section).
   - **The spec is silent on it.** Silence is not exclusion. A finding proposing something the ticket never considered is
     in scope for this PR's code and gets submitted.
   - The finding differs from a sibling convention and the team chose not to follow it. **This is PR #371's exact failure
     mode** — two medium findings flagged a new per-channel map as disable-only while five sibling flags honoured both
     directions, and both were worth fixing. A convention finding survives PASS C.
   - "Not what this ticket is about" as an argument about scope of *work*. That is C1's follow-up route, which submits.
   - Anything you would express as a preference rather than a citation.

   **Fail-closed:** if there is no ticket folder and no `ticket-intent.md` (STEP 3.5 skipped), **C2 cannot run** — the
   `intent-satisfied` bucket is unavailable for the whole round, every surviving finding is routed by C1 alone, and the gate
   block says so. Never reconstruct intent from the diff, the PR title, or your own reading of what the change was for:
   inferring the criterion from the code and then using it to withhold a finding about that code is circular.

   A returned **development rule** (step 3) may support a C2 withhold only on the same terms as a PASS A refutation — name
   the rule and show where the code complies. A rule the change merely does not violate is not a criterion.

7. **Present the gate block and STOP** (format below). Before presenting, run these self-checks and fix what they
   catch rather than reporting it as a caveat:

   - **Completeness:** the number of findings you opened code for equals `raw_findings_count`. If it does not, PASS A is
     unfinished — finish it or stop and say the gate could not be completed.
   - **Every row carries a citation, in both buckets.** Each SUBMIT row states what you read that confirms the defect;
     each WITHHOLD row states what refutes it (INVALID) or what places it outside the diff (out-of-scope). A row whose
     evidence cell reads as an opinion rather than a citation is not presentable: for a WITHHOLD, move it to SUBMIT; for
     a SUBMIT, go back and read the code so the row can be filled honestly.
   - **`code I opened` is stated per finding, for submitted findings too** — it is the record of how much reading backed
     each call, and it is what makes the difference between a verified gate and a rubber-stamped one legible to the
     reader. A withhold backed by no reading is a guess; so is a submit.
   - **PASS C accounting closes:** `fix now` + `fix in follow-up` + `intent-satisfied` equals PASS B's in-scope count. A
     finding in none of the three was not routed.
   - **Every `fix in follow-up` row carries a measured radius** — either "confined to lines this branch added" or a
     callers-check verdict with its depth-1 callers. A follow-up route asserted without the measurement is a guess
     dressed as caution; re-route it to `fix now` or go and measure.
   - **Every `intent-satisfied` row quotes the criterion verbatim.** If the cell paraphrases, infers, or cites rationale
     rather than a criterion, the row is not presentable — move it to SUBMIT.
8. **On approval, build the filtered `codeReviewJson`:** remove the withheld findings from the findings array and
   **recompute every derived aggregate** the object carries — per-severity counts, total count, and the overall score —
   so the payload is internally consistent. A findings array of 4 alongside `"total": 9` is a corrupt submission.
   **PASS C's `fix in follow-up` findings stay in the array** — they were submitted; only the three withhold buckets
   (invalid, out-of-scope, intent-satisfied) are removed.

   **The score is computed, never judged:** `10 − Σ(weight × count)` over the post-withhold array, to 2 dp, per the
   rubric in the LOCAL CONVERGENCE LOOP section (high −1.5, medium −0.5, low −0.15). The server overrides anything
   outside ±0.05, so a judged number is discarded on arrival.

   **Do not submit yet on the first pass through this gate.** Under the local convergence loop (STEP 4.6) the filtered
   object is built at every iteration as the gate's evidence, but `mh_submit_result` is called **once**, at STEP 4.7,
   after the push — on the final iteration's object. Submit here only if you are explicitly running without the loop.
   **The submitted array must never be empty** — see "Never submit an empty findings array".
9. **Persist the withheld set locally** (next sub-section) and carry it into the downstream nodes:
   - The review-results `send_email` node (gotcha #4, server gap #4) must report the **submitted** score / counts /
     titles — the post-withhold, post-loop numbers, never the raw ones and never an intermediate iteration's.
   - `distill_lessons` sees only submitted findings, which is the point: a false positive must not become a durable
     org-wide lesson. The converse constraint — that it must not see *nothing* — is why the loop nominates a substantive
     finding to ride to the round of record.

#### Persist the withheld set — `./review-artifacts/withheld-findings.md`

Withheld findings leave no server trace, so the **only** record is local. Write it as part of the same step that filters
the payload, not afterwards. It has two readers: you, later in this session, and the next prompt/run on this PR — which
must not re-litigate the same false positives from scratch.

**Granularity: one block per GATE 1 run, nested under the round.** GATE 1 recurs every loop iteration and rewrites the
classification each time, so a single per-round block would be silently overwritten by iteration 2 and the earlier
judgements lost. Mirror the ledger: `## Iteration <i>` blocks under a `# Round <N>` heading.

```markdown
# Round <N> — <PR_LABEL>
Head SHA at round start: <sha>   ·   Iterations: <n>   ·   Submitted at: <pushed sha or "not yet">

## Iteration <i>
Submitted: <count> · Withheld: <count> (<invalid> invalid, <oos> out-of-scope, <is> intent-satisfied)
Raw findings file: ./review-artifacts/<outputFile name>-iter<i>.json   # unfiltered, kept as evidence
Working-tree state reviewed: <base sha + "working tree, N fixes applied" | HEAD sha>

| # | file:line (re-located) | severity | bucket | evidence (what I read that establishes this) | code I opened | follow-up |
|---|---|---|---|---|---|---|
| 1 | src/app/x/y.ts:214 | medium | out-of-scope | VALID defect; y.ts absent from diff vs origin/develop — no line in it added or modified by this branch | y.ts, diff scope | new ticket — legacy exporter guard |
| 2 | src/app/a/b.ts:88 | high | invalid | guard at b.ts:81 returns early on null, so the deref at :88 is unreachable | b.ts:70–95, 3 callers via the call graph | — |
| 3 | src/app/c/d.ts:52 | low | intent-satisfied | AC quoted: "the tab is visible to Guardian-plan teams only"; d.ts:52 is that restriction, and the finding objects to the restriction itself — no mechanism failure alleged | d.ts:40–70, ticket-intent.md AC list | — |

## Submitted, fix recommended in a follow-up — round <N>, final iteration
Not withheld — these go to the server at GATE 3. Listed so the next round knows they were deliberately deferred, not
missed. Record this once per round from the **final** iteration's routing, not per iteration: the intermediate ones were
never submitted.

| # | file:line | severity | minimum fix | measured radius | why deferred |
|---|---|---|---|---|---|
| 4 | src/app/e/f.ts:31 | medium | widen the shared `resolveChannel` signature | callers check: HIGH, 14 depth-1 callers in 2 repos | fix crosses repos; outside this PR's change set |
```

Rules for the file:
- **One row per withheld finding**, with the **re-located** file:line (step 2), never the diff-global offset.
- The `evidence` cell must stand alone for a reader with no session context — same bar as a `reject_comments` reason, and
  it must be a **citation, not a judgement**. `out of scope` / `false positive` / `not a real issue` alone is not
  acceptable; if that is all you can write, the finding belonged in SUBMIT. For `intent-satisfied` the cell must **quote
  the acceptance criterion verbatim** and name the code line the criterion produced — a paraphrase does not qualify.
- **The follow-up table records submits, not withholds.** Keep the two tables separate: conflating them would let a
  deferred finding read as a dropped one on the next round, and vice versa.
- **`code I opened` is mandatory.** It is the honest record of how much reading backed the call, and it is what a later
  round checks when a withheld finding turns out to have been real.
- **Append at both levels, never overwrite.** Each loop iteration adds a `## Iteration <i>` block; each re-review adds a
  new `# Round <N+1>` heading beneath the previous round. The PR's full withholding history — every iteration of every
  round — is one file.
- **A withhold recorded at iteration `i` is not carried into iteration `i+1`'s classification.** The file is read as
  prior evidence (STEP 0's rule applies within the loop too); the code changed between iterations, so the judgement is
  re-made. Recording it and reusing it are different things.
- Cite it in the report as `withheld-findings.md` (no path) per `.claude/rules/output-guardian.md` if any of that
  content reaches Jira or a PR comment; the local file itself is an internal session artifact and may name paths freely.
- It stays **local** — it is not uploaded, not emailed, and not fed to `distill_lessons`.
- `review-artifacts/` must not be staged (see STEP 0's never-stage list).

### LOCAL CONVERGENCE LOOP (STEP 4.6 — runs between GATE 1 and the push; the server is not touched)

**The premise, restated because everything here depends on it:** findings become server state only at
`mh_submit_result`. So the fix → re-review cycle does not need the server at all. Fix locally, recompute the diff,
re-dispatch the lenses, re-gate — as many times as it takes — and write to the server **exactly once**, on the state you
actually pushed. The server sees one round; you ran four.

**This is not score manipulation, and it is worth being precise about why.** If a high-severity defect is genuinely
fixed before the push, the pushed code genuinely has no high-severity defect, and a review of the pushed code that says
so is *accurate*. The loop improves the code and then reports the improved code. What would be manipulation is
withholding a finding you could not refute in order to move a number — which is exactly what the exit criterion below is
shaped to make pointless.

#### The rubric — read it off the returned block, compute, never judge

**Do not decode the rubric from the UI. The code_review block the server returns carries it verbatim** under
`## Scoring Rubric (MANDATORY — the score is computed, not judged)`, with a `rubricVersion` field. Read that section
every run and follow it. The values below are `rubricVersion 1` as returned on 2026-08-11 — recorded so drift is
visible, **not** a substitute for reading the block.

Base **10**, minus a weight per **new** finding, **plus carried debt for every entry you mark `STILL_OPEN`** at **½ the
new-finding weight for that entry's own severity**:

| Severity | New finding | Carried (`STILL_OPEN`) — ½ weight |
|---|---|---|
| `critical` | −2.5 | −1.25 *(inferred; no round has submitted one — record the delta when one does)* |
| `high` | −1.5 | **−0.75** |
| `medium` | −0.5 | **−0.25** |
| `low` | −0.15 | **−0.08** |

```
computedScore = clamp(10 − Σ(new weights) − Σ(carried weights), 0, 10), rounded to 1 decimal
finalScore    = clamp(computedScore + adjustment, 0, 10)   // adjustment: ±0.5 max, needs a one-line reason, else null
```

Emit the whole calculation as a `scoreBreakdown` object (`rubricVersion`, `base`, `deductions[]` of
`{severity, kind: "new"|"carried", count, perFinding, total}`, `computedScore`, `adjustment`, `finalScore`), and make
the top-level `score` **equal** `scoreBreakdown.finalScore`.

- **The v1.2 claim that only *new* findings are scored is DISPROVEN.** It was read off a `high new` UI badge. On
  PR #422 round 1, 1 new low + 13 carried entries gave `10 − 0.15 − (2×0.75 + 5×0.25 + 6×0.08) = 6.62 → 6.6`, and the
  server's breakdown panel itemised every carried row. **On a PR with a long open-comments tail the score is dominated
  by inherited debt, not by the change under review** — 3.38 of that round's 3.53 total came from carried entries. Say
  so in the gate block and in the review-results email, or the number reads as a verdict on this PR.
- **Round to 1 decimal, and `.x5` rounds DOWN.** A value computed as `6.65` was rejected when submitted as `6.7`.
  Beware both Python's banker's-rounding `round()` and rounding half-up by hand; compute the exact figure and check it
  against the block before submitting.
- **The ±0.05 tolerance is enforced and a miss is logged as prompt drift, visibly.** PR #422 round 1 submitted `6.7`
  and the panel replaced it with *"Model-reported score 6.7 deviates from the rubric value 6.6 beyond the ±0.05
  tolerance"* — which the whole team can read on the PR. Worth the extra arithmetic.
- **Recompute on the post-withhold array**, not the raw one (withhold procedure step 8) and not the pre-fix array — and
  recompute the carried half *after* the open-comments pass, since every `STILL_OPEN` decision moves the score.
- **The carried-½-vs-fresh-full weighting answers "should I just open a clean PR?"** Re-opening the same work as a new
  PR **re-raises every in-diff defect at double its current price**. On PR #422: ~9.6 staying (after rejecting the
  out-of-diff findings) versus ~6.2 on a fresh PR. A fresh PR is the right call when the PR was opened against the
  **wrong base**, so its board carries findings on another ticket's files — a correctness problem for the record, and the
  reason PR #422 was in fact re-opened. It is never a way to move the number: it scores *worse*. Present both figures
  when the question comes up.

For orientation only — new findings alone, **not a target**, and carried debt sits on top of every row:

| Composition (new only) | Score |
|---|---|
| 1 high + 2 medium | 7.50 |
| 0 high + 4 medium + 3 low | 7.55 |
| 0 high + 0 medium + 6 low | 9.10 |
| 0 high + 0 medium + 16 low | 7.60 |

Lows are nearly free: sixteen of them cost less than one high. But **ten carried mediums cost more than five new
lows** — on an old PR, check the carried column before assuming the budget is spent on this round's findings.

#### Exit criterion — zero fixable highs, not a score

> **EXIT WHEN: no `high` or `critical` finding routed `fix now` survives GATE 1 on the current working tree.**
> The score is **computed and reported at every gate, and targeted at none of them.**

**Follow-up-routed high/criticals are excluded from the criterion, and this exclusion is load-bearing.** A high whose
minimum fix crosses repos or changes a shared signature is routed `fix in follow-up` by C1, submitted, and left OPEN by
design — GATE 2 states that a HIGH/CRITICAL radius is a hard stop on editing here. It is therefore *never* fixed inside
this loop. A criterion counting all surviving highs would be unsatisfiable in exactly that case: the finding survives
every iteration, the loop runs to its max-3 bound, and the runbook reports a stall on a loop that behaved correctly.

That is not hypothetical — on the run this section came from, two of the high-severity findings were precisely this
shape: correctly measured, correctly deferred, and unfixable in-place. So: **a follow-up-routed high is a measured,
disclosed defect with a ticket behind it, not an unfixed one.** Report both counts on separate lines at every gate so
the exclusion is visible rather than assumed — a reader must be able to see that a high exists and see why it does not
block.

**Why the criterion is not "score ≥ 7.5", even though that number is achievable and tempting.** The score is computed
from what you *submit*, and this runbook hands you three withhold buckets. A round sitting at 7.2 has two ways to reach
7.5: fix the high, or reclassify it as invalid / out-of-scope / intent-satisfied. The second is cheaper, faster, and —
this is the part that matters — **produces no signal that it happened**: nothing on the server, nothing in the email,
nothing in `distill_lessons`, nothing for a later reviewer to catch. A numeric target puts a standing 1.5-point bounty on
the one error class this runbook cannot detect.

"No fixable high remains in the pushed code" has no such property. A withheld high is still *in the code*, so
withholding does not satisfy the criterion — only fixing does. The score becomes a readout of the work rather than the
object of it. Note the deferral route is not a loophole either: it **submits**, so a high routed to follow-up costs the
full −1.5 on the score exactly as an unfixed one would. Routing buys nothing numerically; it only says where the work
happens.

**The pressure is real even when the rules hold.** On the run this section came from, a high-severity finding was later
established to be parity with an existing reference implementation — a textbook `intent-satisfied` candidate worth 1.5
points. PASS C's categorical bar (high + correctness is never eligible) refused it. The rule holding is not the same as
the pressure being absent, which is why the criterion is structured so the pressure never arises.

#### Avoid submitting an empty findings array — but check what `distill_lessons` actually receives first

**Measured correction (PR #422 round 1): the node does NOT see only your submitted array.** The server materialises
every entry you marked `STILL_OPEN` as a `carried-<fingerprint>` finding and feeds those to `distill_lessons` too. That
round submitted **1** new low and the node received **14** findings — the two carried highs and five carried mediums
among them — and distilled 14 lessons, the substantive ones coming from carried entries, not from the new one.

So the starvation risk is **conditional, and you can check it before deciding**:

| Carried `STILL_OPEN` entries | Is the corpus at risk if you fix everything new? |
|---|---|
| Several, with real severity | **No.** Fix every new finding. The carried set feeds `distill_lessons` on its own. |
| None (first review, or all prior findings resolved) | **Yes.** An empty array means the node runs on nothing. |

**Count the carried set before nominating anything.** Nominating a finding to ride when a dozen carried entries are
already going to the node buys nothing and leaves a real defect in the pushed code — which is the worse trade. On
PR #422 the nomination was made against a thin `low` convention finding and was, in hindsight, unnecessary; the corpus
would have been fed regardless. **Prefer fixing.**

**The preference is a preference, not a constraint.** The server accepts `"findings": []` — nothing rejects an empty
submission. It binds the *nomination decision*, not the submission call. When there is genuinely nothing to submit,
submit nothing and say so; never manufacture a finding, and never leave a real defect unfixed to fill the slot.

When the table above says the corpus *is* at risk, and only then, the round of record is composed of mediums, lows, and
any follow-up-routed highs. To stop the corpus degenerating into semicolons and underscore prefixes:

**Nominate one substantive finding to ride to the round of record.** At the final iteration, deliberately leave one
finding unfixed so it is reviewed, submitted, and distilled:

- Eligible severity: **`medium` or `low`.** Never `high`, never `critical`.
- Ineligible categories regardless of severity: **security, data integrity, and any finding alleging data loss or a
  crash.** Those are fixed, not ridden.
- It must carry a **transferable lesson** — one a different engineer on a different file could act on. State the lesson
  in the gate block. *"When porting a resolver, port every branch, not just the one your data exercises"* is a lesson;
  *"missing semicolon"* is not.
- Cost is explicit: −0.5 (medium) or −0.15 (low) off the score. That is the price of a non-empty, non-vacuous corpus.
- **Record it as a deliberate nomination at GATE 2**, with the reason. A finding that merely went unfixed because nobody
  got to it is not a nomination — it is an unfinished loop, and it must be reported as one.

If no surviving finding carries a transferable lesson, say so plainly and submit the surviving set as-is. Do not
manufacture a finding to fill the slot.

**If the loop fixed everything, the surviving set is empty — submit it empty.** That is the one case the preference
above yields to: there is no finding left to nominate, `distill_lessons` gets nothing this round, and that is the
correct outcome of a PR with no remaining defects. Say so at GATE 3 rather than reaching back for something already
fixed.

#### Iteration procedure

Each iteration `i` (starting at 1):

1. **Fix.** Apply the fixes approved at GATE 2 for iteration `i−1` (iteration 1 fixes the GATE 1 output of the initial
   review). Fan out **one subagent per file** to avoid parallel-edit conflicts, each given exact old/new strings.
   **Re-read every edited file to confirm the edit landed** (`agents-safety.md` A3 — a subagent's "done" is a
   hypothesis).
2. **Recompute the diff.** In the checkout:
   ```
   git -C {{CHECKOUT}} diff --merge-base origin/{{BASE_REF}} HEAD > local-diff.patch        # committed state
   git -C {{CHECKOUT}} diff --merge-base origin/{{BASE_REF}}      > local-diff.patch        # working tree, incl. uncommitted fixes
   ```
   **Use the second form during the loop.** The whole point is to review edits that are not committed yet; the
   HEAD-based form (STEP 3's) would review the state you started from and report every fix as still broken. Switch back
   to the HEAD-based form only at STEP 4.7, after the push, so the submitted findings describe the pushed state.
   Re-split into `./review-artifacts/artifact-N.patch` if you are passing those paths (server gap #2).
3. **Re-dispatch the lenses.** Same N specialists, same verbatim lens text, same output contract — against the
   recomputed diff. **Re-dispatch all of them, not just the ones that found something.** A fix changes the file the
   other lenses read; narrowing the fan-out to "the lens that complained" is how a fix that breaks something adjacent
   survives to the push.
4. **Re-run GATE 1** in full on the new findings: PASS A first-hand on every finding, then B, then C. **The prior
   iteration's classifications do not carry over.** Code changed; a finding withheld against the old code has to be
   re-judged against the new. Feed the ledger in as facts (below), which is the opposite of carrying a verdict.
5. **Check the exit criterion.** Zero `fix now` highs and zero `fix now` criticals surviving → the loop is done, go to
   STEP 4.7. **Follow-up-routed highs do not count** — they are excluded by construction (see the exit criterion), so a
   loop holding two deferred highs and no fix-now ones exits cleanly on iteration 1. Otherwise present GATE 2 for
   iteration `i+1`.

**Expect new findings, and treat them as the loop working.** A fix routinely surfaces something the previous round could
not see — either because the fix was superficial or because it moved the problem. On the run this section came from,
round 0 missed a defect entirely and round 2 caught it, and separately a fix that dressed a keyword change as a type fix
was caught by two independent lenses precisely *because* they had not been told the finding was resolved. A later
iteration finding more than an earlier one is the expected shape, not a regression.

**The zero-iteration round — the common case on a re-review, and it must not be dressed up as a loop.**

If GATE 1's very first evaluation shows no `fix now` high or critical, the loop is **already done**: it runs zero
iterations, applies zero fixes, and the three gates collapse into one decision. Then:

- **Do not print loop state.** Lines like `iteration 1 of max 3` are noise when nothing will iterate — the bound governs
  repeated *fix attempts*, so announcing it on a round with no fix implies a loop that is not running. Print one line
  instead: `Loop: 0 iterations — exit criterion held at GATE 1 (no fix-now high/critical).` Report the surviving
  high/critical counts as always; suppress only the iteration counter.
- **GATE 2 has nothing to approve** — no fix plan, no ledger entries, no subagent fan-out. Fold its one live question
  (fix the survivors, or submit as-is) into GATE 1 rather than staging an empty gate.
- **GATE 3 has nothing to push.** With no edit, HEAD is already the reviewed and pushed state. Skip the `git add` /
  commit / push block entirely and **skip the diff re-upload** — verify instead that the recomputed HEAD-based diff
  still hashes identical to the one STEP 3 uploaded, and say that you checked. Do not ask for a commit that has no
  content.
- **`local-fix-ledger.md` still gets written**, with a `## Round <N> — no iterations run` block recording the hash
  check and the facts carried forward. A missing ledger and an empty ledger read the same to the next round; only one of
  them is true.

**Bounds — the loop must terminate.**

- **Max 3 iterations by default.** At iteration 4, stop and present the state to me rather than continuing: a `fix now`
  defect that survives three fix attempts is a design question, not a fix question. **Reaching the bound with only
  follow-up-routed highs outstanding is not that case** — it means the exit criterion was mis-evaluated, since deferred
  highs never block. Re-check the routing before reporting a stall.
- **No-progress stop.** If an iteration produces the same surviving `fix now` high as the one before it, with a fix
  applied in between, stop and surface that — the fix is not addressing the finding.
- **Every iteration is a GATE 2 STOP.** The loop never runs unattended; each iteration's fix plan is approved before it
  is applied.
- The heartbeat (STEP 2) **keeps running for the whole loop.** The server is still in `AWAIT_RESULT` the entire time,
  and the loop can easily outlast its window.

**Why the execution is held open at all — this is forced, not chosen.** The specialist lens prompts only exist in the
block the server returns from `mh_report_checkout` / `mh_poll_next_action`. There is no way to obtain them, and
therefore no way to re-dispatch the lenses, without a live execution. So the loop cannot run before `mh_start_review`
and cannot be moved outside the execution window: holding `AWAIT_RESULT` across several human gates is a consequence of
that dependency. Do not "optimise" it away by starting the review after the fixes — you would have no lenses to fix
against.

#### If the execution dies mid-loop

Long `AWAIT_RESULT` holds fail: the backgrounded heartbeat can be killed, the loop can outlast the server's window, or
the host can drop. **The local work is not lost, and this is worth stating plainly because the instinct is to assume it
is.** Everything the loop produced is local — the fixes are in the checkout, `local-fix-ledger.md` records what changed,
`withheld-findings.md` records what was judged, and none of it was ever server-side. Only the *execution* died.

Recovery:

1. `mh_review_status({executionId})` first — confirm it is actually dead (`FAILED`) rather than still `RUNNING`. Gotcha
   #4's lesson applies: assume nothing about server state you have not read.
2. If dead: `mh_start_review({prId, workflowId})` for a **fresh** `executionId`. Never reuse the old one — every
   subsequent call keys off it.
3. Re-run STEP 2 (heartbeat with the new id), STEP 3 (diff upload — from the **current** working tree, which already
   carries the loop's fixes), and STEP 3.6 (`report_checkout`). `ticket-intent.md` already exists; leave it.
4. Resume the loop at the iteration the ledger says you reached — not at iteration 1. The new execution returns fresh
   lens prompts, so re-dispatch against the current diff and re-run GATE 1; the ledger feeds forward as facts exactly as
   it does between normal iterations.

The one thing that genuinely does not survive is a submitted round, and by design nothing has been submitted yet.

#### FEED-FORWARD ARTIFACTS — `./review-artifacts/local-fix-ledger.md`

Everything fixed inside the loop is invisible to the server: the submitted round describes the *final* state, so a defect
found and fixed at iteration 1 leaves no trace anywhere. The ledger is that trace. It has two readers — the next
iteration of this loop, and any later review round on this PR.

**Write it as facts, never as verdicts. This is the load-bearing rule of the whole artifact.**

A verdict (*"F3 is fixed"*, *"the `any` finding is resolved"*) tells a lens what to conclude, so it suppresses the
re-raise — and the re-raise is the mechanism that catches a superficial fix. A fact (*"line 102 now declares
`{ exportUrl?: string } | null` and guards the read with `typeof`"*) is something a lens can read the code and
**disagree with**. This is the same include/exclude split the CONTEXT BRIEF applies, for exactly the same reason: state
what is true, never what to accept.

| Write this — a checkable fact | Never this — a verdict |
|---|---|
| "line 102 now declares `{ exportUrl?: string } \| null` and guards the read with `typeof`" | "the `any` finding is fixed" |
| "`_buildExportUrl` now handles the `draft` and `void` branches as well as `active`" | "F3 resolved" |
| "the null check moved from the caller at `:88` to the top of `resolveChannel`" | "no longer an issue" |
| "the map at `:41` now writes both `true` and `false`, matching the five sibling flags" | "convention finding addressed" |

```markdown
# Local fix ledger — <PR_LABEL>
Head SHA at loop start: <sha>   ·   Loop iterations: <n>   ·   Pushed as: <sha or "not yet pushed">

## Iteration <i>
| # | file:line (post-fix) | severity as found | what the code says NOW (fact, not verdict) | what it said before |
|---|---|---|---|---|
| 1 | src/app/x/y.ts:102 | high | declares `{ exportUrl?: string } \| null`; read guarded with `typeof` at :104 | `any`, unguarded read at :104 |
| 2 | src/app/x/y.ts:141 | medium | `_buildExportUrl` branches on `draft` / `void` / `active` | only the `active` branch existed |

## Ridden to the round of record — iteration <final>
Deliberately left unfixed so `distill_lessons` has substantive input. Not an oversight.

| # | file:line | severity | the transferable lesson | why this one |
|---|---|---|---|---|
| 3 | src/app/x/y.ts:77 | medium | when porting a resolver, port every branch — not only the one your data exercises | generalises beyond this file; no security/data-integrity exposure |
```

Rules for the file:

- **Append across iterations and across rounds.** One `## Iteration <i>` block per pass; never overwrite.
- **Feed it into every lens dispatch** as a read path alongside `ticket-intent.md`, with this framing verbatim:
  > Prior fixes already applied in this working tree are described as facts in `./review-artifacts/local-fix-ledger.md`.
  > They are statements about what the code says now, not verdicts — verify them against the code and raise a finding if
  > a described fix is incomplete or wrong.
- **It stays local**, alongside `withheld-findings.md` — never staged, never uploaded, never emailed, never fed to
  `distill_lessons`. `review-artifacts/` is on STEP 0's never-stage list.
- **Known limit, stated rather than worked around: the feed-forward is checkout-local.** A review started from a fresh
  clone, on another machine, or in CI has none of it and starts cold. The continuity this section buys is real but
  bounded to this `{{CHECKOUT}}` — do not describe a fresh-clone round as having the loop's history behind it. (In
  `main` mode the artifacts sit in your everyday repo folder and so tend to survive across tickets; that makes STEP 0's
  never-stage list load-bearing, not optional.)
- Same output-guardian boundary as the other artifacts: the local file may name paths and internal tokens freely; any
  content quoted from it into Jira, a PR comment, or Confluence is subject to `.claude/rules/output-guardian.md` at that
  boundary.

### CONTEXT BRIEF (ticket intent — file written at STEP 3.5, injected into the prompt at STEP 4)

The reviewers are structurally blind to intent. Verified on PR #371: the `pr` object passed into workflow context carries
only `state, title, number, baseRef, headRef, htmlUrl, additions, deletions, authorLogin, changedFiles` — **no `body`** — so
the PR description never reaches them. Team Context is team-wide and Development Rules are convention-wide, so **no
sanctioned per-ticket channel exists**. Supplying the ticket's own facts locally fills that gap; it is not a workaround of
an existing channel.

**Where the injection happens.** The prompt is assembled **server-side** and handed back by `mh_report_checkout` (and by
each subsequent `run_review` / `run_node` action) as a verbatim bash block. You cannot pass a ticket-intent parameter to
that call — there is no such field on `mh_report_checkout` or `mh_submit_result`, and the server's own instructions to the
reviewers must not be edited. What you *can* do is add one line to the returned block's **Team Context**, which the
server's coordinator prompt already promises to propagate. So the sequencing is: **write the file before
`report_checkout`** (so the path resolves when the prompt is read), **add the line to the prompt after it comes back**.

**Mechanism (uses what the server prompt already defines — do not edit the server's instructions to the reviewers):**

1. Distil the ticket folder `tickets/{KEY}/` (`rca.md`, `spec.md`) into **one** file,
   `./review-artifacts/ticket-intent.md`, **≤50 lines**. Do this at STEP 3.5, before `report_checkout`.
2. At STEP 4, add **one** line to the returned prompt's **Team Context** block naming that path — nothing else changes:
   ```
   Ticket intent for this change (facts, not rationale) — read ./review-artifacts/ticket-intent.md before forming findings.
   ```
   Since v1.1 you assemble each specialist prompt yourself, so **prepend that Team Context to each dispatch prompt
   directly** — the same effect the coordinator prompt's *"prepend any specialist-relevant guidance from this Team
   Context … to the top of each specialist's prompt"* used to produce, now done by you and verifiable per agent. The
   lens, output contract, and dedup rules still go in unmodified.
3. **Reference the path; never inline the brief.** `spec.md` is routinely 40–64 KB and `rca.md` 30–46 KB — inlining into 5
   specialist prompts costs ~500 KB and buries a ~10 KB diff. The specialists have `Read` and are given the diff /
   `artifact-N.patch` paths.
4. Keep local workflow tokens out of the brief's substance (ticket keys, wave IDs, session IDs). Findings feed
   `distill_lessons`, and distilled lessons are durable org-wide state.
5. **Verify the path is readable from the checkout before running the node** — the specialists' `Read` resolves relative
   to the checkout, and server gap #2 shows they fail silently on missing artifact paths. A brief that no reviewer read is
   worse than none, because you will credit it for the findings' quality.

**Relationship to the withhold gate — they are not substitutes.** The brief reduces *how many* out-of-scope and invalid
findings get produced; the gate stops the ones still produced from reaching the server. Both are worth running, and note
the asymmetry: the brief is the riskier of the two, because it acts on reviewers *before* they think, and PR #371 showed
stated intent silently suppressing two medium findings that were worth fixing. The gate acts *after*, on findings you can
read, re-locate, and reverse. Prefer withholding a bad finding over pre-empting it — that is why the include/exclude split
below is strict.

**PASS C is the sanctioned place for intent to act, and this is why.** The brief and PASS C consume the same facts, but at
opposite ends: the brief lets intent shape findings that do not exist yet (unreviewable, irreversible, invisible), while
PASS C applies it to a written finding you can read the code for and put back. That is the direction this runbook prefers.
It also means the include/exclude split governs PASS C verbatim: only the left column — criteria, paths, teams in scope,
BA-confirmed decisions **as facts** — can support an `intent-satisfied` withhold. Nothing from the right column can, and
"we deliberately did X" is the right column.

**What to include vs exclude — this is the load-bearing rule:**

| Include — what must be TRUE | Exclude — why you CHOSE it |
|---|---|
| Acceptance criteria / the behaviour being changed | Design rationale, "we deliberately did X" |
| The exact config path or DB node in play | Justifications for the chosen shape |
| Which teams / channels / envs are in scope | Anything phrased as a conclusion |
| Constraints and explicit out-of-scope exclusions | "This approach is correct because…" |
| Decisions a BA actually confirmed (as facts) | Pre-emptive answers to anticipated findings |

Intent tells the reviewer what to **check**; rationale tells it what to **accept**. Only the first is worth injecting.

*Evidence for the split, from PR #371's 9 findings — context cuts both ways:*
- **Helps goal-conformance findings.** The high-severity finding (a third, unmigrated reader of the widened config key,
  leaving the hidden action reachable one screen over) is exactly what a reviewer finds when it knows the goal and can ask
  "does this still hold everywhere?"
- **Suppresses convention findings.** Two medium findings flagged the new per-channel map as disable-only while five sibling
  channel flags in the same file honour both directions. A brief saying "opt-out-only is intentional, BA-confirmed" would
  have killed both — and both were worth fixing. Stated intent buys silence on genuine improvements.

---

### DEVELOPMENT RULES GATE (MANDATORY — run at STEP 4.5, BEFORE classifying findings, never after)

> Called from the **PRE-SUBMIT WITHHOLD GATE** step 3. "Before classifying" now means *before deciding what to submit*,
> not merely before deciding what to fix — a finding that complies with a returned rule is withheld, not posted-then-rejected.

Paired with the code-lessons corpus, and part of the latest code-review-kms MCP. `get_development_rules` (served by the
**code-lesson** MCP, tool id `mcp__code-lesson__get_development_rules`) returns the team's human-authored,
project / language / file-scoped constraints — service-design decisions, file naming, approved libraries, "read this
sample first". These are team conventions, NOT the global lessons corpus. Treat them as **constraints, not suggestions**:
a change that **violates** a returned rule is a legitimate finding; a change that merely differs from your taste but
**complies** with the rules is **not** a finding.

Before classifying the review findings at the GATE below, call it once per distinct review scope:

```
get_development_rules({
  project: "<owner/repo>",           // bare slug from `git remote` (strip scheme/host + trailing .git), e.g. "FireHawk/FCRM-Web"
  repoId: "<manager-hub repo CUID>", // optional; unambiguous alternative to project, wins over it
  language: "<language>",            // e.g. "typescript" — read the changed files' imports, DON'T guess
  frameworks: ["<fw>", ...],         // only frameworks actually imported in the changed files
  filePath: "<changed/path>"         // optional; picks up path-specific rules
})
```

- Returned rules are ranked **most-specific-first** (project+language+framework+path beats team-wide). On conflict, the
  higher-ranked rule wins.
- **Allowed-tools (this is the "expose the tool" requirement):** the reviewer sub-agents must carry
  `mcp__code-lesson__get_development_rules` so they consult rules while forming findings. **Since v1.1 this is
  satisfied by construction** — STEP 4 dispatches them as `code-review-depth` / `code-review-breadth` subagents, whose
  whitelists already include the tool, so the server's missing `--allowedTools` flag no longer blinds them. The driving
  session also has it allowed via `.claude/settings.local.json` → `permissions.allow`. If you ever fall back to running the
  node's `claude -p` block as returned, the old constraint returns: the block is verbatim server output, it ships no
  such flag, and the whole dev-rules check falls to the driving agent at this gate.
- **Auto-skip when absent:** the tool is team-scoped and only present when `MANAGER_HUB_TEAM_ID` +
  `MANAGER_HUB_TEAM_TOKEN` are configured for the project's code-lessons MCP. If it isn't exposed, this gate auto-skips —
  that absence is the only acceptable skip. (Manage rules in Manager Hub → **Settings → Development Rules**, Team Manager
  role to edit; API `GET /api/public/dev-rules`, same Bearer auth as the PR tools.)
- **Self-audit:** in the gate breakdown, state that you called `get_development_rules` (naming `project` / `language` /
  `frameworks` / `filePath`), which rules applied, and how each surviving finding maps to a rule — or record the skip
  (tool absent). Omitting this on a logic-change review is itself a gate failure.

> **Availability note — UPDATED, verified live on PR #371 (2026-07-30):** `get_development_rules` **is now exposed and
> working** on the driving session. The gate no longer auto-skips — run it. A call with
> `project: "FireHawk/FCRM-Web"`, `language: "typescript"`, `frameworks: ["angular","rxjs","firebase"]` returned **14 rules**
> ranked most-specific-first. `filePath` did not narrow further for two files both matching `src/app/**/*.ts` (identical
> rule set returned), so one call per distinct *area* is usually enough — not one per file.
>
> The tool lives on the **code-lessons** MCP (`mcp__code-lesson__get_development_rules`), not code-review. The earlier
> note here (2026-07-01) recorded the gate auto-skipping because the local builds were code-lessons 0.4.0 / code-review
> 0.3.3; that is now stale. **Still auto-skip only if the tool is genuinely absent from the tool list** — and say so
> explicitly in the self-audit rather than silently omitting the gate.
>
> Caveat observed on the same run: the code_review bash block the server returned carried **no `--allowedTools` flag at
> all**, so the 5 specialists could not call the tool themselves — only the coordinator could (the driving session allows
> it via `.claude/settings.local.json`). **v1.1 sidesteps this** rather than waiting for the server: the specialists are now
> `Agent`-dispatched subagent types that carry the tool in their own whitelist. Instruct each dispatch prompt to call it
> for its lens; the gate below still runs the coordinator-side call as the backstop.

### GATE 1 — PRE-SUBMIT (STOP; recurs once per loop iteration, and always before `mh_submit_result`)

Run the **DEVELOPMENT RULES GATE** above first, then present the four-bucket classification from the **PRE-SUBMIT
WITHHOLD GATE**, every finding VERIFIED against the real code (re-located line numbers, never diff-global offsets).
Under the local convergence loop this gate runs **every iteration**, from scratch — prior classifications do not carry
over, because the code they were judged against has changed:

```
Raw findings: <N>   →   SUBMIT: <n> (<now> fix now, <fu> fix in follow-up)
                    ·   WITHHOLD: <m> (<invalid> invalid, <oos> out-of-scope, <is> intent-satisfied)
PASS A (validity, judged first-hand in this thread): <valid> VALID · <invalid> INVALID
  code opened for <N> of <N> raw findings          ← must equal raw findings; anything less = gate unfinished
PASS B (scope, VALID findings only):                 <n+is> in scope · <oos> out-of-scope
PASS C (intent + radius, in-scope findings only):    <now> fix now · <fu> follow-up · <is> intent-satisfied
  (now + fu + is must equal PASS B's in-scope count)

SUBMIT — fix now (valid + in scope; minimum fix stays inside this PR)
  1. <file:line> · <severity> · <one-line summary>
     validity: VALID — <what I read that makes the defect real, citing file:line — not a restatement of the finding>
     code I opened: <files/ranges/symbols>
     scope:    in added range <a–b> (±3)   |   outside window but touches changed code   |   no coordinates (architectural)
     minimum fix: <files/symbols it must change>
     radius:   confined to lines this branch added   |   callers check <LOW|MEDIUM>, <k> depth-1 callers

SUBMIT — fix in follow-up (valid + in scope; minimum fix exceeds this PR — still posted)
  2. <file:line> · <severity> · <summary>
     validity: VALID — <citation>
     code I opened: <files/ranges/symbols>
     minimum fix: <files/symbols it must change>
     radius:   callers check <HIGH|CRITICAL>, <k> depth-1 callers in <repos>   |   touches files absent from the change set
     defer because: <crosses repos | changes a shared signature/API contract | needs a DB/config write | HIGH/CRITICAL>
     follow-up: <suggested ticket scope>

WITHHOLD — out-of-scope (VALID defect; belongs in a follow-up ticket)
  3. <file:line> · <severity> · <summary>
     validity: VALID — <what I read that confirms the defect is real>
     code I opened: <files/ranges/symbols>
     scope:    <file not in parsed change set | line predates this branch — <@@ range or git log evidence>>
     follow-up: <suggested ticket scope>

WITHHOLD — intent-satisfied (the alleged defect IS the acceptance criterion)
  4. <file:line> · <severity> · <summary>
     validity: VALID — <citation>
     criterion (verbatim): "<the AC / BA-confirmed decision, quoted — a paraphrase does not qualify>"
     source:   <ticket-intent.md | rca.md | spec.md>
     produced by: <the code line that implements that criterion>
     eligibility: no mechanism failure alleged · severity not high/critical · category not correctness/security/data-integrity
     code I opened: <files/ranges/symbols>

WITHHOLD — invalid / false positive   (each row MUST carry a refutation citation, not an opinion)
  5. <file:line> · <severity> · <summary>
     refuted by: <concrete file:line or invariant that makes the defect impossible — or the dev rule it complies with,
                  naming the rule and where the code complies>
     code I opened: <files/symbols>

Loop state: iteration <i> of max 3 · specialist lenses dispatched: <N observed, counted from the block>
  (zero-iteration round instead → "Loop: 0 iterations — exit criterion held at GATE 1"; suppress the counter)
  surviving high/critical routed FIX NOW:   <h> / <c>   ← EXIT when both are 0; the score is NOT the criterion
  surviving high/critical routed FOLLOW-UP: <h> / <c>   ← excluded from the criterion by design; submitted, left OPEN,
                                                          each carrying a measured radius. Not unfixed — deferred.
Aggregates to be recomputed on submit: total <N>→<n>, severity counts <before>→<after>
  score (computed per the RETURNED block's rubric, not judged; carried debt included):
    new     : 1.5×<high> + 0.5×<med> + 0.15×<low>            = <a.aa>
    carried : 0.75×<high> + 0.25×<med> + 0.08×<low>          = <b.bb>   ← every STILL_OPEN entry, ½ weight
    10 − <a.aa> − <b.bb> = <x.xx> → <x.x> (1 dp, .x5 rounds DOWN; ±0.05 or the server overrides and logs drift)
  carried share of the total deduction: <b.bb>/<a.aa+b.bb> — if this dominates, SAY SO: the score is measuring
    inherited debt, not this PR
  (n counts the follow-up-routed findings — submitted, not withheld. n may be 0; see the empty-array section, and
   note the server ALSO feeds every carried entry to distill_lessons, so n=0 does not imply a starved corpus)
Dev-rules self-audit: called with project/language/frameworks/filePath = <…>; rules applied: <…>   (or: skipped — tool absent)
Context brief: injected via Team Context → ./review-artifacts/ticket-intent.md   (or: skipped — no ticket folder)
Validity self-audit: judged first-hand, no subagent delegation · code opened for <N>/<N> findings
  · VALID on positive evidence: <p>   · VALID (uncertain after reading, unresolved): <k>   · INVALID with refutation: <i>
  (p + k + i must equal N. A finding in none of these three was not classified.)
Intent self-audit: C2 <ran | UNAVAILABLE — no ticket folder/brief, routed by radius alone>
  · every intent-satisfied row quotes a criterion verbatim: <yes/no>
  · radius measured for every follow-up row (reposphere callers check): <yes/no>
```

If the INVALID list is empty, say so plainly — that is a normal and healthy outcome, not a gap. A gate that withholds
nothing is working correctly; a gate that reliably finds several false positives per round is the one to distrust. **The
same applies with more force to `intent-satisfied`: empty is the expected result.** A reviewer contradicting a quoted
acceptance criterion is rare; a round that withholds two or three findings on intent is far more likely to be a gate using
intent as a convenience than a reviewer that misread the spec three times.

Equally: **"all N submitted" is only a healthy outcome if the `code opened for N of N` line is true.** The same summary
line is produced by a gate that verified nine findings and by one that read none of them, so the reader is entitled to
the accounting above to tell them apart. If you did not open code for a finding, do not fill in its citation from the
finding's own text — report the shortfall and stop.

Then STOP. On my approval:
- Write `./review-artifacts/withheld-findings.md` (append if it exists), filter the payload, and **recompute the
  aggregates including the rubric score**. Keep the filtered object on disk as this iteration's evidence.
- **Do not submit.** Go to GATE 2 and run the local convergence loop. `mh_submit_result` happens once, at GATE 3, after
  the push. (Submit here only if explicitly running without the loop — then continue driving the remaining nodes with
  the post-withhold numbers in the review-results `send_email`.)

### GATE 2 — LOCAL FIX (STOP once per loop iteration, before applying any edit)

The surviving findings are all VALID + in scope by construction — GATE 1 withheld the rest. So this gate is about *how*
to fix, not *whether*, and it recurs: one GATE 2 per iteration of the local convergence loop. **Nothing has been
submitted to the server at this point**, which is what makes iterating free.

**PASS C's routing carries into this gate.** Split the fix plan in two: the `fix now` findings, and the `fix in
follow-up` ones with their measured radius. Fix the first group in this PR; the second becomes follow-up tickets — a
HIGH/CRITICAL radius is a hard stop on editing here (CLAUDE.md guardrail), not something to work around. Follow-up-routed
findings are **still submitted** at GATE 3 and stay OPEN on the server by design; they are not withheld and never get
`reject_comments`, because `WONT_FIX` means "we decided not to do this" and "correct defect, wrong PR" is not that. If
you decide to fix a follow-up-routed finding in this PR anyway, say why the radius is acceptable before doing it.

Present, then STOP:

```
GATE 2 — iteration <i> of max 3

FIX NOW (this iteration)
  1. <file:line> · <severity> · <summary>
     minimum fix: <exact change>          radius: <confined to branch lines | impact LOW/MEDIUM, k callers>

DEFER TO FOLLOW-UP (submitted at GATE 3, left OPEN, not fixed here)
  2. <file:line> · <severity> · <summary>   radius: <impact HIGH/CRITICAL, k callers in n repos>

NOMINATED TO RIDE (final iteration only — deliberate, so distill_lessons is not starved)
  3. <file:line> · <severity: medium|low> · <summary>
     transferable lesson: <the lesson a different engineer on a different file could act on>
     eligibility: not high/critical · not security/data-integrity · no crash or data-loss alleged
     score cost: −<0.5|0.15>

EXIT CHECK: fix-now high <h> · critical <c>     → <continue to iteration i+1 | EXIT to GATE 3>
            follow-up high <h> · critical <c>   → excluded from the criterion (deferred with a measured radius)
score if submitted as-is (computed): <x.xx>     ← readout only; deferral does not reduce it
```

On my approval:
- Fix via **fan-out subagents — ONE subagent per file** (avoid parallel-edit conflicts), each given exact old/new
  strings and forbidden from grep/explore. **Verify each subagent's edits landed** (re-read, don't trust — A3).
- Append this iteration's changes to `./review-artifacts/local-fix-ledger.md` **as facts, not verdicts** (see
  FEED-FORWARD ARTIFACTS — the phrasing rule is load-bearing, not stylistic).
- Recompute the working-tree diff, re-dispatch **all N** lenses against it, and re-run GATE 1 from scratch.
- If a finding is refuted during the fix, it has not been submitted yet — reclassify it at the next GATE 1 with the
  refutation, and record it in `withheld-findings.md`. No `reject_comments` is needed: it was never on the server.

### GATE 3 — PUSH, THEN SUBMIT ONCE (STOP after the loop exits)

The exit criterion holds: no `fix now` high or critical survives on the current working tree (deferred ones may remain —
name them). Present, then STOP:

- The `git add` (**explicit paths, never `git add .`**, and never the never-stage list from STEP 0) + commit message.
  **I commit and push** — you never do (`git-safety.md` G11).
- The final submission preview: findings count, per-severity counts, computed score `10 − Σ(weights)`, the ridden
  finding named with its lesson, and any follow-up-routed high/criticals with their measured radius.
- A one-line loop summary: iterations run, findings fixed locally, findings submitted.

After I confirm the push has landed:
1. **Recompute the diff HEAD-based** (`git diff --merge-base origin/{{BASE_REF}} HEAD > local-diff.patch`) and confirm
   it matches what the loop reviewed — the submitted findings must describe the **pushed** state, not the working tree
   you reviewed a moment before the commit. If they differ, something was staged or dropped; stop and surface it.
2. **Re-upload it.** The diff the server holds is the one STEP 3 uploaded **before** the loop ran, so it is stale by
   construction — the loop changed the code after it. Submitting post-loop findings against a pre-loop diff means the
   server's line anchors and the findings' line numbers describe different files:
   ```
   POST .../api/public/code-review-mcp/diff-upload?executionId=<executionId>
     (Bearer auth, Content-Type text/plain, --data-binary @local-diff.patch)
   ```
   Skip this only if the loop ran zero iterations (no fix applied), and say so.
3. `mh_submit_result` the code_review node **once**, with the final filtered `codeReviewJson` and your
   `openCommentsResolvedJson` (gotcha #2).
4. Drive the remaining nodes — the review-results `send_email` (substituting the real post-loop numbers per server gap
   #4) and `distill_lessons`.
5. On a **re-review**, prior-round findings still on the server that you are not fixing go through `reject_comments`
   with evidence — withholding cannot retract server state. Never `reject_comments` a finding whose fix you pushed:
   `WONT_FIX` means "we decided not to do this", and using it to mean "done" corrupts the one record the next reviewer
   trusts (same rule as `/fix-review-findings` Step 6).
6. **Verify the board against what you sent (server gap #7 — mandatory, not optional).** After the code_review submit,
   read it back:
   ```
   get_open_comments({ pullRequestId, includeStatuses: ["OPEN", "WONT_FIX", "RESOLVED"] })
   ```
   Diff every status against your `openCommentsResolvedJson`. Report three counts: sent-`STILL_OPEN`-and-still-`OPEN`,
   sent-`RESOLVED`-and-`RESOLVED`, and **sent-`STILL_OPEN`-but-came-back-`RESOLVED`**. The third bucket is a live defect
   the board has silently closed: name each one, state that nothing was fixed, and raise a follow-up ticket in the same
   turn, because the board will not surface it again. A round that skips this read-back cannot tell a tracked defect from
   a lost one.

---

## Notes / lessons baked in (from PR #152, GEN-2993)

- The driving session's `executionId` powers heartbeat + diff-upload + report_checkout + every submit — capture it once
  from `mh_start_review` and reuse it (a fresh run gets a fresh one; don't hardcode an old one).
- Two databases exist (RTDB vs Firestore) — irrelevant to this workflow (read-only review), but keep findings honest about which.
- The checkout commonly carries local-dev dirt (`environment.ts`, `server/.env.development`, `server/package.json`). HEAD
  match is what matters for the diff; never stage that dirt, never read `.env*` (hard credential rule).
- Heredoc-built bash blocks may emit a benign stderr `Warning: no stdin data received in 3s` — ignore it.

## The withhold discovery (why this runbook has gates at all)

Findings are generated **locally** — by the Code Review node's `claude -p` originally, by the in-thread fan-out since
v1.1 — and become server state only at `mh_submit_result`. Nothing in the protocol requires submitting all of them, or
submitting them promptly. That single fact carries two consequences, discovered a fortnight apart:

- **v1.0 (the withhold gate):** an invalid or out-of-scope finding never has to be posted-then-dismissed. It can simply
  never be submitted. Detailed below.
- **v1.2 (the convergence loop):** the *timing* is equally unconstrained. If findings only count when uploaded, the
  entire fix-and-re-review cycle can run locally and the server can be written to once, on the pushed state. That is
  STEP 4.6.

The two share a hazard and it is the same one: local means invisible. A wrong withhold and a fix that only *looks*
applied both leave no server trace. The gates and the ledger's facts-not-verdicts rule are the two answers to it.

The withhold half in detail:

- **What changed:** invalid + out-of-scope findings are **withheld pre-submit**, recorded in
  `./review-artifacts/withheld-findings.md`, and never posted. Only valid + in-scope findings are uploaded.
- **What did NOT change:** `reject_comments` remains the only way to dismiss findings **already on the server** — prior
  rounds, re-raised findings, human-posted ones. On a re-review both mechanisms are live.
- **What the capability does NOT license.** Being able to drop a finding for free is not a reason to drop more of them.
  The classification bar went *up*, not down: validity is judged first-hand in the main thread before scope is even
  computed, then intent last of all, **every finding gets real code opened for it**, `VALID` requires a positive citation of
  what makes the defect real, `INVALID` requires a refutation citing real code, and `intent-satisfied` requires a quoted
  acceptance criterion plus proof the finding alleges no mechanism failure. Withholding is invisible to the server, the review email,
  `distill_lessons`, and the next reviewer — so a wrong withhold produces **no signal that it happened**. That silence is
  the one failure mode this gate can introduce that the old post-then-reject loop could not, which is why the burden of
  proof is heaviest on withholding and uncertainty resolves to SUBMIT.
- **Nor does it license the opposite shortcut.** "Uncertainty resolves to SUBMIT" is a rule about what to do *after*
  reading, not a licence to submit unread. Submitting everything unverified is cheap, produces an output line identical
  to a fully verified gate, and hands the developer exactly the noise this step exists to remove — so the gate reports
  `code opened for <N>/<N>` and that count, not the SUBMIT/WITHHOLD split, is what says whether it ran.
- **Two consistency traps.** (1) Filtering the findings array without recomputing `total` / severity counts / score
  submits a self-contradicting object. (2) The review-results `send_email` (server gap #4) already receives a truncated
  stub, so its numbers must be substituted from the **post-withhold** submission, not the raw file.
- **Read the withheld file at STEP 0 on a re-review** — otherwise round N+1 re-derives the same false positives from
  scratch and the written reasons are wasted. Read its **follow-up table** too: a deferred finding is still OPEN on the
  server and will come back, and it must not be mistaken for a re-raised false positive.
- The classification buckets and the 3-line TOLERANCE deliberately mirror `/fix-review-findings` Steps 2–3, so the same
  finding classifies identically whether it is caught pre-submit here or post-submit there. **PASS C has no counterpart
  there** — `/fix-review-findings` operates on findings already on the server, where deferring is expressed by leaving a
  finding OPEN rather than by routing it, and where nothing may be dropped on intent at all.

## Why PASS C was added (and why it is shaped the way it is)

PASS A and PASS B answer "is this real?" and "is this ours?". Neither answers "is fixing it *here* the right move?" — so a
valid in-scope finding whose minimum fix changes a shared signature reachable from two other repos arrived at the fix gate
looking identical to a one-line null guard, and the radius only surfaced once someone started editing. PASS C moves that
measurement before the gate, where it is a routing annotation the human can act on.

Its withhold bucket exists for a narrower and rarer case: a reviewer that has not seen the specification objecting to the
specification. That is a genuine class of false signal, but it is also the most dangerous licence in the runbook, because
"this was intentional" is available to justify withholding almost anything. Hence the shape: **C1 can never withhold, C2
requires a verbatim criterion, high/critical and correctness/security/data-integrity findings are categorically ineligible,
silence is never exclusion, a convention finding always survives, and with no session brief the bucket does not exist at
all.** If a round finds itself reaching for `intent-satisfied` more than once, the correct conclusion is that the pass is
being misused, not that the reviewer misread the spec repeatedly.

## Server-side gaps observed (PR #371, GEN-3357 — 2026-07-30)

Recorded for retrieval, **not** raised upstream. We drive around these; we do not fix or patch the server. If a future run
sees one of them repaired, delete the entry.

1. **`pr` object carries no `body`.** Confirmed independently from two nodes (the code_review coordinator's "Repo + PR
   Context" block and the send_email workflow context). Reviewers therefore never see the PR description. This is the gap
   the **CONTEXT BRIEF** section exists to fill.
2. **Specialist prompts reference artifact files the server never creates.** The 5 specialist prompts each say to read
   `./review-artifacts/artifact-1.patch` and `artifact-2.patch`, but no returned step creates them and the directory did
   not exist. Workaround: split `local-diff.patch` per component into those paths before running the node, so the
   specialists see 100% of the diff instead of failing their reads. Disclose the split when reporting. *(v1.1: still do
   the split if you pass those paths through; the fan-out also lets you hand each subagent the diff path directly, in
   which case the gap is moot — say which you did.)*
3. **No `--allowedTools` flag in the code_review bash block** — see the Development Rules Gate caveat above. Specialists
   cannot reach `get_development_rules`; the coordinator can. *(v1.1: no longer bites — the fan-out's subagent types
   carry the tool in their own whitelist. The server's block is still unrepaired; we route around it.)*
4. **The review-results `send_email` node gets the findings truncated.** Its workflow context contained
   `"code_review": {"__truncated": true, "sizeBytes": 14434}`, yet its instruction demands "overall score, number of
   findings by severity, and key issues found". Substitute the real submitted results (score / stats / finding titles) in
   place of the stub or the email to ~11 recipients is vacuous. Keep the instruction, output contract, and formatting rules
   verbatim; replace only the truncated stub.
5. **`claude -p` on the code_review node is flaky — expect retries.** *(v1.1: the code_review node no longer runs this
   way, so this entry now applies to the send_email / distill_lessons blocks — and stands as the primary reason the
   code_review node moved to an in-thread fan-out.)* Three consecutive failures with
   `API Error: Connection closed mid-response` (exit 1) before the 4th attempt succeeded. The failures landed at *different*
   points (after spawning specialists; during dev-rules fetch), i.e. connection instability, not a deterministic bug.
   Retrying is safe **provided the heartbeat is alive** — `mh_review_status` kept reporting
   `workflowExecutionStatus: RUNNING` / `devActionState: AWAIT_RESULT` across all attempts, so no restart of
   `mh_start_review` / diff-upload / `report_checkout` was needed. A failed attempt writes its error text into
   `<outputFile>`; copy it aside before retrying so the evidence survives.
6. **GitNexus reads the registered repo path, not your checkout — and which tool that breaks FLIPS with
   `CHECKOUT_MODE`.** GitNexus resolves a repo by its registered absolute path. That single fact produces opposite
   failure modes in the two modes, so the mitigation is not the same in both. **In neither mode do you get both tools
   for free — check which one you are in before citing either.**

   | | `worktree` mode (registered path = the *main* checkout) | `main` mode (registered path = the checkout you are fixing in) |
   |---|---|---|
   | change-scope detection | `git diff` is the only authority — the code index never sees your dirty working copy. | `git diff` remains the authority. |
   | impact / blast radius (reposphere callers) | **Trustworthy.** The indexed tree is genuinely pre-edit state, which is exactly what a blast radius needs. | **May describe your own change back to you.** If the index has picked up the PR branch, the reading is no longer pre-edit — verify against the base branch before citing. |

   **Mitigation by mode:**
   - `worktree` — use the reposphere callers check (pre-edit indexed tree) plus an explicit `git diff` for scope.
   - `main` — use `git diff` for scope, and treat indexed impact readings as **advisory only**. To get a genuine radius,
     compute it against the base: `git -C {{CHECKOUT}} stash` → run `impact` → `git stash pop`, **or** simply state in
     the gate that the radius was not independently verified. Do not silently present a contaminated reading as clean —
     that is the specific way this gap loses a real defect.

   Mode detection and the reasoning behind it: `./checkout-modes.md`.

## Server-side gaps observed (PR #422, GEN-3426 — 2026-08-11)

7. **`STILL_OPEN` on the immediately-preceding review's comments comes back as `RESOLVED`. This one loses real defects —
   check it every round.** Round 1 submitted two `high` entries as `resolution: "STILL_OPEN"` with the live code quoted as
   evidence. The server accepted the payload (it kept both `updatedLine` values, 107 and 119), re-emitted them as
   `carried-<fingerprint>` findings, **and stamped both `RESOLVED`** — while the *scoring* path charged them as 2 carried
   highs (−1.5). The two subsystems disagreed: the scorer treated them as open, the comment store closed them. Nothing had
   been fixed; both defects were still in the file.

   The 9 `STILL_OPEN` entries from an **older** review in the same submission stayed correctly `OPEN`, so this is specific
   to the entries carried from the immediately-preceding review, not to the payload shape.

   **Consequence: a wrongly-`RESOLVED` finding will not reappear on the next round, and it flatters the score** (a closed
   entry stops being charged). This is the same silent-loss class the withhold gate is built to prevent, produced by the
   server rather than by the gate.

   **Mitigation — do this at GATE 3, after submitting:** re-read the board with
   `get_open_comments({pullRequestId, includeStatuses: ["OPEN","WONT_FIX","RESOLVED"]})` and diff its statuses against the
   `openCommentsResolvedJson` you sent. For every entry you sent as `STILL_OPEN` that came back `RESOLVED`, say so
   explicitly and **raise a follow-up ticket immediately** — the ticket becomes the only surviving record. Never treat the
   server's `RESOLVED` as evidence a defect is fixed; your own first-hand read is the authority.

8. **`findingsCount` and the UI both include carried findings, so "I submitted 1" and "the board shows 14" are both true.**
   Every `STILL_OPEN` entry is re-materialised as a `carried-<fingerprint>` finding attached to the new review. A round
   submitting 1 new finding reported `findingsCount: 14` and the open list showed 12. Explain this proactively — the
   author otherwise reads the carried tail as findings the review just raised against their change.

---

## NOT a server gap — a wrong PR base permanently pollutes the board

**Recorded here because this was first misdiagnosed as a server gap, and the wrong diagnosis leads to the wrong fix.**

On PR #422 the board carried 11 findings describing another ticket's files. The server did nothing wrong and no
calculation was wrong: **the PR had been opened against the wrong base branch**, so at that moment its computed diff
genuinely spanned the other ticket's merged work, and the review correctly raised findings on the code it was given.
Correcting the base afterwards removed those files from the diff but left their findings attached to the PR — where they
cost carried debt (½ weight, rubric section) every subsequent round on a PR that cannot possibly fix them.

So the failure is **upstream of this runbook**: a base-branch mistake at PR creation, not a review-protocol defect.

**Precondition (cheap, prevents all of it).** `mh_start_review` reports `baseRef`. Before STEP 2, confirm it is the base
the change is actually meant to merge into — and confirm the change set it implies is only this ticket's files:

```
git -C {{CHECKOUT}} diff --merge-base origin/<reported baseRef> HEAD --stat
```

If that `--stat` lists files belonging to another ticket, **stop and surface it before reviewing.** The base is wrong, or
the branch was cut from the wrong place. Reviewing anyway puts findings on the board that no round of this PR can ever
resolve. Note the runbook's `BASE_REF` default (`develop`) is only a default — **the server's reported `baseRef` wins**,
and on PR #422 it was `main`.

**Once the board is already polluted, two lawful exits:**

| Exit | Cost | When |
|---|---|---|
| `reject_comments` each stale finding, reason naming the PR the code really belongs to | cheapest; keeps review history; carried debt disappears next round | the base is now correct and only the findings are stale |
| Close and re-open as a fresh PR against the right base | clean board, but every in-diff defect returns at **full** weight instead of ½ | the base itself is wrong, or the board is too polluted to be worth 9+ rejections |

PR #422 took the fresh-PR route: with the base wrong at creation, a correct board mattered more than the score, and
re-opening fixes the cause rather than the symptom. **Neither exit is a way to move the number** — see the rubric
section, where a fresh PR scores *worse* (~6.2 vs ~9.6) precisely because it re-prices real defects at full weight.
