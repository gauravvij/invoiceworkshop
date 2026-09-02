/**
 * Country presets for invoicing.
 *
 * These are not translations. Each preset changes what the document computes and
 * what it must state: the tax label and default rate, the name and requirement
 * of the tax registration number, the wording the tax authority insists on, the
 * currency and the date format. A UK VAT invoice and an Australian tax invoice
 * are different documents, not the same document in different words.
 *
 * Rates are the standard rates at time of writing and are defaults, not advice —
 * the user can change every one of them, and which rate applies to a given
 * supply is their responsibility.
 */

export interface LocalePreset {
  key: string;
  country: string;
  /** Label used everywhere tax appears: "VAT", "GST", "Sales tax". */
  taxLabel: string;
  /** Default rate applied to new lines, in basis points. */
  defaultTaxBps: number;
  /** Selectable rates for this country, in basis points. */
  rateOptions: number[];
  currency: string;
  /** What the seller's registration number is called here. */
  businessTaxIdLabel: string;
  clientTaxIdLabel: string;
  /** Wording the tax authority requires on the face of the document. */
  documentTitle?: string;
  /** Locale used to render dates on the document. */
  dateLocale: string;
  /** One sentence on what makes a valid invoice here. Factual, not advice. */
  requirement: string;
}

export const localePresets: Record<string, LocalePreset> = {
  gb: {
    key: 'gb', country: 'United Kingdom', taxLabel: 'VAT', defaultTaxBps: 2000,
    rateOptions: [2000, 500, 0], currency: 'GBP',
    businessTaxIdLabel: 'VAT registration number', clientTaxIdLabel: 'Customer VAT number',
    documentTitle: 'VAT INVOICE', dateLocale: 'en-GB',
    requirement: 'A VAT invoice must show your VAT registration number, the rate charged and the VAT amount as a separate figure.',
  },
  in: {
    key: 'in', country: 'India', taxLabel: 'GST', defaultTaxBps: 1800,
    rateOptions: [1800, 1200, 500, 2800, 0], currency: 'INR',
    businessTaxIdLabel: 'GSTIN', clientTaxIdLabel: 'Customer GSTIN',
    documentTitle: 'TAX INVOICE', dateLocale: 'en-IN',
    requirement: 'A GST tax invoice carries both parties’ GSTIN, the place of supply and the HSN or SAC code for each line.',
  },
  au: {
    key: 'au', country: 'Australia', taxLabel: 'GST', defaultTaxBps: 1000,
    rateOptions: [1000, 0], currency: 'AUD',
    businessTaxIdLabel: 'ABN', clientTaxIdLabel: 'Customer ABN',
    documentTitle: 'TAX INVOICE', dateLocale: 'en-AU',
    requirement: 'The ATO requires the words “Tax invoice”, your ABN, and the GST amount shown separately.',
  },
  ca: {
    key: 'ca', country: 'Canada', taxLabel: 'GST/HST', defaultTaxBps: 500,
    rateOptions: [500, 1300, 1500, 1200, 0], currency: 'CAD',
    businessTaxIdLabel: 'CRA business number', clientTaxIdLabel: 'Customer business number',
    dateLocale: 'en-CA',
    requirement: 'The rate depends on the province of supply: 5% GST alone, or 13% and 15% HST in the participating provinces.',
  },
  ae: {
    key: 'ae', country: 'United Arab Emirates', taxLabel: 'VAT', defaultTaxBps: 500,
    rateOptions: [500, 0], currency: 'AED',
    businessTaxIdLabel: 'TRN', clientTaxIdLabel: 'Customer TRN',
    documentTitle: 'TAX INVOICE', dateLocale: 'en-AE',
    requirement: 'The FTA requires the words “Tax Invoice” and your 15-digit TRN on the document.',
  },
  za: {
    key: 'za', country: 'South Africa', taxLabel: 'VAT', defaultTaxBps: 1500,
    rateOptions: [1500, 0], currency: 'ZAR',
    businessTaxIdLabel: 'VAT registration number', clientTaxIdLabel: 'Customer VAT number',
    documentTitle: 'TAX INVOICE', dateLocale: 'en-ZA',
    requirement: 'SARS requires the words “Tax Invoice” and your VAT number for a full tax invoice.',
  },
  ie: {
    key: 'ie', country: 'Ireland', taxLabel: 'VAT', defaultTaxBps: 2300,
    rateOptions: [2300, 1350, 900, 0], currency: 'EUR',
    businessTaxIdLabel: 'VAT number', clientTaxIdLabel: 'Customer VAT number',
    documentTitle: 'VAT INVOICE', dateLocale: 'en-IE',
    requirement: 'Revenue requires your VAT number and the VAT shown separately at the rate applied.',
  },
  sg: {
    key: 'sg', country: 'Singapore', taxLabel: 'GST', defaultTaxBps: 900,
    rateOptions: [900, 0], currency: 'SGD',
    businessTaxIdLabel: 'GST registration number', clientTaxIdLabel: 'Customer UEN',
    documentTitle: 'TAX INVOICE', dateLocale: 'en-SG',
    requirement: 'IRAS requires the words “Tax Invoice”, your GST registration number and the GST amount.',
  },
  nz: {
    key: 'nz', country: 'New Zealand', taxLabel: 'GST', defaultTaxBps: 1500,
    rateOptions: [1500, 0], currency: 'NZD',
    businessTaxIdLabel: 'GST number', clientTaxIdLabel: 'Customer GST number',
    documentTitle: 'TAX INVOICE', dateLocale: 'en-NZ',
    requirement: 'Inland Revenue requires your GST number and the GST amount for supplies over the threshold.',
  },
  de: {
    key: 'de', country: 'Germany', taxLabel: 'USt', defaultTaxBps: 1900,
    rateOptions: [1900, 700, 0], currency: 'EUR',
    businessTaxIdLabel: 'USt-IdNr', clientTaxIdLabel: 'Kunden USt-IdNr',
    dateLocale: 'de-DE',
    requirement: 'A Rechnung must carry your USt-IdNr or Steuernummer and show the USt separately.',
  },
};

export const localeFor = (key?: string): LocalePreset | undefined =>
  key ? localePresets[key] : undefined;

/** Format a yyyy-mm-dd date the way this country writes it. */
export const formatLocaleDate = (iso: string, preset?: LocalePreset): string => {
  if (!preset || !iso) return iso;
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat(preset.dateLocale, {
      day: '2-digit', month: '2-digit', year: 'numeric',
    }).format(parsed);
  } catch {
    return iso;
  }
};
