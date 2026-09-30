import unittest

import main
from db.local_db import get_by_id, get_session, init_db
from db.models import User
from utils.config import load_config


class AppSmokeTests(unittest.TestCase):
    def test_import_entrypoint(self):
        self.assertIsNotNone(main.MainWindow)

    def test_config_loads(self):
        cfg = load_config()
        self.assertIsInstance(cfg.app_title, str)
        self.assertGreaterEqual(cfg.ui_scaling, 0.75)

    def test_database_bootstrap_creates_seed_users(self):
        init_db()
        session = get_session()
        try:
            users = session.query(User).all()
            usernames = {u.username for u in users}
            self.assertIn("admin", usernames)
            self.assertIn("user", usernames)
        finally:
            session.close()

    def test_lookup_helper_returns_seed_user(self):
        init_db()
        session = get_session()
        try:
            user = get_by_id(session, User, 1)
            self.assertIsNotNone(user)
            self.assertEqual(user.username, "admin")
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
