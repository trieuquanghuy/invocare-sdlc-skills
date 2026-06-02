## IMPORTANT RULES (remove before saving):
- Replace every [PLACEHOLDER] with real data from this investigation
- Evidence must use real DB keys only — no made-up fields
- Every factual claim must come from fetched data (Jira/Firebase/code) in this run
- If a value is not found, state `not found` — never guess
- **Status History events = Jira status changes, comments, and real-world actions only. NEVER include Firebase session IDs, session numbers, MCP tool operations, or any internal tooling reference (e.g. "Session 124 applied", "write_rtdb executed"). Those belong in session-log.md, not here.**
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

[Detailed explanation with evidence. For bugs: the specific code/config defect and where it lives. For stories: gap analysis — what was built vs what is needed.]

**Classification:** `CONFIGURATION_GAP` / `CODE_DEFECT` / `DATA_MAPPING_GAP` / `NEW_FEATURE`

### 3.2 Secondary Root Causes / Dependencies

| Dependency | Status | Impact |
| --- | --- | --- |
| [Related ticket or system] | [Status] | [How it affects this ticket] |

### 3.3 Contributing Factors

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

## 4. Status History

> Events = Jira status transitions, comments, and real-world actions (e.g. "Assigned to QA", "Deployed to UAT"). Never reference Firebase session IDs, session numbers, or internal tool operations here.
> For Confluence-shared RCAs, prefer first names or group labels (e.g. "QA team", "PM") in the Actor column over full names to avoid surfacing personal info.

| # | Date | Event | Actor |
| --- | --- | --- | --- |
| 1 | [DATE] | Created | [ACTOR] |
| 2 | [DATE] | [Jira status change or real-world action] | [ACTOR] |

### Pattern Analysis

[1-2 sentences on what the history shows — e.g. "Rapid triage within 24 hours, no fix in progress yet."]

## 5. Impact Assessment

| Dimension | Impact |
| --- | --- |
| **Business** | [Who is affected and how] |
| **Operations** | [Manual effort or operational risk] |
| **Data Integrity** | [Any data accuracy risk] |
| **Urgency** | [Why this needs to be fixed now or its priority] |
| **Regression Risk** | [Adjacent areas that could break] |

## 6. Related Issues

| Key | Summary | Status | Relevance |
| --- | --- | --- | --- |
| [KEY] | [Summary] | [Status] | [Why it relates — parent, dependency, sibling, blocker] |

## 7. Technical Analysis

### 7.1 Repositories Involved

| Repository | Role | Relevance |
| --- | --- | --- |
| [Repo name] | [What it does] | **Primary** / Secondary / Not involved |

### 7.2 Key Code Files

| File | Function / Purpose |
| --- | --- |
| `[path/to/file.ts:line]` | [What it does relevant to this issue] |

### 7.3 Feature / Flow / Workflow

```
[ASCII diagram of the relevant flow]
[Entry point] → [Processing] → [Output]
```

### 7.4 Technical Solution

[What code/config areas are involved in this issue — files, paths, functions that produce the broken behavior. Describe what currently happens and where, not how to fix it.]

## 8. Estimation

### Normal Estimate: [N] SP

[Rationale — what drives the estimate: number of files, integration points, testing surface area, clarity of requirements.]

### Worst Case Estimate: [N] SP

[What would push it higher — unresolved dependencies, unclear requirements, cross-team coordination needed.]

## 9. Recommendations (Priority Order)

1. **[IMMEDIATE]** — [Specific action]
2. **[HIGH]** — [Specific action]
3. **[MEDIUM]** — [Specific action]

## Open Questions

> Heading is `## Open Questions` (no number) so downstream skills (`create-spec` precondition, `apply-fix` R1) can match it. Remove this section entirely if no questions remain.

1. [Question 1]
2. [Question 2]
