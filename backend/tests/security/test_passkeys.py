"""
Passkeys: registration + passwordless sign-in with a software authenticator.

The session is a small in-memory fake that understands the simple
select / delete statements the service issues (col == value, col < value).
"""
import operator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, BooleanClauseList

from src.models import User, WebAuthnChallenge, WebAuthnCredential
from src.security import passkeys
from tests.security.soft_authenticator import SoftAuthenticator

RP = passkeys.RelyingParty("localhost", "FinanceHub", ("http://localhost:5173",))
ORIGIN = "http://localhost:5173"
_OPS = {operators.eq: operator.eq, operators.lt: operator.lt}


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self.rows)

    def scalar_one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def scalar_one(self):
        assert len(self.rows) == 1
        return self.rows[0]


class FakeSession:
    def __init__(self, *objects):
        self.rows = {User: [], WebAuthnChallenge: [], WebAuthnCredential: []}
        self._next_id = 1
        for obj in objects:
            self.add(obj)

    def add(self, obj):
        if getattr(obj, "id_", None) is None:
            obj.id_ = self._next_id
            self._next_id += 1
        if isinstance(obj, WebAuthnCredential):
            obj.created_at = obj.created_at or datetime.now(timezone.utc)
            obj.sign_count = obj.sign_count or 0
        if obj not in self.rows[type(obj)]:
            self.rows[type(obj)].append(obj)

    @staticmethod
    def _matches(obj, clause) -> bool:
        if clause is None:
            return True
        if isinstance(clause, BooleanClauseList):
            return all(FakeSession._matches(obj, c) for c in clause.clauses)
        assert isinstance(clause, BinaryExpression) and isinstance(clause.right, BindParameter), clause
        return _OPS[clause.operator](getattr(obj, clause.left.key), clause.right.value)

    async def execute(self, stmt):
        if stmt.is_delete:
            model = next(m for m in self.rows if m.__tablename__ == stmt.table.name)
            self.rows[model] = [o for o in self.rows[model] if not self._matches(o, stmt.whereclause)]
            return _Result([])
        column = stmt.column_descriptions[0]
        model, expr = column["entity"], column["expr"]
        hits = [o for o in self.rows[model] if self._matches(o, stmt.whereclause)]
        if expr is not model:   # select(Model.attr)
            hits = [getattr(o, expr.key) for o in hits]
        return _Result(hits)

    async def delete(self, obj):
        self.rows[type(obj)].remove(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


@pytest.fixture
def user():
    return User(id_=7, username="olena", email="olena@example.com", hashed_password="x")


async def _register(db, user, auth, name="Laptop"):
    options = await passkeys.registration_options(db, user, RP)
    credential = auth.create(options["public_key"])
    return await passkeys.register(db, user, options["challenge_id"], credential, name, RP)


async def _login(db, auth, **get_kwargs):
    options = await passkeys.login_options(db, RP)
    return options, auth.get(options["public_key"], **get_kwargs)


@pytest.mark.anyio
async def test_register_then_sign_in(user):
    db, auth = FakeSession(user), SoftAuthenticator("localhost", ORIGIN, backed_up=True)
    options = await passkeys.registration_options(db, user, RP)
    pk = options["public_key"]
    assert pk["rp"] == {"id": "localhost", "name": "FinanceHub"}
    assert pk["authenticatorSelection"]["residentKey"] == "required"
    assert pk["authenticatorSelection"]["userVerification"] == "required"
    assert user.webauthn_user_handle and len(user.webauthn_user_handle) == 32   # random, not the numeric id

    stored = await passkeys.register(db, user, options["challenge_id"], auth.create(pk), "  Work laptop ", RP)
    assert stored.credential_id == auth.credential_id and stored.name == "Work laptop"
    assert stored.backed_up is True and stored.transports == ["internal"]
    assert db.rows[WebAuthnChallenge] == []   # used up

    options, assertion = await _login(db, auth)
    assert "allowCredentials" not in options["public_key"] or options["public_key"]["allowCredentials"] == []
    signed_in, passkey = await passkeys.authenticate(db, options["challenge_id"], assertion, RP)
    assert signed_in is user and passkey is stored
    assert passkey.sign_count == 1 and passkey.last_used_at is not None


@pytest.mark.anyio
async def test_challenge_is_single_use(user):
    db, auth = FakeSession(user), SoftAuthenticator("localhost", ORIGIN)
    await _register(db, user, auth)
    options, assertion = await _login(db, auth)
    await passkeys.authenticate(db, options["challenge_id"], assertion, RP)
    with pytest.raises(passkeys.PasskeyError, match="challenge_expired"):   # replay
        await passkeys.authenticate(db, options["challenge_id"], assertion, RP)


@pytest.mark.anyio
async def test_expired_challenge(user):
    db, auth = FakeSession(user), SoftAuthenticator("localhost", ORIGIN)
    await _register(db, user, auth)
    options, assertion = await _login(db, auth)
    db.rows[WebAuthnChallenge][0].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(passkeys.PasskeyError, match="challenge_expired"):
        await passkeys.authenticate(db, options["challenge_id"], assertion, RP)


@pytest.mark.anyio
async def test_wrong_origin_is_rejected(user):
    db, auth = FakeSession(user), SoftAuthenticator("localhost", ORIGIN)
    await _register(db, user, auth)
    options, assertion = await _login(db, auth, origin="https://evil.example")   # phishing site relaying the challenge
    with pytest.raises(passkeys.PasskeyError, match="verification_failed"):
        await passkeys.authenticate(db, options["challenge_id"], assertion, RP)


@pytest.mark.anyio
async def test_user_verification_is_required(user):
    db, auth = FakeSession(user), SoftAuthenticator("localhost", ORIGIN)
    options = await passkeys.registration_options(db, user, RP)
    with pytest.raises(passkeys.PasskeyError, match="verification_failed"):
        await passkeys.register(db, user, options["challenge_id"], auth.create(options["public_key"], user_verified=False), None, RP)

    await _register(db, user, auth)
    options, assertion = await _login(db, auth, user_verified=False)
    with pytest.raises(passkeys.PasskeyError, match="verification_failed"):
        await passkeys.authenticate(db, options["challenge_id"], assertion, RP)


@pytest.mark.anyio
async def test_forged_signature_and_unknown_passkey(user):
    db, auth = FakeSession(user), SoftAuthenticator("localhost", ORIGIN)
    await _register(db, user, auth)

    impostor = SoftAuthenticator("localhost", ORIGIN)   # different key, same credential id
    impostor.credential_id, impostor.user_handle = auth.credential_id, auth.user_handle
    options, assertion = await _login(db, impostor)
    with pytest.raises(passkeys.PasskeyError, match="verification_failed"):
        await passkeys.authenticate(db, options["challenge_id"], assertion, RP)

    stranger = SoftAuthenticator("localhost", ORIGIN)
    options, assertion = await _login(db, stranger)
    with pytest.raises(passkeys.PasskeyError, match="unknown_passkey"):
        await passkeys.authenticate(db, options["challenge_id"], assertion, RP)


@pytest.mark.anyio
async def test_cloned_authenticator_counter_going_back(user):
    db, auth = FakeSession(user), SoftAuthenticator("localhost", ORIGIN)
    await _register(db, user, auth)
    options, assertion = await _login(db, auth, counter_step=5)
    await passkeys.authenticate(db, options["challenge_id"], assertion, RP)
    auth.counter = 1   # a copy of the key with an older counter
    options, assertion = await _login(db, auth, counter_step=0)
    with pytest.raises(passkeys.PasskeyError, match="verification_failed"):
        await passkeys.authenticate(db, options["challenge_id"], assertion, RP)


@pytest.mark.anyio
async def test_user_handle_must_belong_to_the_account(user):
    db, auth = FakeSession(user), SoftAuthenticator("localhost", ORIGIN)
    await _register(db, user, auth)
    auth.user_handle = b"\x01" * 32
    options, assertion = await _login(db, auth)
    with pytest.raises(passkeys.PasskeyError, match="verification_failed"):
        await passkeys.authenticate(db, options["challenge_id"], assertion, RP)


@pytest.mark.anyio
async def test_same_authenticator_is_excluded_and_rejected_twice(user):
    db, auth = FakeSession(user), SoftAuthenticator("localhost", ORIGIN)
    await _register(db, user, auth)
    options = await passkeys.registration_options(db, user, RP)
    assert [c["id"] for c in options["public_key"]["excludeCredentials"]] == [auth.create(options["public_key"])["id"]]
    with pytest.raises(passkeys.PasskeyError, match="already_registered"):
        await passkeys.register(db, user, options["challenge_id"], auth.create(options["public_key"]), None, RP)


@pytest.mark.anyio
async def test_registration_challenge_belongs_to_the_user(user):
    other = User(id_=8, username="taras", email="taras@example.com", hashed_password="x")
    db, auth = FakeSession(user, other), SoftAuthenticator("localhost", ORIGIN)
    options = await passkeys.registration_options(db, user, RP)
    with pytest.raises(passkeys.PasskeyError, match="challenge_expired"):
        await passkeys.register(db, other, options["challenge_id"], auth.create(options["public_key"]), None, RP)


@pytest.mark.anyio
async def test_passkey_limit(user, monkeypatch):
    monkeypatch.setattr(passkeys, "MAX_PASSKEYS", 1)
    db = FakeSession(user)
    await _register(db, user, SoftAuthenticator("localhost", ORIGIN))
    with pytest.raises(passkeys.PasskeyError, match="too_many_passkeys"):
        await passkeys.registration_options(db, user, RP)
