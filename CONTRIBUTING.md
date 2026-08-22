# Contributing

## Branch and pull request

```bash
git clone git@github.com:trieuquanghuy/invocare-sdlc-skills.git
cd invocare-sdlc-skills
git switch -c fix/short-description
# edit and test one focused change
git add -p
git commit -m "fix(create-rca): tighten evidence validation"
git push -u origin HEAD
gh pr create --fill
```

Keep pull requests focused. Use short subject-only commits with no automation attribution.

## Import workspace changes

Use the workspace-to-checkout flow in [`SYNC.md`](SYNC.md). It previews or copies the shared payload but never deletes, commits, or pushes.

## Required gates

Before executable changes, run the code-lessons high and medium skims plus the applicable development-rules check. Markdown-only changes follow the documented skip list.

Every change must preserve:

- output and secret boundaries;
- read-only checker isolation;
- explicit Firebase RTDB versus Firestore ownership;
- safe git behavior and local development overrides;
- callers of shared files and schemas.

## Edit shared content

```text
rules/                 cross-cutting governance
agents/                checker and reviewer definitions
scripts/               deterministic hooks and helpers
skills/_shared/        contracts, templates, and references used by multiple skills
skills/<skill>/        SKILL.md, checker prompts, and skill-specific references
```

- Put per-skill references under that skill; move content to `_shared` only when multiple skills use it.
- When adding a Quality Bar item, update the matching checker prompt.
- Do not renumber referenced workflow steps; use an inserted suffix such as `4a.5`.
- Keep each skill's `## Next step` router at the bottom.
- Keep checker JSON schemas aligned with every caller that parses them.
- Use `fixable: true` only for mechanical fixes; severity remains `blocker` or `warning`.
- Preserve `disable-model-invocation: true` on write-capable skills.
- Search consumers before changing anything under `_shared`.

## Validate

Run the smallest existing test for the changed behavior. The sync package owns its complete test matrix in [`tools/sync/README.md`](tools/sync/README.md).

For prompt-only changes, exercise the skill on representative input. For checker changes, include a known-bad artifact and confirm the expected blocking result without output-boundary leaks.

Before opening a pull request:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/sync/tests -p 'test_*.py'
while IFS= read -r file; do
  bash -n "$file"
done < <(find hooks scripts tools/sync -type f -name '*.sh' | sort)
git diff --check
git status --short
```

## Local validation and manual releases

This repository has no CI/CD runner. Contributors must run the validation commands above locally before opening or updating a pull request.

Maintainers publish immutable CalVer tags manually after reviewing the pull request and repeating the local validation:

```bash
TAG=v2026.08.22
bash scripts/validate-calver.sh "$TAG"
git tag -a "$TAG" -m "Release $TAG"
git push origin "$TAG"
```

Never move or reuse a published tag.

For repository ownership and layout, start with [`README.md`](README.md); implementation-specific rules remain in `rules/` and each skill's `SKILL.md`.
