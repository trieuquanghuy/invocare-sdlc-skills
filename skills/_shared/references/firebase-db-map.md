# Firebase DB Map — InvoCare

**Last refreshed:** 2026-05-17 (live probe against `dev` AND `uat`)
**Source envs:** dev (`firehawk-ivc-dev`) and uat (`firehawk-ivc-test`); structure ~95% identical with explicit dev/uat-only annotations below.
**Note:** firebase-explorer has dev + uat only — no prod environment registered. RTDB root query (`path: "/"`) is blocked server-side; enumerate top-level keys via the curated list below or by probing each root with `query_rtdb shallow=true`.

**Usage:** Before any Firebase read/write, look up the path here. If listed → use the stated DB. If not → query both, append to `## Discovered paths` (`path | DB | first-seen | last-verified | source: {TICKET_KEY}`).

**To refresh this map:** ask Claude "refresh the firebase db map". The session will run `mcp__firebase-explorer__list_collections` against `dev` + `uat`, plus `mcp__firebase-explorer__query_rtdb(path: "/core", shallow: true)` against both envs, diff against the current file, then update the curated tables + env annotations + `Last refreshed` timestamp. Always preserve the `## Discovered paths` section verbatim.

## Collision set — names that exist in BOTH databases ⚠️

These root names exist in **both** RTDB and Firestore with different schemas. Using the wrong tool silently returns wrong data. Always confirm intent before querying.

| Name | RTDB shape | Firestore shape |
|------|------------|-----------------|
| `core` | Hierarchical config tree (`core/funerals/...`, `core/twig-mappings/...`) | Collection (purpose TBD — likely platform meta) |
| `clients` | `clients/list/{clientId}` — full record | Collection of client docs |
| `events` | `events/{eventId}` — full record | Collection of event docs |
| `teams` | `teams/{teamId}/configuration/...` — config tree | Collection of team docs |

## RTDB

**Top-level roots:** `core`, `teams`, `clients`, `events`, `documents`.

**Inside `/core`** (25 keys on dev, 26 on uat): `article-builder`, `automation`, `boards`, `clientTypes`, `countries`, `customForms`, `dashboard`, `email-templates`, `emailTemplates`, `external-portal`, `field-mapping`, `finance`, `forbidden-slugs`, `forbidden-usernames`, `forms`, `funeral`, `funeral-transfers`, `funerals`, `hospitals`, `integrations`, `menu`, `onboarding` (uat only), `stylesheets`, `support`, `templates`, `twig-mappings`.

### Common RTDB paths

| Path | Purpose |
|------|---------|
| `core/funerals/teamForms/{formId}` | Main form definition |
| `core/funerals/statuses` | Workflow status definitions |
| `core/twig-mappings/mappings/event` | Field mapping for events |
| `teams/{teamId}/configuration/teamExports` | Full export config block |
| `teams/{teamId}/configuration/teamExports/filters` | Per-team export overrides |
| `teams/{teamId}/configuration/quotes/contractDocument` | Contract template name reference |
| `teams/{teamId}/quoteDocument` | Estimate template ID |
| `teams/{teamId}/modules` | Feature flags per team |
| `clients/list/{clientId}` | Full client record |
| `clients/list/{clientId}/totalValueOfAgreement` | Preneed contract fields (+ siblings) |
| `events/{eventId}` | Full event record |
| `documents/{documentId}` | Twig template body + CSS |

## Firestore

**137 collections across both envs** (dev: 133, uat: 118; probed 2026-05-17). Most are present in both; differences are annotated `(dev)` or `(uat)` below. Query the named collection directly with `query_firestore`.

- **Identity / users:** `users`, `user-roles`, `user-role-assignments`, `user-roles-assignments`, `user-sessions` (dev), `user-invitations`, `user-favourites`, `user-qualifications`, `user-qualification-assignments`, `external-users`, `scim-tokens`, `password-reset-requests`, `verify-email`, `email-verification` (uat)
- **Org / teams / portals:** `teams`, `team-actions`, `team-emails`, `team-portals`, `team-tax-rates`, `external-portals`, `staged-team-actions` (uat)
- **Business entities:** `clients`, `events`, `events-categories`, `contacts`, `funeral-suppliers` (dev), `ashes`, `attendance`, `incidents`, `sign-documents`, `personal-effects`, `interactions` (dev), `comments`, `feedback` (dev), `timeline`, `tasks`, `workflows`, `procedure-logs`, `procedure-log-items`, `entity-assignments`, `entity-bookings`, `entity-types`
- **Quotes / billing:** `quotes`, `quote-templates`, `bills` (dev), `invoices`, `invoice-templates`, `credit-notes`, `payment`, `payments`, `payment-types`, `price-classes`, `promotions`, `tax-rates`, `currencies`, `cash-managements` (dev), `audit-non-gp-fund` (dev)
- **Payments (Adyen / Firehawk Pay):** `adyen-transactions`, `adyen-transfers`, `firehawk-pay-fees`, `firehawk-pay-notifications`, `firehawk-pay-payment-types`, `firehawk-pay-transactions` (uat), `terminal-payment-requests`, `pos-terminals`, `pos-terminal-requests`, `client-cards-on-files`, `client-credentials`
- **Stock / inventory / assets:** `assets`, `asset-annual-checks`, `assetplanner-logs`, `inventory` (dev), `stock`, `stock-categories`, `stock-locations`, `stock-prices`, `stock-process` (dev), `stock-purchases`, `stock-sales`, `stock-usages`, `suppliers`, `supplier-categories`, `supplier-stock-indices`
- **Logistics:** `fleet-logistics`, `staff-logistics`, `locations` (dev), `location-events`, `shifts`, `roster-availability`
- **Communications:** `emails`, `email-events`, `email-signatures`, `email-templates`, `sms` (dev), `messages`, `notifications`
- **Templates / forms:** `card-feed-templates`, `pdf-mapper-documents`, `todo-list-templates`, `todo-lists`, `form-fields`, `form-overrides`
- **Articles / content:** `articles`, `article-categories`, `pages`, `pageComponents`, `language-translations`, `languages`, `translations`, `countries`, `tags` (dev), `tag-categories`, `nfc-tags` (uat)
- **Music / graphics:** `music-playlists`, `graphic-preset-categories`, `graphics-builder-books`, `graphics-builder-themes`
- **Channels / analytics:** `channels`, `dashboard`, `reports`
- **Investments:** `investments` (dev)
- **Imports / batches:** `imports` (dev), `batch-processes`
- **Misc / admin:** `_migrations` (dev), `_settings`, `_webhook_tracking`, `core`, `app-verification` (dev), `database-access-groups` (dev), `support-center-groups`, `support-tickets`, `tables`, `quick-links`, `quick-test` (dev), `short-urls`, `qr-scans`

## Discovered paths

Append rows here when an investigation hits a path not listed above.

| Path | DB | First seen | Last verified | Source |
|------|----|-----------|---------------|--------|
| `core/funerals/forms/{formId}` | RTDB | 2026-05-18 | 2026-05-18 | GEN-2889 |
| `forms/custom/{teamId}/funerals/enquiry/cards/enquiry/fields` | RTDB | 2026-05-26 | 2026-05-26 | GEN-2919 |
| `core/funerals/templates/enquiry` | RTDB | 2026-06-02 | 2026-06-02 | FIR-2012 |
| `core/funerals/templates/enquiry-contacts/create-modal-form` | RTDB | 2026-06-02 | 2026-06-02 | GEN-2919 (wizard create node; `fields` is a leaf array under a `root` key — write via update_partial at this parent) |
| `core/funerals/hybrid-events/forms/enquiry` | RTDB | 2026-06-02 | 2026-06-02 | GEN-2919/G5 (Pre-Need converted-record Enquiry-snapshot; `fields` array is element-addressable by numeric index, e.g. `.../fields/7` — MCP shows a synthetic `root` wrapper but numeric paths resolve) |
