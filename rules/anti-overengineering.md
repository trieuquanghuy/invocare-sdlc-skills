# Anti-Overengineering — Proportionality of Code, Thought, and Process

Applies to every task in this project, by the main agent or any dispatched subagent. Cited from `CLAUDE.md` so all skills inherit it.

The other rules say what good work looks like; this one says how much work a task deserves. The failure it targets is disproportion: a small task answered with a big diff, a long investigation, a pile of process, or all three. The test throughout is the same one `code-quality.md` CQ4 uses — *would a senior engineer looking at this say "that's more than the job needed"?*

This rule **cross-links, never restates**: `engineering-conduct.md` EC2 (simplicity) and EC3 (surgical) own code minimalism; `code-quality.md` CQ4–CQ6 own KISS/YAGNI/SOLID restraint; EC6 owns cost-ballooning disclosure. This file adds the sizing discipline that ties them together and the two gaps they don't cover: **overthinking** and **process proportionality**.

---

## AO1 — Size the task before you start, and let that size govern everything

Before acting, classify the task in one silent judgment call:

- **Trivial** — typo, one-line config read, cosmetic tweak, a question answerable from one file. Deserves: direct action, no plan, no fan-out, minimal prose.
- **Standard** — a normal bug fix or small feature with a known shape. Deserves: the mandatory gates (code-lessons, dev-rules), a focused read of the touched code, a surgical diff.
- **Complex** — cross-repo blast radius, unclear root cause, prod risk. Deserves: real investigation, impact analysis, checkpoints.

Then hold that size. The most common failure is drift: a task classified trivial that quietly accretes standard-sized investigation, or a standard fix that grows a complex-task plan. If mid-task you find the size was genuinely wrong, say so in one line and re-size — deliberate escalation is fine; silent drift is not.

Mandatory gates (code-lessons, dev-rules, firebase-safety, git-safety) are never skipped or downgraded by this rule — classifying a task "trivial" does NOT move a change onto a gate's skip list; only the gate's own skip list can exempt it. If a change touches executable code, the code-lessons and dev-rules gates run at full coverage regardless of AO sizing. AO governs the *optional* effort around the gates (investigation depth, planning, fan-out, reporting), never the gates themselves.

## AO2 — Build the minimum that solves the stated problem (code)

EC2/CQ4 are the authorities; this adds the sizing checks reviewers actually flag.

**The reuse ladder — stop at the first rung that holds.** The best code is the code never written. Before writing anything, after you understand the problem (never instead of understanding it — read the task, read the code it touches, trace the real flow end to end):

1. Does this need to be built at all? (YAGNI)
2. Does it already exist in this codebase? Reuse the helper, util, or pattern that's already here — don't re-write it.
3. Does the standard library already do this? Use it.
4. Does a native platform feature cover it? Use it.
5. Does an already-installed dependency solve it? Use it. (A *new* dependency is not a rung — avoid it unless nothing above holds.)
6. Can this be one line? Make it one line.
7. Only then: write the minimum code that works.

**Bug fix = root cause, not symptom.** A report names a symptom. Find the callers of the function you touch (reposphere first, per `code-search.md`) and fix the shared function once — one guard there is a smaller diff than one per caller, and patching only the path the ticket names leaves a sibling caller still broken. The smallest change in the wrong place isn't lazy, it's a second bug.

Concrete checks:

- No abstraction, interface, wrapper, or config knob with exactly one caller/value today. Add it when the second case arrives.
- No handling of inputs that cannot occur in this codebase ("defensive" branches for states upstream code already prevents). Handle the empty/null/error paths that *can* occur (CQ1) — that's correctness, not gold-plating.
- No "flexible" data shapes (maps of options, plugin hooks, strategy params) for a requirement stated in the singular.
- The diff should be explainable in one sentence. If your done-summary needs a bulleted architecture tour for a bug fix, the fix is too big.
- When the request hints at hypothetical future needs ("we may eventually…", "keep in mind we might…"), build for today's stated need and *mention* the future option in the summary instead of coding for it. Speculative flexibility coded now is the most common over-engineering vector.
- Prefer deletion over addition, boring over clever, fewest files possible. When two same-size approaches differ only in edge-case correctness, pick the edge-case-correct one — minimal means less code, not the flimsier algorithm.
- Question complex requests before building them: "do you actually need X, or does Y cover it?" A simpler reframe offered early beats a big diff rewritten later (EC1).
- A deliberate simplification that cuts a real corner with a known ceiling (a global lock, an O(n²) scan, a naive heuristic) gets a one-line comment naming the ceiling and the upgrade path — that's a constraint the code can't show, so it passes `code-comments.md` CC1.

**What minimalism never trims.** Lazy means efficient, not careless. Not negotiable, regardless of task size: understanding the problem before choosing an approach; input validation at trust boundaries (CQ3); error handling that prevents data loss (CQ1); security; accessibility; anything explicitly requested. And non-trivial logic leaves one runnable check behind — the smallest thing that fails if the logic breaks (a small test file or an assert-based self-check; no frameworks or fixtures needed). Trivial one-liners need no test.

## AO3 — Think in proportion to the stakes (overthinking)

Investigation and reasoning are budgeted by what a wrong answer costs, not by what's interesting:

- Once you have enough evidence to act safely, act. A second confirming source is worth fetching when the write is risky (prod, shared config); it is waste when the change is reversible and cheap to verify after the fact.
- Don't re-derive what's already established — in the conversation, the ticket, the RCA, or a memory. Re-verification is for stale or load-bearing facts, not a ritual.
- Cap option-analysis: when two approaches are both adequate, pick the simpler one and move — don't write a comparison essay the user didn't ask for. Surface a real trade-off only when the user must decide it (EC1).
- If you notice loop behavior — re-reading the same files, re-running near-identical queries, expanding a search past the original scope — that's the EC6 signal: stop, summarize what you have, and either act or ask.
- RCA investigations have their own stop rule (`create-rca` Step 4b): one confirming Evidence row per claim, stop at the first confirmed root cause that explains the full symptom, adjacent anomalies become Open Questions — an honest `UNRESOLVED` with a precise Open Question beats an endless query loop.

## AO4 — Match process weight to task weight (process)

Skills, subagents, plans, and checklists are tools with a cost, not virtue signals:

- No subagent fan-out for work one context can do in a few reads. Dispatch parallel agents when the work is genuinely independent and sizable, not to look thorough.
- No plan documents or multi-phase todo scaffolding for a trivial or standard task — a plan is for work whose steps you'd otherwise lose track of.
- No speculative artifacts: don't produce specs, diagrams, migration docs, or test scaffolds that the task didn't ask for and the next step doesn't need. Offer them; don't build them.
- Verification is proportional too: verify what the change actually risks (EC9, `verification-before-completion`), not every property of the system.

## AO5 — Report in proportion to what happened

A one-line fix gets a short summary: what changed, gates run, how it was verified. Long enumerations, restated diffs, and section-headed reports for small tasks are the prose form of over-engineering. (Format authority: the harness's own output guidance and `output-guardian.md` for external artifacts.)

---

## Scope

Applies to all skills (`.claude/skills/**`), all dispatched subagents (the dispatcher binds the dispatched, per `agents-safety.md`), and both code and config-ops work. It never relaxes a mandatory gate or safety rule — where a safety rule demands effort (session logs, dry-runs, per-write approval), the safety rule wins. This rule trims the *discretionary* effort, not the required kind.
