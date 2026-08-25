import type {
  Address,
  BusinessProfile,
  Client,
  DocumentKind,
  DocumentRecord,
  LineItem,
  NumberingSettings,
} from './types';

export const emptyAddress = (): Address => ({
  line1: '',
  line2: '',
  city: '',
  region: '',
  postalCode: '',
  country: '',
});

export const emptyBusiness = (): BusinessProfile => ({
  id: 'default-business',
  name: '',
  email: '',
  phone: '',
  website: '',
  taxId: '',
  address: emptyAddress(),
  paymentInstructions: '',
  defaultCurrency: 'USD',
  defaultTaxBps: 0,
  defaultTerms: 'Payment due within 30 days.',
});

export const emptyClient = (): Client => {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    name: '',
    email: '',
    phone: '',
    taxId: '',
    address: emptyAddress(),
    createdAt: now,
    updatedAt: now,
  };
};

export const emptyLineItem = (taxBps = 0): LineItem => ({
  id: crypto.randomUUID(),
  description: '',
  quantity: '1',
  unit: 'item',
  unitPriceMinor: 0,
  taxBps,
  discountBps: 0,
});

export const defaultNumbering = (): NumberingSettings => ({
  prefixes: {
    invoice: 'INV-',
    proforma: 'PRO-',
    quotation: 'QUO-',
    estimate: 'EST-',
    workOrder: 'WO-',
    purchaseOrder: 'PO-',
    receipt: 'REC-',
  },
  nextNumbers: {
    invoice: 1001,
    proforma: 1001,
    quotation: 1001,
    estimate: 1001,
    workOrder: 1001,
    purchaseOrder: 1001,
    receipt: 1001,
  },
});

const addDays = (date: Date, days: number) => {
  const result = new Date(date);
  result.setUTCDate(result.getUTCDate() + days);
  return result.toISOString().slice(0, 10);
};

export const createDocument = (
  kind: DocumentKind,
  business = emptyBusiness(),
  numbering = defaultNumbering(),
): DocumentRecord => {
  const now = new Date();
  const timestamp = now.toISOString();
  return {
    id: crypto.randomUUID(),
    kind,
    status: 'draft',
    number: `${numbering.prefixes[kind]}${numbering.nextNumbers[kind]}`,
    issueDate: timestamp.slice(0, 10),
    dueDate: addDays(now, kind === 'receipt' ? 0 : 30),
    currency: business.defaultCurrency,
    business: structuredClone(business),
    client: emptyClient(),
    lineItems: [emptyLineItem(business.defaultTaxBps)],
    shippingMinor: 0,
    adjustmentMinor: 0,
    notes: '',
    paymentInstructions: business.paymentInstructions,
    terms: business.defaultTerms,
    projectName: '',
    jobsite: '',
    reference: '',
    depositMinor: 0,
    progressBillingNote: '',
    createdAt: timestamp,
    updatedAt: timestamp,
  };
};

export const documentLabels: Record<DocumentKind, string> = {
  invoice: 'Invoice',
  proforma: 'Proforma Invoice',
  quotation: 'Quotation',
  estimate: 'Estimate',
  workOrder: 'Work Order',
  purchaseOrder: 'Purchase Order',
  receipt: 'Receipt',
};
