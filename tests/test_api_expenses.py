import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api import deps, rate_limit
from api.main import app
from core import db
from core import files
from tests.helpers import text_pdf

USER_A = "00000000-0000-0000-0000-00000000000a"
USER_B = "00000000-0000-0000-0000-00000000000b"
RECEIPT = ["TRADER JOES MARKET", "10/28/2026", "VISA ****1234", "BANANAS 1.67", "SUBTOTAL 1.67", "TAX 0.13", "TOTAL 1.80"]
PDF = text_pdf(RECEIPT)


@pytest.fixture
def api(conn, monkeypatch):
    """Runs the real app against real Postgres, with a switchable current user."""
    monkeypatch.setenv("EXTRACTION_BACKEND", "local")
    monkeypatch.setenv("AUTH_MODE", "local")
    state = {"user": USER_A}
    rate_limit.reset()

    def conn_as_user():
        db.act_as(conn, state["user"])  # runs under row-level security, as in production
        return conn

    app.dependency_overrides[deps.current_user] = lambda: state["user"]
    app.dependency_overrides[deps.get_conn] = conn_as_user
    client = TestClient(app, raise_server_exceptions=False)
    client.state = state
    client.db = conn
    yield client
    app.dependency_overrides.clear()


def form(**changes):
    return {"merchant": "Safeway", "date": "2026-10-28", "total": 10.0, **changes}


def post_expense(api, **changes):
    return api.post("/api/expenses", json=form(**changes))


def extract(api, name="r.pdf", data=PDF):
    return api.post("/api/extractions", files={"file": (name, data)})


def count(api):
    return api.db.execute("SELECT count(*) AS n FROM expenses").fetchone()["n"]


# Extracting


def test_extract_reads_file_and_saves_nothing(api):
    response = extract(api)
    assert response.status_code == 200
    body = response.json()
    assert body["extraction"]["total"] == 1.80
    assert (body["category"], body["category_source"], body["blocks_save"]) == ("Groceries", "rule", False)
    assert count(api) == 0


@pytest.mark.parametrize(
    "name, data, text",
    [("a.gif", b"GIF89a", "isn't supported"), ("a.png", b"", "empty"), ("a.png", b"x" * (10 * 1024 * 1024 + 1), "10 MB")],
)
def test_bad_uploads_explain_what_to_do(api, name, data, text):
    response = extract(api, name, data)
    assert response.status_code == 400
    assert text in response.json()["detail"]
    assert "manually" in response.json()["detail"]


def test_corrupt_image_is_unreadable_not_a_crash(api):
    body = extract(api, "a.png", b"junk").json()
    assert body["extraction"]["document_type"] == "unreadable"
    assert [i["code"] for i in body["issues"]] == ["V02"]
    assert body["blocks_save"] is False


def test_non_receipt_gets_v01(api):
    body = extract(api, "n.pdf", text_pdf(["Lecture notes about databases and normalization"])).json()
    assert [i["code"] for i in body["issues"]] == ["V01"]


def test_mock_mode(api, monkeypatch):
    monkeypatch.setenv("EXTRACTION_BACKEND", "mock")
    body = extract(api, "mismatch.jpg", b"anything").json()
    assert "V08" in [i["code"] for i in body["issues"]]


def test_missing_date_warns_and_suggests_today(api):
    client_today = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    body = api.post(
        "/api/extractions",
        files={"file": ("r.pdf", text_pdf(["PINE MARKET GROCERS", "TOTAL 5.00"]))},
        data={"client_today": client_today},
    ).json()
    assert body["suggested_date"] == client_today  # the user's date, which can differ from the server's
    assert "V05" in [i["code"] for i in body["issues"]]


# Validating


def test_validate_reports_blocking_issues_and_saves_nothing(api):
    body = api.post("/api/validate", json=form(total=0)).json()
    assert body["blocks_save"] is True
    assert count(api) == 0


def test_validate_suggests_category_from_merchant(api):
    assert api.post("/api/validate", json=form()).json()["category"] == "Groceries"


def test_validate_finds_likely_duplicate(api):
    post_expense(api)
    assert [d["kind"] for d in api.post("/api/validate", json=form()).json()["duplicates"]] == ["likely"]


# Saving


def test_save_end_to_end_keeps_details_and_text_but_no_file(api):
    body = extract(api).json()
    response = post_expense(api, total=1.80, extraction=body["extraction"], file_hash=body["file_hash"])
    assert response.status_code == 201
    expense = response.json()["expense"]
    assert (expense["total"], expense["category"]) == (1.80, "Groceries")
    assert not {"file_path", "file_hash", "user_id", "has_file"} & set(expense)
    assert "BANANAS" in api.get(f"/api/expenses/{expense['id']}").json()["extraction"]["raw_text"]
    assert api.get(f"/api/expenses/{expense['id']}/file").status_code == 404
    columns = api.db.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'expenses'"
    ).fetchall()
    assert "file_path" not in {c["column_name"] for c in columns}


def test_uploads_are_not_written_to_disk(api, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    post_expense(api, extraction=extract(api).json()["extraction"])
    assert list(tmp_path.iterdir()) == []


def test_same_file_is_flagged_as_exact_duplicate_from_its_hash(api):
    body = extract(api).json()
    assert body["file_hash"] == files.file_hash(PDF)
    post_expense(api, extraction=body["extraction"], file_hash=body["file_hash"], merchant="Different")
    assert [d["kind"] for d in extract(api).json()["duplicates"]] == ["exact"]


def test_bad_file_hash_is_refused(api):
    assert post_expense(api, file_hash="../etc").status_code == 422


def test_saved_extraction_is_redacted(api):
    extraction = extract(api).json()["extraction"]
    assert "****1234" in extraction["raw_text"]
    expense_id = post_expense(api, total=1.80, extraction=extraction).json()["expense"]["id"]
    stored = api.db.execute("SELECT extraction_json::text AS j FROM expenses WHERE id = %s", (expense_id,)).fetchone()["j"]
    assert "1234" not in stored
    assert "1234" not in api.get(f"/api/expenses/{expense_id}").text


@pytest.mark.parametrize(
    "changes, code",
    [({"total": None}, "V03"), ({"total": 0}, "V04"), ({"total": -1}, "V04"),
     ({"date": (date.today() + timedelta(days=3)).isoformat()}, "V06")],
)
def test_server_refuses_blocked_saves(api, changes, code):
    response = post_expense(api, **changes)
    assert response.status_code == 422
    assert code in [i["code"] for i in response.json()["detail"]["issues"]]
    assert count(api) == 0


def test_client_today_cannot_allow_a_far_future_date(api):
    future = (date.today() + timedelta(days=30)).isoformat()
    assert post_expense(api, date=future, client_today=future).status_code == 422


def test_unreadable_extraction_cannot_bypass_validation(api):
    extraction = {"document_type": "unreadable", "raw_text": "x", "text_confidence": 10}
    assert post_expense(api, total=None, extraction=extraction).status_code == 422
    saved = post_expense(api, total=5.0, extraction=extraction).json()["expense"]
    assert saved["document_type"] == "manual"


@pytest.mark.parametrize(
    "changes",
    [{"total": 1e30}, {"merchant": "x" * 201}, {"payment_method": "gold"}, {"unknown_field": 1}, {"date": "not-a-date"}],
)
def test_bad_values_are_refused_without_a_server_error(api, changes):
    assert post_expense(api, **changes).status_code == 422


def test_invalid_json_and_category_are_refused(api):
    response = api.post("/api/expenses", content="{", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "couldn't be read" in response.json()["detail"]
    assert post_expense(api, category="Not A Category").status_code == 422


def test_blank_merchant_is_refused(api):
    response = post_expense(api, merchant="  ", category="Other")
    assert response.status_code == 422
    assert [i["code"] for i in response.json()["detail"]["issues"]] == ["V12"]
    assert api.get("/api/expenses").json() == []


def test_always_use_category_applies_next_time(api):
    response = post_expense(api, merchant="Joe's Deli", category="Groceries", always_use_category=True)
    assert response.json()["expense"]["category_source"] == "manual"
    body = api.post("/api/validate", json=form(merchant="JOE'S DELI #12")).json()
    assert (body["category"], body["category_source"]) == ("Groceries", "override")


# Listing, editing, deleting


def test_list_filters_and_order(api):
    post_expense(api, merchant="Old", date="2026-09-01", category="Other")
    post_expense(api, merchant="New", date="2026-10-20", category="Groceries")
    assert [e["merchant"] for e in api.get("/api/expenses").json()] == ["New", "Old"]
    assert [e["merchant"] for e in api.get("/api/expenses", params={"start": "2026-10-01"}).json()] == ["New"]
    assert [e["merchant"] for e in api.get("/api/expenses", params={"end": "2026-09-30"}).json()] == ["Old"]
    assert [e["merchant"] for e in api.get("/api/expenses", params={"category": "Other"}).json()] == ["Old"]


def test_edit_changes_only_what_was_sent(api):
    created = post_expense(api, note="lunch", tax=1.0).json()["expense"]
    response = api.patch(f"/api/expenses/{created['id']}", json={"total": 12.5})
    assert response.status_code == 200
    updated = response.json()["expense"]
    assert (updated["total"], updated["note"], updated["tax"], updated["merchant"]) == (12.5, "lunch", 1.0, "Safeway")
    assert updated["category_source"] == created["category_source"]


def test_edit_can_clear_an_optional_field(api):
    created = post_expense(api, note="lunch", tax=1.0).json()["expense"]
    updated = api.patch(f"/api/expenses/{created['id']}", json={"tax": None, "note": ""}).json()["expense"]
    assert (updated["tax"], updated["note"]) == (None, None)


def test_edit_category_becomes_manual(api):
    created = post_expense(api).json()["expense"]
    updated = api.patch(f"/api/expenses/{created['id']}", json={"category": "Travel"}).json()["expense"]
    assert (updated["category"], updated["category_source"]) == ("Travel", "manual")


@pytest.mark.parametrize("change", [{"total": 0}, {"total": None}, {"date": "2099-01-01"}, {"category": "Nope"}])
def test_edit_is_validated(api, change):
    created = post_expense(api).json()["expense"]
    assert api.patch(f"/api/expenses/{created['id']}", json=change).status_code == 422
    assert api.get(f"/api/expenses/{created['id']}").json()["total"] == 10.0


def test_edit_does_not_flag_itself_as_duplicate(api):
    created = post_expense(api).json()["expense"]
    assert api.patch(f"/api/expenses/{created['id']}", json={"note": "x"}).json()["duplicates"] == []


# Settings


def test_settings_roundtrip_and_limits(api):
    assert api.get("/api/settings").json() == {"name": "", "monthly_budget": None, "cycle_start_day": 1}
    saved = api.put("/api/settings", json={"name": " Ava ", "monthly_budget": 800, "cycle_start_day": 15}).json()
    assert saved == {"name": "Ava", "monthly_budget": 800.0, "cycle_start_day": 15}
    assert api.get("/api/settings").json() == saved
    assert api.put("/api/settings", json={"cycle_start_day": 29}).status_code == 422
    assert api.put("/api/settings", json={"monthly_budget": -1}).status_code == 422
    assert api.put("/api/settings", json={"monthly_budget": 0}).json()["monthly_budget"] is None


def test_categories(api):
    assert "Groceries" in api.get("/api/categories").json()


# Users stay separate


def test_another_users_expense_looks_missing(api):
    created = post_expense(api, merchant="Private Shop").json()["expense"]
    url = f"/api/expenses/{created['id']}"
    api.state["user"] = USER_B
    for response in (api.get(url), api.patch(url, json={"total": 1.0}), api.delete(url)):
        assert response.status_code == 404
        assert "Private Shop" not in response.text
    assert api.get("/api/expenses").json() == []
    api.state["user"] = USER_A
    assert api.get(url).json()["total"] == 10.0


def test_same_file_for_two_users_is_not_a_duplicate(api):
    body = extract(api).json()
    post_expense(api, extraction=body["extraction"], file_hash=body["file_hash"])
    api.state["user"] = USER_B
    assert extract(api).json()["duplicates"] == []


def test_delete_removes_the_expense(api):
    created = post_expense(api).json()["expense"]
    assert api.delete(f"/api/expenses/{created['id']}").status_code == 204
    assert api.get(f"/api/expenses/{created['id']}").status_code == 404
    assert api.delete(f"/api/expenses/{created['id']}").status_code == 404


def test_settings_and_overrides_stay_separate(api):
    api.put("/api/settings", json={"name": "Ava"})
    post_expense(api, merchant="Joe's Deli", category="Travel", always_use_category=True)
    api.state["user"] = USER_B
    assert api.get("/api/settings").json()["name"] == ""
    assert api.post("/api/validate", json=form(merchant="Joe's Deli")).json()["category_source"] != "override"


def test_user_id_in_a_request_is_refused(api):
    assert post_expense(api, user_id=USER_B).status_code == 422


def test_upload_rate_limit_is_per_user(api, monkeypatch):
    monkeypatch.setattr(rate_limit, "MAX_UPLOADS", 2)
    assert extract(api).status_code == 200
    assert extract(api).status_code == 200
    response = extract(api)
    assert response.status_code == 429
    assert "Wait a minute" in response.json()["detail"]
    api.state["user"] = USER_B
    assert extract(api).status_code == 200


def test_rate_limit_window_expires():
    rate_limit.reset()
    for _ in range(rate_limit.MAX_UPLOADS):
        assert rate_limit.allow_upload("u", now=0.0)
    assert not rate_limit.allow_upload("u", now=59.0)
    assert rate_limit.allow_upload("u", now=60.0)
    rate_limit.reset()


# Protection


def test_non_local_mode_refuses_every_data_route_until_tokens_are_checked(conn, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "supabase")
    app.dependency_overrides[deps.get_conn] = lambda: conn
    client = TestClient(app)
    try:
        assert client.get("/api/expenses").status_code == 401
        assert client.get("/api/settings").status_code == 401
        assert client.get("/api/categories").status_code == 401
        assert client.post("/api/validate", json=form()).status_code == 401
        assert client.post("/api/extractions", files={"file": ("r.pdf", PDF)}).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_server_errors_reveal_nothing_to_browser_or_logs(api, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("secret receipt text Private Shop")

    monkeypatch.setattr(db, "list_expenses", broken)
    with caplog.at_level(logging.ERROR):
        response = api.get("/api/expenses")
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on our side. Please try again."}
    assert response.headers["cache-control"] == "no-store"
    assert "secret" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_validation_errors_do_not_echo_values(api):
    response = api.post("/api/validate", json=form(merchant="y" * 300))
    assert response.status_code == 422
    assert "yyy" not in response.text
    assert response.json()["fields"] == ["merchant"]


def test_interactive_docs_are_off(api):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert api.get(path).status_code == 404


def manual_body(**changes):
    return {"merchant": "Made Up Shop", "date": "2026-10-20", "total": 12.5, "client_today": "2026-11-01", **changes}


def test_editing_isnt_its_own_duplicate_but_another_expense_is(api):
    client = api
    first = client.post("/api/expenses", json=manual_body()).json()["expense"]["id"]
    second = client.post("/api/expenses", json=manual_body(total=99)).json()["expense"]["id"]

    alone = client.post(f"/api/expenses/{first}/validate", json={"note": "lunch"}).json()
    assert alone["duplicates"] == []
    clash = client.post(f"/api/expenses/{second}/validate", json={"total": 12.5}).json()
    assert [d["expense_id"] for d in clash["duplicates"]] == [first]


def test_validating_an_edit_saves_nothing_and_reports_blocking_errors(api):
    client = api
    expense_id = client.post("/api/expenses", json=manual_body()).json()["expense"]["id"]
    report = client.post(f"/api/expenses/{expense_id}/validate", json={"total": 0}).json()
    assert report["blocks_save"] is True
    assert client.get(f"/api/expenses/{expense_id}").json()["total"] == 12.5


def test_another_users_expense_cant_be_validated(api):
    client, state = api, api.state
    expense_id = client.post("/api/expenses", json=manual_body()).json()["expense"]["id"]
    state["user"] = USER_B
    assert client.post(f"/api/expenses/{expense_id}/validate", json={"total": 1}).status_code == 404


def test_an_edit_can_remember_the_category_for_the_merchant(api):
    client = api
    expense_id = client.post("/api/expenses", json=manual_body(category="Other")).json()["expense"]["id"]
    assert client.patch(
        f"/api/expenses/{expense_id}", json={"category": "Education", "always_use_category": True}
    ).status_code == 200
    next_one = client.post("/api/validate", json=manual_body(total=1))
    assert next_one.json()["category"] == "Education"
    assert next_one.json()["category_source"] == "override"


def test_periods_follow_the_users_cycle(api):
    client, state = api, api.state
    today = datetime.now(timezone.utc).date()
    assert client.get("/api/periods").json()[0]["start"] == today.replace(day=1).isoformat()

    assert client.put("/api/settings", json={"cycle_start_day": 15}).status_code == 200
    found = client.get("/api/periods").json()
    assert date.fromisoformat(found[0]["start"]).day == 15
    assert len(found) == 12

    state["user"] = USER_B  # another user's settings don't apply
    assert date.fromisoformat(client.get("/api/periods").json()[0]["start"]).day == 1


def test_dashboard_counts_only_this_users_expenses(api):
    today = datetime.now(timezone.utc).date().isoformat()
    assert post_expense(api, date=today, total=30.0, merchant="Mine", client_today=today).status_code == 201
    assert api.get(f"/api/dashboard?client_today={today}").json()["spent"] == 30

    api.state["user"] = USER_B
    other = api.get(f"/api/dashboard?client_today={today}").json()
    assert other["spent"] == 0
    assert other["top"]["rows"] == []


def test_dashboard_uses_the_users_budget_and_cycle(api):
    assert api.put("/api/settings", json={"name": "Sam", "monthly_budget": 500, "cycle_start_day": 15}).status_code == 200
    result = api.get("/api/dashboard").json()
    assert result["budget"]["budget"] == 500
    assert date.fromisoformat(result["period"]["start"]).day == 15


def test_dashboard_doesnt_expose_owner_or_file_details(api):
    today = datetime.now(timezone.utc).date().isoformat()
    post_expense(api, date=today, client_today=today, file_hash="a" * 64)
    text = api.get(f"/api/dashboard?client_today={today}").text
    assert "a" * 64 not in text
    assert "user_id" not in text and USER_A not in text


def test_dashboard_opens_a_past_period_for_this_user_only(api):
    assert post_expense(api, date="2025-03-10", total=44.0, merchant="Old").status_code == 201
    assert api.get("/api/dashboard?period=2025-03-01").json()["spent"] == 44
    assert api.get("/api/dashboard").json()["trend"]["history"][-1]["total"] == 44
    assert api.get("/api/dashboard?period=not-a-date").status_code == 422

    api.state["user"] = USER_B
    other = api.get("/api/dashboard?period=2025-03-01").json()
    assert other["spent"] == 0
    assert len(other["trend"]["history"]) == 1
