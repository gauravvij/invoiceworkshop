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

export const emptyLineItem = (taxBps = 0, kind?: DocumentKind): LineItem => ({
  id: crypto.randomUUID(),
  description: '',
  // A timesheet line is an entry for a day's work, so it starts with today's
  // date and an hour rather than "1 item" -- the two fields someone would
  // otherwise change on every line they add.
  serviceDate: kind === 'timesheet' ? new Date().toISOString().slice(0, 10) : undefined,
  quantityOrdered: kind === 'deliveryNote' ? '1' : undefined,
  quantity: '1',
  unit: kind === 'timesheet' ? 'hour' : 'item',
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
    creditNote: 'CN-',
    timesheet: 'TS-',
    deliveryNote: 'DN-',
  },
  nextNumbers: {
    invoice: 1001,
    proforma: 1001,
    quotation: 1001,
    estimate: 1001,
    workOrder: 1001,
    purchaseOrder: 1001,
    receipt: 1001,
    creditNote: 1001,
    timesheet: 1001,
    deliveryNote: 1001,
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
    // A receipt exists because money arrived. Starting one as a draft asks the
    // user to mark a fact they already stated by choosing the document.
    status: kind === 'receipt' ? 'paid' : 'draft',
    number: `${numbering.prefixes[kind]}${numbering.nextNumbers[kind]}`,
    issueDate: timestamp.slice(0, 10),
    // A receipt, a credit note and a delivery note all record something that has
    // already happened, so none of them has a payment date in the future.
    dueDate: addDays(
      now,
      ['receipt', 'creditNote', 'deliveryNote'].includes(kind) ? 0 : 30,
    ),
    currency: business.defaultCurrency,
    business: structuredClone(business),
    client: emptyClient(),
    lineItems: [emptyLineItem(business.defaultTaxBps, kind)],
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
    paymentMethod: '',
    amountPaidMinor: 0,
    creditReason: '',
    deliveryAddress: kind === 'deliveryNote' ? emptyAddress() : undefined,
    carrier: '',
    consignmentRef: '',
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
  creditNote: 'Credit Note',
  timesheet: 'Timesheet Invoice',
  deliveryNote: 'Delivery Note',
};
