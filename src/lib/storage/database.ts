import { defaultNumbering, emptyBusiness } from '../documents/factory';
import { normalizeNumbering } from '../documents/numbering';
import type {
  BusinessProfile,
  CatalogItem,
  Client,
  DocumentRecord,
  NumberingSettings,
  WorkspaceSnapshot,
} from '../documents/types';

const DB_NAME = 'invoice-workshop';
const DB_VERSION = 1;

type StoreName = 'profiles' | 'clients' | 'catalog' | 'documents' | 'settings';

const requestResult = <T>(request: IDBRequest<T>): Promise<T> =>
  new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('The browser storage request failed.'));
  });

const openDatabase = (): Promise<IDBDatabase> =>
  new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) {
      reject(new Error('This browser does not support local document storage.'));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      for (const name of ['profiles', 'clients', 'catalog', 'documents', 'settings'] as StoreName[]) {
        if (!database.objectStoreNames.contains(name)) database.createObjectStore(name, { keyPath: 'id' });
      }
    };
    request.onsuccess = () => resolve(request.result);
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
    const result = await requestResult(operation(transaction.objectStore(name)));
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error('Local storage transaction failed.'));
      transaction.onabort = () => reject(transaction.error ?? new Error('Local storage transaction was cancelled.'));
    });
    return result;
  } finally {
    database.close();
  }
};

const getAll = <T>(store: StoreName) => withStore<T[]>(store, 'readonly', (objectStore) => objectStore.getAll());
const put = <T>(store: StoreName, value: T) => withStore<IDBValidKey>(store, 'readwrite', (objectStore) => objectStore.put(value));
const remove = (store: StoreName, id: string) => withStore<undefined>(store, 'readwrite', (objectStore) => objectStore.delete(id));

export const loadWorkspace = async (): Promise<WorkspaceSnapshot> => {
  const [profiles, clients, catalogItems, documents, settings] = await Promise.all([
    getAll<BusinessProfile>('profiles'),
    getAll<Client>('clients'),
    getAll<CatalogItem>('catalog'),
    getAll<DocumentRecord>('documents'),
    getAll<NumberingSettings & { id: string }>('settings'),
  ]);
  return {
    profile: profiles[0] ?? emptyBusiness(),
    clients,
    catalogItems,
    documents: documents.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
    numbering: normalizeNumbering(settings.find((setting) => setting.id === 'numbering') ?? defaultNumbering()),
  };
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
