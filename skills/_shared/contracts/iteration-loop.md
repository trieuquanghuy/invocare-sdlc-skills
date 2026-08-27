# Shared Checker Iteration Loop

This file defines the standard 3-iteration verification loop used by artifact-generating skills (`create-rca`, `create-spec`, and any future skill that drafts content and verifies it via a checker subagent before saving).

> **Source:** referenced by `create-rca/SKILL.md` Step 7 and `create-spec/SKILL.md` Step 4. Keep in sync.

The loop is NOT used by pre-flight gates (`apply-fix`, `create-pr`, `ticket-comment`, `publish-rca`) — those run the checker ONCE and stop on FAIL. Pre-flight gates auto-fix nothing because their job is to refuse, not to refine.

---

## Loop body

The dispatching skill drafts an artifact in memory (NOT yet saved to disk), then runs:

```
iteration = 1
previous_gap_signature = null

loop:
  1. Dispatch the checker subagent with the current draft.
       — iteration 1: full rubric.
       — iteration 2+: SCOPED re-check (see below) — verify only the rules that
         failed last iteration, against the sections that changed.
  2. Parse the JSON result. Expect: { verdict, gaps[], iteration_hint, ... }.
  3. Print iteration_hint to the user (e.g. "Iter 1: 3 gaps remaining — applying fixes...").
  4. If verdict == PASS:
       → exit loop with final_classification = CLEAR.
  5. Compute current_gap_signature = sorted list of (rule, issue) pairs from gaps[].
  6. If current_gap_signature == previous_gap_signature AND iteration > 1:
       → early-out. Auto-fixes aren't converging.
       → exit loop with final_classification = quality=FAIL.
  7. For each gap with fixable: true:
       → apply suggested_fix to the draft.
  8. MECHANICAL-FIX SHORT-CIRCUIT: if EVERY gap this iteration was
     (fixable: true) AND (severity: warning or info) AND every suggested_fix
     was applied verbatim (pure text substitution — no judgment, no fresh data):
       → self-verify each fix landed (re-read the changed lines; per agents-safety
         A3 this is the same verification the skill owes any claim), then
       → exit loop with final_classification = CLEAR, noting in the done-summary:
         "iter {N} gaps were mechanical; fixes self-verified, checker not re-dispatched".
     Any blocker-severity gap, judgment-requiring fix, or partially-applied fix
     disqualifies the short-circuit — those need a real re-check.
  9. previous_gap_signature = current_gap_signature.
  10. iteration += 1.
  11. If iteration > 3:
       → exit loop with final_classification = quality=FAIL.
  12. Otherwise → goto step 1.
```

### Scoped re-check (iteration 2+)

A full re-dispatch re-reads the template, rules, source artifacts, and the entire draft — expensive and mostly redundant when iteration 1 already validated the rest. On iteration 2+, the dispatch prompt MUST name the scope:

> Re-check ONLY these rules against this draft: {list of rules that failed last iteration}. The remaining rubric passed on the previous iteration and the only changes since are: {one-line list of applied fixes}. Do not re-verify passing rules; do not re-run spot-check queries that already matched.

The checker still returns the standard JSON. If a fix plausibly ripples beyond its rule (e.g. a section was deleted — heading structure changed), include the affected structural rule (Q6/S-structure) in the scope list. This typically cuts iteration-2 cost by 60-80% while keeping the verification honest.

---

## Final-classification semantics

| `final_classification` | Meaning | Caller behavior |
|------------------------|---------|-----------------|
| `CLEAR` | verdict=PASS on the most recent iteration | Save artifact, proceed to next pipeline step |
| `quality=FAIL` | verdict=FAIL after 3 iterations OR early-out on stuck gaps | Save artifact, ALSO write `tickets/{TICKET_KEY}/QUALITY-REPORT.md` listing every gap from the last iteration. Do NOT proceed to the next pipeline step — print the QUALITY-REPORT path and require user review. |
| `readiness=UNRESOLVED` (create-rca only) | verdict=PASS but the rca-checker emitted readiness=UNRESOLVED | Save artifact with an appended `## Open Questions` section. Do NOT proceed to create-spec. (See create-rca/SKILL.md Step 7 for the formatted question block.) |

---

## QUALITY-REPORT.md format

When `final_classification == quality=FAIL`, the dispatching skill writes:

```markdown
# Quality Report — {TICKET_KEY}

**Skill:** {skill name}
**Run:** {DATE}
**Final classification:** quality=FAIL

## Open gaps after 3 iterations

- [{rule}] ({severity}) — {issue}
  Suggested fix: {suggested_fix or "n/a — not auto-fixable"}
  Reason not applied: {why fixable=false, or "stuck — same gap returned across iterations"}
```

The QUALITY-REPORT serves as the input the user reads before re-running the skill or hand-editing the draft.

---

## Why early-out matters

If two consecutive iterations produce the same gap signature, the auto-fix logic isn't converging — typically because:

- The fix mechanically applies but the rubric's check is broken (false positive).
- The fix introduces a different gap that the next iteration fixes, undoing the first fix (oscillation).
- The gap requires fresh data (`fixable: false` was misclassified as `fixable: true`).

Early-out at iter 2 prevents wasting iter 3 and surfaces the convergence failure to the user faster. The hardcoded cap of 3 iterations is a backstop — early-out usually fires first.

---

## What the dispatching skill MUST do

1. Pre-check the Quality Bar before the first dispatch (skill-specific Step Nx.b "self-check"). Cheap pre-filter; saves wasted iterations on obvious gaps.
2. Print `iteration_hint` between iterations so the user can follow progress.
3. Save the (possibly-amended) draft AFTER the loop exits — never inside the loop.
4. Honor `readiness=UNRESOLVED` (create-rca only) by appending `## Open Questions`.
5. On `quality=FAIL`, write QUALITY-REPORT.md AND save the (gap-laden) draft so the user can see what was attempted.
