import { describe, expect, it } from 'vitest';
import { defaultNumbering } from '@/lib/documents/factory';
import { nextDocumentNumber, normalizeNumbering } from '@/lib/documents/numbering';

describe('document numbering', () => {
  it('allocates and increments independently by document kind', () => {
    const starting = defaultNumbering();
    const allocated = nextDocumentNumber(starting, 'invoice');
    expect(allocated.number).toBe('INV-1001');
    expect(allocated.settings.nextNumbers.invoice).toBe(1002);
    expect(allocated.settings.nextNumbers.quotation).toBe(1001);
    expect(starting.nextNumbers.invoice).toBe(1001);
  });

  it('safely fills settings introduced in a later schema', () => {
    const normalized = normalizeNumbering({ prefixes: { invoice: 'CUSTOM-' } } as never);
    expect(normalized.prefixes.invoice).toBe('CUSTOM-');
    expect(normalized.prefixes.receipt).toBe('REC-');
  });
});
