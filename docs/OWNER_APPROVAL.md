# Level-1A owner approval

Prepared: 2026-09-01 UTC

No new external action can be approved without a signature made on a machine
this server has no access to.

## Why this replaced the previous gate

The first activation used an HMAC secret. HMAC is symmetric, so any process able
to *verify* an approval could equally *produce* one — and that key was generated
on this server by the same agent that executes sends. It proved a change was
signed, not that the owner signed it. That key has been destroyed.

Approvals are now Ed25519 signatures over a canonical payload, verified with a
public key. The server can check an approval and can never manufacture one.

## Architecture

```
owner's Mac                          InvoiceWorkshop server
-----------                          ----------------------
~/.ssh/invoiceworkshop_owner         (never present)
~/.ssh/invoiceworkshop_owner.pub --> ~/.config/invoiceworkshop/
                                       level1_owner_allowed_signers   (0600)

  ssh-keygen -Y sign  ---signature--> ssh-keygen -Y verify
```

Signing uses the SSHSIG format built into OpenSSH, which ships with macOS and
every modern Linux. Nothing needs installing on either machine, and the
signature primitive is audited code rather than something hand-rolled here.

The signed payload is regenerated from live database state at verification time
and is deliberately human-readable:

```
invoiceworkshop-level1a:approve-action:v2
action_id=21
organization=Coalesco
execution_class=level1a_email
contact_kind=email
recipient=info@coalesco.co.uk
external_page_url=https://coalesco.co.uk/resources/ebooks-and-downloads/
target_url=https://invoiceworkshop.com/invoice-template/
max_followups=1
approval_hash=0e9d798b…
message_hash[0]=2e759df0…
message_hash[1]=6c4afcf1…
```

Read it before signing: it names the recipient, the page, the target URL and the
hash of every message that may be sent. Because the payload is rebuilt from the
database, changing the recipient, the target, the copy or the follow-up count
produces a different payload and the old signature stops verifying. A signature
therefore cannot be moved onto a different action, message or recipient. Both
replay paths are covered by tests, and were demonstrated to fail in practice.

Every verification attempt — pass or fail — is written to
`level1a_approval_audit` with the payload hash, the signer key fingerprint and
the result.

## What the owner runs, once

On the Mac:

```sh
ssh-keygen -t ed25519 -f ~/.ssh/invoiceworkshop_owner -C "invoiceworkshop-owner"
cat ~/.ssh/invoiceworkshop_owner.pub
```

Use a passphrase. Then, on the server, install **only the `.pub` value**:

```sh
cd /home/azureuser/invoiceworkshop
PYTHONPATH=scripts python3 scripts/growth_level1a_admin.py install-owner-key \
  --public-key 'ssh-ed25519 AAAA... invoiceworkshop-owner'
```

`install-owner-key` refuses anything that is not an `ssh-ed25519` public key and
refuses private key material outright.

## Approving an action

Server — produce the payload:

```sh
PYTHONPATH=scripts python3 scripts/growth_level1a_admin.py approval-request --action-id 21
```

It writes `~/.config/invoiceworkshop/approvals/action-21.approval` and prints it.

Mac — read it, then sign:

```sh
scp <server>:~/.config/invoiceworkshop/approvals/action-21.approval .
cat action-21.approval        # read what you are authorising
ssh-keygen -Y sign -f ~/.ssh/invoiceworkshop_owner \
  -n invoiceworkshop-level1a action-21.approval
scp action-21.approval.sig <server>:/tmp/
```

Server — verify and approve:

```sh
PYTHONPATH=scripts python3 scripts/growth_level1a_admin.py approve-action \
  --action-id 21 --signature-file /tmp/action-21.approval.sig
```

Enabling the outbound switches uses the same flow with `approval-request` (no
`--action-id`) and `activate --signature-file`.

Turning outbound **off** needs no signature. `deactivate` always works, as does
setting `LEVEL1_OUTBOUND_ENABLED=false` in
`~/.config/invoiceworkshop/level1.env`. Stopping is never gated.

## Current state

- Owner public key: **not yet installed**. Until it is, no new action can be
  approved and no manifest can be activated.
- The four pilot approvals made under the previous HMAC gate are preserved and
  recorded in the audit as `hmac_legacy`, with the reason noted.
- The HMAC key file has been destroyed and no code path reads it.
