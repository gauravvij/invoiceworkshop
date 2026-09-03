import { documentLabels } from './factory';
import { calculateDocument } from './money';
import type { DocumentKind, DocumentRecord, NumberingSettings } from './types';

export const allowedConversions: Partial<Record<DocumentKind, DocumentKind[]>> = {
  quotation: ['invoice'],
  estimate: ['workOrder', 'invoice'],
  workOrder: ['invoice'],
  proforma: ['invoice'],
  invoice: ['receipt', 'creditNote'],
};

export const canConvert = (from: DocumentKind, to: DocumentKind): boolean =>
  allowedConversions[from]?.includes(to) ?? false;

export const convertDocument = (
  source: DocumentRecord,
  targetKind: DocumentKind,
  numbering: NumberingSettings,
): DocumentRecord => {
  if (!canConvert(source.kind, targetKind)) {
    throw new Error(`${documentLabels[source.kind]} cannot be converted to ${documentLabels[targetKind]}.`);
  }
  const timestamp = new Date().toISOString();
  // Receipting an invoice acknowledges the invoice in full unless the user says
  // otherwise, and the invoice number is the reference the customer will match
  // it against, so it is carried rather than left for retyping.
  const paidInFull = targetKind === 'receipt'
    ? calculateDocument(source).totalMinor
    : 0;
  return {
    ...structuredClone(source),
    id: crypto.randomUUID(),
    kind: targetKind,
    status: targetKind === 'receipt' ? 'paid' : 'draft',
    number: `${numbering.prefixes[targetKind]}${numbering.nextNumbers[targetKind]}`,
    convertedFrom: { id: source.id, kind: source.kind, number: source.number },
    createdAt: timestamp,
    updatedAt: timestamp,
    dueDate: targetKind === 'receipt' ? source.issueDate : source.dueDate,
    amountPaidMinor: paidInFull,
    // Both documents point back at the invoice by number: a receipt so the
    // customer can match it to their bank, a credit note because the credit is
    // meaningless without saying what it reverses.
    reference: ['receipt', 'creditNote'].includes(targetKind) && !source.reference
      ? source.number
      : source.reference,
  };
};
