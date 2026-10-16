"""Split Bill, approval, and payments on the emulators."""

import pytest
from fastapi.testclient import TestClient

from travelin.ai import receipt
from travelin.ai.receipt import Receipt, ReceiptItem, check

from .emulator import firestore_client, requires_emulators, sign_up
from .test_trips import TRIP


def planned_trip(client: TestClient) -> dict:
    """Hana (host), Raka, and Sari, with an itinerary already planned."""
    people = {name: sign_up(name) for name in ("Hana", "Raka", "Sari")}
    created = client.post("/v1/trips", json=TRIP, headers=people["Hana"]).json()
    for name in ("Raka", "Sari"):
        client.post(f"/v1/join/{created['inviteCode']}", headers=people[name])
    store = firestore_client()
    trip_ref = store.document(f"trips/{created['tripId']}")
    trip_ref.update({"status": "planned"})
    uids = {doc.to_dict()["displayName"]: doc.id for doc in trip_ref.collection("members").stream()}
    return {"id": created["tripId"], "headers": people, "uids": uids}


def expense(paid_by: str, amount: int, participants: list[str], title: str = "Dinner") -> dict:
    return {
        "title": title,
        "amountIdr": amount,
        "paidBy": paid_by,
        "split": {"mode": "equal", "participants": participants},
    }


def transfers_of(trip_id: str) -> list[dict]:
    return [
        {"id": doc.id, **doc.to_dict()}
        for doc in firestore_client().collection(f"trips/{trip_id}/transfers").stream()
    ]


def test_receipt_check_flags_bad_arithmetic():
    good = Receipt(
        merchant="Warung",
        items=[ReceiptItem(name="Gudeg", unit_price=30_000, qty=2, line_total=60_000)],
        subtotal=60_000, tax=6_000, service=0, discount=0, total=66_000,
    )  # fmt: skip
    assert check(good) == []
    bad = good.model_copy(update={"total": 70_000})
    assert check(bad) == [
        "Subtotal, tax, service, and discount make Rp66,000, but the total reads Rp70,000."
    ]


@requires_emulators
def test_full_settle_up_flow(client: TestClient):
    trip = planned_trip(client)
    tid, h, u = trip["id"], trip["headers"], trip["uids"]
    everyone = list(u.values())

    # Hana paid the homestay for all three; Raka paid a dinner for himself and Sari.
    created = client.post(
        f"/v1/trips/{tid}/expenses",
        json=expense(u["Hana"], 900_000, everyone, "Homestay"),
        headers=h["Hana"],
    )
    assert created.status_code == 201, created.text
    client.post(
        f"/v1/trips/{tid}/expenses",
        json=expense(u["Raka"], 100_000, [u["Raka"], u["Sari"]]),
        headers=h["Raka"],
    )

    preview = client.get(f"/v1/trips/{tid}/split:preview", headers=h["Sari"]).json()
    assert preview["balances"] == {u["Hana"]: 600_000, u["Raka"]: -250_000, u["Sari"]: -350_000}
    assert sorted((t["from"], t["to"], t["amountIdr"]) for t in preview["transfers"]) == sorted(
        [(u["Raka"], u["Hana"], 250_000), (u["Sari"], u["Hana"], 350_000)]
    )

    assert client.post(f"/v1/trips/{tid}/split:open", headers=h["Raka"]).status_code == 204
    version = firestore_client().document(f"trips/{tid}").get().get("split")["version"]

    # A change while approving resets everyone's approval.
    assert (
        client.post(
            f"/v1/trips/{tid}/split:approve", json={"version": version}, headers=h["Hana"]
        ).json()["complete"]
        is False
    )
    client.post(
        f"/v1/trips/{tid}/expenses",
        json=expense(u["Sari"], 30_000, everyone, "Parking"),
        headers=h["Sari"],
    )
    stale = client.post(
        f"/v1/trips/{tid}/split:approve", json={"version": version}, headers=h["Raka"]
    )
    assert stale.status_code == 409

    version += 1
    for name in ("Hana", "Raka"):
        assert (
            client.post(
                f"/v1/trips/{tid}/split:approve", json={"version": version}, headers=h[name]
            ).json()["complete"]
            is False
        )
    last = client.post(
        f"/v1/trips/{tid}/split:approve", json={"version": version}, headers=h["Sari"]
    ).json()
    assert last == {"complete": True, "transfers": 2}

    trip_doc = firestore_client().document(f"trips/{tid}").get().to_dict()
    assert trip_doc["status"] == "settling"
    assert trip_doc["paymentStatus"] == {
        u["Hana"]: "waiting",
        u["Raka"]: "unpaid",
        u["Sari"]: "unpaid",
    }
    transfers = {t["from"]: t for t in transfers_of(tid)}
    assert transfers[u["Raka"]]["amountIdr"] == 260_000  # 250k + his 10k share of parking
    assert transfers[u["Sari"]]["amountIdr"] == 330_000  # 350k - 30k she paid + her 10k share
    assert {t["to"] for t in transfers.values()} == {u["Hana"]}

    raka_transfer, sari_transfer = transfers[u["Raka"]]["id"], transfers[u["Sari"]]["id"]
    assert (
        client.post(
            f"/v1/trips/{tid}/transfers/{raka_transfer}:send", headers=h["Sari"]
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/v1/trips/{tid}/transfers/{raka_transfer}:confirm", headers=h["Hana"]
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/v1/trips/{tid}/transfers/{raka_transfer}:send", headers=h["Raka"]
        ).status_code
        == 204
    )
    assert (
        client.post(
            f"/v1/trips/{tid}/transfers/{raka_transfer}:confirm", headers=h["Raka"]
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/v1/trips/{tid}/transfers/{raka_transfer}:confirm", headers=h["Hana"]
        ).status_code
        == 204
    )

    # Expenses are locked during payments.
    assert (
        client.post(
            f"/v1/trips/{tid}/expenses", json=expense(u["Hana"], 1_000, everyone), headers=h["Hana"]
        ).status_code
        == 409
    )

    client.post(f"/v1/trips/{tid}/transfers/{sari_transfer}:send", headers=h["Sari"])
    client.post(f"/v1/trips/{tid}/transfers/{sari_transfer}:confirm", headers=h["Hana"])
    trip_doc = firestore_client().document(f"trips/{tid}").get().to_dict()
    assert trip_doc["status"] == "settled"
    assert set(trip_doc["paymentStatus"].values()) == {"settled"}

    store = firestore_client()
    raka_texts = [
        d.to_dict()["text"] for d in store.collection(f"users/{u['Raka']}/notifications").stream()
    ]
    assert "Pay Hana Rp260.000 for Jogja long weekend." in raka_texts
    assert "Hana confirmed your Rp260.000 payment." in raka_texts


@requires_emulators
def test_adjust_split_keeps_confirmed_payments(client: TestClient):
    trip = planned_trip(client)
    tid, h, u = trip["id"], trip["headers"], trip["uids"]
    everyone = list(u.values())
    client.post(
        f"/v1/trips/{tid}/expenses", json=expense(u["Hana"], 300_000, everyone), headers=h["Hana"]
    )
    client.post(f"/v1/trips/{tid}/split:open", headers=h["Hana"])
    version = firestore_client().document(f"trips/{tid}").get().get("split")["version"]
    for name in ("Hana", "Raka", "Sari"):
        client.post(f"/v1/trips/{tid}/split:approve", json={"version": version}, headers=h[name])

    raka = next(t for t in transfers_of(tid) if t["from"] == u["Raka"])
    client.post(f"/v1/trips/{tid}/transfers/{raka['id']}:send", headers=h["Raka"])
    client.post(f"/v1/trips/{tid}/transfers/{raka['id']}:confirm", headers=h["Hana"])

    assert client.post(f"/v1/trips/{tid}/split:adjust", headers=h["Sari"]).status_code == 204
    remaining = transfers_of(tid)
    assert [t["status"] for t in remaining] == ["confirmed"]
    assert firestore_client().document(f"trips/{tid}").get().get("status") == "splitting"

    # Sari adds a taxi she paid for; Raka's earlier payment still counts.
    client.post(
        f"/v1/trips/{tid}/expenses",
        json=expense(u["Sari"], 60_000, everyone, "Taxi"),
        headers=h["Sari"],
    )
    preview = client.get(f"/v1/trips/{tid}/split:preview", headers=h["Hana"]).json()
    assert preview["balances"] == {u["Hana"]: 80_000, u["Raka"]: -20_000, u["Sari"]: -60_000}


@requires_emulators
def test_expense_validation(client: TestClient):
    trip = planned_trip(client)
    tid, h, u = trip["id"], trip["headers"], trip["uids"]
    url = f"/v1/trips/{tid}/expenses"

    outsider = client.post(
        url, json=expense("someone-else", 10_000, [u["Hana"]]), headers=h["Hana"]
    )
    assert outsider.status_code == 422
    exact = {
        **expense(u["Hana"], 100_000, [u["Hana"], u["Raka"]]),
        "split": {
            "mode": "exact",
            "participants": [u["Hana"], u["Raka"]],
            "exact": {u["Hana"]: 10_000, u["Raka"]: 10_000},
        },
    }
    assert "add up to" in client.post(url, json=exact, headers=h["Hana"]).json()["detail"]

    receipt_expense = {
        "title": "Gudeg Yu Djum",
        "paidBy": u["Raka"],
        "split": {"mode": "items"},
        "items": [
            {
                "name": "Gudeg",
                "unitPriceIdr": 30_000,
                "qty": 2,
                "portions": {u["Hana"]: 1, u["Raka"]: 1},
            },
            {"name": "Es teh", "unitPriceIdr": 5_000, "qty": 1, "portions": {u["Sari"]: 1}},
        ],
        "taxIdr": 6_500,
    }
    saved = client.post(url, json=receipt_expense, headers=h["Raka"]).json()
    assert saved["amountIdr"] == 71_500
    doc = firestore_client().document(f"trips/{tid}/expenses/{saved['expenseId']}").get().to_dict()
    assert doc["computedShares"] == {u["Hana"]: 33_000, u["Raka"]: 33_000, u["Sari"]: 5_500}
    assert doc["source"] == "receipt"

    assert client.delete(f"{url}/{saved['expenseId']}", headers=h["Sari"]).status_code == 204
    assert client.delete(f"{url}/{saved['expenseId']}", headers=h["Sari"]).status_code == 404


@requires_emulators
def test_receipt_scan_endpoint(client: TestClient, monkeypatch):
    async def fake_scan(storage_path: str) -> Receipt:
        return Receipt(
            merchant="Gudeg Yu Djum",
            items=[ReceiptItem(name="Gudeg", unit_price=30_000, qty=2, line_total=60_000)],
            subtotal=60_000, tax=6_000, service=0, discount=0, total=66_000,
        )  # fmt: skip

    monkeypatch.setattr(receipt, "scan", fake_scan)
    trip = planned_trip(client)
    tid, h, u = trip["id"], trip["headers"], trip["uids"]
    url = f"/v1/trips/{tid}/receipts:scan"

    elsewhere = client.post(
        url, json={"storagePath": f"trips/{tid}/receipts/{u['Raka']}/r.jpg"}, headers=h["Hana"]
    )
    assert elsewhere.status_code == 422
    scanned = client.post(
        url, json={"storagePath": f"trips/{tid}/receipts/{u['Hana']}/r.jpg"}, headers=h["Hana"]
    ).json()
    assert scanned["items"] == [{"name": "Gudeg", "unitPriceIdr": 30_000, "qty": 2}]
    assert scanned["taxIdr"] == 6_000
    assert scanned["warnings"] == []


@pytest.mark.parametrize("status", ["voting", "settling"])
@requires_emulators
def test_expenses_are_closed_outside_planned_and_splitting(client: TestClient, status: str):
    trip = planned_trip(client)
    firestore_client().document(f"trips/{trip['id']}").update({"status": status})
    response = client.post(
        f"/v1/trips/{trip['id']}/expenses",
        json=expense(trip["uids"]["Hana"], 10_000, [trip["uids"]["Hana"]]),
        headers=trip["headers"]["Hana"],
    )
    assert response.status_code == 409
