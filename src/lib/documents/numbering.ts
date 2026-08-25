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

export const normalizeNumbering = (value?: Partial<NumberingSettings>): NumberingSettings => {
  const defaults = defaultNumbering();
  return {
    prefixes: { ...defaults.prefixes, ...value?.prefixes },
    nextNumbers: { ...defaults.nextNumbers, ...value?.nextNumbers },
  };
};
