# Template Artifact Protocol — Wire Format Contract

The format `prepare-uat` produces and `apply-fix` consumes when a deploy plan injects twig/css template bodies into a Firebase write.

**Producers:**
- `prepare-uat` Step 4.5 — captures local twig/css, computes hashes, builds the section.

**Consumers:**
- `apply-fix` Step 4b.0 — parses the section, hash-verifies local files, substitutes placeholders into the wire payload.

**Why this contract exists:** twig/css bodies are 12-45 KB each. Inlining them into the deploy markdown bloats the file, breaks diffs, and exceeds Firestore document limits. The protocol captures content **by reference + integrity hash**, never by inlining.

---

## T_id naming

Each `document-templates/{Name}/` folder gets exactly one `T_id` per deploy plan, assigned sequentially: `T1`, `T2`, `T3`, …

**De-duplicate by folder.** If the Technical Approach mentions the same folder multiple times, register ONE `T_id`. Never produce two artifacts for one physical folder.

The `T_id` is the join key between every other part of the protocol (table row, full-sha256 block, placeholder, drive URL).

## Classification taxonomy

Every artifact carries a classification derived from the linked Firebase write operation:

| Linked write operation | Template classification | Notes |
|---|---|---|
| `create` | `new` | Brand-new template record. Firebase has nothing at this path. |
| `update_partial` — `template` field only | `update — twig only` | css is unchanged on Firebase. |
| `update_partial` — `styles` field only | `update — css only` | twig is unchanged on Firebase. |
| `update_partial` — both fields | `update — twig + css` | Both fields changing in one write. |
| `update_full` | `update — full doc` | Whole record replaced. Before snapshot must include sibling fields. |
| `delete` | `delete` | No file content consumed; artifact entry kept for Before snapshot record only. |

Classification is derived from the write **operation**, not from disk contents. If the source document is ambiguous about classification, the producer stops and asks the user — never guesses.

## SHA256 truncation convention

Hashes appear in two forms in the protocol:

- **Truncated** (4 + 4 characters with `…` separator, e.g. `a3f9…2c1b`) — for the human-readable table only.
- **Full** (64-char lowercase hex) — for byte-match validation by the consumer.

Both must be present. Truncated 4+4 hashes can collide (16⁸ = 4.3B keyspace — reachable in practice), so the consumer MUST hash-verify against the full block, never the truncated table.

## Truncated table format

The first artifact in the protocol is a human-readable table with one row per artifact:

```
| ID | Name | Files | Class | twig sha256 | css sha256 | New size | Linked write | Size budget |
|----|------|-------|-------|-------------|------------|----------|--------------|-------------|
| T1 | Memorial Slideshow Cover | twig + css | new | a3f9…2c1b | 8e44…91d2 | 15 KB | Step 2.1 (RTDB create) | RTDB ok |
| T2 | Cremation Booking Form   | twig       | update — twig only | b5d2…7c10 | (unchanged) | 45 KB | Step 2.2 (RTDB update_partial) | RTDB ok |
```

Column meanings:

- **ID** — the `T_id` (`T1`, `T2`, …).
- **Name** — the folder name under `document-templates/`.
- **Files** — which of `twig`, `css`, or `twig + css` are part of this artifact.
- **Class** — from the classification taxonomy above.
- **twig sha256 / css sha256** — truncated hashes (`a3f9…2c1b` form). Cells read `(unchanged)` when the field is not part of this write, `(none)` when the artifact has no such file.
- **New size** — total size of the file content being injected (KB / MB).
- **Linked write** — pointer to the Execution Step that consumes this artifact.
- **Size budget** — `RTDB ok` / `Firestore ok` / `RTDB warn — N MB` (per the producer's size-budget check).

When `prepare-uat` Step 6.5 ran, two extra columns appear: `twig Drive URL` and `css Drive URL`, each carrying either a Drive web URL or an explicit verdict (`skipped — user declined`, `failed: <reason>`, `(unchanged — not uploaded)`).

## Full-sha256 block

A fenced block IMMEDIATELY AFTER the truncated table, recording the authoritative full 64-char hex hash per file:

```
T1.twig.sha256: a3f9b22e<48 more hex chars>2c1b
T1.css.sha256:  8e44d10f<48 more hex chars>91d2
T2.twig.sha256: b5d29ad0<48 more hex chars>7c10
```

**Mandatory.** A Template Artifacts section with a truncated table but no full-sha256 block is malformed — the consumer (`apply-fix` Step 4b.0.i) stops with a re-run-/prepare-uat directive.

Files recorded as `(unchanged)` or `(none)` in the truncated table do NOT appear in the full block.

## `<ARTIFACT T_id {twig|css}>` placeholder syntax

Inside any `data: {}` block in the deploy plan's Execution Steps, twig/css fields are written as placeholder tokens, never as literal content:

```
data: {
  label: "Memorial Slideshow Cover",
  template: <ARTIFACT T1 twig>,
  styles: <ARTIFACT T1 css>,
  active: true
}
```

Token rules:

- `T_id` must correspond to a row in the truncated table AND the full-sha256 block.
- `{twig|css}` must refer to a file the artifact actually carries (not `(unchanged)`, not `(none)`).
- The consumer substitutes the placeholder with the local file's bytes on the wire-bound payload — never on the deploy markdown.
- The literal placeholder string must NEVER reach a `write_rtdb` / `write_firestore` invocation. If it does, the consumer skipped substitution and silently corrupts the template.

Non-template fields (`label`, `active`, etc.) appear verbatim in the same `data: {}` block — placeholders only replace twig/css.

## Before / After integrity records (for `update — *` writes)

When the write changes a `template` and/or `styles` field, the corresponding write step in the deploy plan carries:

```
Before-template-sha256: <full 64-char hex of current Firebase template field>
Before-template-excerpt: <first 10 non-blank lines of current Firebase template>
Before-template-size: <bytes>

After-template-sha256: <full 64-char hex of new local twig>
After-template-excerpt: <first 10 non-blank lines of new local twig>
After-template-size: <bytes>
```

Same shape applies to `styles` if css changes. These are integrity records, not content; the verbatim 45 KB string never appears in the deploy file.

The consumer (`apply-fix` Step 4b.ii Format B) hashes the freshly-read Firebase field and compares full-hex to `Before-{field}-sha256` to detect drift since the plan was prepared. The Verification table's `Expected:` cell for template-field writes carries `sha256 of {field} == {truncated_4plus4_hash}` — consumed by `apply-fix` Step 4e with truncated-prefix comparison after hashing the post-write read.

## Drive URLs (optional, when producer Step 6.5 ran)

When the producer ran its Drive-upload step, each artifact carries Drive URLs in the table. The consumer's drift-handling (`apply-fix` Step 4i) MAY re-upload the local file to refresh these URLs when local drifted from the plan and the user accepted local. The URLs are advisory — the local file is always the source of truth for the actual Firebase write.

## Producer and consumer must stay in sync

If either side changes a format detail (column order, column name, T_id syntax, hash truncation, placeholder syntax), update this contract first, then update both the producer and consumer references to match. Diverging from the contract silently breaks integration.
