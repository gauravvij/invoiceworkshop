import { describe, expect, it } from 'vitest';
import { createDocument } from '@/lib/documents/factory';

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
});
