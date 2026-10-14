def test_deposit_is_70_percent(make_order):
    order = make_order("API REST au forfait")
    assert order["total_amount"] == 75000
    assert order["deposit_amount"] == 52500
    assert order["status"] == "pending"


def test_unknown_plan_is_rejected(client):
    r = client.post("/api/orders", json={"plan_name": "Gratuit", "client_name": "X", "client_email": "x@example.com"})
    assert r.status_code == 400


def test_client_cannot_choose_the_price(client):
    r = client.post(
        "/api/orders",
        json={"plan_name": "Revue de code", "client_name": "X", "client_email": "x@example.com", "total_amount": 1},
    )
    assert r.json()["total_amount"] == 15000


def test_invalid_email_is_rejected(client):
    r = client.post("/api/orders", json={"plan_name": "Revue de code", "client_name": "X", "client_email": "pas-un-email"})
    assert r.status_code == 422


def test_custom_quote_flow(client, admin):
    q = client.post("/api/quote-request", json={"client_name": "Kofi", "client_email": "k@example.com", "description": "App mobile"}).json()
    assert q["status"] == "awaiting_price"

    orders = client.get("/api/admin/orders", headers=admin).json()
    order_id = next(o["id"] for o in orders if o["public_ref"] == q["public_ref"])

    r = client.post(f"/api/admin/orders/{order_id}/set-price", json={"total_amount": 500000}, headers=admin)
    assert r.json() == {"status": "pending", "total_amount": 500000, "deposit_amount": 350000}


def test_testimonials_need_approval(client, admin):
    client.post("/api/testimonials", json={"client_name": "Sam", "message": "Super travail", "rating": 5})
    assert all(t["client_name"] != "Sam" for t in client.get("/api/testimonials").json())

    pending = client.get("/api/admin/testimonials", headers=admin).json()
    tid = next(t["id"] for t in pending if t["client_name"] == "Sam")
    client.post(f"/api/admin/testimonials/{tid}/approve", headers=admin)
    assert any(t["client_name"] == "Sam" for t in client.get("/api/testimonials").json())
