import { documentLabels } from './factory';
import type { DocumentKind, DocumentRecord, NumberingSettings } from './types';

export const allowedConversions: Partial<Record<DocumentKind, DocumentKind[]>> = {
  quotation: ['invoice'],
  estimate: ['workOrder', 'invoice'],
  workOrder: ['invoice'],
  proforma: ['invoice'],
  invoice: ['receipt'],
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
  };
};
