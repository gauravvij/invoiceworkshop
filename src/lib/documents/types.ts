export type DocumentKind =
  | 'invoice'
  | 'proforma'
  | 'quotation'
  | 'estimate'
  | 'workOrder'
  | 'purchaseOrder'
  | 'receipt'
  | 'creditNote'
  | 'timesheet'
  | 'deliveryNote';

export type DocumentStatus = 'draft' | 'completed' | 'paid';

export interface Address {
  line1: string;
  line2: string;
  city: string;
  region: string;
  postalCode: string;
  country: string;
}

export interface BusinessProfile {
  id: string;
  name: string;
  email: string;
  phone: string;
  website: string;
  taxId: string;
  address: Address;
  logoDataUrl?: string;
  paymentInstructions: string;
  defaultCurrency: string;
  defaultTaxBps: number;
  defaultTerms: string;
}

export interface Client {
  id: string;
  name: string;
  email: string;
  phone: string;
  taxId: string;
  address: Address;
  createdAt: string;
  updatedAt: string;
}

export interface CatalogItem {
  id: string;
  name: string;
  description: string;
  unitPriceMinor: number;
  taxBps: number;
  unit: string;
  createdAt: string;
  updatedAt: string;
}

export interface LineItem {
  id: string;
  description: string;
  /**
   * The day the work was done. Only a timesheet uses it: an invoice line is a
   * thing supplied and a timesheet line is a thing supplied ON A DATE, and that
   * is the difference a client checks a timesheet against. Empty elsewhere.
   */
  serviceDate?: string;
  /**
   * What was ordered, where that differs from what is in the box. Only a
   * delivery note carries it: `quantity` is what is actually being delivered,
   * and the gap between the two is the back-order the recipient signs for.
   */
  quantityOrdered?: string;
  quantity: string;
  unit: string;
  unitPriceMinor: number;
  taxBps: number;
  discountBps: number;
}

export interface DocumentRecord {
  id: string;
  kind: DocumentKind;
  status: DocumentStatus;
  number: string;
  issueDate: string;
  dueDate: string;
  currency: string;
  business: BusinessProfile;
  client: Client;
  lineItems: LineItem[];
  shippingMinor: number;
  adjustmentMinor: number;
  notes: string;
  paymentInstructions: string;
  terms: string;
  projectName: string;
  jobsite: string;
  reference: string;
  depositMinor: number;
  progressBillingNote: string;
  /**
   * How the money arrived. Only a receipt uses these: an invoice asks for
   * payment and a receipt records one, and that is the whole difference
   * between the two documents. Stored on the shared record rather than in a
   * separate receipt type so that converting an invoice keeps everything else.
   */
  paymentMethod: string;
  /** What this receipt acknowledges. Below the total, a balance remains. */
  amountPaidMinor: number;
  /**
   * Why a credit note was issued -- a return, an overcharge, a cancelled order.
   * Tax authorities that require credit notes at all generally require the
   * reason, and it is what stops the document being mistaken for a discount.
   */
  creditReason: string;
  /**
   * Where the goods physically went, which is routinely not where the invoice
   * goes. A delivery note sent to a billing address is the single most common
   * reason a delivery is disputed.
   */
  deliveryAddress?: Address;
  /** Carrier and consignment reference: how the recipient traces the shipment. */
  carrier: string;
  consignmentRef: string;
  convertedFrom?: { id: string; kind: DocumentKind; number: string };
  createdAt: string;
  updatedAt: string;
}

export interface NumberingSettings {
  prefixes: Record<DocumentKind, string>;
  nextNumbers: Record<DocumentKind, number>;
}

export interface WorkspaceSnapshot {
  profile: BusinessProfile;
  clients: Client[];
  catalogItems: CatalogItem[];
  documents: DocumentRecord[];
  numbering: NumberingSettings;
}
