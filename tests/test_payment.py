import main


def test_deposit_confirmed_when_amount_matches(client, make_order, kkiapay_ok):
    order = make_order()
    r = client.post("/api/kkiapay/confirm", json={"public_ref": order["public_ref"], "transaction_id": "tx-1"})
    assert r.json() == {"status": "confirmed"}
    assert client.get(f"/api/orders/{order['public_ref']}").json()["status"] == "deposit_paid"


def test_wrong_amount_is_refused(client, make_order, monkeypatch):
    monkeypatch.setattr(main, "_verify_with_kkiapay", lambda tx: (True, 100, "SUCCESS"))
    order = make_order()
    r = client.post("/api/kkiapay/confirm", json={"public_ref": order["public_ref"], "transaction_id": "tx-2"})
    assert r.json()["status"] == "failed"
    assert client.get(f"/api/orders/{order['public_ref']}").json()["status"] == "failed"


def test_transaction_cannot_be_replayed_on_another_order(client, make_order, kkiapay_ok):
    first, second = make_order(), make_order()
    ok = client.post("/api/kkiapay/confirm", json={"public_ref": first["public_ref"], "transaction_id": "tx-replay"})
    assert ok.json() == {"status": "confirmed"}

    replay = client.post("/api/kkiapay/confirm", json={"public_ref": second["public_ref"], "transaction_id": "tx-replay"})
    assert replay.status_code == 409
    assert client.get(f"/api/orders/{second['public_ref']}").json()["status"] == "pending"


def test_failed_payment_does_not_block_a_legit_retry(client, make_order, monkeypatch):
    order = make_order()
    monkeypatch.setattr(main, "_verify_with_kkiapay", lambda tx: (False, None, "FAILED"))
    client.post("/api/kkiapay/confirm", json={"public_ref": order["public_ref"], "transaction_id": "tx-retry"})

    monkeypatch.setattr(main, "_verify_with_kkiapay", lambda tx: (True, 52500, "SUCCESS"))
    r = client.post("/api/kkiapay/confirm", json={"public_ref": order["public_ref"], "transaction_id": "tx-retry"})
    assert r.json() == {"status": "confirmed"}


def test_missing_transaction_id_is_refused(client, make_order):
    order = make_order()
    r = client.post("/api/kkiapay/confirm", json={"public_ref": order["public_ref"]})
    assert r.json()["status"] == "failed"
