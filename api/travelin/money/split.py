"""Who owes what for one expense. All amounts are whole rupiah; shares always add up exactly."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

SplitMode = Literal["equal", "shares", "exact", "items"]


class SplitError(ValueError):
    """An expense that can't be split as entered; the message is shown to the user."""


@dataclass
class Item:
    name: str
    unit_price: int
    qty: int
    portions: dict[str, int] = field(default_factory=dict)  # uid -> portions eaten


def largest_remainder(total: int, weights: Mapping[str, int]) -> dict[str, int]:
    """Splits `total` in proportion to `weights` into whole rupiah that sum to `total`.

    Each key gets the floor of its exact share; the leftover rupiah go to the largest
    fractional parts (ties broken by key, so the result is deterministic).
    """
    weights = {key: weight for key, weight in weights.items() if weight > 0}
    weight_sum = sum(weights.values())
    if weight_sum == 0:
        raise SplitError("Nobody is assigned to pay for this.")
    if total < 0:
        return {key: -share for key, share in largest_remainder(-total, weights).items()}

    exact = {key: Fraction(total * weight, weight_sum) for key, weight in weights.items()}
    shares = {key: int(value) for key, value in exact.items()}
    leftover = total - sum(shares.values())
    by_remainder = sorted(exact, key=lambda key: (-(exact[key] - shares[key]), key))
    for key in by_remainder[:leftover]:
        shares[key] += 1
    return shares


def compute_shares(
    *,
    mode: SplitMode,
    amount: int,
    participants: list[str],
    shares: Mapping[str, int] | None = None,
    exact: Mapping[str, int] | None = None,
    items: list[Item] | None = None,
    tax: int = 0,
    service: int = 0,
    discount: int = 0,
) -> tuple[int, dict[str, int]]:
    """Returns (total amount, uid -> share). For receipts the total comes from the items."""
    if mode == "items":
        return _split_items(items or [], tax, service, discount)
    if amount <= 0:
        raise SplitError("Enter an amount above zero.")
    if not participants:
        raise SplitError("Choose who this expense is for.")

    if mode == "equal":
        result = largest_remainder(amount, dict.fromkeys(participants, 1))
    elif mode == "shares":
        weights = {uid: (shares or {}).get(uid, 0) for uid in participants}
        if any(weight < 0 for weight in weights.values()):
            raise SplitError("Shares can't be negative.")
        result = largest_remainder(amount, weights)
    elif mode == "exact":
        amounts = {uid: (exact or {}).get(uid, 0) for uid in participants}
        if any(value < 0 for value in amounts.values()):
            raise SplitError("Amounts can't be negative.")
        entered = sum(amounts.values())
        if entered != amount:
            raise SplitError(f"The amounts add up to Rp{entered:,}, not Rp{amount:,}.")
        result = amounts
    else:
        raise SplitError(f"Unknown split mode {mode!r}.")
    return amount, {uid: share for uid, share in result.items() if share != 0}


def _split_items(
    items: list[Item], tax: int, service: int, discount: int
) -> tuple[int, dict[str, int]]:
    if not items:
        raise SplitError("Add at least one item.")
    per_person: dict[str, int] = {}
    for item in items:
        if item.unit_price < 0 or item.qty < 1:
            raise SplitError(f"Check the price and quantity of {item.name}.")
        portions = {uid: count for uid, count in item.portions.items() if count > 0}
        if not portions:
            raise SplitError(f"Choose who had {item.name}.")
        for uid, share in largest_remainder(item.unit_price * item.qty, portions).items():
            per_person[uid] = per_person.get(uid, 0) + share

    subtotal = sum(per_person.values())
    if subtotal <= 0:
        raise SplitError("The items add up to zero.")
    # Tax, service, and discount follow what each person ordered.
    extras = tax + service - discount
    for uid, share in largest_remainder(extras, per_person).items() if extras else []:
        per_person[uid] += share
    total = subtotal + extras
    if total <= 0:
        raise SplitError("The discount is larger than the bill.")
    return total, {uid: share for uid, share in per_person.items() if share != 0}
