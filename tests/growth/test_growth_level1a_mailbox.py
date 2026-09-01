from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_common import utc_now  # noqa: E402
from growth_level1a import _record_audit, initialize, load_action, render_message, seed_pilot  # noqa: E402
from growth_level1a_mailbox import bootstrap, poll  # noqa: E402


class FakeClient:
    def __init__(self, pages, contents=None, headers=None):
        self.pages = list(pages)
        self.contents = contents or {}
        self.content_reads = []
        self.header_reads = []
        self.headers = headers or {"Authentication-Results": "spf=pass; dkim=pass; dmarc=pass"}

    def list_messages(self, *, limit=50):
        return self.pages.pop(0)

    def get_message_content(self, folder_id, message_id):
        self.content_reads.append((folder_id, message_id))
        return self.contents[message_id]

    def get_message_headers(self, folder_id, message_id):
        self.header_reads.append((folder_id, message_id))
        return self.headers


class MailboxPollingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "growth.db"
        self.connection = initialize(self.db)
        now = utc_now()
        for values in (
            (
                "freelancethings.co", "https://www.freelancethings.co/official-information",
                "https://www.freelancethings.co/official-information", "freelancer",
            ),
            ("ledgerco.ca", "https://ledgerco.ca/resources/", "https://ledgerco.ca/contact/", "accounting"),
        ):
            domain, page, contact, channel = values
            cursor = self.connection.execute(
                """INSERT INTO prospects (
                     domain,page_url,prospect_type,opportunity_score,risk,why_fit,audience,
                     contact_method,requires_account,requires_payment,link_type,source_url,
                     status,discovered_at,updated_at)
                   VALUES (?,?,'resource',85,'low','Relevant resource','Small businesses',?,0,0,
                           'editorial',?,'qualified',?,?)""",
                (domain, page, contact, page, now, now),
            )
            self.connection.execute(
                """INSERT INTO prospect_qualification (
                     prospect_id,channel,page_evidence,outbound_resources,target_url,
                     proposed_action,confidence,second_pass_pass,review_reason,reviewed_at)
                   VALUES (?,?,'Evidence','[]','https://invoiceworkshop.com/invoice-template/',
                           'Suggest resource','high',1,'Useful without SEO',?)""",
                (cursor.lastrowid, channel, now),
            )
        self.connection.commit()
        ids = seed_pilot(self.connection)
        self.action = load_action(self.connection, ids[1])
        rendered = render_message(self.connection, self.action)
        _record_audit(
            self.connection, self.action, rendered, mode="live", result="passed",
            provider_id="sent-1", provider_thread_id="thread-1",
            side_effects="email_sent",
        )

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_matched_reply_is_read_classified_and_suppressed(self):
        message = {
            "messageId": "reply-1", "threadId": "thread-1", "folderId": "inbox",
            "receivedTime": "2000", "fromAddress": "info@ledgerco.ca",
            "subject": "Re: Possible companion resource for your invoice-template library",
            "hasAttachment": "0",
        }
        client = FakeClient([[{"messageId": "old", "receivedTime": "1000"}], [message]], {"reply-1": "No thanks, please do not contact us."})
        bootstrap(self.connection, client)
        result = poll(self.connection, client)
        self.assertEqual((result["matched_replies"], result["suppressions_updated"]), (1, 1))
        action = load_action(self.connection, self.action["id"])
        self.assertEqual(action["suppression_state"], "declined")
        inbound = self.connection.execute("SELECT * FROM level1a_inbound_audit").fetchone()
        self.assertEqual(
            (inbound["match_method"], inbound["authentication_state"], inbound["classification"], inbound["external_content_executed"]),
            ("thread_id", "pass", "decline", 0),
        )

    def test_unmatched_mail_content_is_not_read_or_exposed(self):
        message = {
            "messageId": "other-1", "threadId": "other-thread", "folderId": "inbox",
            "receivedTime": "2000", "fromAddress": "private@example.net",
            "subject": "Unrelated private message", "hasAttachment": "1",
        }
        client = FakeClient([[], [message]], {"other-1": "private body"})
        bootstrap(self.connection, client)
        result = poll(self.connection, client)
        self.assertEqual((result["matched_replies"], client.content_reads), (0, []))
        inbound = self.connection.execute("SELECT * FROM level1a_inbound_audit").fetchone()
        self.assertIsNone(inbound["matched_action_id"])
        self.assertIsNone(inbound["content_hash"])
        self.assertEqual(inbound["attachment_ignored"], 1)

    def test_bounce_matches_approved_recipient_and_suppresses(self):
        message = {
            "messageId": "bounce-1", "threadId": "", "folderId": "inbox",
            "receivedTime": "2000", "fromAddress": "mailer-daemon@example.net",
            "subject": "Mail delivery failed", "hasAttachment": "0",
        }
        client = FakeClient([[], [message]], {"bounce-1": "Delivery failed for info@ledgerco.ca"})
        bootstrap(self.connection, client)
        result = poll(self.connection, client)
        self.assertEqual((result["bounces_detected"], result["suppressions_updated"]), (1, 1))
        action = load_action(self.connection, self.action["id"])
        self.assertEqual(action["suppression_state"], "bounced")

    def test_unauthenticated_matching_message_cannot_suppress(self):
        message = {
            "messageId": "spoof-1", "threadId": "thread-1", "folderId": "inbox",
            "receivedTime": "2000", "fromAddress": "info@ledgerco.ca",
            "subject": "Re: Possible companion resource for your invoice-template library",
            "hasAttachment": "0",
        }
        client = FakeClient(
            [[], [message]], {"spoof-1": "Unsubscribe and do not contact us."},
            {"Authentication-Results": "spf=fail; dkim=fail; dmarc=fail"},
        )
        bootstrap(self.connection, client)
        result = poll(self.connection, client)
        self.assertEqual(result["suppressions_updated"], 0)
        action = load_action(self.connection, self.action["id"])
        self.assertEqual(action["suppression_state"], "active")
        inbound = self.connection.execute("SELECT * FROM level1a_inbound_audit").fetchone()
        self.assertEqual((inbound["authentication_state"], inbound["classification"], inbound["requires_escalation"]), ("fail", "ambiguous", 1))


if __name__ == "__main__":
    unittest.main()
