from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from lens.models import (
    Assistant,
    LensNode,
    Message,
    Run,
    Session,
    SharedQA,
)

User = get_user_model()

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}


def _results(data):
    """Return list rows from a paginated or plain list response."""

    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data


@override_settings(CACHES=TEST_CACHES)
class SharedQAApiTests(TestCase):
    """Integration tests for the public shareable Q&A feature."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="qa-owner",
            email="owner@example.com",
            password="pass12345",
        )
        self.other = User.objects.create_user(
            username="qa-other",
            email="other@example.com",
            password="pass12345",
        )
        self.group_peer = User.objects.create_user(
            username="qa-peer",
            email="peer@example.com",
            password="pass12345",
        )
        self.admin = User.objects.create_user(
            username="qa-admin",
            email="admin@example.com",
            password="pass12345",
            is_staff=True,
        )
        self.group = Group.objects.create(name="qa-group")
        self.owner.groups.add(self.group)
        self.group_peer.groups.add(self.group)
        self.lensnode = LensNode.objects.create(
            name="Node",
            status=LensNode.Status.ONLINE,
            enrollment_status=LensNode.EnrollmentStatus.APPROVED,
        )
        self.assistant = Assistant.objects.create(
            name="Data Helper",
            slug="data-helper",
            lensnode=self.lensnode,
            selected_task="qa",
            status=Assistant.Status.ACTIVE,
            visibility=Assistant.Visibility.PUBLIC,
        )
        self.run = self._make_done_run()

    def _make_done_run(self, assistant=None):
        """Create a completed run with a question and an answer message."""

        session = Session.objects.create(
            assistant=assistant or self.assistant,
            user=self.owner,
            title="t",
        )
        question = Message.objects.create(
            session=session,
            role=Message.Role.USER,
            content="What is X?",
            sequence=1,
        )
        run = Run.objects.create(
            session=session,
            status=Run.Status.DONE,
            input_message=question,
        )
        answer = Message.objects.create(
            session=session,
            role=Message.Role.ASSISTANT,
            content="X is a thing.",
            run=run,
            sequence=2,
        )
        run.output_message = answer
        run.save(update_fields=["output_message"])
        return run

    def _share(self, user=None, payload=None, run=None):
        """POST the run share action as the given (default owner) user."""

        self.client.force_authenticate(user or self.owner)
        return self.client.post(
            f"/api/lens/runs/{(run or self.run).uuid}/share/",
            payload or {},
            format="json",
        )

    def _private_share_token(self):
        """Create a share token from a private assistant run."""

        private_assistant = Assistant.objects.create(
            name="Private Helper",
            slug="private-helper",
            lensnode=self.lensnode,
            selected_task="qa",
            status=Assistant.Status.ACTIVE,
            visibility=Assistant.Visibility.PRIVATE,
        )
        run = self._make_done_run(private_assistant)
        return self._share(run=run).data["token"]

    def test_share_creates_snapshot(self):
        resp = self._share()
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(resp.data["is_listed"])
        self.assertEqual(resp.data["status"], "published")
        self.assertEqual(resp.data["run_uuid"], str(self.run.uuid))
        share = SharedQA.objects.get(token=resp.data["token"])
        self.assertEqual(share.question, "What is X?")
        self.assertEqual(share.answer, "X is a thing.")
        self.assertEqual(share.assistant_slug, "data-helper")
        self.assertEqual(share.assistant_name, "Data Helper")
        self.assertEqual(share.published_by, self.owner)
        self.assertIsNotNone(share.published_at)
        self.assertTrue(share.title)

    def test_share_is_idempotent_per_run(self):
        first = self._share()
        second = self._share()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["token"], second.data["token"])
        self.assertEqual(SharedQA.objects.filter(run=self.run).count(), 1)

    def test_share_rejects_unfinished_run(self):
        self.run.status = Run.Status.RUNNING
        self.run.save(update_fields=["status"])
        resp = self._share()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "RUN_NOT_SHAREABLE")

    def test_share_requires_run_ownership(self):
        resp = self._share(user=self.other)
        self.assertEqual(resp.status_code, 404)

    def test_unlisted_single_requires_login_then_allows_authenticated_user(self):
        token = self._share().data["token"]
        self.client.force_authenticate(user=None)
        anonymous = self.client.get(f"/api/lens/public/qa/{token}/")
        self.assertEqual(anonymous.status_code, 404)

        self.client.force_authenticate(self.other)
        other = self.client.get(f"/api/lens/public/qa/{token}/")
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.data["question"], "What is X?")

        self.client.force_authenticate(self.group_peer)
        peer = self.client.get(f"/api/lens/public/qa/{token}/")
        self.assertEqual(peer.status_code, 200)
        self.assertEqual(peer.data["question"], "What is X?")
        self.assertEqual(peer.data["view_count"], 2)

    def test_unlisted_single_allows_authenticated_session_user(self):
        token = self._share().data["token"]
        self.client.force_authenticate(user=None)
        self.assertTrue(
            self.client.login(username="qa-peer", password="pass12345")
        )

        resp = self.client.get(f"/api/lens/public/qa/{token}/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["question"], "What is X?")

    def test_unlisted_single_is_visible_to_owner(self):
        token = self._share().data["token"]
        self.client.force_authenticate(self.owner)
        resp = self.client.get(f"/api/lens/public/qa/{token}/")
        self.assertEqual(resp.status_code, 200)

    def test_listed_single_is_anonymous_and_counts_views(self):
        token = self._private_share_token()
        share = SharedQA.objects.get(token=token)
        share.is_listed = True
        share.save(update_fields=["is_listed"])

        self.client.force_authenticate(user=None)
        resp = self.client.get(f"/api/lens/public/qa/{token}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["question"], "What is X?")
        self.assertEqual(resp.data["answer"], "X is a thing.")
        self.assertEqual(resp.data["view_count"], 1)
        self.assertNotIn("published_by", resp.data)
        again = self.client.get(f"/api/lens/public/qa/{token}/")
        self.assertEqual(again.data["view_count"], 2)

    def test_hidden_single_returns_404(self):
        token = self._share().data["token"]
        share = SharedQA.objects.get(token=token)
        share.status = SharedQA.Status.HIDDEN
        share.save(update_fields=["status"])
        self.client.force_authenticate(user=None)
        resp = self.client.get(f"/api/lens/public/qa/{token}/")
        self.assertEqual(resp.status_code, 404)

    def test_public_list_shows_only_listed(self):
        token = self._share().data["token"]
        url = "/api/lens/public/assistants/data-helper/qa/"
        self.client.force_authenticate(user=None)
        before = self.client.get(url)
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.data["total"], 0)

        share = SharedQA.objects.get(token=token)
        self.client.force_authenticate(self.admin)
        patch = self.client.patch(
            f"/api/lens/admin/shares/{share.uuid}/",
            {"is_listed": True},
            format="json",
        )
        self.assertEqual(patch.status_code, 200)

        self.client.force_authenticate(user=None)
        after = self.client.get(url)
        self.assertEqual(after.data["total"], 1)
        self.assertEqual(after.data["results"][0]["token"], token)
        self.assertIn("answer_snippet", after.data["results"][0])

    def test_public_list_can_show_listed_private_assistant_share(self):
        token = self._private_share_token()
        share = SharedQA.objects.get(token=token)
        share.is_listed = True
        share.save(update_fields=["is_listed"])

        self.client.force_authenticate(user=None)
        resp = self.client.get("/api/lens/public/assistants/private-helper/qa/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total"], 1)
        self.assertEqual(resp.data["results"][0]["token"], token)

    def test_my_shares_list_and_revoke(self):
        token = self._share().data["token"]
        self.client.force_authenticate(self.owner)
        listing = self.client.get("/api/lens/shares/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(_results(listing.data)), 1)

        share = SharedQA.objects.get(token=token)
        deleted = self.client.delete(f"/api/lens/shares/{share.uuid}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(SharedQA.objects.filter(token=token).exists())

    def test_my_shares_isolated_per_user(self):
        self._share()
        self.client.force_authenticate(self.other)
        listing = self.client.get("/api/lens/shares/")
        self.assertEqual(len(_results(listing.data)), 0)

    def test_moderation_requires_admin(self):
        token = self._share().data["token"]
        share = SharedQA.objects.get(token=token)
        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"/api/lens/admin/shares/{share.uuid}/",
            {"is_listed": True},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_owner_can_rename_share(self):
        token = self._share().data["token"]
        share = SharedQA.objects.get(token=token)
        self.client.force_authenticate(self.owner)
        resp = self.client.patch(
            f"/api/lens/shares/{share.uuid}/",
            {"title": "Renamed Title"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["title"], "Renamed Title")
        share.refresh_from_db()
        self.assertEqual(share.title, "Renamed Title")

    def test_rename_requires_ownership(self):
        token = self._share().data["token"]
        share = SharedQA.objects.get(token=token)
        self.client.force_authenticate(self.other)
        resp = self.client.patch(
            f"/api/lens/shares/{share.uuid}/",
            {"title": "Hacked"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
