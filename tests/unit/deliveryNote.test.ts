import { describe, expect, it } from 'vitest';
import { createDocument, defaultNumbering, documentLabels, emptyLineItem } from '@/lib/documents/factory';
import { calculateDocument, formatUnits } from '@/lib/documents/money';
import { normalizeWorkspaceRecords } from '@/lib/storage/database';
import type { DocumentRecord, LineItem } from '@/lib/documents/types';

const shipped = (over: Partial<LineItem> = {}): LineItem => ({
  id: crypto.randomUUID(), description: 'Item', quantityOrdered: '1', quantity: '1',
  unit: 'item', unitPriceMinor: 18500, taxBps: 825, discountBps: 0, ...over,
});

const partial = (): DocumentRecord => {
  const document = createDocument('deliveryNote');
  document.lineItems = [
    shipped({ description: 'Oak dining chair', quantityOrdered: '6', quantity: '4' }),
    shipped({ description: 'Dining table', quantityOrdered: '1', quantity: '1' }),
    shipped({ description: 'Felt protectors', quantityOrdered: '2', quantity: '3' }),
  ];
  return document;
};

describe('delivery notes', () => {
  it('is its own kind with its own numbering series', () => {
    expect(documentLabels.deliveryNote).toBe('Delivery Note');
    expect(defaultNumbering().prefixes.deliveryNote).toBe('DN-');
  });

  it('totals units rather than money', () => {
    const totals = calculateDocument(partial());
    expect(totals.unitsOrderedMilli).toBe(9_000);
    expect(totals.unitsDeliveredMilli).toBe(8_000);
    expect(formatUnits(totals.unitsDeliveredMilli)).toBe('8');
  });

  it('states the back-order rather than leaving it to be worked out', () => {
    expect(calculateDocument(partial()).unitsBackOrderedMilli).toBe(1_000);
  });

  it('shows over-delivery as a negative back-order instead of hiding it', () => {
    const document = createDocument('deliveryNote');
    document.lineItems = [shipped({ quantityOrdered: '2', quantity: '5' })];
    expect(calculateDocument(document).unitsBackOrderedMilli).toBe(-3_000);
  });

  it('treats a line with no ordered quantity as delivered, not as an over-delivery', () => {
    const document = createDocument('deliveryNote');
    document.lineItems = [shipped({ quantityOrdered: undefined, quantity: '4' })];
    const totals = calculateDocument(document);
    expect(totals.unitsOrderedMilli).toBe(4_000);
    expect(totals.unitsBackOrderedMilli).toBe(0);
  });

  it('starts a line with an ordered quantity, and only on a delivery note', () => {
    expect(emptyLineItem(0, 'deliveryNote').quantityOrdered).toBe('1');
    expect(emptyLineItem(0, 'invoice').quantityOrdered).toBeUndefined();
  });

  it('gives every other kind no unit counts at all', () => {
    for (const kind of ['invoice', 'receipt', 'creditNote', 'timesheet'] as const) {
      const document = partial();
      document.kind = kind;
      const totals = calculateDocument(document);
      expect(totals.unitsOrderedMilli, kind).toBe(0);
      expect(totals.unitsDeliveredMilli, kind).toBe(0);
    }
  });

  it('has its own delivery address, separate from the billing address', () => {
    const document = createDocument('deliveryNote');
    expect(document.deliveryAddress).toBeDefined();
    expect(createDocument('invoice').deliveryAddress).toBeUndefined();
  });

  it('asks for nothing later, so it carries no future payment date', () => {
    const note = createDocument('deliveryNote');
    expect(note.dueDate).toBe(note.issueDate);
  });

  it('survives a save and reload with its shipment details', () => {
    const document = partial();
    document.carrier = 'Own vehicle';
    document.consignmentRef = 'CON-9912';
    document.deliveryAddress = { ...document.deliveryAddress!, line1: 'Bay 4, Maple Street' };
    const { documents } = normalizeWorkspaceRecords({ documents: [document] });
    expect(documents[0].carrier).toBe('Own vehicle');
    expect(documents[0].consignmentRef).toBe('CON-9912');
    expect(documents[0].deliveryAddress?.line1).toBe('Bay 4, Maple Street');
    expect(documents[0].lineItems[0].quantityOrdered).toBe('6');
  });

  it('reads back a document saved before delivery notes existed', () => {
    const legacy = { ...createDocument('invoice') } as Record<string, unknown>;
    delete legacy.carrier;
    delete legacy.consignmentRef;
    delete legacy.deliveryAddress;
    const { documents } = normalizeWorkspaceRecords({ documents: [legacy] });
    expect(documents[0].carrier).toBe('');
    expect(documents[0].deliveryAddress).toBeUndefined();
  });
});
