import { describe, expect, it } from 'vitest';
import { convertDocument } from '@/lib/documents/conversions';
import { createDocument, defaultNumbering } from '@/lib/documents/factory';

describe('document conversions', () => {
  it.each([
    ['quotation', 'invoice'], ['estimate', 'workOrder'], ['estimate', 'invoice'],
    ['workOrder', 'invoice'], ['proforma', 'invoice'], ['invoice', 'receipt'],
  ] as const)('converts %s to %s while preserving relevant data', (from, to) => {
    const source = createDocument(from);
    source.client.name = 'Northwind LLC';
    source.lineItems[0].description = 'Site visit';
    source.reference = 'PROJECT-7';
    const result = convertDocument(source, to, defaultNumbering());
    expect(result.kind).toBe(to);
    expect(result.id).not.toBe(source.id);
    expect(result.client.name).toBe('Northwind LLC');
    expect(result.lineItems[0].description).toBe('Site visit');
    expect(result.reference).toBe('PROJECT-7');
    expect(result.convertedFrom).toMatchObject({ id: source.id, kind: from });
  });

  it('rejects invalid conversion paths', () => {
    expect(() => convertDocument(createDocument('purchaseOrder'), 'invoice', defaultNumbering())).toThrow(/cannot be converted/i);
  });
});
