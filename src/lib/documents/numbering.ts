import { defaultNumbering } from './factory';
import type { DocumentKind, NumberingSettings } from './types';

export const nextDocumentNumber = (
  settings: NumberingSettings,
  kind: DocumentKind,
): { number: string; settings: NumberingSettings } => {
  const current = settings.nextNumbers[kind];
  return {
    number: `${settings.prefixes[kind]}${current}`,
    settings: {
      prefixes: { ...settings.prefixes },
      nextNumbers: { ...settings.nextNumbers, [kind]: current + 1 },
    },
  };
};

export const normalizeNumbering = (value?: unknown): NumberingSettings => {
  const defaults = defaultNumbering();
  const source = value !== null && typeof value === 'object' ? value as Partial<NumberingSettings> : undefined;
  const prefixes: Partial<Record<DocumentKind, unknown>> = source?.prefixes !== null && typeof source?.prefixes === 'object'
    ? source.prefixes
    : {};
  const nextNumbers: Partial<Record<DocumentKind, unknown>> = source?.nextNumbers !== null && typeof source?.nextNumbers === 'object'
    ? source.nextNumbers
    : {};
  const normalizedPrefixes = Object.fromEntries(
    (Object.keys(defaults.prefixes) as DocumentKind[]).map((kind) => [
      kind,
      typeof prefixes[kind] === 'string' && prefixes[kind] ? prefixes[kind] : defaults.prefixes[kind],
    ]),
  ) as Record<DocumentKind, string>;
  const normalizedNumbers = Object.fromEntries(
    (Object.keys(defaults.nextNumbers) as DocumentKind[]).map((kind) => {
      const candidate = nextNumbers[kind];
      return [kind, typeof candidate === 'number' && Number.isSafeInteger(candidate) && candidate > 0
        ? candidate
        : defaults.nextNumbers[kind]];
    }),
  ) as Record<DocumentKind, number>;
  return {
    prefixes: normalizedPrefixes,
    nextNumbers: normalizedNumbers,
  };
};
