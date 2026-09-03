import type { DocumentRecord, LineItem } from './types';

const currencyDigits = (currency: string): number => {
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
    }).resolvedOptions().maximumFractionDigits ?? 2;
  } catch {
    return 2;
  }
};

export const parseMoney = (value: string, currency: string): number => {
  const digits = currencyDigits(currency);
  const normalized = value.replace(/[^0-9.-]/g, '');
  if (!normalized || normalized === '-' || normalized === '.') return 0;
  const negative = normalized.startsWith('-');
  const unsigned = normalized.replace('-', '');
  const [whole = '0', fraction = ''] = unsigned.split('.');
  const factor = 10 ** digits;
  const padded = `${fraction}${'0'.repeat(digits)}`.slice(0, digits);
  const minor = Number.parseInt(whole || '0', 10) * factor + Number.parseInt(padded || '0', 10);
  return negative ? -minor : minor;
};

export const moneyInputValue = (minor: number, currency: string): string => {
  const digits = currencyDigits(currency);
  return (minor / 10 ** digits).toFixed(digits);
};

export const formatMoney = (minor: number, currency: string): string => {
  const digits = currencyDigits(currency);
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(minor / 10 ** digits);
  } catch {
    return `${currency} ${(minor / 10 ** digits).toFixed(digits)}`;
  }
};

const parseQuantityMicros = (quantity: string): bigint => {
  const normalized = quantity.replace(/[^0-9.-]/g, '');
  if (!normalized || normalized === '-' || normalized === '.') return 0n;
  const negative = normalized.startsWith('-');
  const [whole = '0', fraction = ''] = normalized.replace('-', '').split('.');
  const micros = BigInt(whole || '0') * 1_000_000n + BigInt(`${fraction}000000`.slice(0, 6));
  return negative ? -micros : micros;
};

const roundedDivide = (numerator: bigint, denominator: bigint): bigint => {
  if (numerator < 0n) return -roundedDivide(-numerator, denominator);
  return (numerator + denominator / 2n) / denominator;
};

/**
 * Hours on one line, in thousandths. Only quantities booked in hours count: a
 * timesheet may still carry an expense or a fixed-fee line, and adding those
 * into an hours total would make it disagree with the timesheet it came from.
 */
export const hoursMilli = (line: LineItem): number => {
  if (!/^h(ou)?rs?$/i.test(line.unit.trim())) return 0;
  return Number(roundedDivide(parseQuantityMicros(line.quantity), 1_000n));
};

/**
 * Ordered against delivered. A line with no ordered quantity was not on the
 * order at all -- an extra, a replacement -- and counts as delivered without
 * inflating what was supposedly ordered.
 */
export const deliveryCounts = (document: DocumentRecord) => {
  if (document.kind !== 'deliveryNote') {
    return { unitsOrderedMilli: 0, unitsDeliveredMilli: 0, unitsBackOrderedMilli: 0 };
  }
  let ordered = 0n;
  let delivered = 0n;
  for (const line of document.lineItems) {
    const shipped = roundedDivide(parseQuantityMicros(line.quantity), 1_000n);
    const asked = line.quantityOrdered
      ? roundedDivide(parseQuantityMicros(line.quantityOrdered), 1_000n)
      : shipped;
    ordered += asked;
    delivered += shipped;
  }
  return {
    unitsOrderedMilli: Number(ordered),
    unitsDeliveredMilli: Number(delivered),
    // Over-delivery is a real event and shows as a negative back-order rather
    // than being clamped away.
    unitsBackOrderedMilli: Number(ordered - delivered),
  };
};

export const formatUnits = (milli: number): string => {
  const units = milli / 1000;
  return Number.isInteger(units) ? `${units}` : units.toFixed(3).replace(/0+$/, '');
};

export const formatHours = (milli: number): string => {
  const hours = milli / 1000;
  return Number.isInteger(hours) ? `${hours}` : hours.toFixed(2).replace(/0$/, '');
};

export interface LineCalculation {
  grossMinor: number;
  discountMinor: number;
  taxableMinor: number;
  taxMinor: number;
  totalMinor: number;
}

export const calculateLine = (line: LineItem): LineCalculation => {
  const gross = roundedDivide(BigInt(line.unitPriceMinor) * parseQuantityMicros(line.quantity), 1_000_000n);
  const discount = roundedDivide(gross * BigInt(line.discountBps), 10_000n);
  const taxable = gross - discount;
  const tax = roundedDivide(taxable * BigInt(line.taxBps), 10_000n);
  return {
    grossMinor: Number(gross),
    discountMinor: Number(discount),
    taxableMinor: Number(taxable),
    taxMinor: Number(tax),
    totalMinor: Number(taxable + tax),
  };
};

export interface DocumentTotals {
  subtotalMinor: number;
  discountMinor: number;
  taxableMinor: number;
  taxMinor: number;
  shippingMinor: number;
  adjustmentMinor: number;
  depositMinor: number;
  totalMinor: number;
  balanceDueMinor: number;
  /**
   * A receipt's own arithmetic. `amountPaidMinor` is what the receipt says was
   * received; `balanceRemainingMinor` is what is still owed after it, which is
   * the figure a part-payment receipt exists to state and the one a customer
   * will check. Zero on every other document kind.
   */
  amountPaidMinor: number;
  balanceRemainingMinor: number;
  /**
   * What a credit note gives back, as a negative number. The line items stay
   * positive -- you list what is being credited, not a column of minus signs --
   * and the sign is applied once, here, so the preview, the PDF and any future
   * reader all get it from the same place instead of each inverting their own.
   * Zero on every other kind.
   */
  creditedMinor: number;
  /**
   * Total hours on a timesheet, in thousandths of an hour so quarter-hours are
   * exact. A timesheet is checked twice -- once against the money and once
   * against the hours -- and the two have to reconcile, which they cannot if
   * the hours are re-derived from a rounded money figure.
   */
  totalHoursMilli: number;
  /**
   * A delivery note's totals are counts, not money. Ordered, delivered and the
   * difference, in thousandths so a part-unit quantity survives. Zero on every
   * other kind, and a delivery note's money totals are never shown: a document
   * that states a price is a document the recipient may be asked to pay.
   */
  unitsOrderedMilli: number;
  unitsDeliveredMilli: number;
  unitsBackOrderedMilli: number;
}

export const calculateDocument = (document: DocumentRecord): DocumentTotals => {
  const lines = document.lineItems.map(calculateLine);
  const subtotalMinor = lines.reduce((sum, line) => sum + line.grossMinor, 0);
  const discountMinor = lines.reduce((sum, line) => sum + line.discountMinor, 0);
  const taxableMinor = lines.reduce((sum, line) => sum + line.taxableMinor, 0);
  const taxMinor = lines.reduce((sum, line) => sum + line.taxMinor, 0);
  const totalMinor = taxableMinor + taxMinor + document.shippingMinor + document.adjustmentMinor;
  // A receipt with nothing entered acknowledges the whole total: that is the
  // common case, and asking someone to retype the figure they can already see
  // is how a receipt ends up disagreeing with its own line items.
  const amountPaidMinor = document.kind === 'receipt'
    ? (document.amountPaidMinor || totalMinor)
    : 0;
  return {
    subtotalMinor,
    discountMinor,
    taxableMinor,
    taxMinor,
    shippingMinor: document.shippingMinor,
    adjustmentMinor: document.adjustmentMinor,
    depositMinor: document.depositMinor,
    totalMinor,
    balanceDueMinor: Math.max(0, totalMinor - document.depositMinor),
    amountPaidMinor,
    // Overpayment is a real thing and clamping it to zero would hide it.
    balanceRemainingMinor: document.kind === 'receipt' ? totalMinor - amountPaidMinor : 0,
    creditedMinor: document.kind === 'creditNote' ? -totalMinor : 0,
    totalHoursMilli: document.kind === 'timesheet'
      ? document.lineItems.reduce((sum, line) => sum + hoursMilli(line), 0)
      : 0,
    ...deliveryCounts(document),
  };
};
