"""Who pays whom: net balances, then the fewest transfers that clear them."""

from collections.abc import Iterable, Mapping
from typing import Any

Transfer = tuple[str, str, int]  # (from uid, to uid, amount)


def net_balances(
    expenses: Iterable[Mapping[str, Any]], confirmed: Iterable[Mapping[str, Any]] = ()
) -> dict[str, int]:
    """Positive: the person is owed money. Negative: they owe.

    Confirmed transfers from an earlier round already moved money, so they count.
    """
    balances: dict[str, int] = {}
    for expense in expenses:
        payer = expense["paidBy"]
        balances[payer] = balances.get(payer, 0) + expense["amountIdr"]
        for uid, share in expense["computedShares"].items():
            balances[uid] = balances.get(uid, 0) - share
    for transfer in confirmed:
        balances[transfer["from"]] = balances.get(transfer["from"], 0) + transfer["amountIdr"]
        balances[transfer["to"]] = balances.get(transfer["to"], 0) - transfer["amountIdr"]
    return balances


def _settle_group(members: list[tuple[str, int]]) -> list[Transfer]:
    """Clears one zero-sum group with len - 1 transfers, largest debts first."""
    debtors = sorted(((-amount, uid) for uid, amount in members if amount < 0), reverse=True)
    creditors = sorted(((amount, uid) for uid, amount in members if amount > 0), reverse=True)
    debtors = [[amount, uid] for amount, uid in debtors]
    creditors = [[amount, uid] for amount, uid in creditors]
    transfers: list[Transfer] = []
    while debtors and creditors:
        debt, creditor = debtors[0], creditors[0]
        paid = min(debt[0], creditor[0])
        transfers.append((debt[1], creditor[1], paid))
        debt[0] -= paid
        creditor[0] -= paid
        if debt[0] == 0:
            debtors.pop(0)
        if creditor[0] == 0:
            creditors.pop(0)
        debtors.sort(key=lambda entry: (-entry[0], entry[1]))
        creditors.sort(key=lambda entry: (-entry[0], entry[1]))
    return transfers


def simplify(balances: Mapping[str, int]) -> list[Transfer]:
    """The minimum number of transfers that brings every balance to zero.

    With n people who are owed or owe, the minimum is n minus the largest number of
    groups whose balances each sum to zero. A bitmask DP finds those groups exactly;
    it is fine for a squad of up to 8 (256 subsets).
    """
    people = sorted((uid, amount) for uid, amount in balances.items() if amount != 0)
    if sum(amount for _, amount in people) != 0:
        raise ValueError("Balances must sum to zero.")
    n = len(people)
    if n == 0:
        return []

    full = (1 << n) - 1
    totals = [0] * (full + 1)
    for mask in range(1, full + 1):
        lowest = (mask & -mask).bit_length() - 1
        totals[mask] = totals[mask & (mask - 1)] + people[lowest][1]

    # groups[mask]: most zero-sum groups the people in `mask` can be split into.
    groups = [0] * (full + 1)
    for mask in range(1, full + 1):
        best = max(groups[mask & ~(1 << i)] for i in range(n) if mask >> i & 1)
        groups[mask] = best + (1 if totals[mask] == 0 else 0)

    # Walk back down from everyone; each time the remainder sums to zero again,
    # the people removed since the last zero point form one group.
    transfers: list[Transfer] = []
    mask, removed = full, []
    while mask:
        bonus = 1 if totals[mask] == 0 else 0
        i = next(
            i
            for i in range(n)
            if mask >> i & 1 and groups[mask & ~(1 << i)] + bonus == groups[mask]
        )
        removed.append(people[i])
        mask &= ~(1 << i)
        if totals[mask] == 0:
            transfers.extend(_settle_group(removed))
            removed = []
    return transfers


def payment_status(member_uids: Iterable[str], transfers: Iterable[Mapping[str, Any]]) -> dict:
    """Per member, for the Home screen: "unpaid" while they still have a transfer to send,
    "waiting" while any transfer of theirs awaits confirmation, otherwise "settled"."""
    transfers = list(transfers)
    status = {}
    for uid in member_uids:
        mine = [t for t in transfers if uid in (t["from"], t["to"])]
        if any(t["from"] == uid and t["status"] == "unpaid" for t in mine):
            status[uid] = "unpaid"
        elif any(t["status"] != "confirmed" for t in mine):
            status[uid] = "waiting"
        else:
            status[uid] = "settled"
    return status
