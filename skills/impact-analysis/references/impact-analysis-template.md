# [TICKET_KEY] — Impact Analysis

> Confidence-rated blast-radius assessment.

---

## 0. Strategic Framing

**Ticket signal:** [one-line characterization — e.g., "New field added to funeral event entity"]

**Risk hypotheses (ranked):**
1. [Hypothesis — e.g., "Denormalized copies in RTDB won't have the new field"] → Tiers [T3, T4] → Depth: deep
2. [Hypothesis — e.g., "Export templates won't resolve the field"] → Tiers [T2] → Depth: normal
3. [Hypothesis — e.g., "No mobile consumer reads this entity directly"] → Tiers [T5] → Depth: skim

**User-directed adjustments:** [what the user said during checkpoint, or
"None — framing approved as-is"]

**Mid-analysis pivots:** [any hypothesis changes during investigation, or
"None — anchors matched expectations"]

---

## 1. Change Anchors

[What's being modified, in plain dev terms. List each anchor with its repo,
file path, and a one-sentence description of the change.]

| Anchor | Repo | File | What Changes |
|--------|------|------|-------------|
| [SYMBOL_OR_COMPONENT] | [REPO_NAME] | [file.ts:line] | [One-sentence description] |

---

## 2. Coverage Statement

**Searched:**
- [List every source consulted BY KIND, not by tool name: code repositories,
  Firestore collections, RTDB paths, Elasticsearch indices, security rules, etc.
  Name the area inspected — never the search tool used to inspect it.]

**NOT searched (explicit blind spots):**
- [List what was NOT analyzed: dynamic dispatch, mobile clients, cron jobs,
  specific repos not indexed, etc.]
- [Each blind spot should explain WHY it wasn't searched: "not indexed",
  "no access", "out of token budget", etc.]

---

## 3. Impact Map

### T1 — Direct (Change Anchors)

| Location | Why It's Impacted | Confidence | Evidence |
|----------|-------------------|------------|----------|
| [repo/path/file.ts:line] | [Direct change target] | H | [from ticket description / plan] |

### T2 — Callers / Importers

| Location | Why It's Impacted | Confidence | Evidence |
|----------|-------------------|------------|----------|
| [repo/path/file.ts:line] | [Calls ANCHOR_NAME directly] | H | [direct caller — 1 call-graph hop] |
| [repo/path/file.ts:line] | [Imports module containing anchor] | M | [transitive import — 2 call-graph hops] |

### T3 — Data-Coupled

> DB column: `RTDB` or `Firestore` for every Firebase path; `n/a` for code-only rows.

| Location | DB | Why It's Impacted | Confidence | Evidence |
|----------|----|-------------------|------------|----------|
| [repo/path/file.ts:line] | n/a | [Reads FIELD_NAME from COLLECTION] | H | [call-graph — accesses FIELD_NAME] |
| [collection/path] | Firestore | [Writes denormalized copy of FIELD] | M | [cross-repo code search + live config read] |

### T4 — Config-Coupled

> DB column: `RTDB` or `Firestore` for every Firebase path; `n/a` for code-only rows.

| Location | DB | Why It's Impacted | Confidence | Evidence |
|----------|----|-------------------|------------|----------|
| [firestore.rules:line] | Firestore | [Security rule references COLLECTION] | H | [text-search match] |
| [functions/src/triggers.ts:line] | n/a | [onUpdate trigger for COLLECTION] | H | [code search] |
| [config/path] | RTDB | [Feature flag gates affected feature] | M | [live config read] |

### T5 — Contract-Coupled

| Location | Why It's Impacted | Confidence | Evidence |
|----------|-------------------|------------|----------|
| [repo/path/file.spec.ts] | [Tests ANCHOR_NAME behavior] | H | [test-file search] |
| [MISSING: no test coverage] | [No tests found for ANCHOR_NAME] | — | [absence signal] |

---

## 4. Open Questions for BA

1. **[QUESTION]**
   - Ambiguity: [what's unclear]
   - Unblocks: [which impact area / tier this resolves]

2. **[QUESTION]**
   - Ambiguity: [what's unclear]
   - Unblocks: [which impact area / tier this resolves]

---

## 5. Suggested Plan Edits

[Skip this section if no rca.md or spec.md exists. Note: "No spec exists
yet; suggested edits will be generated once /create-spec produces one."]

### New tasks to add

```
old_string: [EXISTING_TEXT_IN_PLAN]
new_string: [REPLACEMENT_WITH_NEW_TASK_INSERTED]
```

### New test cases

```
old_string: [EXISTING_TEST_SECTION]
new_string: [REPLACEMENT_WITH_NEW_TEST_CASES]
```

### Verification checklist additions

```
old_string: [EXISTING_CHECKLIST]
new_string: [REPLACEMENT_WITH_NEW_ITEMS]
```

---

## 6. Risk Assessment

| # | Most Likely to Break | Mitigation |
|---|---------------------|------------|
| 1 | [RISK_DESCRIPTION] | [ONE_LINE_MITIGATION] |
| 2 | [RISK_DESCRIPTION] | [ONE_LINE_MITIGATION] |
| 3 | [RISK_DESCRIPTION] | [ONE_LINE_MITIGATION] |

---

## 7. Failure Modes Log

| What Was Abandoned | Why |
|-------------------|-----|
| [INVESTIGATION_AREA] | [REASON: token budget, not indexed, no access, etc.] |
