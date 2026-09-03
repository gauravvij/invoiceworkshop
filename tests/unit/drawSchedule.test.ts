import { describe, expect, it } from 'vitest';
import {
  calculateLine,
  calculateSchedule,
  defaultRetainage,
  effectiveRetainageBps,
  type DrawLine,
} from '@/lib/draws/schedule';

const line = (over: Partial<DrawLine> = {}): DrawLine => ({
  id: 'x', description: 'Work', scheduledValueMinor: 0, previousMinor: 0,
  thisPeriodMinor: 0, storedMinor: 0, ...over,
});

describe('progress draw schedule', () => {
  it('computes column G as previous plus this period plus stored', () => {
    const result = calculateLine(
      line({ scheduledValueMinor: 10_000_00, previousMinor: 3_000_00, thisPeriodMinor: 2_000_00, storedMinor: 500_00 }),
      1000,
    );
    expect(result.totalCompletedMinor).toBe(5_500_00);
    expect(result.balanceToFinishMinor).toBe(4_500_00);
    expect(result.percentBps).toBe(5500);
    expect(result.retainageMinor).toBe(550_00);
  });

  it('rounds percent complete once rather than drifting', () => {
    // 1/3 of the line. 3333.33... basis points must land on 3333, not 3334.
    const result = calculateLine(line({ scheduledValueMinor: 30_000, previousMinor: 10_000 }), 0);
    expect(result.percentBps).toBe(3333);
  });

  it('sums retainage from the column, so the total matches what is listed', () => {
    // Three lines each rounding up by half a cent. Retaining 10% of the sum
    // would give 100.00; the column adds to 100.02, and the column is what a
    // reviewer checks.
    const lines = [
      line({ scheduledValueMinor: 100_00, previousMinor: 33_35 }),
      line({ scheduledValueMinor: 100_00, previousMinor: 33_35 }),
      line({ scheduledValueMinor: 100_00, previousMinor: 33_35 }),
    ];
    const totals = calculateSchedule(lines, { ...defaultRetainage() }, 0);
    expect(totals.totalCompletedMinor).toBe(100_05);
    expect(totals.retainageMinor).toBe(10_02);
    expect(totals.retainageMinor).toBe(
      lines.reduce((sum, l) => sum + calculateLine(l, 1000).retainageMinor, 0),
    );
  });

  it('produces the G702 payment rollup', () => {
    const lines = [line({ scheduledValueMinor: 200_000_00, previousMinor: 60_000_00, thisPeriodMinor: 40_000_00 })];
    const totals = calculateSchedule(lines, { ...defaultRetainage() }, 54_000_00);
    expect(totals.totalCompletedMinor).toBe(100_000_00);
    expect(totals.retainageMinor).toBe(10_000_00);
    expect(totals.earnedLessRetainageMinor).toBe(90_000_00);
    expect(totals.currentPaymentDueMinor).toBe(36_000_00);
    expect(totals.balanceIncludingRetainageMinor).toBe(110_000_00);
  });

  it('judges the retainage reduction on the contract, not on one line', () => {
    const settings = { retainageBps: 1000, reducedAfterHalf: true, reducedRetainageBps: 500 };
    // One line finished, the project 25% complete. The finished line must not
    // release retainage on its own.
    const early = [
      line({ scheduledValueMinor: 100_00, previousMinor: 100_00 }),
      line({ scheduledValueMinor: 300_00 }),
    ];
    expect(effectiveRetainageBps(early, settings)).toBe(1000);
    const halfway = [
      line({ scheduledValueMinor: 100_00, previousMinor: 100_00 }),
      line({ scheduledValueMinor: 100_00, previousMinor: 100_00 }),
    ];
    expect(effectiveRetainageBps(halfway, settings)).toBe(500);
  });

  it('leaves the reduction off unless the contract says so', () => {
    const done = [line({ scheduledValueMinor: 100_00, previousMinor: 100_00 })];
    expect(effectiveRetainageBps(done, defaultRetainage())).toBe(1000);
  });

  it('does not divide by zero on an empty schedule', () => {
    const totals = calculateSchedule([], defaultRetainage(), 0);
    expect(totals.percentBps).toBe(0);
    expect(totals.currentPaymentDueMinor).toBe(0);
  });

  it('shows an over-billed line as a negative balance rather than hiding it', () => {
    const result = calculateLine(line({ scheduledValueMinor: 100_00, previousMinor: 120_00 }), 1000);
    expect(result.balanceToFinishMinor).toBe(-20_00);
    expect(result.percentBps).toBe(12_000);
  });
});
