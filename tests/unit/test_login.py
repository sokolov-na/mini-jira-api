from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import dns.resolver
import pytest
from pwdlib import PasswordHash
from pydantic import ValidationError

from mini_jira.exceptions import InvalidCredentials
from mini_jira.users.models import User
from mini_jira.users.repository.protocol import UserRepository
from mini_jira.users.schemas import UserCredentials, UserPasswordReset
from mini_jira.users.use_cases import LoginUserUseCase

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "login,email",
    [
        ("  User@EXAMPLE.ORG  ", "User@example.org"),
        ("Alice <User@EXAMPLE.ORG>", "User@example.org"),
        ("иван@ПРИМЕР.РФ", "иван@пример.рф"),
        ("user@xn--e1afmkfd.xn--p1ai", "user@пример.рф"),
        ("e\u0301@EXAMPLE.ORG", "é@example.org"),
    ],
)
async def test_login_normalizes_email_without_dns(
    login: str, email: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolver = Mock(spec=dns.resolver.Resolver)
    resolver.resolve.side_effect = AssertionError("Unexpected DNS request")
    monkeypatch.setattr(dns.resolver, "get_default_resolver", lambda: resolver)
    user = User(
        id=uuid4(),
        username="test-user",
        email=email,
        password_hash=PasswordHash.recommended().hash("password"),
    )
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = user
    result = await LoginUserUseCase(cast(UserRepository, repository)).execute(
        UserCredentials(login=login, password="password")
    )
    assert result == user.id
    repository.get_by_email.assert_awaited_once_with(email, for_update=True)
    repository.get_by_username.assert_not_awaited()
    resolver.resolve.assert_not_called()


@pytest.mark.parametrize("login", ["test-user", "Test-User", "TEST-USER"])
async def test_username_login_is_normalized(login: str) -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_username.return_value = None
    with pytest.raises(InvalidCredentials):
        await LoginUserUseCase(cast(UserRepository, repository)).execute(
            UserCredentials(login=login, password="password")
        )
    repository.get_by_username.assert_awaited_once_with(
        "test-user", for_update=True
    )
    repository.get_by_email.assert_not_awaited()


@pytest.mark.parametrize("model", [UserCredentials, UserPasswordReset])
@pytest.mark.parametrize(
    "login",
    [
        "",
        "ab",
        "u" * 33,
        "-leading",
        "trailing-",
        "bad_name",
        " test-user ",
        "broken@",
        "user..name@host.org",
        None,
        123,
    ],
)
def test_login_schemas_reject_invalid_input(
    model: type[UserCredentials] | type[UserPasswordReset], login: object
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({"login": login, "password": "password"})


@pytest.mark.parametrize("model", [UserCredentials, UserPasswordReset])
@pytest.mark.parametrize(
    "login,normalized",
    [
        ("Mixed-Case", "mixed-case"),
        ("U" * 32, "u" * 32),
        ("  User@EXAMPLE.ORG  ", "User@example.org"),
        ("Alice <User@EXAMPLE.ORG>", "User@example.org"),
    ],
)
def test_login_schemas_share_registration_normalization(
    model: type[UserCredentials] | type[UserPasswordReset],
    login: str,
    normalized: str,
) -> None:
    data = model.model_validate({"login": login, "password": "password"})
    assert data.login == normalized
    assert data.model_dump()["login"] == normalized


async def test_unknown_valid_email_does_not_fall_back_to_username() -> None:
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = None
    with pytest.raises(InvalidCredentials):
        await LoginUserUseCase(cast(UserRepository, repository)).execute(
            UserCredentials(login="missing@example.org", password="password")
        )
    repository.get_by_email.assert_awaited_once_with(
        "missing@example.org", for_update=True
    )
    repository.get_by_username.assert_not_awaited()
