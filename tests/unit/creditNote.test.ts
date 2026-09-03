import { describe, expect, it } from 'vitest';
import { canConvert, convertDocument } from '@/lib/documents/conversions';
import { createDocument, defaultNumbering, documentLabels } from '@/lib/documents/factory';
import { calculateDocument } from '@/lib/documents/money';
import { normalizeNumbering } from '@/lib/documents/numbering';
import { normalizeWorkspaceRecords } from '@/lib/storage/database';
import type { DocumentKind, DocumentRecord } from '@/lib/documents/types';

const returned = (kind: DocumentKind): DocumentRecord => {
  const document = createDocument(kind);
  document.lineItems = [
    { id: 'a', description: 'Oak dining chair, returned', quantity: '2', unit: 'item', unitPriceMinor: 18500, taxBps: 825, discountBps: 0 },
    { id: 'b', description: 'Delivery surcharge, refunded', quantity: '1', unit: 'item', unitPriceMinor: 4500, taxBps: 825, discountBps: 0 },
  ];
  return document;
};

describe('credit notes', () => {
  it('is a document kind of its own, not an invoice with a heading', () => {
    expect(documentLabels.creditNote).toBe('Credit Note');
    expect(defaultNumbering().prefixes.creditNote).toBe('CN-');
    expect(normalizeNumbering({}).nextNumbers.creditNote).toBe(1001);
  });

  it('presents the total as money going back', () => {
    const totals = calculateDocument(returned('creditNote'));
    expect(totals.totalMinor).toBe(44924);
    expect(totals.creditedMinor).toBe(-44924);
  });

  it('matches the worked partial credit published on the page', () => {
    // $30.53 on the chairs plus $3.71 on delivery. Tax is rounded per line and
    // then summed, so the page has to agree with that order, not with 8.25% of
    // the subtotal computed in one step.
    const totals = calculateDocument(returned('creditNote'));
    expect(totals.subtotalMinor).toBe(41500);
    expect(totals.taxMinor).toBe(3424);
  });

  it('leaves the credit sign off every other kind', () => {
    expect(calculateDocument(returned('invoice')).creditedMinor).toBe(0);
    expect(calculateDocument(returned('receipt')).creditedMinor).toBe(0);
  });

  it('credits an invoice and points back at it by number', () => {
    const invoice = returned('invoice');
    invoice.number = 'INV-2026-0311';
    expect(canConvert('invoice', 'creditNote')).toBe(true);
    const credit = convertDocument(invoice, 'creditNote', defaultNumbering());
    expect(credit.kind).toBe('creditNote');
    expect(credit.reference).toBe('INV-2026-0311');
    expect(credit.number).toBe('CN-1001');
    // The invoice it reverses is untouched: that is the point of a credit note.
    expect(invoice.number).toBe('INV-2026-0311');
    expect(invoice.kind).toBe('invoice');
  });

  it('cannot be created from documents that were never billed', () => {
    for (const from of ['quotation', 'estimate', 'proforma'] as const) {
      expect(canConvert(from, 'creditNote')).toBe(false);
    }
  });

  it('has no future payment date, because nothing is being asked for', () => {
    const credit = createDocument('creditNote');
    expect(credit.dueDate).toBe(credit.issueDate);
  });

  it('survives a save and reload, including the reason', () => {
    const credit = returned('creditNote');
    credit.creditReason = 'Goods returned';
    const { documents } = normalizeWorkspaceRecords({ documents: [credit] });
    expect(documents[0].kind).toBe('creditNote');
    expect(documents[0].creditReason).toBe('Goods returned');
  });

  it('reads back a document saved before credit notes existed', () => {
    const legacy = { ...createDocument('invoice') } as Record<string, unknown>;
    delete legacy.creditReason;
    const { documents } = normalizeWorkspaceRecords({ documents: [legacy] });
    expect(documents[0].creditReason).toBe('');
  });
});
