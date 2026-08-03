from tests.conftest import auth


def test_plans_public(client):
    r = client.get("/api/v1/payment/plans")
    assert r.status_code == 200
    assert any(p["id"] == "pro_monthly" for p in r.json()["plans"])


def test_status_requires_auth(client):
    assert client.get("/api/v1/payment/status").status_code == 401


def test_revenuecat_webhook_rejects_without_auth(client):
    r = client.post("/api/v1/payment/webhook/revenuecat",
                    json={"event": {"type": "INITIAL_PURCHASE", "app_user_id": "victim"}})
    assert r.status_code == 401


def test_revenuecat_webhook_valid_auth_upgrades(client, monkeypatch):
    from services.payment_service import payment_service
    from services.database_service import db_service
    monkeypatch.setattr(payment_service, "revenuecat_webhook_auth", "secret-token")

    r = client.post("/api/v1/payment/webhook/revenuecat",
                    headers={"Authorization": "secret-token"},
                    json={"event": {"type": "INITIAL_PURCHASE", "app_user_id": "u9"}})
    assert r.status_code == 200 and r.json()["action"] == "upgrade"
    assert db_service.get_or_create_user("u9").tier_status.value == "pro"


def test_stripe_webhook_invalid_signature(client):
    # No webhook secret configured -> verification returns None -> 400 (no stripe import).
    r = client.post("/api/v1/payment/webhook/stripe",
                    content=b"{}", headers={"stripe-signature": "bad"})
    assert r.status_code == 400


def test_entitlement_active_expiry_logic():
    from services.payment_service import payment_service
    assert payment_service._entitlement_active("2999-01-01T00:00:00Z") is True
    assert payment_service._entitlement_active("2000-01-01T00:00:00Z") is False
    assert payment_service._entitlement_active(None) is False
    assert payment_service._entitlement_active("not-a-date") is False
