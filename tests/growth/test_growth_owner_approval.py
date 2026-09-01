from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import growth_level1a_admin as admin  # noqa: E402
from growth_level1a import initialize, seed_reference_data  # noqa: E402


def build_action(connection, *, organization="Example Org", recipient="info@example.org",
                 page="https://example.org/resources/",
                 target="https://invoiceworkshop.com/invoice-template/") -> int:
    """Minimal approved-shape action row: prospect + qualification + action."""
    seed_reference_data(connection)
    now = "2026-09-01T00:00:00+00:00"
    cursor = connection.execute(
        """INSERT INTO prospects (domain, page_url, prospect_type, opportunity_score, risk,
             why_fit, audience, contact_method, requires_account, requires_payment,
             link_type, source_url, status, notes, discovered_at, updated_at)
           VALUES ('example.org', ?, 'resource', 80, 'low', 'fit', 'audience', ?, 0, 0,
                   'editorial', ?, 'qualified', '', ?, ?)""",
        (page, page, page, now, now),
    )
    prospect_id = int(cursor.lastrowid)
    connection.execute(
        """INSERT INTO prospect_qualification (prospect_id, channel, page_evidence,
             outbound_resources, target_url, proposed_action, confidence, second_pass_pass,
             review_reason, reviewed_at)
           VALUES (?, 'resource', 'evidence', '[]', ?, 'resource inclusion', 'high', 1, 'ok', ?)""",
        (prospect_id, target, now),
    )
    cursor = connection.execute(
        """INSERT INTO level1a_actions (prospect_id, organization, external_page_url,
             verified_contact_route, contact_kind, execution_class, recipient, form_handler,
             action_type, target_url, allowed_intent, allowed_claim_keys_json,
             forbidden_claims_json, relevance_terms_json, template_id, template_version,
             subject_value, opening_value, context_value, fit_value, close_value,
             max_followups, attachments_allowed, payment_allowed, external_action_approved,
             message_approved, suppression_state, page_title, page_excerpt,
             created_at, updated_at)
           VALUES (?, ?, ?, ?, 'email', 'level1a_email', ?, NULL, 'resource_suggestion', ?,
                   'intent', '["free_no_signup_local"]', '[]', '["resource"]',
                   'human_resource', 1, 'Subject here', 'Hello team,', 'Context line.',
                   'Fit line.', 'Close line.', 1, 0, 0, 0, 0, 'active', 'Title', 'Excerpt',
                   ?, ?)""",
        (prospect_id, organization, page, page, recipient, target, now, now),
    )
    connection.commit()
    return int(cursor.lastrowid)


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = initialize(str(Path(self.temp.name) / "growth.db"))
        self.action_id = build_action(self.connection)
        self.second_id = build_action(
            self.connection, organization="Other Org", recipient="hello@other.example",
            page="https://other.example/resources/",
        )

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_payload_names_what_is_being_authorised(self):
        payload, approval_hash, hashes = admin.action_payload(self.connection, self.action_id)
        row = self.connection.execute(
            "SELECT recipient, target_url, organization FROM level1a_actions WHERE id=?",
            (self.action_id,),
        ).fetchone()
        self.assertIn(f"recipient={row['recipient']}", payload)
        self.assertIn(f"target_url={row['target_url']}", payload)
        self.assertIn(f"organization={row['organization']}", payload)
        self.assertIn(f"approval_hash={approval_hash}", payload)
        for index, value in enumerate(hashes):
            self.assertIn(f"message_hash[{index}]={value}", payload)

    def test_changing_the_recipient_changes_the_signed_payload(self):
        before, _, _ = admin.action_payload(self.connection, self.action_id)
        self.connection.execute(
            "UPDATE level1a_actions SET recipient='attacker@example.com' WHERE id=?",
            (self.action_id,),
        )
        self.connection.commit()
        after, _, _ = admin.action_payload(self.connection, self.action_id)
        self.assertNotEqual(before, after)

    def test_changing_the_target_url_changes_the_signed_payload(self):
        before, _, _ = admin.action_payload(self.connection, self.action_id)
        self.connection.execute(
            "UPDATE level1a_actions SET target_url='https://invoiceworkshop.com/' WHERE id=?",
            (self.action_id,),
        )
        self.connection.commit()
        after, _, _ = admin.action_payload(self.connection, self.action_id)
        self.assertNotEqual(before, after)

    def test_payloads_for_two_actions_are_distinct(self):
        first, _, _ = admin.action_payload(self.connection, self.action_id)
        second, _, _ = admin.action_payload(self.connection, self.second_id)
        self.assertNotEqual(first, second)


class KeyInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = admin.DEFAULT_ALLOWED_SIGNERS
        self.original_system = admin.SYSTEM_ALLOWED_SIGNERS
        self.original_pin = admin.TRUST_ANCHOR_PIN
        admin.DEFAULT_ALLOWED_SIGNERS = Path(self.temp.name) / "allowed_signers"
        # Isolate from the real root-owned anchor and committed pin.
        admin.SYSTEM_ALLOWED_SIGNERS = Path(self.temp.name) / "absent_system_anchor"
        admin.TRUST_ANCHOR_PIN = Path(self.temp.name) / "absent_pin.json"

    def tearDown(self):
        admin.DEFAULT_ALLOWED_SIGNERS = self.original
        admin.SYSTEM_ALLOWED_SIGNERS = self.original_system
        admin.TRUST_ANCHOR_PIN = self.original_pin
        os.environ.pop("LEVEL1_OWNER_ALLOWED_SIGNERS", None)
        self.temp.cleanup()

    def _args(self, key, identity="owner"):
        class Args:
            public_key = key
            identity = "owner"
        Args.identity = identity
        return Args()

    def test_a_private_key_is_refused(self):
        with self.assertRaises(SystemExit):
            admin.cmd_install_owner_key(self._args(
                "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----"
            ))

    def test_a_non_ed25519_key_is_refused(self):
        with self.assertRaises(SystemExit):
            admin.cmd_install_owner_key(self._args("ssh-rsa AAAAB3NzaC1yc2E test"))

    def test_public_key_is_stored_with_restrictive_permissions(self):
        with contextlib.redirect_stdout(io.StringIO()):
            admin.cmd_install_owner_key(self._args(
                "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleExampleExampleExampleExampleEx owner@mac"
            ))
        path = admin.DEFAULT_ALLOWED_SIGNERS
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIn("ssh-ed25519", path.read_text())
        # Only the key type and value are kept, never a comment that could be a path.
        self.assertEqual(len(path.read_text().split()), 3)

    def test_verification_requires_an_installed_key(self):
        with self.assertRaises(SystemExit):
            admin._allowed_signers()


class TrustAnchorTests(unittest.TestCase):
    """The trust anchor must not be writable by the account that sends email."""

    def test_anchor_is_root_owned_and_not_executor_writable(self):
        anchor = admin.SYSTEM_ALLOWED_SIGNERS
        if not anchor.is_file():
            self.skipTest("system trust anchor not installed in this environment")
        stat = anchor.stat()
        self.assertEqual(stat.st_uid, 0, "trust anchor must be owned by root")
        self.assertFalse(
            os.access(anchor, os.W_OK),
            "the executor account can write the trust anchor",
        )
        self.assertTrue(os.access(anchor, os.R_OK), "the executor must be able to read it")
        # The containing directory must not be writable either, or the file
        # could simply be replaced by unlinking it.
        self.assertFalse(os.access(anchor.parent, os.W_OK))

    def test_a_replaced_anchor_is_refused(self):
        """Swapping the key without updating the committed pin must fail closed."""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        rogue = Path(temp.name) / "rogue"
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(rogue), "-N", "", "-q", "-C", "rogue"],
            check=True, capture_output=True,
        )
        fields = (rogue.with_suffix(".pub")).read_text().split()
        swapped = Path(temp.name) / "allowed_signers"
        swapped.write_text(f"owner {fields[0]} {fields[1]}\n")
        os.environ["LEVEL1_OWNER_ALLOWED_SIGNERS"] = str(swapped)
        self.addCleanup(os.environ.pop, "LEVEL1_OWNER_ALLOWED_SIGNERS", None)
        if not admin.TRUST_ANCHOR_PIN.is_file():
            self.skipTest("no pinned fingerprint in this environment")
        with self.assertRaises(SystemExit) as caught:
            admin._allowed_signers()
        self.assertIn("does not match the fingerprint pinned", str(caught.exception))

    def test_pin_matches_the_installed_anchor(self):
        anchor = admin.SYSTEM_ALLOWED_SIGNERS
        if not (anchor.is_file() and admin.TRUST_ANCHOR_PIN.is_file()):
            self.skipTest("anchor or pin not present")
        import json as _json
        pinned = _json.loads(admin.TRUST_ANCHOR_PIN.read_text())["fingerprint"]
        self.assertEqual(admin.anchor_fingerprint(anchor), pinned)

    def test_install_command_refuses_to_overwrite_a_root_owned_anchor(self):
        anchor = admin.SYSTEM_ALLOWED_SIGNERS
        if not anchor.is_file() or os.access(anchor, os.W_OK):
            self.skipTest("anchor not root-protected in this environment")

        class Args:
            public_key = ("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIRogueRogueRogueRogue"
                          "RogueRogueRo rogue@elsewhere")
            identity = "owner"

        with self.assertRaises(SystemExit) as caught:
            admin.cmd_install_owner_key(Args())
        self.assertIn("root-owned", str(caught.exception))


class NoPrivateKeyOnServerTests(unittest.TestCase):
    def test_admin_module_never_generates_a_keypair(self):
        source = (SCRIPTS / "growth_level1a_admin.py").read_text(encoding="utf-8")
        for forbidden in ('"-t"', "-t ed25519", "keygen -t"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_only_verification_is_performed(self):
        source = (SCRIPTS / "growth_level1a_admin.py").read_text(encoding="utf-8")
        self.assertIn('"-Y", "verify"', source)
        self.assertNotIn('"-Y", "sign"', source)

    def test_symmetric_hmac_gate_is_gone(self):
        source = (SCRIPTS / "growth_level1a_admin.py").read_text(encoding="utf-8")
        for forbidden in ("hmac", "compare_digest", "LEVEL1_OWNER_APPROVAL_KEY_FILE"):
            self.assertNotIn(forbidden, source.lower(), forbidden)


@unittest.skipIf(shutil.which("ssh-keygen") is None, "ssh-keygen unavailable")
class SignatureVerificationTests(unittest.TestCase):
    """End-to-end with a throwaway key standing in for the owner's Mac."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(self.dir / "k"), "-N", "", "-q",
             "-C", "test"],
            check=True, capture_output=True,
        )
        public = (self.dir / "k.pub").read_text().split()
        signers = self.dir / "allowed_signers"
        signers.write_text(f"owner {public[0]} {public[1]}\n")
        os.environ["LEVEL1_OWNER_ALLOWED_SIGNERS"] = str(signers)
        # This suite exercises signature maths with a throwaway key, which by
        # design cannot match the committed production pin.
        self.original_pin = admin.TRUST_ANCHOR_PIN
        admin.TRUST_ANCHOR_PIN = self.dir / "absent_pin.json"

    def tearDown(self):
        admin.TRUST_ANCHOR_PIN = self.original_pin
        os.environ.pop("LEVEL1_OWNER_ALLOWED_SIGNERS", None)
        self.temp.cleanup()

    def _sign(self, payload: str) -> Path:
        target = self.dir / "payload.approval"
        target.write_text(payload)
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(self.dir / "k"),
             "-n", admin.NAMESPACE, str(target)],
            check=True, capture_output=True,
        )
        return Path(str(target) + ".sig")

    def test_a_genuine_signature_verifies(self):
        payload = "invoiceworkshop-level1a:approve-action:v2\naction_id=1\n"
        ok, fingerprint, _ = admin.verify_signature(payload, self._sign(payload), "owner")
        self.assertTrue(ok)
        self.assertTrue(fingerprint.startswith("SHA256:"))

    def test_a_signature_does_not_transfer_to_a_different_payload(self):
        signature = self._sign("invoiceworkshop-level1a:approve-action:v2\naction_id=1\n")
        ok, _, _ = admin.verify_signature(
            "invoiceworkshop-level1a:approve-action:v2\naction_id=2\n", signature, "owner"
        )
        self.assertFalse(ok)

    def test_a_signature_from_an_unknown_key_is_refused(self):
        payload = "invoiceworkshop-level1a:approve-action:v2\naction_id=1\n"
        signature = self._sign(payload)
        # Trust a different, genuine key: the signature must no longer verify.
        other = self.dir / "other"
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(other), "-N", "", "-q", "-C", "other"],
            check=True, capture_output=True,
        )
        fields = other.with_suffix(".pub").read_text().split()
        (self.dir / "allowed_signers").write_text(f"owner {fields[0]} {fields[1]}\n")
        ok, _, _ = admin.verify_signature(payload, signature, "owner")
        self.assertFalse(ok)

    def test_an_unreadable_anchor_fails_closed(self):
        payload = "invoiceworkshop-level1a:approve-action:v2\naction_id=1\n"
        signature = self._sign(payload)
        (self.dir / "allowed_signers").write_text("owner ssh-ed25519 not-a-real-key\n")
        with self.assertRaises(SystemExit):
            admin.verify_signature(payload, signature, "owner")


if __name__ == "__main__":
    unittest.main()
