# Firebase config probe playbook

In the InvoCare FireHawk / Barndoor codebase, behavior is frequently steered by Firebase RTDB / Firestore config — not code. A reviewer who says "this is wrong for the Sydney team" may be describing a config override, not a bug. Editing code in that case introduces a regression while appearing to address the comment.

This probe is a **mandatory first step** for any `behavioral` comment and for any comment about UI columns, form fields, document templates, workflow states, or per-team behavior. The probe can only escalate — it cannot grant permission to apply a code edit.

## What lives in Firebase (high-leverage probe locations)

Use these as the first lookups for the corresponding comment shapes. Exact paths vary per project; treat these as starting points and confirm.

| Comment touches… | Probable Firebase location | Tool |
|---|---|---|
| Forms, fields shown to users | `forms/`, `pdf-mapper-forms/` (RTDB), or Firestore equivalents | `query_firestore` / `query_rtdb` |
| UI columns, table layouts, per-team display | Team override collections, e.g. `teams/{teamId}/funeralServiceColumns` | `query_firestore` |
| Workflow / status transitions | Workflow definition documents | `query_firestore` |
| Document templates, letters, PDFs | `document-templates/` (in repo) and config in Firestore | `query_firestore` |
| Permissions / roles | Firebase custom claims, RTDB role mappings | `query_firestore` / `query_rtdb` |
| Email triggers, notification rules | `emailRules/`, `notificationConfig/` | `query_firestore` |

## Which environment to query

Default to **`ivc-dev`** for the probe. Dev mirrors the schema, the data is non-sensitive, and the override patterns that drive a reviewer's comment are visible there.

Only escalate to `ivc-test` (UAT) or `ivc-prod` if:

- the comment explicitly references UAT or prod behavior, OR
- a `dev` probe returns no matching configuration document and the comment's behavior could only be explained by per-env config divergence.

`mcp__firebase-explorer__list_environments` shows what's available if you are unsure.

## Probe pattern

The probe is small: list possible collections, read the one that fits, decide.

```
1. List candidate collections (only if you don't already know the schema)
   mcp__firebase-explorer__list_collections({ environment: "ivc-dev" })

2. Query the candidate that matches the comment's domain
   mcp__firebase-explorer__query_firestore({
     environment: "ivc-dev",
     collection: "teams",
     where: [["name", "==", "Sydney"]]
   })

3. Inspect the returned document for the field that controls the disputed behavior.
   - If the field is missing or contradicts the comment's expectation, the bug is in config.
   - If the field matches the code's current behavior, the code is correct as-config-driven.
```

For RTDB lookups, use `mcp__firebase-explorer__query_rtdb` with the path.

## What "config drives this" looks like

Concrete signals from a probe that mean **escalate, do not edit code**:

- A document exists with a field that explicitly excludes / includes whatever the comment is asking about (e.g., `funeralServiceColumns: ["name", "date"]` — `disposition` is deliberately absent).
- A workflow state document defines the transitions the comment is questioning.
- A form definition omits the field the reviewer says should be visible.
- A template references the variable the reviewer says is "missing."

In each case, the escalation note must include the exact path so the human can fix it in Firebase rather than asking "where is this config?".

## Anti-patterns

- ❌ **Modifying Firestore/RTDB from this skill.** `firebase-explorer` exposes write operations. The skill is read-only when probing. Even if the probe surfaces a clear config-side fix, the human owns that change.
- ❌ **Probing prod data unnecessarily.** Dev mirrors the structure; prod adds risk (rate limits, sensitive data exposure in logs) without adding signal.
- ❌ **Treating absence of a config document as "code is the source of truth."** Some behavior has env-specific config in some envs only. If `dev` has no override but `uat` might, say so in the escalation rather than concluding the code path is config-free.
- ❌ **Using `firebase-explorer` for general code investigation.** It is the config probe. Cross-repo / cross-file code questions go to reposphere.

## When to escalate vs. continue

After the probe, decide:

| Probe result | Action |
|---|---|
| Config explicitly drives the behavior the reviewer is questioning | Escalate `behavioral` with the path. Do not edit code. |
| No config touches this behavior; comment is about pure code logic | Continue with the `behavioral` bucket's four exception criteria. Confidence floor 0.95. |
| Probe is inconclusive (schema unclear, env mismatch) | Escalate. Treat inconclusive as "don't know" — do not edit code on a hunch. |
