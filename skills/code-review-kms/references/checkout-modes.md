# Checkout modes — where the review runs, and what changes because of it

The driver reviews and fixes code in **one folder**: `{{CHECKOUT}}`. That folder is either a **plain repo checkout** with
the PR branch checked out, or a **git worktree**. Both work. But they are not interchangeable — one GitNexus tool is
trustworthy in each mode and contaminated in the other, so the mode must be *resolved*, never assumed.

`{{CHECKOUT_MODE}}` ∈ `main` | `worktree`.

**If you have never used `git worktree`, you are in `main` mode and nothing here needs setting up.** Skip to
[Preconditions](#preconditions-by-mode).

---

## Detection ladder (STEP 0 — first match wins)

Run in order. Stop at the first rule that fires.

**1 → `worktree`.** Either signal is sufficient:
```sh
git -C "$CHECKOUT" rev-parse --git-dir          # a worktree returns …/.git/worktrees/<name>
git -C "$CHECKOUT" rev-parse --git-common-dir   # …and this differs from --git-dir
```
A `.worktrees/` path segment corroborates it, but the git query is the authority — a worktree can live anywhere.

**2 → `main`.** All three must hold:
```sh
git -C "$CHECKOUT" rev-parse --git-dir              # returns plain ".git"
git -C "$CHECKOUT" rev-parse --abbrev-ref HEAD      # == {{BRANCH}}
git -C "$CHECKOUT" rev-parse HEAD                   # == the headSha mh_start_review reports
```

**3 → STOP and ask.** Neither rule fired. Report what was actually found and ask which folder to use:

```
Cannot resolve the checkout mode.
  path:           <CHECKOUT>
  git-dir:        <plain .git | worktree>
  current branch: <X>   (expected: <BRANCH>)
  HEAD:           <sha>  (PR head: <headSha>)
  working tree:   <clean | N modified files>
```

The usual cause is benign — the branch is not checked out yet. `git -C "$CHECKOUT" switch <BRANCH>` and re-run.
**Never switch branches for the user**: in `main` mode that is their real working folder and may hold uncommitted work
(`.claude/rules/git-safety.md` G2, G9).

---

## Preconditions by mode

| | `worktree` | `main` |
|---|---|---|
| HEAD == PR `headSha` | required | required |
| Current branch == `{{BRANCH}}` | implied by the worktree | **must be checked explicitly** |
| Working tree state | dirt tolerated; the main checkout stays pristine as reference | **enumerate pre-existing modified files before the loop starts** |
| Re-review: fixes committed + pushed | required | required |

**Why `main` mode needs the two extra checks.** The worktree model gives you a second, pristine copy of the repo — a
wrong branch is just the wrong worktree, and pre-existing dirt is quarantined away from your reference copy. In `main`
mode there is no second copy: the folder you review in is the folder the user works in every day. So a wrong branch means
reviewing (and then *editing*) the wrong code, and untracked pre-existing edits become indistinguishable from the
driver's own fixes the moment the loop starts. GATE 3 hands over an **explicit-path** `git add`; that list is only
correct if you knew what was already dirty beforehand.

---

## The GitNexus asymmetry (server gap #6)

GitNexus resolves a repo by its **registered absolute path**. Which tool that breaks *flips* with the mode:

| | `worktree` (registered path = the *main* checkout) | `main` (registered path = the folder you are fixing in) |
|---|---|---|
| change-scope detection | `git diff` is the only authority — the code index reflects the committed tree, not your dirty working copy. | `git diff` remains the authority; the index may lag your branch. |
| impact / blast radius (reposphere `graph_query` callers) | **Trustworthy** — the indexed tree is genuinely pre-edit state. | **May lag** — the index reflects the last indexed commit, not your just-applied fixes; verify symbols still exist in the working tree. |

**In `main` mode, treat indexed impact readings as advisory.** For a genuine pre-edit radius either stash first
(`git stash` → `impact` → `git stash pop`) or state plainly in the gate that the radius was not independently verified.
A contaminated reading presented as clean is precisely how this gap loses a real defect — it describes your own change
back to you and calls it safe.

---

## Artifact hygiene — stricter in `main` mode, never looser

The driver writes working files into the checkout:

```
review-artifacts/          ticket-intent.md, withheld-findings.md, local-fix-ledger.md
local-diff.patch
manager-hub-open-comments.json
code-review-*.json  ·  *-prompt.txt
```

**None of these may ever be staged or committed.** In `worktree` mode they die with the worktree. In `main` mode they
land in the user's real repo and persist across tickets — so the risk of one drifting into an unrelated commit is
materially higher.

Two rules follow, and neither is optional:
- The handover at GATE 3 uses an **explicit-path** `git add <file> <file>` — never `git add .`, never `git add -A`
  (`.claude/rules/git-safety.md` G10).
- Local-dev dirt (`.env*`, `environment*.ts`, `server/package.json`) is never staged either — it was there before the
  review and is not part of the fix.

Add the paths above to the repo's `.gitignore` (or `.git/info/exclude` to keep it personal) if you review in `main` mode
regularly.

---

## What a worktree is — and why you can ignore it

`git worktree` checks out a second branch into a second folder that shares one `.git` object store. You get two branches
open at once with no stashing and no branch switching.

It is **optional**. The driver supports it because some of us keep a main checkout pinned to `origin/main` as a clean
reference while all ticket work happens in `.worktrees/<ticket>/<repo>` — which is what makes the indexed impact reading
trustworthy in that mode.

If you want to try it:

```sh
git -C FCRM-Web fetch origin
git -C FCRM-Web worktree add ../.worktrees/gen-1234/FCRM-Web feat/gen-1234-my-branch
```

Then pass that path as `{{CHECKOUT}}`. Note the worktree starts with **no `node_modules`** — run `npm ci` inside it
before any wave that builds or tests. Removing one is manual and deliberate:
`git -C FCRM-Web worktree remove ../.worktrees/gen-1234/FCRM-Web`.

**Not using worktrees costs you nothing in this driver** beyond the two extra preconditions above and the advisory
status of the indexed impact reading. Both are handled by the procedure, not by you.
