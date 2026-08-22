## IMPORTANT RULES (remove before saving):
- Replace every [PLACEHOLDER] with real data from this investigation
- Evidence must use real DB keys only — no made-up fields
- Every factual claim must come from fetched data (Jira/Firebase/code) in this run
- If a value is not found, state `not found` — never guess
- **Status History events = Jira status changes, comments, and real-world actions only. NEVER include Firebase session IDs, session numbers, MCP tool operations, or any internal tooling reference (e.g. "Session 124 applied", "write_rtdb executed"). Those belong in session-log.md, not here.**
- **Section tiering — omit empty sections, never fill with n/a.** CORE sections are always present: header block, Sources Investigated, Executive Summary, 1 Problem Statement, 2 Steps to Reproduce / Acceptance Criteria, 3.1 Primary Root Cause, 3.4 Evidence Summary, 5 Impact Assessment, 7.4 Technical Solution, 8 Estimation, 9 Recommendations. 7.2 Key Code Files is CORE for code-involved root causes and omitted for pure config causes. CONDITIONAL sections (marked below) are included ONLY when they carry real content — a conditional section with nothing to say is omitted entirely, heading and all. A table with only filler rows is noise for the reader, not rigor.
- Keep prose tight: one paragraph where the template says one paragraph; no restating the same fact in multiple sections.
- Remove this IMPORTANT RULES block before saving

---

# RCA: [TICKET_KEY] — [JIRA_TITLE]

**Confluence RCA:** <!-- publish-rca writes URL here -->
**Currency:** CURRENT | PARTIALLY_STALE | OUTDATED
**Date:** [DATE]

**Summary:** [JIRA_TITLE]

| Field | Value |
| --- | --- |
| Key | [TICKET_KEY] |
| Type | Bug / Story / Task |
| Priority | Critical / High / Medium / Low |
| Status | [STATUS] |
| Environment | dev / uat / prod |
| Reporter | [REPORTER] |
| Labels | [LABELS] |
| Created | [DATE] |
| Last Updated | [DATE] |

---

## Sources Investigated

| Source | Location | Purpose |
| --- | --- | --- |
| [Source name] | [DB type + path, or `file:line`, or Jira KEY] | [What this source was used to confirm] |

---

## Executive Summary (Evidence-Based)

**Root Cause:** [One paragraph — evidence-backed root cause. For bugs: what is broken and why. For stories: what is missing and what needs to be built. Include specific field names, path values, or function names where confirmed. End with current fix status.]

---

## 1. Problem Statement

[What is broken or what is needed. For bugs: what the user sees vs what they should see. For stories: what the business process requires that doesn't exist yet. Be concrete — reference specific screens, exports, or behaviours.]

## 2. Steps to Reproduce (Bug) / Acceptance Criteria (Story)

**Bug:**

1. [Step 1]
2. [Step 2]

**Actual:** [What happens]
**Expected:** [What should happen]

**Reproduction data (verified from Firebase):**
- Client / path: `[Firebase path]`
- Key fields: `[field: value, field: value]`

---

**Story (replace Steps to Reproduce with Acceptance Criteria):**

1. [Acceptance criterion 1]
2. [Acceptance criterion 2]

## 3. Root Cause Analysis

### 3.1 Primary Root Cause

[Detailed explanation with evidence. For bugs: the specific code/config defect and where it lives. For stories: the overall gap narrative — the row-by-row required/current/gap survey lives in 7.5 Gap Analysis, not here.]

**Classification:** `CONFIGURATION_GAP` / `CODE_DEFECT` / `DATA_MAPPING_GAP` / `NEW_FEATURE`

### 3.2 Dependencies *(CONDITIONAL — omit if none; related tickets/systems whose state affects this fix)*

| Dependency | Status | Impact |
| --- | --- | --- |
| [Related ticket or system] | [Status] | [How it affects this ticket] |

### 3.3 Contributing Factors *(CONDITIONAL — omit if none beyond the root cause)*

| Factor | Detail |
| --- | --- |
| [Factor 1] | [Explanation] |
| [Factor 2] | [Explanation] |

### 3.4 Evidence Summary

| Source | DB | Path | Finding |
| --- | --- | --- | --- |
| Firebase | RTDB / Firestore | `[exact/path]` | [What was found] |
| Code | — | `[file:line]` | [What was confirmed] |
| Jira | — | [KEY] | [Relevant detail] |

## 4. Status History *(CONDITIONAL — omit when the history is just Created→In Progress with no signal)*

> Events = Jira status transitions, comments, and real-world actions (e.g. "Assigned to QA", "Deployed to UAT"). Never reference Firebase session IDs, session numbers, or internal tool operations here.
> For Confluence-shared RCAs, prefer first names or group labels (e.g. "QA team", "PM") in the Actor column over full names to avoid surfacing personal info.

| # | Date | Event | Actor |
| --- | --- | --- | --- |
| 1 | [DATE] | Created | [ACTOR] |
| 2 | [DATE] | [Jira status change or real-world action] | [ACTOR] |

[Optional: one italic sentence under the table when the history shows a real signal — e.g. *Rapid triage within 24 hours, no fix in progress yet.* Omit when it would just narrate the rows above.]

## 5. Impact Assessment

| Dimension | Impact |
| --- | --- |
| **Business** | [Who is affected and how] |
| **Operations** | [Manual effort or operational risk] |
| **Data Integrity** | [Any data accuracy risk] |
| **Urgency** | [Why this needs to be fixed now or its priority] |
| **Regression Risk** | [Adjacent areas that could break] |

## 6. Related Issues *(CONDITIONAL — omit if none found)*

| Key | Summary | Status | Relevance |
| --- | --- | --- | --- |
| [KEY] | [Summary] | [Status] | [Why it relates — parent, dependency, sibling, blocker] |

## 7. Technical Analysis

### 7.1 Repositories Involved *(CONDITIONAL — omit for config-only root causes; list only repos actually involved, never "Not involved" rows)*

| Repository | Role | Relevance |
| --- | --- | --- |
| [Repo name] | [What it does] | **Primary** / Secondary / Not involved |

### 7.2 Key Code Files

| File | Function / Purpose |
| --- | --- |
| `[path/to/file.ts:line]` | [What it does relevant to this issue] |

### 7.3 Feature / Flow / Workflow *(CONDITIONAL — include the diagram only when the flow spans 3+ components; a one-hop flow is a sentence, not a diagram)*

```
[ASCII diagram of the relevant flow]
[Entry point] → [Processing] → [Output]
```

### 7.4 Technical Solution

[What code/config areas are involved in this issue — files, paths, functions that produce the broken behavior. Describe what currently happens and where, not how to fix it.]

### 7.5 Gap Analysis *(CONDITIONAL — story-type RCAs only; omit for bugs)*

| # | Required (per AC / requirement) | Current state (evidence) | Gap |
| --- | --- | --- | --- |
| 1 | [what the story needs] | [what exists today — paired Evidence row per Step 5b] | [what must be built] |

## 8. Estimation

### Normal Estimate: [N] SP

[Rationale — what drives the estimate: number of files, integration points, testing surface area, clarity of requirements.]

### Worst Case Estimate: [N] SP

[What would push it higher — unresolved dependencies, unclear requirements, cross-team coordination needed.]

## 9. Recommendations (Priority Order)

1. **[IMMEDIATE]** — [Specific action]
2. **[HIGH]** — [Specific action]
3. **[MEDIUM]** — [Specific action]

## Resolution Basis *(CONDITIONAL — only when a fix has already been applied; states what the applied fix was based on)*

[2-4 lines: which recommendation was implemented, the session/PR that carried it, and what evidence confirmed it. Keep session IDs out — reference session-log.md implicitly by run, not by ID.]

## Follow-ups During the Fix *(CONDITIONAL — only when applying the fix surfaced new items; one line each)*

1. [New item discovered while applying — deferred to TICKET-KEY / needs BA input / separate concern]

## Open Questions

> Heading is `## Open Questions` (no number) so downstream skills (`create-spec` precondition, `apply-fix` R1) can match it. Every entry must pass the triage gate (SKILL.md Step 7): not already answered in Jira comments or Evidence, blocks THIS ticket's spec/fix, and names who/what resolves it. Answered points become cited claims; tracked dependencies go to 3.2; non-blocking anomalies go to Follow-ups. Remove this section entirely if no questions survive — the common correct outcome.

1. [Question 1]
2. [Question 2]
