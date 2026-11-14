import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from mini_jira.database.connection import get_session
from mini_jira.main import api, app

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "token,results",
    [
        ("unknown-token", [None]),
        ("expired-or-consumed-token", [uuid4(), uuid4(), None]),
        ("deleted-user-token", [uuid4(), None]),
        ("\ud800", []),
        ("\udfff", []),
    ],
)
def test_reset_confirmation_rejects_invalid_tokens(
    token: str, results: list[object]
) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.side_effect = results

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    api.dependency_overrides[get_session] = override_session
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/auth/password/reset/confirm",
            content=json.dumps(
                {
                    "password_reset_token": token,
                    "new_password": "new-test-password",
                }
            ),
            headers={"Content-Type": "application/json"},
        )
    finally:
        del api.dependency_overrides[get_session]

    assert response.status_code == 401
    assert response.json() == {"detail": "Token is invalid"}
    session.commit.assert_not_awaited()
    assert session.scalar.await_count == len(results)
