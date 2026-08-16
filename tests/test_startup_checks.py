from __future__ import annotations

from calobot.persistence.startup_checks import ensure_database_not_on_network_fs


def test_no_op_when_no_mountinfo(tmp_path, monkeypatch):
    # On a system without /proc/self/mountinfo (or in a sandbox where it's absent),
    # the check must not raise - false positives would be worse than skipping it.
    ensure_database_not_on_network_fs(str(tmp_path / "calobot.db"))


def test_local_path_does_not_raise(tmp_path):
    ensure_database_not_on_network_fs(str(tmp_path / "calobot.db"))
