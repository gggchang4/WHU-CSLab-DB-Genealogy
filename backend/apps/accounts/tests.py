from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class RegistrationViewTests(TestCase):
    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            data={
                "username": "tester",
                "display_name": "Test User",
                "email": "tester@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("genealogy:dashboard"))
        user = User.objects.get(username="tester")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.user_id)
