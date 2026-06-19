import unittest
from datetime import datetime, timedelta

from fastapi import HTTPException

from app.api import auth
from app.config import Settings


class SecurityControlsTest(unittest.TestCase):
    def setUp(self):
        auth._attempts.clear()

    def test_login_rate_limit_blocks_repeated_attempts(self):
        now = datetime(2026, 6, 19, 12, 0, 0)
        for i in range(auth._RATE_LIMITS["giris"]):
            auth._rate_limit("giris", "User@Example.com", now + timedelta(seconds=i))

        with self.assertRaises(HTTPException) as ctx:
            auth._rate_limit("giris", "user@example.com", now + timedelta(seconds=60))

        self.assertEqual(ctx.exception.status_code, 429)

    def test_login_rate_limit_window_expires(self):
        now = datetime(2026, 6, 19, 12, 0, 0)
        for i in range(auth._RATE_LIMITS["giris"]):
            auth._rate_limit("giris", "user@example.com", now + timedelta(seconds=i))

        auth._rate_limit(
            "giris",
            "user@example.com",
            now + timedelta(seconds=auth._RATE_WINDOW_SEC + 1),
        )

    def test_production_rejects_default_jwt_secret(self):
        settings = Settings(
            app_env="production",
            jwt_secret="dev-secret-change-me",
            cors_origins="https://api.harbiganyan.com",
        )

        with self.assertRaises(RuntimeError):
            settings.validate_for_runtime()

    def test_production_rejects_wildcard_cors(self):
        settings = Settings(
            app_env="production",
            jwt_secret="x" * 32,
            cors_origins="*",
        )

        with self.assertRaises(RuntimeError):
            settings.validate_for_runtime()


if __name__ == "__main__":
    unittest.main()
