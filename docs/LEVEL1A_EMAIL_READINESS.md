# InvoiceWorkshop Level-1A email readiness

Prepared: 2026-09-01 UTC

No prospect was contacted. The only outbound messages were a bounded
owner-controlled create/read/reply test from and to `hello@invoiceworkshop.com`.
No form, account, public post, payment, production change, deployment, or Level-1
schedule was created.

## Zoho API

- Datacenter: India.
- Accounts endpoint: `https://accounts.zoho.in`.
- Mail API: `https://mail.zoho.in/api`.
- Exact scopes: `ZohoMail.accounts.READ`, `ZohoMail.messages.READ`, and
  `ZohoMail.messages.CREATE`. No `.ALL` scope is present.
- Mailbox: `hello@invoiceworkshop.com`.
- Resolved account ID: `290640000000002002`.
- Refresh/access material:
  `/home/azureuser/.config/invoiceworkshop/zoho_oauth.json`, directory mode 700,
  file mode 600. Tokens and client secrets are never printed or stored in Git,
  the growth database, action manifests, audit output, or model context.
- Original self-client file mode was tightened from 664 to 600.

The runtime refreshes the access token using the India OAuth endpoint, atomically
replaces the secret file, pins the India API domains, verifies the exact three-
scope set, and refuses a secret file accessible by group or other users.

The API successfully resolved the account and listed inbox metadata. A fixed
owner-controlled self-mail verification then passed message creation, inbound
delivery, content read, API reply, reply delivery, and reply content read. The
original and reply share the same Zoho thread ID. No prospect address was used.

The currently configured Zoho display name is `Invoice Workshop Team`, not the
required `InvoiceWorkshop`. The narrow OAuth token correctly has no account-update
permission. Change this send identity in Zoho Mail settings before owner approval;
do not broaden the routine token merely to change a one-time mailbox setting.

## Authentication

Public resolution through both Cloudflare and Google returns:

- SPF: `v=spf1 include:zohomail.in ~all`;
- DKIM: one `zmail` DKIM record;
- DMARC: one record with `p=none`, `sp=none`, relaxed SPF/DKIM alignment, and
  owner-controlled aggregate/forensic report destinations.

The received self-mail header API reported SPF, DKIM, and DMARC as `pass`. An
external owner-controlled recipient is still required to verify those results and
the exact From display outside Zoho's own mailbox boundary. No external address
was guessed from mailbox contents.

## Inbound automation

`growth_level1a_mailbox.py` exposes only `status`, `bootstrap`, and `poll`.
Bootstrap records the current receive watermark without reading message content.
Polling reads up to 100 rows of inbox metadata and fetches content only when:

- a thread ID matches a sent Level-1A email audit row;
- the exact approved sender and normalized subject match; or
- a delivery-failure sender/subject is present and the bounce content contains an
  exact previously approved recipient.

Unmatched bodies and attachments are never read. The output contains only counts
and redacted error hashes, so Hermes does not receive arbitrary mailbox content.
Matched content goes only through deterministic classification, is stored only as
a SHA-256 hash, and is never treated as an executable instruction.
Before a matched message can create suppression or reply state, the poller reads
its authentication headers and requires DMARC pass or both SPF and DKIM pass.
Failed or unverified authentication is recorded as ambiguous and escalated; it
cannot suppress a route automatically.

Decline, unsubscribe, and bounce create durable suppressions. Any reply or live
placement stops follow-ups. Positive replies stop follow-ups; information requests
require a factual draft review; payment, author/byline, partnership, legal/
compliance, and ambiguous replies escalate. Bounce matching and suppression are
covered by a deterministic integration test; no deliberate external bounce was
generated in this task.

## Execution-class separation

Every action is explicitly one of:

- `level1a_email`: eligible for the restricted Zoho transport after exact owner
  approval and activation;
- `level1a_form`: remains disabled and has no installed live handler.

Database switches are independent. `outbound_enabled`,
`email_outbound_enabled`, and `form_outbound_enabled` are all currently false.
Owner activation can enable only the global and email switches; it explicitly
keeps the form switch false. Live execution additionally requires
`LEVEL1_OUTBOUND_ENABLED=true`, action approval, exact initial/follow-up hashes,
current page evidence, recipient and contact match, suppression/duplicate/cadence
checks, and daily caps.

## Email-only pilot

All five current pages and public routes passed the deterministic dry run on
2026-09-01. Each result is `review_ready`; approvals remain false and external
side effects are `none`.

### LedgerCo

To: `info@ledgerco.ca`  
Target: `https://invoiceworkshop.com/invoice-template/`  
Initial hash: `25bbdf12c05096b396dad68f235b8ba405da538524faa4b11861edf4e0b2f792`

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

### Coalesco

To: `info@coalesco.co.uk`  
Target: `https://invoiceworkshop.com/invoice-template/`  
Initial hash: `d58b7ce00c86be5f764b4c6b63116d4baec9a7c8e3a01c2149225d7df8e53079`

> **Possible browser companion to your invoice download**
>
> Hello Coalesco team,
>
> InvoiceWorkshop is free to use, requires no signup for its core document tools,
> and saves workspace data locally in the browser.
>
> Your downloads page includes an invoice template and other practical business
> resources. This working invoice template may be a useful optional companion:
> https://invoiceworkshop.com/invoice-template/
>
> Please consider it only if it fits your resource standards.
>
> InvoiceWorkshop  
> hello@invoiceworkshop.com

### Umbrex

To: `inquiry@umbrex.com`  
Target: `https://invoiceworkshop.com/invoice-template/`  
Initial hash: `54db5f8328a1b9c1845beb648ab60c43d4029ca28a8c14b9cc31d979566bd667`

> **Working companion for your consultant invoice guide**
>
> Hello Umbrex team,
>
> InvoiceWorkshop creates PDFs in the browser, and document contents are not
> uploaded to InvoiceWorkshop application servers.
>
> Your invoice guide helps independent consultants prepare and manage client
> invoices. This browser-based invoice template may be a useful optional working
> companion: https://invoiceworkshop.com/invoice-template/
>
> Please consider it only if it improves the existing resource for consultants.
>
> InvoiceWorkshop  
> hello@invoiceworkshop.com

### Freelancers Union

To: `partnerships@freelancersunion.org`  
Target: `https://invoiceworkshop.com/invoice-template/`  
Initial hash: `7b528e756fb4742c7a9255397c4ed18bb5dfeca071a658ef89ac3dab4eb636fa`

> **Free invoicing resource for independent workers**
>
> Hello Freelancers Union team,
>
> InvoiceWorkshop is free to use, requires no signup for its core document tools,
> and saves workspace data locally in the browser.
>
> Your resource collection helps independent workers manage clients and finances.
> This invoice template may be a useful addition for freelancers who need a
> working document tool: https://invoiceworkshop.com/invoice-template/
>
> Please consider it only if it serves your members without commercial placement
> terms.
>
> InvoiceWorkshop  
> hello@invoiceworkshop.com

### Creative Boom

To: `hello@creativeboom.com`  
Target: `https://invoiceworkshop.com/invoice-template/`  
Initial hash: `1197b1548c5287d769fedf60406b2741bc215912293d23aaf4de33f0e77a4781`

> **Resource suggestion for your freelancer tools coverage**
>
> Hello Creative Boom team,
>
> InvoiceWorkshop is free to use, requires no signup for its core document tools,
> and saves workspace data locally in the browser.
>
> Your resource coverage collects practical tools for creative freelancers and
> small-business owners. This working invoice template may be worth considering
> in a future update: https://invoiceworkshop.com/invoice-template/
>
> Please include it only if an editor finds it genuinely useful to readers.
>
> InvoiceWorkshop  
> hello@invoiceworkshop.com

The exported email manifest includes the deterministic first and final follow-up
messages and their combined approval hashes. Initial cadence remains three new
emails and five total messages per UTC day.

## Form pilot

- Freelance Things: on-page resource form; no site-specific handler.
- Business-Software.com: on-page directory form with CAPTCHA; no site-specific
  handler.

Both actions remain unapproved. `form_outbound_enabled=false` cannot be changed by
the email activation flow. CAPTCHA and anti-bot controls must never be bypassed.

## Remaining gates

1. In Zoho Mail settings, change the active send identity display name from
   `Invoice Workshop Team` to exactly `InvoiceWorkshop`.
2. Supply an external owner-controlled test address. Send the fixed verification
   message, inspect its external headers for SPF/DKIM/DMARC pass, receive and read
   the owner's reply, and reply once through the API.
3. Review and owner-sign the five email action/message bundles. This task does not
   constitute that approval and did not activate either outbound switch.

### LEVEL 1A EMAIL BLOCKED
