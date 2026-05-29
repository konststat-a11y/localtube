import unittest
from unittest.mock import patch

from app.auth import logout_page, register_page


class FakeRequest:
    def __init__(self, session: dict) -> None:
        self.session = session


class AuthPageTest(unittest.TestCase):
    def test_register_page_opens_when_session_already_has_user(self) -> None:
        request = FakeRequest({"user_id": 1})

        with patch("app.auth.render_auth_form", return_value="register-form") as render:
            response = register_page(request)

        self.assertEqual(response, "register-form")
        render.assert_called_once_with(request, "register.html")

    def test_get_logout_clears_session_and_redirects_home(self) -> None:
        request = FakeRequest({"user_id": 1})

        response = logout_page(request)

        self.assertEqual(request.session, {})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")


if __name__ == "__main__":
    unittest.main()
