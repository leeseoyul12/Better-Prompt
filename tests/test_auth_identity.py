import unittest
from unittest.mock import Mock, patch

from backend.auth import AuthenticationError, GoogleIdentityService


class GoogleIdentityTests(unittest.TestCase):
    def test_only_verified_google_email_can_be_used_for_invite_check(self):
        response = Mock()
        response.json.return_value = {
            "sub": "fixture-sub", "email": "invited@example.com",
            "email_verified": True, "name": "Fixture",
        }
        with patch("backend.auth.httpx.get", return_value=response):
            profile = GoogleIdentityService().fetch_profile("fake-google-token")
        self.assertEqual(profile.email, "invited@example.com")

    def test_unverified_missing_or_malformed_profile_is_rejected(self):
        for payload in [{"sub": "fixture-sub", "email": "invited@example.com"},
                        {"email_verified": False}, {"email_verified": "true"}, []]:
            response = Mock()
            response.json.return_value = payload
            with self.subTest(payload=payload), patch("backend.auth.httpx.get", return_value=response):
                with self.assertRaises(AuthenticationError):
                    GoogleIdentityService().fetch_profile("fake-google-token")
