from __future__ import annotations

import pytest

from shared.control_plane import aws_guard
from shared.control_plane import workspace_context as wc

A, B = "111111111111", "222222222222"


@pytest.fixture(autouse=True)
def _no_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(aws_guard.EXPECTED_ENV, raising=False)


def test_unpinned_session_is_reported_not_blocked():
    assert aws_guard.check({}, resolver=lambda: (A, "default"))["status"] == "unpinned"


def test_matching_account_is_ok():
    assert aws_guard.check({"aws_account": A}, resolver=lambda: (A, "default"))["status"] == "ok"


def test_mismatch_is_detected_and_context_says_stop():
    result = aws_guard.check({"aws_account": A}, resolver=lambda: (B, "default"))
    assert result["status"] == "mismatch"
    assert "STOP" in "\n".join(aws_guard.context_lines(result))


def test_environment_pin_overrides_session(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(aws_guard.EXPECTED_ENV, B)
    assert aws_guard.check({"aws_account": A}, resolver=lambda: (B, "p"))["status"] == "ok"


def test_unresolvable_credentials_are_unavailable():
    def boom():
        raise RuntimeError("no credentials")
    assert aws_guard.check({"aws_account": A}, resolver=boom)["status"] == "unavailable"


def test_invalid_pin_rejected():
    with pytest.raises(ValueError):
        aws_guard.validate_account("12345")


def test_login_pins_account_and_aws_check_exit_codes(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(wc.SESSION_ENV, str(tmp_path / "session.json"))
    session = wc.login("hcherian@example.com", "project/orders", tmp_path, aws_account=A)
    assert session["aws_account"] == A
    monkeypatch.setattr(aws_guard, "resolve_current_account", lambda: (A, "default"))
    assert wc.main(["aws-check"]) == 0
    monkeypatch.setattr(aws_guard, "resolve_current_account", lambda: (B, "default"))
    assert wc.main(["aws-check"]) == 2
