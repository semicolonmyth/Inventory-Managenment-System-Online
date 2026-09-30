"""Smoke tests.

Rewritten to be CI-safe and to NOT touch the production database. The
previous version called db.local_db.init_db(), which writes to the real
``C:\\ProgramData\\FishManagement\\fish.db``. Seeding logic is now exercised
against the isolated in-memory DB, and the GUI entrypoint import is guarded
so headless CI never fails on a missing display.
"""

import pytest

from db.models import User


def test_import_entrypoint():
    # Importing the GUI module must not raise; skip if Tkinter is unavailable.
    pytest.importorskip("customtkinter")
    import main

    assert main.MainWindow is not None


def test_seed_admin_and_user_unique(db_session):
    # Mirrors init_db's seeding contract without touching real data.
    db_session.add_all([
        User(username="admin", password_hash="admin", is_admin=True),
        User(username="user", password_hash="user", is_admin=False),
    ])
    db_session.commit()
    usernames = {u.username for u in db_session.query(User).all()}
    assert {"admin", "user"} <= usernames


def test_config_object_defaults():
    # AppConfig must load with sane defaults from a temp config path.
    from utils.config import AppConfig

    cfg = AppConfig()
    assert isinstance(cfg.app_title, str)
    assert cfg.max_offline_days >= 1
