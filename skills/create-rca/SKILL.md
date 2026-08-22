---
name: create-rca
description: "Use when investigating a Jira ticket (bug or feature story) to produce an RCA at tickets/{KEY}/rca.md. Symptoms: ticket key like GEN-XXXX or FIR-XXXX, request to analyze root cause, investigate broken behavior, or gap-analyze a feature story before spec."
argument-hint: "Jira ticket key (e.g. GEN-2759) or describe the issue"
disable-model-invocation: true
---

# Create RCA

Produce an RCA document for a Jira ticket following the team's standard format — used for both bugs and feature stories. Output goes to `tickets/{TICKET_KEY}/rca.md`.

**The local `rca.md` must reflect the CURRENT state of the system.** Analyses written by others may be outdated — always verify evidence against live Firebase data before using it for `create-spec` or `apply-fix`.

**Output guardian:** all output reads as written by a developer. Apply `.claude/rules/output-guardian.md` — never include tool names, session IDs, or any indication of automation.

**Firebase safety:** apply `.claude/rules/firebase-safety.md` — this skill is read-only against Firebase. NEVER call write_rtdb / write_firestore / create_session. Every Evidence row must label its DB (RTDB or Firestore) explicitly.

**Secrets safety:** apply `.claude/rules/secrets-safety.md` — if any query or attachment surfaces a secret-looking value, redact before continuing; never paste config dumps into rca.md.

**Agent safety:** apply `.claude/rules/agents-safety.md` — the rca-checker subagent (Step 7) is read-only, returns structured JSON, the iteration loop escalates after 3 rounds without convergence.

## NOT This Skill If

The user wants to understand a feature's architecture or blast radius with no ticket attached — use `/impact-analysis` instead.

---

## Step 0: Determine Starting Point

**Always fetch the Jira ticket first** — it provides current status, assignee, latest comments, and any environment-specific details.

**Status guard — exit early if ticket will not be fixed.** Before any further work, check the ticket's `status` and `resolution` fields. If either matches a rejection outcome below (case-insensitive), STOP. Do NOT query Firebase, run reposphere, read code, or write any file. No RCA is needed for a ticket that won't be fixed.

Rejection outcomes:
- Status: `Rejected`, `Reject`, `Won't Do`, `Won't Fix`, `Wontfix`, `Cancelled`, `Canceled`, `Duplicate`, `Invalid`, `Not a Bug`
- Resolution: `Won't Do`, `Won't Fix`, `Duplicate`, `Cannot Reproduce`, `Incomplete`, `Invalid`

Print exactly this one-liner and exit — do NOT print the "Next step" footer:

```
{TICKET_KEY} status is "{STATUS}" (resolution: {RESOLUTION_OR_"none"}). No RCA produced — ticket will not be fixed.
```

Then check for existing analysis:

| State | Route |
|-------|-------|
| No `tickets/{TICKET_KEY}/rca.md` and no Confluence RCA page | → Step 1: Full investigation |
| Existing RCA found (local file or Confluence) | → Step 0b: Verify currency |

Search Confluence: `searchConfluenceUsingCql(cql: 'title ~ "{TICKET_KEY}" AND type = page')`

---

## Step 0b: Verify Currency of Existing RCA

Read the existing RCA in full. Then verify each factual claim against the **current** live environment.

**For every Firebase path in the Evidence section:**
- Re-query via firebase-explorer against the environment the ticket refers to (dev by default; UAT/prod if ticket explicitly states it)
- Compare current DB state vs what the RCA claims

**Check Jira for updates since the RCA was written:**
- New comments, status changes, or linked tickets added after the RCA date

**Classify:**

| Result | Meaning | Action |
|--------|---------|--------|
| `CURRENT` | All evidence matches live data, no new Jira context changes the analysis | Save as-is → Step 6 |
| `PARTIALLY_STALE` | Some paths or field values have changed but root cause still holds | Update stale sections → Step 5 |
| `OUTDATED` | Core data has changed — root cause may be wrong | Re-investigate from scratch → Step 1 |

State the classification explicitly: `RCA verified CURRENT as of [DATE]` or `RCA PARTIALLY_STALE — updated sections: [list]`.

---

## Step 1: Gather Context from Jira

Extract from the Jira ticket:
- Title, reporter, description, acceptance criteria
- Reported symptoms (bug) or requirements (story)
- Which entity types, teams, or config paths are involved
- Environment specifics (dev / UAT / prod)
- Any attachments, screenshots, or linked tickets — note filenames and what they show; they are evidence for the RCA

**Attachment-readability guard.** If an attachment looks relevant to the investigation (referenced in the description, named like `error-*.png`, `payload.json`, `export.pdf`, etc.) and its content is NOT already described in the ticket text or comments:

1. Try to fetch it via the Atlassian MCP first.
2. If the fetch returns binary content the MCP cannot surface (image, PDF, .docx, .xlsx, .zip), STOP and ask the user:

   ```
   {TICKET_KEY} has attachment "{FILENAME}" that I cannot read directly. To continue the RCA, please either:
     a) Paste the relevant content / describe what it shows in this chat, OR
     b) Download it and drop it at a local path (e.g. tickets/{TICKET_KEY}/attachments/{FILENAME}) and tell me the path.
   ```

3. Do NOT invent a description like `[screenshot shows X]` or `[PDF contains Y]` — fabricated attachment content violates the Evidence rule in the Quality Bar and breaks the spec downstream.

If Atlassian MCP is unavailable: note `Jira ticket not fetched — working from user description`.

---

## Step 2: Query Firebase

Firebase is the **source of truth**. Query via firebase-explorer MCP (read-only — never write here).

**Always specify the database.** The project has two: Realtime Database (RTDB) and Firestore. Paths can look identical across both — using the wrong one silently returns wrong data.

**Consult the DB map first.** Check whether `.claude/skills/_shared/references/firebase-db-map.md` exists.

**If the map file does NOT exist** (fresh clone, new teammate hasn't bootstrapped yet, etc.): skip the consult/staleness/append logic and fall back to the pre-map behavior — for each path, query both DBs with `query_rtdb` and `query_firestore`, use whichever returns data. Print a one-line note: `Note: firebase-db-map.md not found; falling back to live probe per path. Consider downloading the map via the team's onboarding flow.` Continue.

**If the map file exists:** look up the path. First, glance at its `Last refreshed:` header — if the date is >60 days old, ask the user `The Firebase DB map was last refreshed {DATE} ({N} days ago); refresh before using? (yes/no)` and only proceed after confirmation. If the path is listed, use the stated DB tool (`query_rtdb` / `query_firestore`). If the path is NOT listed, query both DBs to find which holds the data, then append a row to the `## Discovered paths` section of that file (`path | DB | first-seen | last-verified | source: {TICKET_KEY}`) so the next investigation skips the guess.

Use the environment the ticket refers to. Default: `dev`. Switch to `uat` or `prod` only if the ticket explicitly states the issue occurs there.

**Rules:**
- Record every path queried — successful or not
- If a path returns nothing, write `not found` — never guess
- Most InvoCare issues are `CONFIGURATION_GAP` — check config paths before code

---

## Step 3: Cross-Validate with Elasticsearch

Use the **same environment as Firebase** (default: `dev`). Query only indices relevant to the investigation:

| Index | When to query |
|-------|---------------|
| `form-exports` | Confirm form filename, path, exportUrl matches Firebase config |
| `form-fields` | Check whether expected field keys exist |
| `file-exports` | Look up previous export artifacts by `entityId` |
| `form-overrides` | Check team-level form overrides |
| `clients` / `events` | Verify entity data when Firebase lookup is ambiguous |

---

## Step 4: Inspect Code Paths

**Search with reposphere first.** Before reading files directly:

1. **Broad concept search** (don't know which repo yet):
   - `cross_repo_search({query: "concept"})` — semantic search across all repos

2. **Targeted search with call graph** (know which repo):
   - `search_with_context({query: "concept", repo: "FCRM-Exports-API"})` — returns semantic hits + callers/callees/data co-accessors in one call

3. **Deep traversal** (have a node ID from step 1 or 2):
   - `explore_neighborhood({node_id: "...", repo: "...", hops: 2})` — walk the call graph outward

Only fall back to direct file reads when a symbol isn't in the graph.

| Layer | Where to look |
|-------|---------------|
| Frontend | `FCRM-Web/src/app/` — Angular components, services, routes |
| API Gateway | `FCRM-Cloud-App/` — Express routes and middleware |
| Cloud Functions | `FCRM-Cloud-Functions/` — function exports, triggers, indexers |
| Search API | `FCRM-Search-API/` — Elasticsearch query builders |
| Exports API | `FCRM-Exports-API/src/` |
| Reports API | `FCRM-Reports-API/` — Puppeteer PDF, Cloud Tasks |
| Email API | `FCRM-Email-API/` — Postmark/Mandrill dispatch |
| Barndoor | `Barndoor-*-App/` — NestJS controllers, RabbitMQ consumers |
| Shared libs | `fcrm-entity-manager/`, `FireHawk-AuthCheck/` |
| Templates | `document-templates/` — Twig + CSS |

Read enough code to confirm whether the behavior is a **code defect** or **config-following**.

---

## Step 5: Write the RCA

Read [rca-template.md](./references/rca-template.md). Follow its section structure exactly for all ticket types (bugs and stories) — the nine numbered sections plus the unnumbered Sources Investigated, Executive Summary, and Open Questions sections.

**Bug vs Story differences (same outer structure):**
- Section 2: "Steps to Reproduce" (bug) — "Acceptance Criteria" (story)
- Section 3.1: "Primary Root Cause" + defect analysis (bug) — "GAP ANALYSIS" + scope (story)
- Section 3 classification: `CONFIGURATION_GAP` / `CODE_DEFECT` / `DATA_MAPPING_GAP` (bug) — `NEW_FEATURE` (story)
- Story track also requires Step 5b (Story-specific rigor) below — the gap-survey shape needs extra discipline that the bug Quality Bar doesn't enforce

**Section reference:** "Status History" (referenced in Quality Bar Q11 and Common Mistakes) is the template section that captures Jira status transitions and real-world actions — never Firebase session IDs, session numbers, or internal tool references.

**Rules:**
1. Replace every `[PLACEHOLDER]` with real data from this investigation
2. Evidence JSON uses real DB keys only — no synthetic fields
3. Include Firebase path for every evidence block
4. State expected correct behavior: `When [condition], [field] should be [expected state]` — describe the correct outcome, not how to fix it
5. Remove the `## IMPORTANT RULES` block before saving

---

## Step 5b: Story-specific rigor (NEW_FEATURE only)

Skip this step for bug-track RCAs (`CONFIGURATION_GAP` / `CODE_DEFECT` / `DATA_MAPPING_GAP`). For stories, three additional disciplines apply on top of the Step 5 rules — a story's failure mode is silent under-investigation, not visible defect, so the rigor lives here rather than in the universal rubric.

1. **Verify "existing state" before stating the gap.** A story RCA must not claim "X is missing" without first showing what IS in place. For every Gap row in Section 3.1, the Evidence Summary must include at least one paired row capturing the live state of the surrounding schema / code / collection — so the gap is anchored, not a misread. Example: claiming a new field is missing from a form schema requires an Evidence row enumerating the fields that DO exist at that schema path, not just a `not found` lookup of the new field's expected key.

2. **Every Gap row records its search.** When asserting absence ("does not exist", "not found", "no integration matches"), the Gap row must state both (a) what was searched and (b) which keyword / path / collection was used. A single grep with a single keyword does not satisfy a missing-state claim — use **≥2 keyword variants** (exact term + a semantic neighbour) and cite both. This is exactly what the checker spot-checks for stories under "Missing-state under-searched".

3. **Deferred attachments become Open Questions.** If an attachment is referenced in a comment under active design discussion (e.g. a proposed-solution mockup) and the RCA defers reading it, the deferral generates an `## Open Questions` entry naming the attachment and the resolution path — not a free-pass mention buried in an Evidence row.

Step 5b pairs with Q12 in the rubric (stakeholder claims). Together they protect against the most common Story RCA failure modes: fabricated existing-state references, under-searched absence claims, and stakeholder counts accepted as fact.

---

## Step 6: Estimate Effort

Use the story points scale from the template:

Provide **Normal estimate** and **Worst case estimate** with one-paragraph rationale each. Base on: number of files/configs to change, integration points, testing surface area, clarity of requirements.

---

## Step 6b: Self-check the Quality Bar

Before dispatching the checker, walk every item in this skill's Quality Bar against your draft. For each item:

- If it passes, move on
- If it fails AND the fix is mechanical (e.g. "DB column missing — infer from path table"), apply it now
- If it fails AND requires fresh data or judgment, leave it for the checker

This pass typically takes 30 seconds and prevents 1–2 wasted checker iterations on obvious gaps. The checker is the authority — this is just a cheap pre-filter.

---

## Step 7: Verify with rca-checker

After drafting the RCA in memory (do not save yet), gate the artifact through the checker subagent. Run the standard iteration loop defined in `.claude/skills/_shared/contracts/iteration-loop.md` (3 iterations, early-out on stuck gaps, save QUALITY-REPORT on `quality=FAIL`).

1. Read `./checker-prompt.md` from this skill folder.
2. Dispatch a `pipeline-checker` subagent (`.claude/agents/pipeline-checker.md`) with:
   - The full prompt from `checker-prompt.md`
   - The draft rca.md content
   - Ticket key and environment
3. Parse the JSON result block per `.claude/skills/_shared/contracts/checker-contract.md`: `{ verdict, readiness, ticket_key, summary, iteration_hint, gaps[] }`.
4. Apply the iteration loop in `iteration-loop.md`. The loop's `final_classification` resolution for create-rca:

   | verdict | readiness | `final_classification` | Step 8 action |
   |---|---|---|---|
   | PASS | CLEAR | `CLEAR` | save rca.md |
   | PASS | UNRESOLVED | `readiness=UNRESOLVED` | append `## Open Questions` (format below), then save |
   | WARN | (any) | (treated as PASS) | save; surface warnings in the user summary |
   | FAIL (after 3 iters OR early-out on stuck gaps) | (any) | `quality=FAIL` | save + write `QUALITY-REPORT.md` |

The `## Open Questions` block format when `readiness=UNRESOLVED`:

```
## Open Questions

The following questions remain unresolved after investigation. Resolve them
(via UAT, user confirmation, or follow-up data pull) and re-run /create-rca
before generating a spec.

- **Q1:** <question text>
  **Why it matters:** <impact on root cause or fix>
  **How to resolve:** <suggested next action — UAT, user, query, etc.>
```

Each question is sourced from a gap with `rule` starting `Open Question —` in the final iteration's checker output.

The Quality Bar in this file is the rubric the checker enforces. Keep `checker-prompt.md` in sync when Quality Bar entries change. Between iterations, print `iteration_hint` from the checker so the user can follow progress (e.g. "Iter 1: 3 gaps remaining — applying fixes...").

---

## Step 8: Save and Summarize

Save the (possibly amended) draft to: `tickets/{TICKET_KEY}/rca.md`.

If `final_classification == quality=FAIL`: also write `tickets/{TICKET_KEY}/QUALITY-REPORT.md` listing every gap from the last checker iteration. Format:

```
# Quality Report — {TICKET_KEY}

**Skill:** create-rca
**Run:** {DATE}
**Final classification:** quality=FAIL, readiness={CLEAR|UNRESOLVED}

## Open gaps after 3 iterations

- [Quality Bar item] (severity) — issue text
  Suggested fix: text (could not be auto-applied because: reason)
```

End with a brief summary printed to the user:
- Starting point: fresh investigation or verified/updated existing RCA
- Root cause classification
- Estimated story points
- Final classification: CLEAR / UNRESOLVED / quality=FAIL
- (If UNRESOLVED) one-line summary of open questions
- (If quality=FAIL) pointer to QUALITY-REPORT.md

Then print the Next-step footer matching `final_classification` (see § Next step).

---

## Quality Bar

**Authoritative rubric:** `checker-prompt.md` (Q1-Q11) is the source of truth — the checker enforces those rules verbatim. The list below mirrors it for human-eye review during Step 6b; if the two diverge, the checker wins.

- [ ] Jira ticket fetched (or unavailability noted)
- [ ] Every factual claim backed by data queried in this run or verified against live DB
- [ ] Firebase paths included for every evidence block
- [ ] Missing data stated as `not found` — never guessed
- [ ] No Firebase console links in output
- [ ] Template structure followed exactly
- [ ] Existing RCA currency classified: `CURRENT` / `PARTIALLY_STALE` / `OUTDATED`
- [ ] Environment used for Firebase queries matches ticket context
- [ ] DB type (RTDB / Firestore) specified for every Firebase path in the Evidence table
- [ ] Screenshots / attachments from Jira noted where relevant
- [ ] Status History contains only Jira status transitions and real-world actions — no Firebase session IDs, session numbers, or internal tool references
- [ ] Stakeholder claims from comments (reporter / assignee assertions like "X exists", "N records of X", "Y works like Z", "the integration already exists", "we use M default values") are either confirmed/refuted by an Evidence row OR surfaced as an `## Open Questions` entry — never silently absorbed as fact (Q12)

---

## Red Flags — STOP and reconsider

If any of these thoughts surface, the next action is NOT what you were about to do. Pause and re-verify against live data.

- "The existing RCA was written last week, surely it's still current — skip Step 0b." → Step 0b runs every time; live config can change daily. Classify as CURRENT / PARTIALLY_STALE / OUTDATED before reusing any analysis.
- "The path query returned empty — I'll infer what the value should be from peer paths." → Q4. Write `not found` and add an Open Question; never fabricate.
- "The path looks like form-config, so it's RTDB — I'll skip the DB-type check." → `firebase-safety.md` + Q9. Specify DB explicitly per Evidence row; query both if ambiguous.
- "The ticket attached screenshots but the description is clear enough." → Step 1 attachment-readability guard. Referenced attachments are evidence; if you can't read them, ask the user — never invent `[screenshot shows X]`.
- "The ticket is marked Done, but I'll still write a fresh RCA in case it's useful." → Step 0 status guard. Done / Won't Do / Duplicate / Cancelled tickets exit early — no RCA needed.
- "I'll skip the rca-checker dispatch — the draft looks fine." → Step 7. The checker catches Output Guardian, DB-type, Evidence, and currency violations the author misses; the iteration loop runs up to 3 rounds.
- "Checker returned WARN — close enough to PASS, I'll save and move on." → WARN exits the loop but each warning must be surfaced to the user in the Step 8 summary.
- "I'll write 'the root cause is likely X' instead of running another query." → Readiness rule. Hedge phrases ("likely", "appears", "should be confirmed") trigger `readiness: UNRESOLVED` — resolve via query / user / UAT before declaring the RCA clear.
- "The ticket says prod but I'll query dev because dev is easier to access." → Q8. Mismatched env breaks the spec downstream; use the env the ticket specifies.
- "It's a Story, so the gap survey IS the analysis — I don't need to record what the existing schema looks like." → Step 5b rule 1. Without paired existing-state evidence, gap claims are unanchored and the story-track spot-check cannot verify them.
- "I grepped once for the exact product / library name and got zero hits, so the integration doesn't exist." → Step 5b rule 2 + story-track spot-check. Missing-state claims require ≥2 keyword variants; one grep with the exact term is not enough. The actual integration may live under a different name (an internal alias, a wrapping route, or a renamed dependency).
- "The reporter said the integration already exists, so I'll cite that as the answer to G6." → Q12. Stakeholder claims need either a confirming/refuting Evidence row or an Open Question — never quietly absorbed as fact.
- "The assignee proposed a list of default values — I'll copy them into the spec as the recommendation." → Q12. Counts and lists from comments are stakeholder claims; verify against the source data before citing.

---

## Common Mistakes

| Mistake | What to do instead |
|---|---|
| Trusting an existing local `rca.md` (or Confluence page) without re-querying live data. | Run Step 0b. Classify CURRENT / PARTIALLY_STALE / OUTDATED before reusing any analysis. |
| Writing `[screenshot shows error banner]` as a placeholder because the image couldn't be loaded. | Step 1 attachment-readability guard — STOP and ask the user to paste content or drop the file at a local path. |
| Querying `dev` when the ticket explicitly states the issue occurs in `uat` or `prod`. | Step 2. Use the env the ticket refers to; if cross-env data is needed, query both and label clearly. |
| Leaving the DB column blank in the Evidence table because "the path is obvious". | Q9 — RTDB / Firestore must be specified per row. If ambiguous, query both and confirm. |
| Inventing a synthetic field name to fill out an Evidence row when the real path returned empty. | Q4 — write `not found`, then add an Open Question requesting the real value. |
| Stating the root cause tentatively ("the cause appears to be X"). | Triggers `readiness=UNRESOLVED`. Either run another query to lock it down, or escalate as an Open Question for the user. |
| Including session ids or `firebase-explorer` references in the Status History section. | Q11. Status History is Jira transitions + real-world actions only — strip everything else. |
| Dropping the "Steps to Reproduce" section because the bug "is obvious from the ticket title". | Template structure (Q6) — every required section must be present, even if brief. Use `n/a` only if genuinely not applicable. |
| Asserting "X is missing" on a story with a single grep and no paired evidence of what IS in place. | Step 5b rules 1 + 2 — every Gap row needs (a) one Evidence row showing the live current state of the surrounding area, and (b) ≥2 keyword variants for the absence claim. |
| Accepting a reporter / assignee comment claim (e.g. "the integration already exists", "we use N default values", "there are M records") as fact without re-verifying against live data. | Q12 — every stakeholder claim either pairs with a confirming/refuting Evidence row or becomes an `## Open Questions` entry. |
| Mentioning an unread attachment in passing ("not yet downloaded") inside an Evidence row instead of as an Open Question. | Step 5b rule 3 — deferred attachments from active-design-discussion comments are surfaced explicitly in `## Open Questions`, not buried in evidence. |

---

## Guiding Principles

1. **Current state over received analysis.** An RCA written last week may be wrong today. Verify before using.
2. **Config first.** Most issues are configuration gaps, not code defects. Check Firebase before reading code.
3. **Evidence over assumption.** If you can't find it in the DB or code, say `not found`. Never fabricate.
4. **One fix per mismatch.** Write one recommended fix line per requirement-vs-actual mismatch.
5. **Newcomer-friendly.** Any developer unfamiliar with the codebase should be able to pick up the report and act on it.

## Next step

After completing this skill, select EXACTLY ONE action from the decision tree below based on `final_classification` from Step 7. Print the block below with the chosen action substituted for `{ACTION_LINE}`. Substitute the actual ticket key for `{TICKET_KEY}`. Do NOT print the decision tree.

**Decision tree (reasoning input only):**

| `final_classification` | `{ACTION_LINE}` |
|---|---|
| `CLEAR` (quality=PASS, readiness=CLEAR) | `/create-spec {TICKET_KEY}` |
| `readiness=UNRESOLVED` (Open Questions present) | `Resolve the open questions listed in rca.md, then re-run /create-rca {TICKET_KEY}. Do not run /create-spec yet.` |
| `quality=FAIL` (QUALITY-REPORT.md present) | `Review tickets/{TICKET_KEY}/QUALITY-REPORT.md, then re-run /create-rca {TICKET_KEY} or fix manually before /create-spec` |

**Block to print:**

```
---
**Next step**

{ACTION_LINE}
---
```
