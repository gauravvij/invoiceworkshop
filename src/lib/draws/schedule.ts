/**
 * Progress draw arithmetic, on the AIA G702/G703 column model.
 *
 * The column letters are not decoration: a contractor's pay application is
 * reviewed against them by an architect or a lender, and a schedule that
 * computes its own columns in its own order is one the reviewer cannot check.
 * So the names here are the ones on the form.
 *
 *   C  scheduled value                 what the line is worth in the contract
 *   D  completed in previous periods
 *   E  completed this period
 *   F  materials presently stored      on site, not yet installed
 *   G  total completed and stored      D + E + F
 *   H  percent complete                G / C
 *   I  balance to finish               C - G
 *   J  retainage                       a percentage of G
 *
 * Every figure is an integer number of minor units and every division rounds
 * once, explicitly, with BigInt — the same discipline the invoice totals use.
 * Retainage on a large contract is where a rounding drift of a cent per line
 * turns into a disputed number on a pay application.
 */

export interface DrawLine {
  id: string;
  description: string;
  scheduledValueMinor: number;
  previousMinor: number;
  thisPeriodMinor: number;
  storedMinor: number;
}

export interface RetainageSettings {
  /** Basis points withheld from completed work. 1000 = 10%. */
  retainageBps: number;
  /**
   * Many contracts stop withholding once the job passes a threshold, leaving
   * the amount already held in place. Off by default because a contract that
   * does not say so does not do it.
   */
  reducedAfterHalf: boolean;
  /** Rate applied once the threshold is passed. */
  reducedRetainageBps: number;
}

export interface LineResult {
  totalCompletedMinor: number;
  percentBps: number;
  balanceToFinishMinor: number;
  retainageMinor: number;
}

export interface DrawTotals {
  scheduledValueMinor: number;
  previousMinor: number;
  thisPeriodMinor: number;
  storedMinor: number;
  totalCompletedMinor: number;
  percentBps: number;
  balanceToFinishMinor: number;
  retainageMinor: number;
  /** G702 line 6: total earned less retainage. */
  earnedLessRetainageMinor: number;
  /** G702 line 7: less previous certificates for payment. */
  previousCertificatesMinor: number;
  /** G702 line 8: current payment due. */
  currentPaymentDueMinor: number;
  /** G702 line 9: balance to finish including retainage. */
  balanceIncludingRetainageMinor: number;
  effectiveRetainageBps: number;
}

const roundedDivide = (numerator: bigint, denominator: bigint): bigint => {
  if (numerator < 0n) return -roundedDivide(-numerator, denominator);
  return (numerator + denominator / 2n) / denominator;
};

export const emptyLine = (): DrawLine => ({
  id: crypto.randomUUID(),
  description: '',
  scheduledValueMinor: 0,
  previousMinor: 0,
  thisPeriodMinor: 0,
  storedMinor: 0,
});

export const defaultRetainage = (): RetainageSettings => ({
  retainageBps: 1000,
  reducedAfterHalf: false,
  reducedRetainageBps: 500,
});

/**
 * The rate actually applied. The reduction is judged on the whole contract, not
 * line by line: a contract that halves retainage at 50% complete means the job,
 * and applying it per line would release money on a finished line while the
 * project is barely started.
 */
export const effectiveRetainageBps = (
  lines: DrawLine[],
  settings: RetainageSettings,
): number => {
  if (!settings.reducedAfterHalf) return settings.retainageBps;
  const scheduled = lines.reduce((sum, line) => sum + line.scheduledValueMinor, 0);
  const completed = lines.reduce(
    (sum, line) => sum + line.previousMinor + line.thisPeriodMinor + line.storedMinor,
    0,
  );
  if (scheduled <= 0) return settings.retainageBps;
  return completed * 2 >= scheduled ? settings.reducedRetainageBps : settings.retainageBps;
};

export const calculateLine = (line: DrawLine, retainageBps: number): LineResult => {
  const total = line.previousMinor + line.thisPeriodMinor + line.storedMinor;
  const percentBps = line.scheduledValueMinor > 0
    ? Number(roundedDivide(BigInt(total) * 10_000n, BigInt(line.scheduledValueMinor)))
    : 0;
  return {
    totalCompletedMinor: total,
    percentBps,
    balanceToFinishMinor: line.scheduledValueMinor - total,
    retainageMinor: Number(roundedDivide(BigInt(total) * BigInt(retainageBps), 10_000n)),
  };
};

export const calculateSchedule = (
  lines: DrawLine[],
  settings: RetainageSettings,
  previousCertificatesMinor: number,
): DrawTotals => {
  const bps = effectiveRetainageBps(lines, settings);
  const results = lines.map((line) => calculateLine(line, bps));
  const scheduledValueMinor = lines.reduce((sum, line) => sum + line.scheduledValueMinor, 0);
  const totalCompletedMinor = results.reduce((sum, result) => sum + result.totalCompletedMinor, 0);
  // Summed from the per-line figures rather than recomputed on the total, so
  // the column adds up to the number in the box beneath it. A reviewer checks
  // exactly that.
  const retainageMinor = results.reduce((sum, result) => sum + result.retainageMinor, 0);
  const earnedLessRetainageMinor = totalCompletedMinor - retainageMinor;
  return {
    scheduledValueMinor,
    previousMinor: lines.reduce((sum, line) => sum + line.previousMinor, 0),
    thisPeriodMinor: lines.reduce((sum, line) => sum + line.thisPeriodMinor, 0),
    storedMinor: lines.reduce((sum, line) => sum + line.storedMinor, 0),
    totalCompletedMinor,
    percentBps: scheduledValueMinor > 0
      ? Number(roundedDivide(BigInt(totalCompletedMinor) * 10_000n, BigInt(scheduledValueMinor)))
      : 0,
    balanceToFinishMinor: scheduledValueMinor - totalCompletedMinor,
    retainageMinor,
    earnedLessRetainageMinor,
    previousCertificatesMinor,
    currentPaymentDueMinor: earnedLessRetainageMinor - previousCertificatesMinor,
    balanceIncludingRetainageMinor: scheduledValueMinor - earnedLessRetainageMinor,
    effectiveRetainageBps: bps,
  };
};
