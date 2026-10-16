import random

import pytest

from travelin.money.settle import _settle_group, net_balances, simplify
from travelin.money.split import Item, SplitError, compute_shares, largest_remainder


def test_largest_remainder_sums_exactly():
    assert largest_remainder(100_000, {"a": 1, "b": 1, "c": 1}) == {
        "a": 33_334,
        "b": 33_333,
        "c": 33_333,
    }
    assert sum(largest_remainder(99_999, {"a": 3, "b": 2, "c": 7}).values()) == 99_999


def test_largest_remainder_handles_negative_totals():
    assert largest_remainder(-10, {"a": 1, "b": 1, "c": 1}) == {"a": -4, "b": -3, "c": -3}


def test_equal_split_ignores_order_of_participants():
    _, first = compute_shares(mode="equal", amount=100_000, participants=["c", "a", "b"])
    _, second = compute_shares(mode="equal", amount=100_000, participants=["a", "b", "c"])
    assert first == second


def test_shares_split():
    total, shares = compute_shares(
        mode="shares", amount=90_000, participants=["a", "b"], shares={"a": 2, "b": 1}
    )
    assert (total, shares) == (90_000, {"a": 60_000, "b": 30_000})


def test_exact_split_must_match_amount():
    with pytest.raises(SplitError, match="add up to Rp90,000, not Rp100,000"):
        compute_shares(
            mode="exact", amount=100_000, participants=["a", "b"], exact={"a": 50_000, "b": 40_000}
        )


def test_items_split_by_portions_with_tax_and_service_in_proportion():
    items = [
        Item("Gudeg komplit", 30_000, 2, {"a": 1, "b": 1}),
        Item("Es teh", 5_000, 3, {"a": 2, "c": 1}),
    ]
    total, shares = compute_shares(
        mode="items", amount=0, participants=[], items=items, tax=7_500, service=0
    )
    # Subtotals: a 40,000, b 30,000, c 5,000 = 75,000. Tax 10% follows them.
    assert total == 82_500
    assert shares == {"a": 44_000, "b": 33_000, "c": 5_500}


def test_items_split_with_discount():
    total, shares = compute_shares(
        mode="items", amount=0, participants=[], items=[Item("Pizza", 100_000, 1, {"a": 1, "b": 1})],
        discount=20_000,
    )  # fmt: skip
    assert (total, shares) == (80_000, {"a": 40_000, "b": 40_000})


def test_items_need_someone_assigned():
    with pytest.raises(SplitError, match="Choose who had Kopi"):
        compute_shares(mode="items", amount=0, participants=[], items=[Item("Kopi", 20_000, 1)])


def test_net_balances_count_confirmed_transfers():
    expenses = [
        {
            "paidBy": "a",
            "amountIdr": 90_000,
            "computedShares": {"a": 30_000, "b": 30_000, "c": 30_000},
        }
    ]
    assert net_balances(expenses) == {"a": 60_000, "b": -30_000, "c": -30_000}
    confirmed = [{"from": "b", "to": "a", "amountIdr": 30_000}]
    assert net_balances(expenses, confirmed) == {"a": 30_000, "b": 0, "c": -30_000}


def apply(balances: dict[str, int], transfers) -> dict[str, int]:
    result = dict(balances)
    for payer, payee, amount in transfers:
        assert amount > 0
        result[payer] += amount
        result[payee] -= amount
    return result


def test_simplify_beats_largest_first_greedy():
    balances = {"a": 5, "b": 4, "c": -4, "d": -3, "e": -2}
    # Greedy over everyone needs 4 transfers; pairing b with c first needs only 3.
    assert len(_settle_group(list(balances.items()))) == 4
    transfers = simplify(balances)
    assert len(transfers) == 3
    assert set(apply(balances, transfers).values()) == {0}


def test_simplify_random_balances_always_clear():
    rng = random.Random(7)
    for _ in range(200):
        people = [f"u{i}" for i in range(rng.randint(1, 8))]
        amounts = [rng.randint(-9, 9) * 10_000 for _ in people[:-1]]
        balances = dict(zip(people, [*amounts, -sum(amounts)], strict=True))
        transfers = simplify(balances)
        assert set(apply(balances, transfers).values()) <= {0}
        assert len(transfers) <= max(0, sum(1 for v in balances.values() if v) - 1)


def test_simplify_rejects_unbalanced_input():
    with pytest.raises(ValueError):
        simplify({"a": 10, "b": -5})
