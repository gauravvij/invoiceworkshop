export type DocumentKind =
  | 'invoice'
  | 'proforma'
  | 'quotation'
  | 'estimate'
  | 'workOrder'
  | 'purchaseOrder'
  | 'receipt';

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
