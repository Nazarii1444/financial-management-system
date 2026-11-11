"""
Password reset codes (src/auth/password_reset.py) with a small fake DB session.

The fake answers `execute` from a queue of prepared results and records `add`ed rows,
which is enough to drive issue_code / check_code / consume.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.auth import password_reset
from src.auth.password_reset import ResetError, check_code, code_matches, consume, generate_code, hash_code, issue_code
from src.models import PasswordResetCode

UTC = timezone.utc
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
USER = SimpleNamespace(id_=7)


class _Result:
    def __init__(self, value=None):
        self.value = value

    def one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, results=()):
        self.results = list(results)
        self.added = []
        self.statements = []
        self.commits = 0

    async def execute(self, stmt):
        self.statements.append(stmt)
        return self.results.pop(0) if self.results else _Result()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _code_row(code="123456", attempts=0, user_id=7):
    return PasswordResetCode(id_=1, user_id=user_id, code_hash=hash_code(user_id, code), attempts=attempts,
                             created_at=NOW - timedelta(minutes=1), expires_at=NOW + timedelta(minutes=14))


def test_generate_code_is_six_digits():
    codes = {generate_code() for _ in range(200)}
    assert all(len(c) == 6 and c.isdigit() for c in codes)
    assert len(codes) > 150                      # random, not a counter


def test_hash_binds_code_to_user():
    h = hash_code(7, "123456")
    assert code_matches(7, "123456", h)
    assert not code_matches(8, "123456", h)      # same code, another account
    assert not code_matches(7, "123457", h)
    assert "123456" not in h


@pytest.mark.anyio
async def test_issue_code_stores_only_hash():
    session = FakeSession([_Result((0, None))])
    code = await issue_code(session, USER, now=NOW)
    (row,) = session.added
    assert row.user_id == 7 and code_matches(7, code, row.code_hash)
    assert row.expires_at == NOW + timedelta(minutes=password_reset.config.PASSWORD_RESET_CODE_TTL_MINUTES)
    assert len(session.statements) == 2          # rate-limit query + expire older codes
    assert session.commits == 1


@pytest.mark.anyio
@pytest.mark.parametrize("recent", [
    (1, NOW - timedelta(seconds=30)),            # asked again within a minute
    (password_reset.MAX_CODES_PER_HOUR, NOW - timedelta(minutes=10)),
])
async def test_issue_code_is_rate_limited(recent):
    session = FakeSession([_Result(recent)])
    assert await issue_code(session, USER, now=NOW) is None
    assert session.added == []


@pytest.mark.anyio
async def test_issue_code_after_resend_interval():
    session = FakeSession([_Result((1, NOW - timedelta(minutes=2)))])
    assert await issue_code(session, USER, now=NOW) is not None


@pytest.mark.anyio
async def test_check_code_accepts_right_code():
    row = _code_row()
    session = FakeSession([_Result(row)])
    assert await check_code(session, USER, "123456", now=NOW) is row
    assert row.attempts == 0


@pytest.mark.anyio
@pytest.mark.parametrize("user, code", [
    (None, "123456"),            # unknown e-mail: same answer as a wrong code
    (USER, "12345"),
    (USER, "abcdef"),
])
async def test_check_code_rejects_malformed_or_unknown(user, code):
    with pytest.raises(ResetError, match="Invalid or expired code"):
        await check_code(FakeSession(), user, code, now=NOW)


@pytest.mark.anyio
async def test_check_code_without_active_code():
    with pytest.raises(ResetError, match="Invalid or expired code"):
        await check_code(FakeSession([_Result(None)]), USER, "123456", now=NOW)


@pytest.mark.anyio
async def test_wrong_code_counts_attempts_and_locks_after_five():
    row = _code_row()
    for attempt in range(1, password_reset.MAX_ATTEMPTS + 1):
        with pytest.raises(ResetError) as exc:
            await check_code(FakeSession([_Result(row)]), USER, "000000", now=NOW)
        assert row.attempts == attempt
    assert "Too many attempts" in str(exc.value)
    assert row.expires_at == NOW                 # the code is dead now
    # even the right code no longer works on a locked row
    with pytest.raises(ResetError, match="Too many attempts"):
        await check_code(FakeSession([_Result(row)]), USER, "123456", now=NOW)


@pytest.mark.anyio
async def test_consume_marks_used_and_expires_siblings():
    row = _code_row()
    session = FakeSession()
    await consume(session, row, now=NOW)
    assert row.used_at == NOW
    assert len(session.statements) == 1          # UPDATE of the other live codes
