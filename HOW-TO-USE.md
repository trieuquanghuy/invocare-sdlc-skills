# InvoCare Skill Workflow

Use this as the lifecycle map. Each skill's `SKILL.md` owns its detailed behavior, safety gates, and output contract.

## Lifecycle

| Stage | Command | Main result |
|---|---|---|
| Check progress | `/task-status {KEY}` | Current state and next action |
| Map impact (optional) | `/impact-analysis {KEY}` | Code/config blast radius |
| Investigate | `/create-rca {KEY}` | `tickets/{KEY}/rca.md` |
| Plan | `/create-spec {KEY}` | `spec.md`, `validation.md`, deployment guidance |
| Apply on DEV | `/apply-fix {KEY}` | Code/config change and deployment evidence |
| Ship code | `/create-pr {KEY}` | Focused pull request |
| Review code | `/code-review-kms` | Two qualifying review runs |
| Address findings | `/pr-code-review-fixer` | Verified review fixes |
| Communicate | `/ticket-comment {KEY}` | Jira progress or QA handoff |
| Refresh RCA | `/publish-rca {KEY}` | Updated Confluence RCA |

Start with `/task-status` after time away. It reads local artifacts and connected work systems, then routes to the next valid command.

## Config and code paths

**Config change**

```text
create-rca → create-spec → apply-fix DEV → apply-fix UAT → apply-fix PROD
```

Each Firebase write requires explicit approval, the correct RTDB/Firestore target, and a logged rollback session.

**Code change**

```text
create-rca → create-spec → apply-fix DEV → create-pr
→ code-review-kms / pr-code-review-fixer → ticket-comment
```

Code review must satisfy the policy in the review skill before merge.

## Alternative entry

Use `/prepare-uat {KEY}` when an approved technical approach already exists in Confluence and local RCA/spec generation is unnecessary. It produces the UAT deployment input without bypassing write approvals.

## Artifact ownership

```text
tickets/{KEY}/
  rca.md              investigation and reproduction evidence
  spec.md             technical approach
  validation.md       QA scenarios
  deploy.md           approved deployment instructions
  deploy-result.md    observed deployment result
  session-log.md      Firebase rollback audit trail
```

Stakeholder-facing comments and pages contain the needed information inline; they do not reference local artifact paths.

Use `/summarize-firebase-session` to audit Firebase writes and `/create-release-report` for release deployment reporting.
