import { describe, expect, it } from 'vitest';
import { calculateDocument, calculateLine, formatMoney, parseMoney } from '@/lib/documents/money';
import { createDocument } from '@/lib/documents/factory';

describe('money handling', () => {
  it('parses currency values into integer minor units', () => {
    expect(parseMoney('1,234.56', 'USD')).toBe(123456);
    expect(parseMoney('-12.35', 'USD')).toBe(-1235);
    expect(parseMoney('125', 'JPY')).toBe(125);
  });

  it('calculates fractional quantities, discounts and tax with explicit rounding', () => {
    const result = calculateLine({ id: '1', description: 'Hours', quantity: '2.5', unit: 'hour', unitPriceMinor: 1999, discountBps: 1000, taxBps: 825 });
    expect(result.grossMinor).toBe(4998);
    expect(result.discountMinor).toBe(500);
    expect(result.taxableMinor).toBe(4498);
    expect(result.taxMinor).toBe(371);
    expect(result.totalMinor).toBe(4869);
  });

  it('includes shipping, adjustments and deposits in document totals', () => {
    const document = createDocument('invoice');
    document.lineItems = [{ id: '1', description: 'Service', quantity: '1', unit: 'item', unitPriceMinor: 10000, discountBps: 0, taxBps: 500 }];
    document.shippingMinor = 250;
    document.adjustmentMinor = -100;
    document.depositMinor = 3000;
    expect(calculateDocument(document)).toMatchObject({ subtotalMinor: 10000, taxMinor: 500, totalMinor: 10650, balanceDueMinor: 7650 });
  });

  it('formats currency using the selected currency rules', () => {
    expect(formatMoney(123456, 'USD')).toContain('1,234.56');
    expect(formatMoney(1234, 'JPY')).toContain('1,234');
  });
});
