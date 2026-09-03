import { describe, expect, it } from 'vitest';
import { createDocument, defaultNumbering, documentLabels, emptyLineItem } from '@/lib/documents/factory';
import { calculateDocument, formatHours, hoursMilli } from '@/lib/documents/money';
import { normalizeWorkspaceRecords } from '@/lib/storage/database';
import type { DocumentRecord, LineItem } from '@/lib/documents/types';

const entry = (over: Partial<LineItem> = {}): LineItem => ({
  id: crypto.randomUUID(), description: 'Work', serviceDate: '2026-09-01',
  quantity: '1', unit: 'hour', unitPriceMinor: 6000, taxBps: 0, discountBps: 0, ...over,
});

const week = (): DocumentRecord => {
  const document = createDocument('timesheet');
  document.lineItems = [
    entry({ serviceDate: '2026-09-01', quantity: '7.5', description: 'Discovery calls' }),
    entry({ serviceDate: '2026-09-02', quantity: '8', description: 'Schema work' }),
    entry({ serviceDate: '2026-09-03', quantity: '6.25', description: 'Review' }),
  ];
  return document;
};

describe('timesheet invoices', () => {
  it('is its own kind with its own numbering series', () => {
    expect(documentLabels.timesheet).toBe('Timesheet Invoice');
    expect(defaultNumbering().prefixes.timesheet).toBe('TS-');
  });

  it('starts a line as a dated hour rather than one item', () => {
    const line = emptyLineItem(0, 'timesheet');
    expect(line.unit).toBe('hour');
    expect(line.serviceDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(emptyLineItem(0, 'invoice').serviceDate).toBeUndefined();
    expect(emptyLineItem(0, 'invoice').unit).toBe('item');
  });

  it('totals hours exactly at quarter-hour precision', () => {
    const totals = calculateDocument(week());
    expect(totals.totalHoursMilli).toBe(21_750);
    expect(formatHours(totals.totalHoursMilli)).toBe('21.75');
  });

  it('reconciles hours against the money', () => {
    const totals = calculateDocument(week());
    // 21.75 hours at $60.00 is $1,305.00, and both figures come off the same lines.
    expect(totals.subtotalMinor).toBe(130_500);
    expect(totals.totalHoursMilli / 1000 * 6000).toBe(totals.subtotalMinor);
  });

  it('counts only lines actually booked in hours', () => {
    const document = week();
    document.lineItems.push(entry({ unit: 'item', quantity: '1', description: 'Travel expense', unitPriceMinor: 4500 }));
    const totals = calculateDocument(document);
    // The expense is billed but is not time, so the hours total does not move.
    expect(totals.totalHoursMilli).toBe(21_750);
    expect(totals.subtotalMinor).toBe(135_000);
  });

  it('accepts the singular and plural spellings a person actually types', () => {
    for (const unit of ['hour', 'hours', 'hr', 'hrs', 'Hours', ' hour ']) {
      expect(hoursMilli(entry({ unit, quantity: '2' })), unit).toBe(2000);
    }
    for (const unit of ['item', 'day', 'each']) {
      expect(hoursMilli(entry({ unit, quantity: '2' })), unit).toBe(0);
    }
  });

  it('leaves every other kind without an hours total', () => {
    for (const kind of ['invoice', 'receipt', 'creditNote'] as const) {
      const document = week();
      document.kind = kind;
      expect(calculateDocument(document).totalHoursMilli).toBe(0);
    }
  });

  it('keeps the dates through a save and reload', () => {
    const { documents } = normalizeWorkspaceRecords({ documents: [week()] });
    expect(documents[0].kind).toBe('timesheet');
    expect(documents[0].lineItems[1].serviceDate).toBe('2026-09-02');
  });

  it('reads back a line saved before dates existed', () => {
    const document = week() as unknown as Record<string, unknown>;
    const lines = (document.lineItems as Record<string, unknown>[]).map((line) => {
      const copy = { ...line };
      delete copy.serviceDate;
      return copy;
    });
    const { documents } = normalizeWorkspaceRecords({ documents: [{ ...document, lineItems: lines }] });
    expect(documents[0].lineItems[0].serviceDate).toBeUndefined();
  });
});
