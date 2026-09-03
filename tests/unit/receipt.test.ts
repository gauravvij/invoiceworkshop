import { describe, expect, it } from 'vitest';
import { convertDocument } from '@/lib/documents/conversions';
import { createDocument, defaultNumbering } from '@/lib/documents/factory';
import { calculateDocument } from '@/lib/documents/money';
import { normalizeWorkspaceRecords } from '@/lib/storage/database';
import type { DocumentRecord } from '@/lib/documents/types';

const priced = (kind: DocumentRecord['kind']) => {
  const document = createDocument(kind);
  document.lineItems = [
    { id: 'a', description: 'Kitchen fit, labour', quantity: '38', unit: 'hour', unitPriceMinor: 6200, taxBps: 825, discountBps: 0 },
    { id: 'b', description: 'Worktop and fittings', quantity: '1', unit: 'item', unitPriceMinor: 118000, taxBps: 825, discountBps: 0 },
  ];
  return document;
};

describe('receipts', () => {
  it('starts paid, because a receipt exists only once money has arrived', () => {
    expect(createDocument('receipt').status).toBe('paid');
    expect(createDocument('invoice').status).toBe('draft');
  });

  it('acknowledges the full total when no amount is entered', () => {
    const totals = calculateDocument(priced('receipt'));
    expect(totals.totalMinor).toBe(382772);
    expect(totals.amountPaidMinor).toBe(382772);
    expect(totals.balanceRemainingMinor).toBe(0);
  });

  it('states the balance left after a part payment', () => {
    const receipt = priced('receipt');
    receipt.amountPaidMinor = 200000;
    const totals = calculateDocument(receipt);
    expect(totals.amountPaidMinor).toBe(200000);
    expect(totals.balanceRemainingMinor).toBe(182772);
  });

  it('reports an overpayment rather than clamping it away', () => {
    const receipt = priced('receipt');
    receipt.amountPaidMinor = 400000;
    expect(calculateDocument(receipt).balanceRemainingMinor).toBe(-17228);
  });

  it('matches the worked example published on the page, line by line', () => {
    // The page states $194.37 and $97.35 adding to $291.72. Tax is rounded per
    // line and then summed, so the page has to agree with that order.
    const totals = calculateDocument(priced('receipt'));
    expect(totals.taxMinor).toBe(29172);
    expect(totals.subtotalMinor).toBe(353600);
  });

  it('leaves every other document kind free of receipt arithmetic', () => {
    const totals = calculateDocument(priced('invoice'));
    expect(totals.amountPaidMinor).toBe(0);
    expect(totals.balanceRemainingMinor).toBe(0);
  });

  it('receipts an invoice in full and carries its number as the reference', () => {
    const invoice = priced('invoice');
    invoice.number = 'INV-2026-0208';
    const receipt = convertDocument(invoice, 'receipt', defaultNumbering());
    expect(receipt.amountPaidMinor).toBe(382772);
    expect(receipt.reference).toBe('INV-2026-0208');
    expect(receipt.status).toBe('paid');
    expect(calculateDocument(receipt).balanceRemainingMinor).toBe(0);
  });

  it('does not overwrite a reference the invoice already had', () => {
    const invoice = priced('invoice');
    invoice.reference = 'PO-4417';
    expect(convertDocument(invoice, 'receipt', defaultNumbering()).reference).toBe('PO-4417');
  });

  it('reads back a document saved before receipts had payment fields', () => {
    const legacy = { ...createDocument('receipt') } as Record<string, unknown>;
    delete legacy.paymentMethod;
    delete legacy.amountPaidMinor;
    const { documents } = normalizeWorkspaceRecords({ documents: [legacy] });
    expect(documents).toHaveLength(1);
    expect(documents[0].paymentMethod).toBe('');
    expect(documents[0].amountPaidMinor).toBe(0);
  });

  it('keeps the payment method through a save and reload', () => {
    const receipt = priced('receipt');
    receipt.paymentMethod = 'Bank transfer';
    const { documents } = normalizeWorkspaceRecords({ documents: [receipt] });
    expect(documents[0].paymentMethod).toBe('Bank transfer');
  });
});
