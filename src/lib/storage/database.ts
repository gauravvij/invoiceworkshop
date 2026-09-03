import { createDocument, emptyAddress, emptyBusiness } from '../documents/factory';
import { normalizeNumbering } from '../documents/numbering';
import type {
  BusinessProfile,
  CatalogItem,
  Client,
  DocumentRecord,
  NumberingSettings,
  WorkspaceSnapshot,
} from '../documents/types';

export const DB_NAME = 'invoice-workshop';
export const DB_VERSION = 2;

type StoreName = 'profiles' | 'clients' | 'catalog' | 'documents' | 'settings';

const documentKinds = new Set(['invoice', 'proforma', 'quotation', 'estimate', 'workOrder', 'purchaseOrder', 'receipt', 'creditNote', 'timesheet', 'deliveryNote']);
const documentStatuses = new Set(['draft', 'completed', 'paid']);
const record = (value: unknown): Record<string, unknown> | undefined =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
const text = (value: unknown, fallback = '') => typeof value === 'string' ? value : fallback;
const amount = (value: unknown, fallback = 0) => typeof value === 'number' && Number.isFinite(value) ? Math.trunc(value) : fallback;

const normalizeAddress = (value: unknown) => {
  const source = record(value);
  const fallback = emptyAddress();
  return {
    line1: text(source?.line1, fallback.line1),
    line2: text(source?.line2, fallback.line2),
    city: text(source?.city, fallback.city),
    region: text(source?.region, fallback.region),
    postalCode: text(source?.postalCode, fallback.postalCode),
    country: text(source?.country, fallback.country),
  };
};

const normalizeBusiness = (value: unknown): BusinessProfile => {
  const source = record(value);
  const fallback = emptyBusiness();
  return {
    ...fallback,
    id: text(source?.id, fallback.id),
    name: text(source?.name),
    email: text(source?.email),
    phone: text(source?.phone),
    website: text(source?.website),
    taxId: text(source?.taxId),
    address: normalizeAddress(source?.address),
    logoDataUrl: typeof source?.logoDataUrl === 'string' && source.logoDataUrl.startsWith('data:image/')
      ? source.logoDataUrl
      : undefined,
    paymentInstructions: text(source?.paymentInstructions),
    defaultCurrency: text(source?.defaultCurrency, fallback.defaultCurrency),
    defaultTaxBps: amount(source?.defaultTaxBps, fallback.defaultTaxBps),
    defaultTerms: text(source?.defaultTerms, fallback.defaultTerms),
  };
};

const normalizeClient = (value: unknown): Client | undefined => {
  const source = record(value);
  const id = text(source?.id);
  if (!source || !id) return undefined;
  const now = new Date().toISOString();
  return {
    id,
    name: text(source.name),
    email: text(source.email),
    phone: text(source.phone),
    taxId: text(source.taxId),
    address: normalizeAddress(source.address),
    createdAt: text(source.createdAt, now),
    updatedAt: text(source.updatedAt, now),
  };
};

const normalizeCatalogItem = (value: unknown): CatalogItem | undefined => {
  const source = record(value);
  const id = text(source?.id);
  if (!source || !id) return undefined;
  const now = new Date().toISOString();
  return {
    id,
    name: text(source.name),
    description: text(source.description),
    unitPriceMinor: amount(source.unitPriceMinor),
    taxBps: amount(source.taxBps),
    unit: text(source.unit, 'item'),
    createdAt: text(source.createdAt, now),
    updatedAt: text(source.updatedAt, now),
  };
};

const normalizeDocument = (value: unknown): DocumentRecord | undefined => {
  const source = record(value);
  const id = text(source?.id);
  const kind = text(source?.kind);
  if (!source || !id || !documentKinds.has(kind)) return undefined;
  const fallback = createDocument(kind as DocumentRecord['kind']);
  const lines = Array.isArray(source.lineItems)
    ? source.lineItems.flatMap((entry) => {
      const line = record(entry);
      if (!line) return [];
      return [{
        id: text(line.id, crypto.randomUUID()),
        description: text(line.description),
        // Absent on every kind but a timesheet, and absent on documents saved
        // before timesheets existed, so it reads back undefined rather than ''.
        serviceDate: typeof line.serviceDate === 'string' && line.serviceDate
          ? line.serviceDate : undefined,
        quantityOrdered: typeof line.quantityOrdered === 'string' && line.quantityOrdered
          ? line.quantityOrdered : undefined,
        quantity: text(line.quantity, '1'),
        unit: text(line.unit, 'item'),
        unitPriceMinor: amount(line.unitPriceMinor),
        taxBps: amount(line.taxBps),
        discountBps: amount(line.discountBps),
      }];
    })
    : [];
  return {
    ...fallback,
    id,
    kind: kind as DocumentRecord['kind'],
    status: documentStatuses.has(text(source.status)) ? text(source.status) as DocumentRecord['status'] : fallback.status,
    number: text(source.number, fallback.number),
    issueDate: text(source.issueDate, fallback.issueDate),
    dueDate: text(source.dueDate, fallback.dueDate),
    currency: text(source.currency, fallback.currency),
    business: normalizeBusiness(source.business),
    client: normalizeClient(source.client) ?? fallback.client,
    lineItems: lines.length ? lines : fallback.lineItems,
    shippingMinor: amount(source.shippingMinor),
    adjustmentMinor: amount(source.adjustmentMinor),
    notes: text(source.notes),
    paymentInstructions: text(source.paymentInstructions),
    terms: text(source.terms, fallback.terms),
    projectName: text(source.projectName),
    jobsite: text(source.jobsite),
    reference: text(source.reference),
    depositMinor: amount(source.depositMinor),
    progressBillingNote: text(source.progressBillingNote),
    // Documents saved before receipts had payment fields simply lack these, so
    // they read back at their defaults rather than failing normalisation. That
    // is the whole migration: everything here already tolerates a missing key.
    paymentMethod: text(source.paymentMethod),
    amountPaidMinor: amount(source.amountPaidMinor),
    creditReason: text(source.creditReason),
    deliveryAddress: source.deliveryAddress ? normalizeAddress(source.deliveryAddress) : undefined,
    carrier: text(source.carrier),
    consignmentRef: text(source.consignmentRef),
    convertedFrom: record(source.convertedFrom) as DocumentRecord['convertedFrom'] | undefined,
    createdAt: text(source.createdAt, fallback.createdAt),
    updatedAt: text(source.updatedAt, fallback.updatedAt),
  };
};

export const normalizeWorkspaceRecords = (input: {
  profiles?: unknown[];
  clients?: unknown[];
  catalogItems?: unknown[];
  documents?: unknown[];
  settings?: unknown[];
}): WorkspaceSnapshot => {
  const clients = (input.clients ?? []).flatMap((value) => normalizeClient(value) ?? []);
  const catalogItems = (input.catalogItems ?? []).flatMap((value) => normalizeCatalogItem(value) ?? []);
  const documents = (input.documents ?? [])
    .flatMap((value) => normalizeDocument(value) ?? [])
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  const numbering = record((input.settings ?? []).find((value) => record(value)?.id === 'numbering'));
  return {
    profile: normalizeBusiness(input.profiles?.[0]),
    clients,
    catalogItems,
    documents,
    numbering: normalizeNumbering(numbering),
  };
};

const openDatabase = (): Promise<IDBDatabase> =>
  new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) {
      reject(new Error('This browser does not support local document storage.'));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      try {
        const database = request.result;
        for (const name of ['profiles', 'clients', 'catalog', 'documents', 'settings'] as StoreName[]) {
          if (!database.objectStoreNames.contains(name)) database.createObjectStore(name, { keyPath: 'id' });
        }
        request.transaction?.objectStore('settings').put({
          id: 'schema',
          version: DB_VERSION,
          migratedAt: new Date().toISOString(),
        });
      } catch {
        request.transaction?.abort();
      }
    };
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => reject(request.error ?? new Error('Could not open local document storage.'));
    request.onblocked = () => reject(new Error('Close other Invoice Workshop tabs and try again.'));
  });

const withStore = async <T>(
  name: StoreName,
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> => {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(name, mode);
    const request = operation(transaction.objectStore(name));
    return await new Promise<T>((resolve, reject) => {
      transaction.oncomplete = () => resolve(request.result);
      transaction.onerror = () => reject(transaction.error ?? new Error('Local storage transaction failed.'));
      transaction.onabort = () => reject(transaction.error ?? new Error('Local storage transaction was cancelled.'));
      request.onerror = () => reject(request.error ?? new Error('The browser storage request failed.'));
    });
  } finally {
    database.close();
  }
};

const getAll = <T>(store: StoreName) => withStore<T[]>(store, 'readonly', (objectStore) => objectStore.getAll());
const put = <T>(store: StoreName, value: T) => withStore<IDBValidKey>(store, 'readwrite', (objectStore) => objectStore.put(value));
const remove = (store: StoreName, id: string) => withStore<undefined>(store, 'readwrite', (objectStore) => objectStore.delete(id));

export const loadWorkspace = async (): Promise<WorkspaceSnapshot> => {
  // Open the stores in sequence so a brand-new database completes its upgrade
  // before another connection is requested. Firefox is particularly strict
  // about concurrent opens while an IndexedDB schema is being created.
  const profiles = await getAll<unknown>('profiles');
  const clients = await getAll<unknown>('clients');
  const catalogItems = await getAll<unknown>('catalog');
  const documents = await getAll<unknown>('documents');
  const settings = await getAll<unknown>('settings');
  return normalizeWorkspaceRecords({ profiles, clients, catalogItems, documents, settings });
};

export const saveBusinessProfile = (profile: BusinessProfile) => put('profiles', profile);
export const saveClient = (client: Client) => put('clients', client);
export const deleteClient = (id: string) => remove('clients', id);
export const saveCatalogItem = (item: CatalogItem) => put('catalog', item);
export const saveDocument = (document: DocumentRecord) => put('documents', document);
export const deleteDocument = (id: string) => remove('documents', id);
export const saveNumbering = (numbering: NumberingSettings) => put('settings', { id: 'numbering', ...numbering });

export const clearLocalData = (): Promise<void> =>
  new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(DB_NAME);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error ?? new Error('Could not clear local data.'));
    request.onblocked = () => reject(new Error('Close other Invoice Workshop tabs and try again.'));
  });

export const exportWorkspace = async (): Promise<void> => {
  const snapshot = await loadWorkspace();
  const blob = new Blob([JSON.stringify({ schemaVersion: DB_VERSION, exportedAt: new Date().toISOString(), ...snapshot }, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `invoice-workshop-backup-${new Date().toISOString().slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
};
