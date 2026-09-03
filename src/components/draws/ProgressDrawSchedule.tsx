import { useEffect, useMemo, useState } from 'react';
import {
  calculateLine,
  calculateSchedule,
  defaultRetainage,
  emptyLine,
  type DrawLine,
  type RetainageSettings,
} from '@/lib/draws/schedule';
import { formatMoney, moneyInputValue, parseMoney } from '@/lib/documents/money';

const STORAGE_KEY = 'invoice-workshop-draw-schedule';
const CURRENCIES = ['USD', 'CAD', 'GBP', 'EUR', 'AUD', 'NZD'];

interface Saved {
  currency: string;
  project: string;
  application: string;
  periodTo: string;
  previousCertificatesMinor: number;
  settings: RetainageSettings;
  lines: DrawLine[];
}

const starter = (): Saved => ({
  currency: 'USD',
  project: '',
  application: '1',
  periodTo: new Date().toISOString().slice(0, 10),
  previousCertificatesMinor: 0,
  settings: defaultRetainage(),
  lines: [
    { ...emptyLine(), description: 'General conditions' },
    { ...emptyLine(), description: 'Sitework' },
    { ...emptyLine(), description: 'Concrete' },
  ],
});

/**
 * Restores a saved schedule without trusting its shape. The same store can be
 * written by an older version of this page, so every field is checked and a
 * bad one falls back rather than throwing away the whole schedule.
 */
const restore = (): Saved => {
  const fallback = starter();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Saved>;
    const lines = Array.isArray(parsed.lines) ? parsed.lines : [];
    return {
      currency: typeof parsed.currency === 'string' ? parsed.currency : fallback.currency,
      project: typeof parsed.project === 'string' ? parsed.project : '',
      application: typeof parsed.application === 'string' ? parsed.application : '1',
      periodTo: typeof parsed.periodTo === 'string' ? parsed.periodTo : fallback.periodTo,
      previousCertificatesMinor: Number.isFinite(parsed.previousCertificatesMinor)
        ? Math.trunc(parsed.previousCertificatesMinor as number) : 0,
      settings: { ...fallback.settings, ...(parsed.settings ?? {}) },
      lines: lines.length ? lines.map((line) => ({ ...emptyLine(), ...line })) : fallback.lines,
    };
  } catch {
    return fallback;
  }
};

export default function ProgressDrawSchedule() {
  const [state, setState] = useState<Saved>(starter);
  const [ready, setReady] = useState(false);

  useEffect(() => { setState(restore()); setReady(true); }, []);
  useEffect(() => {
    if (!ready) return;
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* private mode */ }
  }, [state, ready]);

  const totals = useMemo(
    () => calculateSchedule(state.lines, state.settings, state.previousCertificatesMinor),
    [state],
  );
  const money = (minor: number) => formatMoney(minor, state.currency);
  const percent = (bps: number) => `${(bps / 100).toFixed(1)}%`;

  const patch = (changes: Partial<Saved>) => setState((current) => ({ ...current, ...changes }));
  const patchLine = (id: string, changes: Partial<DrawLine>) => setState((current) => ({
    ...current,
    lines: current.lines.map((line) => (line.id === id ? { ...line, ...changes } : line)),
  }));

  return (
    <div className="draw-tool">
      <fieldset className="editor-section">
        <legend>Application</legend>
        <div className="form-grid form-grid--three">
          <label className="field"><span>Project</span>
            <input value={state.project} onChange={(e) => patch({ project: e.target.value })} placeholder="Maple Street fit-out" />
          </label>
          <label className="field"><span>Application no.</span>
            <input value={state.application} inputMode="numeric" onChange={(e) => patch({ application: e.target.value })} />
          </label>
          <label className="field"><span>Period to</span>
            <input type="date" value={state.periodTo} onChange={(e) => patch({ periodTo: e.target.value })} />
          </label>
          <label className="field"><span>Currency</span>
            <select value={state.currency} onChange={(e) => patch({ currency: e.target.value })}>
              {CURRENCIES.map((code) => <option key={code}>{code}</option>)}
            </select>
          </label>
          <label className="field"><span>Retainage %</span>
            <input
              type="text" inputMode="decimal"
              value={(state.settings.retainageBps / 100).toString()}
              onChange={(e) => patch({ settings: { ...state.settings, retainageBps: Math.round(Number(e.target.value.replace(/[^0-9.]/g, '') || 0) * 100) } })}
            />
          </label>
          <label className="field"><span>Less previous certificates <small>{state.currency}</small></span>
            <input
              type="text" inputMode="decimal"
              value={moneyInputValue(state.previousCertificatesMinor, state.currency)}
              onChange={(e) => patch({ previousCertificatesMinor: parseMoney(e.target.value, state.currency) })}
            />
          </label>
        </div>
        <label className="draw-toggle">
          <input
            type="checkbox" checked={state.settings.reducedAfterHalf}
            onChange={(e) => patch({ settings: { ...state.settings, reducedAfterHalf: e.target.checked } })}
          />
          <span>
            Reduce retainage after 50% complete
            {state.settings.reducedAfterHalf && (
              <> to <input
                className="draw-inline-input" type="text" inputMode="decimal"
                aria-label="Reduced retainage percent"
                value={(state.settings.reducedRetainageBps / 100).toString()}
                onChange={(e) => patch({ settings: { ...state.settings, reducedRetainageBps: Math.round(Number(e.target.value.replace(/[^0-9.]/g, '') || 0) * 100) } })}
              />%</>
            )}
          </span>
        </label>
        <p className="section-hint">
          Only tick this if the contract says so. The reduction is judged on the whole
          contract, not line by line — a finished line on a job that has barely started
          does not release retainage. Currently applying {percent(totals.effectiveRetainageBps)}.
        </p>
      </fieldset>

      <fieldset className="editor-section">
        <legend>Schedule of values</legend>
        <div className="draw-scroll" tabIndex={0} role="region" aria-label="Schedule of values">
          <table className="draw-table">
            <thead>
              <tr>
                <th scope="col">Description of work</th>
                <th scope="col" className="numeric">C · Scheduled value</th>
                <th scope="col" className="numeric">D · Previous</th>
                <th scope="col" className="numeric">E · This period</th>
                <th scope="col" className="numeric">F · Stored</th>
                <th scope="col" className="numeric">G · Completed</th>
                <th scope="col" className="numeric">%</th>
                <th scope="col" className="numeric">I · To finish</th>
                <th scope="col" className="numeric">J · Retainage</th>
                <th scope="col"><span className="visually-hidden">Remove</span></th>
              </tr>
            </thead>
            <tbody>
              {state.lines.map((line, index) => {
                const result = calculateLine(line, totals.effectiveRetainageBps);
                return (
                  <tr key={line.id}>
                    <td>
                      <input
                        aria-label={`Description, line ${index + 1}`}
                        value={line.description}
                        onChange={(e) => patchLine(line.id, { description: e.target.value })}
                      />
                    </td>
                    {([
                      ['scheduledValueMinor', 'Scheduled value'],
                      ['previousMinor', 'Previous'],
                      ['thisPeriodMinor', 'This period'],
                      ['storedMinor', 'Stored'],
                    ] as const).map(([field, label]) => (
                      <td key={field} className="numeric">
                        <input
                          type="text" inputMode="decimal"
                          aria-label={`${label}, line ${index + 1}`}
                          value={moneyInputValue(line[field], state.currency)}
                          onChange={(e) => patchLine(line.id, { [field]: parseMoney(e.target.value, state.currency) })}
                        />
                      </td>
                    ))}
                    <td className="numeric derived">{money(result.totalCompletedMinor)}</td>
                    <td className="numeric derived">{percent(result.percentBps)}</td>
                    <td className={`numeric derived${result.balanceToFinishMinor < 0 ? ' over-billed' : ''}`}>
                      {money(result.balanceToFinishMinor)}
                    </td>
                    <td className="numeric derived">{money(result.retainageMinor)}</td>
                    <td>
                      <button
                        type="button" className="text-button text-button--danger"
                        onClick={() => setState((c) => ({ ...c, lines: c.lines.filter((l) => l.id !== line.id) }))}
                        disabled={state.lines.length === 1}
                      >Remove</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Totals</th>
                <td className="numeric">{money(totals.scheduledValueMinor)}</td>
                <td className="numeric">{money(totals.previousMinor)}</td>
                <td className="numeric">{money(totals.thisPeriodMinor)}</td>
                <td className="numeric">{money(totals.storedMinor)}</td>
                <td className="numeric">{money(totals.totalCompletedMinor)}</td>
                <td className="numeric">{percent(totals.percentBps)}</td>
                <td className="numeric">{money(totals.balanceToFinishMinor)}</td>
                <td className="numeric">{money(totals.retainageMinor)}</td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
        <button
          type="button" className="button button--add"
          onClick={() => setState((c) => ({ ...c, lines: [...c.lines, emptyLine()] }))}
        >+ Add line</button>
      </fieldset>

      <fieldset className="editor-section">
        <legend>Payment due this period</legend>
        <dl className="draw-summary">
          <div><dt>Contract sum (schedule of values)</dt><dd>{money(totals.scheduledValueMinor)}</dd></div>
          <div><dt>Total completed and stored to date</dt><dd>{money(totals.totalCompletedMinor)}</dd></div>
          <div><dt>Less retainage at {percent(totals.effectiveRetainageBps)}</dt><dd>−{money(totals.retainageMinor)}</dd></div>
          <div><dt>Total earned less retainage</dt><dd>{money(totals.earnedLessRetainageMinor)}</dd></div>
          <div><dt>Less previous certificates for payment</dt><dd>−{money(totals.previousCertificatesMinor)}</dd></div>
          <div className="draw-summary-total"><dt>Current payment due</dt><dd>{money(totals.currentPaymentDueMinor)}</dd></div>
          <div><dt>Balance to finish, including retainage</dt><dd>{money(totals.balanceIncludingRetainageMinor)}</dd></div>
        </dl>
        <p className="section-hint">
          The retainage total is the sum of the retainage column, not a percentage of the
          total, so the column adds up to the figure beneath it. On a long schedule those
          two differ by a few cents, and it is the column a reviewer checks.
        </p>
        <div className="workspace-actions no-print">
          <button type="button" className="button button--primary" onClick={() => window.print()}>
            Print / save as PDF
          </button>
          <button
            type="button" className="button button--quiet"
            onClick={() => { if (confirm('Clear this schedule?')) { setState(starter()); } }}
          >Clear</button>
        </div>
      </fieldset>
    </div>
  );
}
