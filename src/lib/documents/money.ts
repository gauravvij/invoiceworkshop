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
}

export const calculateDocument = (document: DocumentRecord): DocumentTotals => {
  const lines = document.lineItems.map(calculateLine);
  const subtotalMinor = lines.reduce((sum, line) => sum + line.grossMinor, 0);
  const discountMinor = lines.reduce((sum, line) => sum + line.discountMinor, 0);
  const taxableMinor = lines.reduce((sum, line) => sum + line.taxableMinor, 0);
  const taxMinor = lines.reduce((sum, line) => sum + line.taxMinor, 0);
  const totalMinor = taxableMinor + taxMinor + document.shippingMinor + document.adjustmentMinor;
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
  };
};
