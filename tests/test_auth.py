"""Real signed tokens, verified against a real public-key endpoint, through the real app."""
import base64
import http.server
import json
import threading
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import Depends
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from api import auth, deps
from api.main import app
from api.routes import account
from core import db

A = "00000000-0000-0000-0000-00000000000a"
B = "00000000-0000-0000-0000-00000000000b"
KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(public_key, algorithm, alg, kid):
    return {**json.loads(algorithm.to_jwk(public_key)), "kid": kid, "alg": alg, "use": "sig"}


JWKS = json.dumps(
    {"keys": [_jwk(KEY.public_key(), ECAlgorithm, "ES256", "ec1"), _jwk(RSA_KEY.public_key(), RSAAlgorithm, "RS256", "rsa1")]}
).encode()


class JwksHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.path == "/auth/v1/.well-known/jwks.json"
        self.send_response(200 if ok else 404)
        self.end_headers()
        self.wfile.write(JWKS if ok else b"")

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def supabase_url():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), JwksHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def client(conn, supabase_url, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", supabase_url)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "test-only")
    auth._key_client.cache_clear()

    def conn_for_token(user_id: str = Depends(deps.current_user)):
        db.act_as(conn, user_id)
        return conn

    app.dependency_overrides[deps.get_conn] = conn_for_token
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def token(url, key=KEY, alg="ES256", kid="ec1", **changes):
    claims = {"sub": A, "aud": "authenticated", "role": "authenticated", "iss": f"{url}/auth/v1", "exp": int(time.time()) + 300}
    claims.update(changes)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


def bearer(value):
    return {"Authorization": f"Bearer {value}"}


def form(**changes):
    return {"merchant": "Private Shop", "date": "2026-10-28", "total": 10.0, "category": "Other", **changes}


@pytest.mark.parametrize("alg, key, kid", [("ES256", KEY, "ec1"), ("RS256", RSA_KEY, "rsa1")])
def test_valid_token_is_accepted(client, supabase_url, alg, key, kid):
    response = client.get("/api/settings", headers=bearer(token(supabase_url, key=key, alg=alg, kid=kid)))
    assert response.status_code == 200


def test_no_token_is_refused(client):
    response = client.get("/api/expenses")
    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in to continue."
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["", "Bearer", "Bearer ", "Basic abc", "abc", "Bearer not.a.token", "Bearer a b c"])
def test_malformed_headers_are_refused(client, header):
    assert client.get("/api/expenses", headers={"Authorization": header}).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": 1},
        {"exp": None},
        {"aud": "someone-else"},
        {"aud": None},
        {"iss": "https://evil.example/auth/v1"},
        {"iss": None},
        {"sub": None},
        {"sub": "not-a-uuid"},
        {"role": "anon"},
        {"role": "service_role"},
        {"role": None},
    ],
)
def test_bad_claims_are_refused(client, supabase_url, changes):
    assert client.get("/api/expenses", headers=bearer(token(supabase_url, **changes))).status_code == 401


def test_token_signed_with_the_wrong_key_is_refused(client, supabase_url):
    assert client.get("/api/expenses", headers=bearer(token(supabase_url, key=OTHER_KEY))).status_code == 401


def test_unknown_key_id_is_refused(client, supabase_url):
    assert client.get("/api/expenses", headers=bearer(token(supabase_url, kid="nope"))).status_code == 401


def _b64(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_unsigned_token_is_refused(client, supabase_url):
    claims = {"sub": A, "aud": "authenticated", "role": "authenticated", "iss": f"{supabase_url}/auth/v1", "exp": int(time.time()) + 300}
    forged = f"{_b64({'alg': 'none', 'kid': 'ec1', 'typ': 'JWT'})}.{_b64(claims)}."
    assert client.get("/api/expenses", headers=bearer(forged)).status_code == 401


def test_tampered_payload_is_refused(client, supabase_url):
    header, _, signature = token(supabase_url).split(".")
    forged_claims = {"sub": B, "aud": "authenticated", "role": "authenticated", "iss": f"{supabase_url}/auth/v1", "exp": int(time.time()) + 300}
    assert client.get("/api/expenses", headers=bearer(f"{header}.{_b64(forged_claims)}.{signature}")).status_code == 401


def test_shared_secret_token_is_refused(client, supabase_url):
    forged = jwt.encode(
        {"sub": A, "aud": "authenticated", "role": "authenticated", "iss": f"{supabase_url}/auth/v1", "exp": int(time.time()) + 300},
        "a-shared-secret-that-is-long-enough-for-hs256",
        algorithm="HS256",
        headers={"kid": "ec1"},
    )
    assert client.get("/api/expenses", headers=bearer(forged)).status_code == 401


def test_key_server_down_refuses_rather_than_allows(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:9")
    auth._key_client.cache_clear()
    assert client.get("/api/expenses", headers=bearer(token("http://127.0.0.1:9"))).status_code == 401


@pytest.mark.parametrize(
    "mode, url", [("supabase", ""), ("something-else", "http://x"), ("", "")]
)
def test_misconfigured_server_refuses_everyone(client, supabase_url, monkeypatch, mode, url):
    monkeypatch.setenv("AUTH_MODE", mode)
    monkeypatch.setenv("SUPABASE_URL", url)
    assert client.get("/api/expenses", headers=bearer(token(supabase_url))).status_code == 401


def test_unset_auth_mode_requires_sign_in(client, monkeypatch):
    monkeypatch.delenv("AUTH_MODE")
    assert client.get("/api/expenses").status_code == 401


def test_status_route_is_public_and_has_no_secrets(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "fake-secret-value")
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "fake-secret-value" not in response.text


def test_two_users_stay_separate_using_only_their_tokens(client, supabase_url):
    ann, bo = bearer(token(supabase_url, sub=A)), bearer(token(supabase_url, sub=B))
    created = client.post("/api/expenses", json=form(), headers=ann)
    assert created.status_code == 201
    url = f"/api/expenses/{created.json()['expense']['id']}"
    assert client.get(url, headers=bo).status_code == 404
    assert client.delete(url, headers=bo).status_code == 404
    assert client.get("/api/expenses", headers=bo).json() == []
    assert [e["merchant"] for e in client.get("/api/expenses", headers=ann).json()] == ["Private Shop"]


def test_user_comes_from_the_token_not_the_request(client, supabase_url):
    ann = bearer(token(supabase_url, sub=A))
    assert client.post("/api/expenses", json=form(user_id=B), headers=ann).status_code == 422
    assert client.get(f"/api/expenses?user_id={B}", headers=ann).json() == []
    client.post("/api/expenses", json=form(), headers=ann)
    assert len(client.get(f"/api/expenses?user_id={B}", headers=ann).json()) == 1


class FakeAdminResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def _account_setup(client, supabase_url):
    ann, bo = bearer(token(supabase_url, sub=A)), bearer(token(supabase_url, sub=B))
    client.post("/api/expenses", json=form(), headers=ann)
    client.post("/api/expenses", json=form(), headers=bo)
    client.put("/api/settings", json={"name": "Ann"}, headers=ann)
    return ann, bo


def test_delete_account_removes_data_and_sign_in_for_that_user_only(client, supabase_url, monkeypatch):
    ann, bo = _account_setup(client, supabase_url)
    calls = []

    def fake_delete(url, headers, timeout):
        calls.append((url, headers))
        return FakeAdminResponse(200)

    monkeypatch.setattr(account.httpx, "delete", fake_delete)
    response = client.request("DELETE", "/api/account", json={"confirm": "DELETE"}, headers=ann)
    assert response.status_code == 204
    assert calls == [(f"{supabase_url}/auth/v1/admin/users/{A}", {"apikey": "test-only"})]
    assert client.get("/api/expenses", headers=ann).json() == []
    assert client.get("/api/settings", headers=ann).json()["name"] == ""
    assert len(client.get("/api/expenses", headers=bo).json()) == 1


@pytest.mark.parametrize("body", [{}, {"confirm": "yes"}, None])
def test_delete_account_needs_explicit_confirmation(client, supabase_url, monkeypatch, body):
    ann, _ = _account_setup(client, supabase_url)
    monkeypatch.setattr(account.httpx, "delete", lambda **k: pytest.fail("should not be called"))
    assert client.request("DELETE", "/api/account", json=body, headers=ann).status_code == 422
    assert len(client.get("/api/expenses", headers=ann).json()) == 1


def test_delete_account_without_token_is_refused(client):
    assert client.request("DELETE", "/api/account", json={"confirm": "DELETE"}).status_code == 401


@pytest.mark.parametrize("failure", [FakeAdminResponse(500), httpx.ConnectError("down")])
def test_failed_sign_in_removal_says_so_and_can_be_retried(client, supabase_url, monkeypatch, failure):
    ann, _ = _account_setup(client, supabase_url)

    def fake_delete(url, headers, timeout):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(account.httpx, "delete", fake_delete)
    response = client.request("DELETE", "/api/account", json={"confirm": "DELETE"}, headers=ann)
    assert response.status_code == 502
    assert "try again" in response.json()["detail"]
    assert "test-only" not in response.text
    assert client.get("/api/expenses", headers=ann).json() == []
    monkeypatch.setattr(account.httpx, "delete", lambda url, headers, timeout: FakeAdminResponse(404))
    assert client.request("DELETE", "/api/account", json={"confirm": "DELETE"}, headers=ann).status_code == 204


def test_local_mode_delete_clears_data_without_calling_supabase(client, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setattr(account.httpx, "delete", lambda **k: pytest.fail("should not be called"))
    client.post("/api/expenses", json=form())
    assert client.request("DELETE", "/api/account", json={"confirm": "DELETE"}).status_code == 204
    assert client.get("/api/expenses").json() == []
