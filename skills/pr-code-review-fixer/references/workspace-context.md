# Workspace context: why this skill is unusually strict here

The InvoCare FireHawk / Barndoor workspace has properties that make naive "address the review comment" agent behavior unusually destructive. This file captures the structural reasons behind the skill's auto-escalation rules and the mandatory MCP gates.

If you are working in a sibling repo for the first time, read the project's own README before doing anything — Angular versions, Node versions, and deploy scripts are not consistent across the workspace.

## Topology in one paragraph

~30 independent git repositories live side-by-side. There is no root-level build. Each project has its own `package.json`, README, and deploy pipeline. They share two published npm libraries (`fcrm-entity-manager`, `FireHawk-AuthCheck`), a folder of HTML/CSS/Twig templates (`document-templates/`), and a config store (Firebase RTDB / Firestore). The frontend (`FCRM-Web`) and most FCRM APIs deploy to GCP App Engine. The Barndoor services (`Barndoor-*`) deploy to GKE via Terraform + Helm + ArgoCD. The BDM services (`vic-bdm-services`, `nsw-bdm-services`) are legacy and deploy to Compute Engine VMs via `npm run deploy` + `forever`. Three environments: `ivc-dev`, `ivc-test` (a.k.a. `ivc-uat`), `ivc-prod`.

## Why specific scopes auto-escalate (hard rule #9)

### `fcrm-entity-manager`, `FireHawk-AuthCheck`

These are **published to npm**, not workspace-linked. A change to either of these libraries does not propagate automatically. Consumers must:

1. Bump the dep version in their own `package.json`.
2. Run their own `npm install` and verify.
3. Re-deploy.

A skill that edits these libraries silently — even with a "perfect" minimal fix — leaves every downstream consumer either pinned to the old broken version or unaware of the new version. That is not within the skill's scope. Escalate so the human can stage the lib change, version bump, and downstream dep updates together.

### `vic-bdm-services`, `nsw-bdm-services`

These are **legacy government BDM (Birth, Death, Marriage) registry integrations**, deployed to Compute Engine via `forever`. They are not protected by the same CI / health-check rails as the App Engine or GKE services. A regression here can produce real-world legal failures (incorrect death certificates filed to government registries) without obvious local symptoms. The skill is not allowed to edit them autonomously.

### `FCRM-Barndoor-Infra/terraform/`, `FCRM-Barndoor-Infra/argocd/`

Terraform plans + ArgoCD manifests drive the GKE deploys via GitOps. ArgoCD watches the infra repo and applies changes. An "edit" here is, in effect, a deploy. The skill is not allowed to do that without human review.

### `FireHawk-Infra-Configs/app-engine/`

App Engine YAMLs determine where and how services are served. Same reasoning: an edit is a deploy.

## Why the Firebase config probe is mandatory for behavioral comments

The default mental model in most codebases is "the code is the source of truth; config is rare." In this workspace, **that model is wrong**. The CLAUDE.md explicitly notes: *"Bugs that look like code bugs are often Firebase config."* The pattern shows up in:

- Forms (which fields appear, in what order, validation rules) — RTDB / Firestore.
- Team-specific overrides (`teams/{teamId}/...`) — Firestore.
- Workflow / status transitions — Firestore.
- Document templates and rendering rules — partly in `document-templates/`, partly in Firestore.
- Email triggers, notification rules — Firestore.

A reviewer who says *"this should also show X"* is, more often than not, describing a missing config entry. Editing the code "to make X appear" creates a regression because the next time the config is updated, the hardcoded code path and the config-driven path will disagree.

## Node / Angular version variance (matters for verification commands)

The verification step must use the right commands per project:

| Project family | Node | Notes |
|---|---|---|
| `FCRM-Web` | 20 | Angular 21. `npm run local-dev` requires the LOCALDEV.md subdomain setup. |
| `FCRM-Document-Signer` | 14 | Legacy Angular 8. |
| `pdf-mapper` | 14 | Angular 10. |
| `FCRM-Cloud-App` | 18 | Main API. |
| `FCRM-Email-API`, `FCRM-Search-API`, `FCRM-Reports-API` | 22.14.0 | |
| `Barndoor-Batch-App`, `Barndoor-Tributes-App`, others | varies | NestJS + TypeScript. |
| `vic-bdm-services`, `nsw-bdm-services` | legacy | Deploy via `npm run deploy` + `forever`. |

Always check `.nvmrc` / `engines` before running scripts. A test failure that turns out to be a Node version mismatch wastes a verification cycle.

## Secrets and config sources

- **Secrets** live in Google Secret Manager — never in the repo. The skill never commits `.env` files or any file that looks like a secret. If a comment requests adding a secret, escalate.
- **Application config** lives in Firebase. The skill probes config via `firebase-explorer` and never edits it.
- **Custom claims** for Firebase users are managed via `firebase-custom-claims-management-script/` — the skill does not invoke that CLI autonomously.

## Cross-references

- High-level architecture: project root `CLAUDE.md`.
- Per-project conventions: each project's own `README.md`.
- Local dev setup for `FCRM-Web`: that project's `LOCALDEV.md`.
- Mandatory pre-implementation lesson gate: project `.claude/rules/code-lessons.md` — the same gate is referenced as Phase 0 of this skill.
