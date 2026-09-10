# Local Dev Overrides — Pre-Existing Dirty Files Are Not Part of the Task

Applies to every skill or agent that reads `git status`, analyzes a working tree, implements code, or prepares a commit/PR in the sibling repos. Cited from `CLAUDE.md` so all skills and subagents inherit it.

## The situation

Some repos are **permanently dirty on this machine by design**: running them locally requires cheating config that must never be committed. FCRM-Web is the canonical case — `src/environments/environment.ts`, `package.json` / `package-lock.json`, `.nvmrc`, `.gitignore` are modified so the app points at local/dev services. Other repos may carry the same kind of run-local overrides.

These files being dirty is **expected noise, not a signal**. Treating them as part of the task causes the three real failures this rule prevents: staging them into a ticket commit, "helpfully" reverting them (breaking the user's local run setup), or flagging them as findings in code analysis/review.

## Rules

**LDO1 — Classify before you react.** When a working tree is dirty, separate the entries into (a) changes made *for this task* and (b) pre-existing modifications that were dirty before the task started. Only (a) is in scope. The tell for (b): the file is a config/env/toolchain file (`environment*.ts`, `package.json`, `package-lock.json`, `.nvmrc`, `.gitignore`, `*.local.*`, untracked `environment.local-*` files) AND the change is unrelated to the ticket. When unsure which bucket a file is in, ask — never guess a revert.

**LDO2 — Never stage, commit, or push a local override.** This is `git-safety.md` G10 applied with intent: stage explicit task paths only. A local override showing up in `git diff --cached` or a PR diff is a blocker — unstage it, don't ship it.

**LDO3 — Never revert or clean a local override.** No `git checkout -- <file>`, `git restore`, or `git stash` on bucket-(b) files to "get a clean tree". The user's local run setup depends on them. If a genuinely clean tree is required (e.g. a checkout must switch branches and the override blocks it), stop and ask the user.

**LDO4 — Exclude local overrides from analysis and review output.** Code analysis, impact checks, reviews, and status reports must not flag pre-existing local overrides as findings, drift, or "uncommitted work to address". At most, one neutral line: `pre-existing local dev overrides present (N files) — ignored`.

**LDO5 — A dirty tree is not a blocker for read-only work.** Skills that only analyze (RCA investigation, status checks, reviews) proceed normally on a dirty repo. Skills that write commits proceed too, as long as LDO1/LDO2 hold — the override files simply stay out of the staged set.

## What this rule does NOT cover

- A task that legitimately changes one of these files (e.g. the ticket IS a dependency bump to `package.json`): that change is bucket (a) — stage the hunks for the task. If the file mixes task changes with local cheats, surface the conflict to the user instead of committing the mix.
- Dirty **source** files unrelated to the ticket that are NOT run-local config: those are surfaced, not silently ignored — they may be forgotten work.
- Nothing here relaxes `git-safety.md`; G-rules still bind. This rule only stops false alarms and accidental cleanup on known local noise.
