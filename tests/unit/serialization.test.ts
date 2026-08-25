import { describe, expect, it } from 'vitest';
import { createDocument } from '@/lib/documents/factory';
import { normalizeWorkspaceRecords } from '@/lib/storage/database';

describe('storage serialization', () => {
  it('round-trips a complete document without losing integer money values', () => {
    const original = createDocument('invoice');
    original.business.name = 'Example & Co.';
    original.client.name = 'Customer';
    original.lineItems[0].unitPriceMinor = 1099;
    original.lineItems[0].quantity = '1.25';
    const restored = JSON.parse(JSON.stringify(original));
    expect(restored).toEqual(original);
    expect(Number.isInteger(restored.lineItems[0].unitPriceMinor)).toBe(true);
  });

  it('recovers valid records and ignores malformed local entries', () => {
    const valid = createDocument('invoice');
    valid.id = 'legacy-document';
    valid.business.name = 'Legacy Workshop';
    const workspace = normalizeWorkspaceRecords({
      profiles: [{ id: 'default-business', name: 'Legacy Workshop', address: null }],
      clients: [null, { id: '', name: 'broken' }],
      catalogItems: [{ id: 'catalog-1', name: 'Consulting', unitPriceMinor: 'invalid' }],
      documents: [null, { id: 'broken', kind: 'unknown' }, { ...valid, updatedAt: null, lineItems: [null, valid.lineItems[0]] }],
      settings: [{ id: 'numbering', prefixes: null, nextNumbers: { invoice: 'invalid' } }],
    });

    expect(workspace.profile.name).toBe('Legacy Workshop');
    expect(workspace.documents).toHaveLength(1);
    expect(workspace.documents[0].id).toBe('legacy-document');
    expect(workspace.documents[0].lineItems).toHaveLength(1);
    expect(workspace.catalogItems[0].unitPriceMinor).toBe(0);
    expect(workspace.numbering.nextNumbers.invoice).toBe(1001);
  });
});
