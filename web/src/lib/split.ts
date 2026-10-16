// Live preview of how one expense splits, mirroring api/travelin/money/split.py.
// The API recomputes on save; its numbers are the ones that count.
import type { ExpenseItem, SplitMode } from './types'

export class SplitError extends Error {}

/** Whole-rupiah shares in proportion to `weights` that add up exactly to `total`. */
export function largestRemainder(
  total: number,
  weights: Record<string, number>,
): Record<string, number> {
  const positive = Object.entries(weights).filter(([, weight]) => weight > 0)
  const weightSum = positive.reduce((sum, [, weight]) => sum + weight, 0)
  if (weightSum === 0) throw new SplitError('Nobody is assigned to pay for this.')
  if (total < 0) {
    return Object.fromEntries(
      Object.entries(largestRemainder(-total, weights)).map(([key, share]) => [key, -share]),
    )
  }
  const shares: Record<string, number> = {}
  const remainders: [string, number][] = []
  for (const [key, weight] of positive) {
    shares[key] = Math.floor((total * weight) / weightSum)
    remainders.push([key, (total * weight) % weightSum])
  }
  let leftover = total - Object.values(shares).reduce((sum, share) => sum + share, 0)
  remainders.sort(([keyA, a], [keyB, b]) => b - a || (keyA < keyB ? -1 : 1))
  for (const [key] of remainders) {
    if (leftover-- <= 0) break
    shares[key] += 1
  }
  return shares
}

export interface SplitInput {
  mode: SplitMode
  amount: number
  participants: string[]
  shares: Record<string, number>
  exact: Record<string, number>
  items: ExpenseItem[]
  tax: number
  service: number
  discount: number
}

/** [total, uid -> share]. Throws SplitError with a message for the user. */
export function computeShares(input: SplitInput): [number, Record<string, number>] {
  if (input.mode === 'items') return splitItems(input)
  if (input.amount <= 0) throw new SplitError('Enter an amount above zero.')
  if (input.participants.length === 0) throw new SplitError('Choose who this expense is for.')

  if (input.mode === 'equal') {
    const weights = Object.fromEntries(input.participants.map((uid) => [uid, 1]))
    return [input.amount, largestRemainder(input.amount, weights)]
  }
  if (input.mode === 'shares') {
    const weights = Object.fromEntries(
      input.participants.map((uid) => [uid, input.shares[uid] ?? 0]),
    )
    return [input.amount, largestRemainder(input.amount, weights)]
  }
  const amounts = Object.fromEntries(input.participants.map((uid) => [uid, input.exact[uid] ?? 0]))
  const entered = Object.values(amounts).reduce((sum, value) => sum + value, 0)
  if (entered !== input.amount) {
    throw new SplitError(
      `The amounts add up to Rp${entered.toLocaleString('id-ID')}, not Rp${input.amount.toLocaleString('id-ID')}.`,
    )
  }
  return [input.amount, amounts]
}

function splitItems(input: SplitInput): [number, Record<string, number>] {
  if (input.items.length === 0) throw new SplitError('Add at least one item.')
  const perPerson: Record<string, number> = {}
  for (const item of input.items) {
    const portions = Object.fromEntries(Object.entries(item.portions).filter(([, n]) => n > 0))
    if (Object.keys(portions).length === 0)
      throw new SplitError(`Choose who had ${item.name || 'each item'}.`)
    for (const [uid, share] of Object.entries(
      largestRemainder(item.unitPriceIdr * item.qty, portions),
    )) {
      perPerson[uid] = (perPerson[uid] ?? 0) + share
    }
  }
  const subtotal = Object.values(perPerson).reduce((sum, value) => sum + value, 0)
  if (subtotal <= 0) throw new SplitError('The items add up to zero.')
  const extras = input.tax + input.service - input.discount
  if (extras !== 0) {
    for (const [uid, share] of Object.entries(largestRemainder(extras, perPerson))) {
      perPerson[uid] += share
    }
  }
  const total = subtotal + extras
  if (total <= 0) throw new SplitError('The discount is larger than the bill.')
  return [total, perPerson]
}
