import main


def test_admin_requires_valid_token(client, admin):
    assert client.get("/api/admin/orders").status_code == 401
    assert client.get("/api/admin/orders", headers={"X-Admin-Token": "faux"}).status_code == 401
    assert client.get("/api/admin/orders", headers=admin).status_code == 200


def test_api_does_not_serve_frontend_or_private_files(client):
    for path in ("/backend/.env", "/backend/main.py", "/backend/data/test.db", "/README.md", "/.git/config", "/Dockerfile"):
        assert client.get(path).status_code == 404, path
    assert client.get("/").status_code == 404  # Render sert uniquement l'API.
    assert client.get("/docs").status_code == 200
    assert client.get("/api/testimonials").status_code == 200


def test_cors_only_allows_configured_origin(client):
    headers = {"Access-Control-Request-Method": "POST", "Origin": "https://evil.example"}
    r = client.options("/api/orders", headers=headers)
    assert "access-control-allow-origin" not in r.headers

    headers["Origin"] = "https://obed.example"
    r = client.options("/api/orders", headers=headers)
    assert r.headers.get("access-control-allow-origin") == "https://obed.example"


def test_invoice_escapes_client_input(client, make_order, kkiapay_ok):
    order = make_order(name="<script>alert(1)</script>")
    client.post("/api/kkiapay/confirm", json={"public_ref": order["public_ref"], "transaction_id": "tx-xss"})

    html = client.get(f"/invoice/{order['public_ref']}").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_invoice_unavailable_before_deposit(client, make_order):
    order = make_order()
    html = client.get(f"/invoice/{order['public_ref']}").text
    assert "sera disponible" in html


def test_oversized_input_is_rejected(client):
    r = client.post("/api/contact", json={"name": "A" * 1000, "email": "a@example.com", "message": "ok"})
    assert r.status_code == 422
