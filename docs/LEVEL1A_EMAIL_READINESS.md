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

The configured Zoho display name was `Invoice Workshop Team` at the time of the
Codex run. The owner has since corrected it in Zoho Mail settings, and the
`/accounts` API now returns display name `InvoiceWorkshop`, enabled, for
`hello@invoiceworkshop.com`. The narrow OAuth token still correctly has no
account-update permission; the setting was changed by the owner, not by the token.
`ZohoMailTransport` refuses to send unless this identity reads exactly
`InvoiceWorkshop`.

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

Four actions. Copy was rewritten on 2026-09-01 to read as a short human
resource suggestion, and follow-ups were reduced from two to one, sent five
business days after the initial message and only when nothing has come back.
Freelancers Union now points at the homepage rather than /invoice-template/.
All four render byte-exact against the approved copy. Manifest hash:
`148e97136ee67e10e48b06a4388f6942401cb9f31d442fabba1ac7213f48872f`.

### LedgerCo

Page: `https://ledgerco.ca/resources/`  
To: `info@ledgerco.ca`  
Target: `https://invoiceworkshop.com/invoice-template/`  
Approval hash: `e3e705cd462682f3f70a0ba6602ea68ef16ee591d940a1d01d3469e8d88faed9`  
Initial hash: `ed23d2fb041505612401289ba93b3056737864b4d39e9c1ba5c9624e2394d3cf`  
Follow-up hash: `b3944cce08d19f7504a4175f5838ccfbdd58bfff71361fbcef4251b7fcee99d0`

> **Free invoice tool for your resource library**
>
> Hello LedgerCo team,
>
> I came across your resources page and noticed the invoice and bookkeeping materials you share with small businesses.
>
> We built InvoiceWorkshop, a free invoice tool that works without signup and keeps the workspace in the browser. It may be useful as an interactive companion to the invoice resources you already provide:
>
> https://invoiceworkshop.com/invoice-template/
>
> If it’s useful for your readers, feel free to include it. If not, no worries.
>
> InvoiceWorkshop
> hello@invoiceworkshop.com

### Coalesco

Page: `https://coalesco.co.uk/resources/ebooks-and-downloads/`  
To: `info@coalesco.co.uk`  
Target: `https://invoiceworkshop.com/invoice-template/`  
Approval hash: `0e9d798b33cf2185003b72945c99c83fd5f9c7331c36df95a0574d457f9bbba8`  
Initial hash: `2e759df0324af0cecd1a8f5b59cbe9073af7f92719e85255ae1be8796853dab2`  
Follow-up hash: `6c4afcf10fa130df2a8b9a9bd77cf1eb1ea2634eb3361e865e35db31b573348e`

> **Interactive companion to your invoice template**
>
> Hello Coalesco team,
>
> I noticed your downloads page includes an invoice template alongside your other practical business resources.
>
> InvoiceWorkshop is a free, no-signup invoice tool that saves workspace information locally in the browser. It could be a useful interactive companion for people who prefer creating an invoice directly online:
>
> https://invoiceworkshop.com/invoice-template/
>
> If it fits your resource library, feel free to include it.
>
> InvoiceWorkshop
> hello@invoiceworkshop.com

### Umbrex

Page: `https://umbrex.com/resources/invoice-template/`  
To: `inquiry@umbrex.com`  
Target: `https://invoiceworkshop.com/invoice-template/`  
Approval hash: `431f699fe9a72a52ddd1defff087832e8bcecf7c31d94d8e8479798fdd8dc03b`  
Initial hash: `fd3632349944b047cc84bb2f66ed9e7a28b9a08192bdff187e85f195fd942a71`  
Follow-up hash: `661d328735d48a67d5541b5ba6c33fc0c831ce9df0bf68adfe4b695eebd8e3d4`

> **Free invoicing tool for independent consultants**
>
> Hello Umbrex team,
>
> I came across your invoice guide for independent consultants and the downloadable templates you provide.
>
> We built InvoiceWorkshop, a free browser-based invoice tool that requires no signup and generates the PDF directly in the browser. It may be useful as a working companion to your existing guide:
>
> https://invoiceworkshop.com/invoice-template/
>
> If it’s useful for your consultants, feel free to include it.
>
> InvoiceWorkshop
> hello@invoiceworkshop.com

### Freelancers Union

Page: `https://freelancersunion.org/resources/`  
To: `community@freelancersunion.org`  
Target: `https://invoiceworkshop.com/`  
Approval hash: `83434860b09c3d4f977521ce417b4eca1aa18042b8d69b483cbb83f705083d26`  
Initial hash: `f46d422f3f4231e3febfdc61af271cec654761f58c6f0a5ddfb4d8d0f618eac0`  
Follow-up hash: `38eb04b5edd73b6880cf3dce3dbd2386325164bd9e3ce540dfd6a83528397c74`

> **Free invoicing tool for freelancers**
>
> Hello Freelancers Union team,
>
> I was looking through your resources for freelancers around managing clients and finances.
>
> We built InvoiceWorkshop, a free invoicing tool that requires no signup and remembers business, customer and item information locally in the browser.
>
> It may be useful to members who need a lightweight way to create invoices without adopting another software account:
>
> https://invoiceworkshop.com/
>
> If you think it belongs in your resource collection, feel free to include it.
>
> InvoiceWorkshop
> hello@invoiceworkshop.com

The single follow-up reuses the initial subject prefixed with `Re:` and repeats
no product claim. Initial cadence remains three new emails and five total
messages per UTC day.

## Form pilot

- Freelance Things: on-page resource form; no site-specific handler.
- Business-Software.com: on-page directory form with CAPTCHA; no site-specific
  handler.

Both actions remain unapproved. `form_outbound_enabled=false` cannot be changed by
the email activation flow. CAPTCHA and anti-bot controls must never be bypassed.

## Remaining gates

1. ~~Change the send identity display name to `InvoiceWorkshop`.~~ Done by the
   owner and verified through the Zoho `/accounts` API on 2026-09-01.
2. ~~External owner-controlled delivery test.~~ Completed 2026-09-01. See the
   external delivery test section below.
3. Review and owner-sign the email action/message bundles. This task does not
   constitute that approval and did not activate either outbound switch.

## Continuity re-verification (2026-09-01, Claude Code takeover)

Ground truth was re-established from the repository, Git, the growth database, the
Hermes scheduler and the live Zoho API rather than from the handoff text.

- HEAD `2db737b` on `main`; tree clean apart from the untracked handoff brief.
- Level-0 jobs `a56bbe317393` (daily 11:00 UTC), `0cf8f7ecec07` (weekly Mon 12:00
  UTC) and `a4bf3bdace36` (research Mon/Wed/Fri 13:00 UTC) are active and match
  the handoff. No Level-1 schedule and no high-frequency cron exist.
- All 66 growth tests pass.
- `outbound_enabled`, `email_outbound_enabled` and `form_outbound_enabled` are all
  false; `LEVEL1_OUTBOUND_ENABLED` is unset. A `live` attempt on 2026-08-31 was
  correctly rejected with `environment kill switch LEVEL1_OUTBOUND_ENABLED is
  false`, which is positive evidence that the gate fires.
- Zero prospect emails, forms, accounts, posts, payments or deployments. Every
  action-audit row is `dry_run` except that one rejected `live` attempt, and every
  row records `external_side_effects=none`.
- OAuth refresh was exercised end to end: a forced refresh issued a new access
  token, persisted it at mode 600, and a subsequent account lookup succeeded.
  Scopes remain exactly the three reviewed ones with no `.ALL`.

### Candidate re-verification

Independent fetches of the five external pages and their contact routes, rather
than machine validation alone, changed two conclusions.

- LedgerCo, Coalesco and Umbrex remain valid. Each page is live and each recipient
  is published on the site. The Umbrex pages return 403 to unusual user agents but
  serve normally to a browser user agent, and `inquiry@umbrex.com` appears on both
  the resource page and the contact page.
- Freelancers Union has a routing defect. Its contact page labels
  `partnerships@freelancersunion.org` as the **Partnerships** route and
  `community@freelancersunion.org` as the **General** route. A no-strings resource
  suggestion belongs on the general route; the partnerships route frames it as a
  commercial proposal, which is an escalation category rather than an opening
  move. The recipient is pinned in the `PILOT` allowlist in
  `scripts/growth_level1a.py`, so correcting it is an owner decision and a code
  change, not a database edit. Held pending that decision.
- Creative Boom is rejected. The roundup is titled "in 2019", was published
  2019-07-04, and its invoicing section lists paid time-tracking and billing SaaS
  (FreeAgent, Harvest, Paymo, Hiveage) rather than free document tools. Creative
  Boom also sells placement through `advertising@creativeboom.com`. Asking an
  editor to retro-edit a seven-year-old listicle fails the "if Google did not
  exist, would this contact still make sense" test.

### Unrelated mailbox traffic observed

The mailbox contains owner/manual traffic that did not come from the Level-1A
system: an inbound `There?` from the owner's external test address
(2026-08-31T18:37:17Z), an inbound `Check` from `discowisco1@gmail.com`
(19:17:50Z) and an outbound `Hey there` to that same address (19:19:29Z), plus a
Zoho notice that an email address was deleted from the account
(2026-09-01T09:00:20Z). The action ledger records no live send, so none of this is
attributable to the growth automation, but the owner should confirm it was manual
webmail testing.

## External owner-controlled delivery test (2026-09-01)

The fixed verification message was sent at 09:12:57Z to the owner's external
address. The owner supplied the receiving Gmail `Show original` headers, which
report, at `mx.google.com`:

- `spf=pass`, `smtp.mailfrom=hello@invoiceworkshop.com`, sending host
  `sender-op-o11.zoho.in` `103.117.158.11`;
- `dkim=pass`, `header.i=@invoiceworkshop.com`, selector `s=zmail`;
- `dmarc=pass`, `p=NONE`, `header.from=invoiceworkshop.com`;
- delivered over TLS 1.3 with `Delivered-To: <owner external address>`.

The owner's reply arrived as `1788254436672110501` on Zoho thread
`1788253977977130100`, the same thread as the original send. Its inbound
authentication headers were read through the poller's own gate helper, which
returned `pass` on SPF, DKIM and DMARC. One API reply was then sent
(`1788254534701119300`) and Zoho placed it on that same thread, so the full
outbound → delivery → reply → threaded API reply cycle is verified.

The mailbox poller correctly reported `matched_replies: 0` for this exchange. That
is the intended behaviour, not a defect: the verification message was sent
directly through `ZohoClient`, so it has no `level1a_action_audit` row, and the
poller refuses to read or act on any message it cannot match to a sent Level-1A
action. Prospect reply matching remains covered by the deterministic integration
tests.

### Defect found and fixed: missing From display name

The received headers showed `From: hello@invoiceworkshop.com` with **no display
name**, despite the Zoho account `displayName` reading `InvoiceWorkshop` and
`ZohoMailTransport` verifying that setting before every send.

Root cause: Zoho emits the `From` header verbatim from the API `fromAddress`
field, and `growth_zoho.py` passed the bare mailbox address. The account
`displayName` setting governs only webmail compose, so the transport's pre-send
check was asserting a setting that had no effect on API sends.

Fix: `growth_zoho.py` now defines `FROM_HEADER = "InvoiceWorkshop
<hello@invoiceworkshop.com>"` and uses it for both `send_plaintext` and
`reply_plaintext`. Two regression tests assert the exact identity string and that
both send paths carry it; the growth suite is 68/68 green. A second
owner-controlled message (`1788254599542130300`) was sent to confirm, and Zoho now
reports `sender: InvoiceWorkshop` for it against `sender:
hello@invoiceworkshop.com` for the pre-fix message.

The transport's `send_identity()` check is retained as defence in depth, but the
emitted identity no longer depends on it.

## Owner-approved pilot revision (2026-09-01)

- **Freelancers Union** re-routed from `partnerships@freelancersunion.org` to
  `community@freelancersunion.org`. The live contact page labels that address as
  the **General** route and lists Partnerships separately, so the general route is
  the correct one for an unsolicited resource suggestion. The closing line was
  also reframed from "only if it serves your members without commercial placement
  terms" to "only if it is genuinely useful to your members", removing commercial
  framing entirely. The bundle was regenerated and re-hashed.
- **Creative Boom** removed from the reviewed `PILOT` allowlist, its action set to
  `suppression_state='suppressed'`, and its prospect marked `rejected` with the
  reason recorded. It is now blocked twice over: the dry run rejects it with
  `prospect is not currently evidence-qualified`, and `_validate_frozen_manifest`
  would reject it as absent from the code allowlist. It was not replaced.
- `export_manifest` now excludes non-active actions, so a suppressed action can no
  longer appear in an owner-review bundle. Covered by a regression test.
- Growth suite: 69/69 green.

All four surviving actions were re-checked live: pages return 200 and each
recipient is published on the site. Coalesco and Umbrex serve 403 to some user
agents through bot protection; both render normally otherwise and were confirmed
present with their published addresses.

## Owner-approved copy revision (2026-09-01)

- Follow-ups reduced from two to one, at five business days, then the action
  stops permanently. `max_followups` is 1 and the CLI accepts only attempt 0 or 1.
- Copy rewritten to the owner's supplied text. The formal "optional companion",
  "resource standards" and "no inclusion is expected" phrasing is gone.
- Freelancers Union target moved from `/invoice-template/` to the homepage.
- Creative Boom remains rejected and suppressed; it was not replaced.

One structural change was required and is worth flagging. The previous template
injected canonical claim text verbatim between the opening and the fit sentence,
so approved claims could not drift. The new hand-written copy states the product
claim in its own words, which that mechanism cannot express. Rather than drop the
guarantee, `level1a_claim_paraphrases` now records owner-approved wordings for
each canonical claim, and an initial message must carry either the canonical text
or a registered wording for every claim key it declares. Each of the four new
sentences was checked against the product and registered with an evidence
reference. Follow-ups repeat no claim and are exempt. Copy was otherwise
unaltered.

### LEVEL 1A EMAIL READY FOR ACTIVATION

