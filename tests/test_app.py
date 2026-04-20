import importlib
import sys
from unittest.mock import MagicMock
import prometheus_client
import pytest
import requests


@pytest.fixture
def app_module(monkeypatch):
    """
    Carrega o módulo app.py com as dependências de ambiente e banco mockadas
    antes do import, evitando sys.exit() e conexão real com PostgreSQL.
    """
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://user:pass@localhost:5432/testdb")
    monkeypatch.setenv("AUTH_SERVICE_URL", "http://auth-service")

    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_pool.getconn.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    prometheus_client.REGISTRY = prometheus_client.CollectorRegistry()

    if "app" in sys.modules:
        del sys.modules["app"]

    import psycopg2.pool
    monkeypatch.setattr(
        psycopg2.pool, "SimpleConnectionPool",
        lambda *args, **kwargs: mock_pool)

    module = importlib.import_module("app")

    # expõe mocks úteis para os testes
    module._mock_pool = mock_pool
    module._mock_conn = mock_conn
    module._mock_cursor = mock_cursor

    return module


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()


def auth_ok(monkeypatch, app_module):
    response = MagicMock()
    response.status_code = 200
    monkeypatch.setattr(
        app_module.requests, "get", lambda *args, **kwargs: response)


# -------------------------
# Health
# -------------------------

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


# -------------------------
# Auth middleware
# -------------------------

def test_require_auth_missing_header(client):
    response = client.get("/flags")
    assert response.status_code == 401
    assert response.get_json() == {"error": "Authorization header obrigatório"}


def test_require_auth_invalid_key(client, app_module, monkeypatch):
    response_mock = MagicMock()
    response_mock.status_code = 401
    monkeypatch.setattr(
        app_module.requests, "get", lambda *args, **kwargs: response_mock)

    response = client.get(
        "/flags", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    assert response.get_json() == {"error": "Chave de API inválida"}


def test_require_auth_timeout(client, app_module, monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(app_module.requests, "get", raise_timeout)

    response = client.get("/flags", headers={"Authorization": "Bearer token"})
    assert response.status_code == 504
    assert response.get_json() == {
        "error": "Serviço de autenticação indisponível (timeout)"}


def test_require_auth_request_exception(client, app_module, monkeypatch):
    def raise_request_exception(*args, **kwargs):
        raise requests.exceptions.RequestException("falha")

    monkeypatch.setattr(app_module.requests, "get", raise_request_exception)

    response = client.get("/flags", headers={"Authorization": "Bearer token"})
    assert response.status_code == 503
    assert response.get_json() == {
        "error": "Serviço de autenticação indisponível"}


# -------------------------
# POST /flags
# -------------------------

def test_create_flag_success(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)

    expected_flag = {
        "name": "nova-flag",
        "description": "teste",
        "is_enabled": True
    }

    app_module._mock_cursor.fetchone.return_value = expected_flag

    response = client.post(
        "/flags",
        json={"name": "nova-flag", "description": "teste", "is_enabled": True},
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 201
    assert response.get_json() == expected_flag
    app_module._mock_conn.commit.assert_called_once()
    app_module._mock_pool.putconn.assert_called()


def test_create_flag_missing_name(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)

    response = client.post(
        "/flags",
        json={"description": "sem nome"},
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "'name' é obrigatório"}


def test_create_flag_duplicate(client, app_module, monkeypatch):
    import psycopg2

    auth_ok(monkeypatch, app_module)
    app_module._mock_cursor.execute.side_effect = psycopg2.IntegrityError()

    response = client.post(
        "/flags",
        json={"name": "duplicada"},
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 409
    assert response.get_json() == {"error": "Flag 'duplicada' já existe"}
    app_module._mock_conn.rollback.assert_called_once()


def test_create_flag_internal_error(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)
    app_module._mock_cursor.execute.side_effect = Exception("erro banco")

    response = client.post(
        "/flags",
        json={"name": "falha"},
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 500
    body = response.get_json()
    assert body["error"] == "Erro interno do servidor"
    assert "erro banco" in body["details"]


# -------------------------
# GET /flags
# -------------------------

def test_get_flags_success(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)

    flags = [
        {"name": "a", "description": "", "is_enabled": True},
        {"name": "b", "description": "", "is_enabled": False},
    ]
    app_module._mock_cursor.fetchall.return_value = flags

    response = client.get("/flags", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.get_json() == flags


def test_get_flags_internal_error(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)
    app_module._mock_cursor.execute.side_effect = Exception("select error")

    response = client.get("/flags", headers={"Authorization": "Bearer token"})

    assert response.status_code == 500
    body = response.get_json()
    assert body["error"] == "Erro interno do servidor"
    assert "select error" in body["details"]


# -------------------------
# GET /flags/<name>
# -------------------------

def test_get_flag_success(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)

    flag = {"name": "feature-x", "description": "desc", "is_enabled": True}
    app_module._mock_cursor.fetchone.return_value = flag

    response = client.get(
        "/flags/feature-x", headers={"Authorization": "Bearer token"})

    assert response.status_code == 200
    assert response.get_json() == flag


def test_get_flag_not_found(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)
    app_module._mock_cursor.fetchone.return_value = None

    response = client.get(
        "/flags/inexistente", headers={"Authorization": "Bearer token"})

    assert response.status_code == 404
    assert response.get_json() == {"error": "Flag não encontrada"}


def test_get_flag_internal_error(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)
    app_module._mock_cursor.execute.side_effect = Exception("erro get")

    response = client.get(
        "/flags/feature-x", headers={"Authorization": "Bearer token"})

    assert response.status_code == 500
    body = response.get_json()
    assert body["error"] == "Erro interno do servidor"
    assert "erro get" in body["details"]


# -------------------------
# PUT /flags/<name>
# -------------------------


def test_update_flag_no_fields(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)

    response = client.put(
        "/flags/feature-x",
        json={"foo": "bar"},
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 400
    expected_err = (
        "Pelo menos um campo "
        "('description', 'is_enabled') é obrigatório"
    )
    assert response.get_json() == {"error": expected_err}


def test_update_flag_success(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)

    updated = {"name": "feature-x", "description": "nova", "is_enabled": True}
    app_module._mock_cursor.rowcount = 1
    app_module._mock_cursor.fetchone.return_value = updated

    response = client.put(
        "/flags/feature-x",
        json={"description": "nova", "is_enabled": True},
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert response.get_json() == updated
    app_module._mock_conn.commit.assert_called()


def test_update_flag_not_found(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)

    app_module._mock_cursor.rowcount = 0

    response = client.put(
        "/flags/inexistente",
        json={"description": "nova"},
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Flag não encontrada"}


def test_update_flag_internal_error(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)
    app_module._mock_cursor.execute.side_effect = Exception("erro update")

    response = client.put(
        "/flags/feature-x",
        json={"description": "nova"},
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 500
    body = response.get_json()
    assert body["error"] == "Erro interno do servidor"
    assert "erro update" in body["details"]


# -------------------------
# DELETE /flags/<name>
# -------------------------

def test_delete_flag_success(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)

    app_module._mock_cursor.rowcount = 1

    response = client.delete(
        "/flags/feature-x", headers={"Authorization": "Bearer token"})

    assert response.status_code == 204
    assert response.data == b""
    app_module._mock_conn.commit.assert_called()


def test_delete_flag_not_found(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)

    app_module._mock_cursor.rowcount = 0

    response = client.delete(
        "/flags/inexistente", headers={"Authorization": "Bearer token"})

    assert response.status_code == 404
    assert response.get_json() == {"error": "Flag não encontrada"}


def test_delete_flag_internal_error(client, app_module, monkeypatch):
    auth_ok(monkeypatch, app_module)
    app_module._mock_cursor.execute.side_effect = Exception("erro delete")

    response = client.delete(
        "/flags/feature-x", headers={"Authorization": "Bearer token"})

    assert response.status_code == 500
    body = response.get_json()
    assert body["error"] == "Erro interno do servidor"
    assert "erro delete" in body["details"]
