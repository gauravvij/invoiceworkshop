# InvoiceWorkshop Level-1A safety and readiness

Prepared: 2026-08-31 UTC

This implementation prepares a tightly bounded resource-suggestion layer. It did
not send email, submit a form, create an account, publish content, purchase
anything, modify the production site, deploy, or add a schedule. Level 1A and
Level 1B remain disabled.

## Level-1A architecture

The execution boundary is deterministic:

```text
qualified CRM prospect
  -> versioned action + template + product claim
  -> current-page and contact-route verification
  -> suppression, duplicate, cadence, and cap checks
  -> exact owner-approved message hash
  -> environment kill switch AND database kill switch
  -> restricted provider adapter
  -> immutable reconstruction audit
```

There is no command that accepts an arbitrary recipient, subject, or body. The
only live command accepts an action ID and attempt number. It reloads every value
from the local database, renders the fixed message, and revalidates it. An action
must have both `external_action_approved=1` and `message_approved=1`, and the
rendered hash must equal `approved_message_hash`.

Owner approvals use an HMAC over the action/message hash. The signing key is read
from `LEVEL1_OWNER_APPROVAL_KEY_FILE` and must not be available to Hermes or any
routine message-analysis context. Activation requires another HMAC over the full
manifest hash. Deactivation does not require the signing key.

Two independent kill switches must be true before a transport can be called:

- `LEVEL1_OUTBOUND_ENABLED=true` in the runtime environment;
- `level1a_settings.outbound_enabled=true` in the growth database.

Both are false now. There is no Level-1 schedule.

## Allowed action manifest

Each `level1a_actions` row freezes the prospect and organization, public evidence
page, verified contact route, contact kind, recipient where applicable, action
type, one InvoiceWorkshop target, allowed intent, versioned claims, forbidden
claim patterns, template/version, exact rendering fields, follow-up limit, no-
attachment and no-payment controls, approvals, suppression state, and the last
page-verification timestamps. The manifest export adds the exact rendered message
and SHA-256 hash.

The allowed Level-1A action types are resource suggestions, legitimate directory
submissions, broken-resource replacements, and relevant roundup suggestions.
Guest articles, named-author pitches, community posts, paid/sponsored/reciprocal
placements, mass email, fake identities, and production SEO changes are outside
Level 1A.

The pilot contains three resource-oriented actions:

1. Freelance Things: its published resource-submission form; no account, payment,
   or generic form automation.
2. LedgerCo: `info@ledgerco.ca`, using its published resource and contact pages.
3. Business-Software.com: its published no-cost product-listing form; an earlier
   model pass did not retain it, so the seed records the later deterministic human
   evidence review explicitly. CAPTCHA means generic automation remains forbidden.

Construction Executive, Modern Contractor Solutions, and Contractor Magazine are
not in this manifest because they require Level-1B editorial/author work.

### Exact initial pilot messages

Freelance Things — form route — hash
`bc95be38c25e44d910db0c7cda3073b55c7d15e81df46502eca38f5e93b46155`:

> **InvoiceWorkshop — invoicing resource for freelancers**
>
> Hello Freelance Things team,
>
> InvoiceWorkshop is free to use, requires no signup for its core document tools,
> and saves workspace data locally in the browser.
>
> The invoice template may be useful to freelancers who want to prepare client
> invoices without opening another hosted account:
> https://invoiceworkshop.com/invoice-template/
>
> Please include it only if it meets your resource standards.
>
> InvoiceWorkshop  
> hello@invoiceworkshop.com

LedgerCo — `info@ledgerco.ca` — hash
`25bbdf12c05096b396dad68f235b8ba405da538524faa4b11861edf4e0b2f792`:

> **Possible companion resource for your invoice-template library**
>
> Hello LedgerCo team,
>
> InvoiceWorkshop creates PDFs in the browser, and document contents are not
> uploaded to InvoiceWorkshop application servers.
>
> Your library already includes invoice and bookkeeping resources. This invoice
> template may be a useful optional companion:
> https://invoiceworkshop.com/invoice-template/
>
> If it does not meet your resource standards, no response or inclusion is
> expected.
>
> InvoiceWorkshop  
> hello@invoiceworkshop.com

Business-Software.com — form route — hash
`69807961a389dc92fa9010700196d0b5703e4918472d5986c9e7ecd50e90912b`:

> **InvoiceWorkshop product listing**
>
> InvoiceWorkshop is a browser-based business-document workspace.
>
> InvoiceWorkshop supports saved customers and reusable items, plus conversion
> between supported estimate, quotation, work-order, proforma, and invoice
> workflows.
>
> It fits the financial-management category and is available at
> https://invoiceworkshop.com/
>
> Please list it only if it meets the directory's editorial standards.
>
> InvoiceWorkshop  
> hello@invoiceworkshop.com

The first and final follow-up texts are also deterministic and exported with the
manifest. Their approval-bundle hashes are, respectively: Freelance Things
`987114e494d2f31b35fb6309ef76a7a307b6795d1717a1ce93b02b20020ab96a`,
LedgerCo `2d4a6caa298c9e357f7469cba25023984744e2edbf930333b9fb49bf9812dad0`,
and Business-Software.com
`e748f50c284561e74747b92671377f019301b08a1223dc874a2b4e7f588d39b9`.

## Versioned claims registry

Only the following narrowly worded claim families can be rendered:

- free core document tools, no signup, and local browser persistence;
- browser-side PDF generation and no upload of document contents to
  InvoiceWorkshop application servers;
- saved customers/items and only the conversions supported in code;
- no InvoiceWorkshop branding or watermark on downloaded customer documents.

Evidence references point to current code, privacy/product documentation, and
tests. The validator rejects unknown or inactive claims and fixed forbidden
patterns including best/leading/#1/safest, compliance and certification claims,
guarantees, endorsements, volume claims, DA/DR/dofollow language, backlinks, link
exchanges, and reciprocal terms. It also rejects invented numeric claims,
unexpected URLs, multiple InvoiceWorkshop URLs, attachment language, payment or
sponsorship language, malformed recipients, and messages over the fixed limit.

## Validation and external-content isolation

Public prospect pages are fetched only to confirm HTTP health and the continued
presence of at least two allowlisted relevance terms. Page text is never appended
to the message and is never interpreted as an instruction. Message generation is
pure string rendering and does not use an LLM. The prompt-injection test supplies
an external page containing an instruction to ignore policy and exfiltrate
passwords; the rendered message remains byte-for-byte unchanged.

The validator also rejects prospect/action page or contact mismatches, account or
payment requirements, stale or irrelevant pages, duplicate organization routes,
already-contacted initials, suppressions, out-of-sequence or early follow-ups,
unapproved content, hash drift, and daily cap exhaustion.

Initial limits are three new contacts per UTC day and five total messages per UTC
day. One initial and at most two follow-ups are allowed. The first follow-up waits
at least four business days; the final one waits at least seven more business
days. Any reply, decline, unsubscribe, bounce, placement, or suppression stops the
sequence.

## Reply state machine

Reply content is not stored; only its SHA-256 hash and deterministic classification
are persisted. Classes are positive, information requested, decline, unsubscribe,
bounce, payment requested, editorial author required, partnership, legal/
compliance, and ambiguous.

- Decline, unsubscribe, and bounce create a durable suppression automatically.
- Positive replies stop follow-ups.
- Information requests may only produce a factual draft for review.
- Payment, author/editorial, partnership, legal/compliance, and ambiguous replies
  always escalate. No business commitment or negotiated response is automatic.

## Audit ledger

Every attempted action records start/end time, action and message IDs, attempt,
dry-run/live mode, exact subject and body, route, source page, target, message hash,
validation result and rejection reason, provider ID if one exists, delivery and
reply states, suppression state, and external side effects. A rejected operation
does not call a provider. Dry runs always record external side effects as `none`.

## Mailbox readiness

Current read-only verification found:

- MX routes to Zoho India (`mx.zoho.in`, `mx2.zoho.in`, and `mx3.zoho.in`);
- SPF authorizes `zohomail.in` with a soft-fail ending;
- a `zmail` DKIM public key is published;
- TLS connections to `imappro.zoho.in:993` and `smtppro.zoho.in:465` succeeded;
- no DMARC TXT record is published at `_dmarc.invoiceworkshop.com`.

No mailbox authentication or live delivery test was performed. That would be an
external action, and no programmatic Zoho credential configuration is available
to this implementation. Therefore send, receive, reply correlation, and bounce
handling are not end-to-end verified.

The preferred mailbox transport is the Zoho Mail API, not a general SMTP tool.
Use the minimum OAuth permissions needed to create/send messages and read message
state/replies. Store the token or refresh-token material in a root-owned secret
file outside the repository and expose only its path as
`ZOHO_MAIL_ACCESS_TOKEN_FILE`; never place the token in Git, the growth database,
an action manifest, a prompt, or model context. Rotate it by replacing that file
and revoking the old grant in Zoho. Hermes must not have the owner signing key,
mail token, arbitrary filesystem/shell access, or the transport object.

Before activation, publish DMARC in monitoring mode with an owner-controlled
aggregate-report mailbox, verify SPF/DKIM/DMARC alignment on an owner-authorized
test, provision least-privilege Zoho API credentials, and implement/test inbound
polling and provider bounce correlation. A site-specific handler is also required
for each approved form; CAPTCHA must never be bypassed.

## Pilot dry-run procedure

```bash
python3 scripts/growth_level1a.py seed-pilot
python3 scripts/growth_level1a.py manifest
python3 scripts/growth_level1a.py dry-run
```

The manifest and exact messages must be reviewed once. Approval and activation are
separate owner-signed commands in `growth_level1a_admin.py`; neither command has
been run. A later operator must not enable the database switch or environment
switch until mailbox and form blockers above are resolved.

## Test evidence

The focused suite covers a clean dry run, unapproved live execution, contact-route
mismatch, stale/irrelevant pages, duplicate initials, suppression, missing and too-
early follow-ups, unknown claims, forbidden and numeric claims, unexpected URLs,
attachments/payment, prompt injection, malformed recipients, duplicate
organizations, reply hard stops, and daily caps. The complete growth suite also
passes.

## Level-1B boundary

Level 1B remains documentation-only. It would require a real approved author,
publication-specific editorial review, byline/credential verification, and
separate approval. No Level-1B actions, schedules, accounts, messages, articles,
or production changes were created.

## Construction asset status

The existing construction page already covers customer/project/jobsite references,
labor/material/equipment line items, deposits and balances, payment terms,
completion/change notes, and estimate/work-order/invoice workflow. It does not yet
contain the proposed filled fictional example, retainage treatment, and explicit
pre-send approval checklist. That enrichment remains a separate product change;
this task did not create a URL or modify the website.

## Current blocker

The deterministic layer and review manifest can be dry-run, but Level 1A is not
safe to activate until DMARC and the least-privilege programmatic mailbox path are
verified end to end, inbound reply/bounce polling is connected, and approved form
routes have site-specific non-CAPTCHA-bypassing handlers. Keep both kill switches
false.

### LEVEL 1A BLOCKED
