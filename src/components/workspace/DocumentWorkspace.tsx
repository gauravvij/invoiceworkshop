import { useEffect, useMemo, useRef, useState } from 'react';
import { trackEvent } from '@/lib/analytics';
import { allowedConversions, convertDocument } from '@/lib/documents/conversions';
import { createDocument, documentLabels, emptyLineItem } from '@/lib/documents/factory';
import { calculateDocument, calculateLine, formatMoney, moneyInputValue, parseMoney } from '@/lib/documents/money';
import { nextDocumentNumber } from '@/lib/documents/numbering';
import type {
  CatalogItem,
  Client,
  DocumentKind,
  DocumentRecord,
  NumberingSettings,
} from '@/lib/documents/types';
import {
  clearLocalData,
  deleteDocument,
  exportWorkspace,
  loadWorkspace,
  saveBusinessProfile,
  saveCatalogItem,
  saveClient,
  saveDocument,
  saveNumbering,
} from '@/lib/storage/database';
import './workspace.css';
import './workspace-a11y.css';

interface Props {
  initialKind: DocumentKind;
  vertical?: 'construction' | 'contractor';
}

type SaveState = 'loading' | 'saved' | 'saving' | 'error';

const currencies = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'NZD', 'INR', 'JPY', 'CHF', 'SGD', 'AED'];

const percentage = (basisPoints: number) => `${basisPoints / 100}%`;
const displayAddress = (client: Client | DocumentRecord['business']) =>
  [client.address.line1, client.address.line2, [client.address.city, client.address.region, client.address.postalCode].filter(Boolean).join(', '), client.address.country]
    .filter(Boolean);

export default function DocumentWorkspace({ initialKind, vertical }: Props) {
  const [document, setDocument] = useState<DocumentRecord>(() => createDocument(initialKind));
  const [numbering, setNumbering] = useState<NumberingSettings | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [saveState, setSaveState] = useState<SaveState>('loading');
  const [message, setMessage] = useState('Loading your saved workspace…');
  const [interactive, setInteractive] = useState(false);
  const [previewVisible, setPreviewVisible] = useState(false);
  const [conversionTarget, setConversionTarget] = useState<DocumentKind | ''>('');
  const hydrated = useRef(false);
  const toolStarted = useRef(false);
  const knownDocumentIds = useRef(new Set<string>());

  const totals = useMemo(() => calculateDocument(document), [document]);
  const conversions = allowedConversions[document.kind] ?? [];

  useEffect(() => {
    let active = true;
    loadWorkspace()
      .then((workspace) => {
        if (!active) return;
        const recent = workspace.documents.find((item) => item.kind === initialKind && item.status === 'draft');
        const next = recent ?? createDocument(initialKind, workspace.profile, workspace.numbering);
        if (vertical && !next.projectName) {
          next.projectName = vertical === 'construction' ? 'Construction project' : 'Contract project';
        }
        knownDocumentIds.current = new Set(workspace.documents.map((item) => item.id));
        setDocument(next);
        setNumbering(workspace.numbering);
        setDocuments(workspace.documents);
        setClients(workspace.clients);
        setCatalog(workspace.catalogItems);
        setSaveState('saved');
        setMessage(recent ? `Restored local draft ${recent.number}.` : 'Ready. Changes save automatically in this browser.');
        setInteractive(true);
        if (workspace.documents.length) trackEvent('returning_workspace_loaded', { document_type: initialKind });
        window.setTimeout(() => {
          hydrated.current = true;
        }, 0);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSaveState('error');
        setMessage(error instanceof Error ? error.message : 'Local storage is unavailable. Export your work before leaving.');
        setInteractive(true);
      });
    return () => {
      active = false;
    };
  }, [initialKind, vertical]);

  useEffect(() => {
    if (!hydrated.current || !numbering) return;
    setSaveState('saving');
    setMessage('Saving locally…');
    const timer = window.setTimeout(async () => {
      try {
        const stamped = { ...document, updatedAt: new Date().toISOString() };
        await Promise.all([
          saveDocument(stamped),
          saveBusinessProfile(document.business),
          document.client.name.trim() ? saveClient({ ...document.client, updatedAt: new Date().toISOString() }) : Promise.resolve(),
        ]);
        if (!knownDocumentIds.current.has(document.id)) {
          knownDocumentIds.current.add(document.id);
          const next = nextDocumentNumber(numbering, document.kind).settings;
          setNumbering(next);
          await saveNumbering(next);
        }
        setDocuments((current) => [stamped, ...current.filter((item) => item.id !== stamped.id)]);
        setSaveState('saved');
        setMessage('Saved locally on this device.');
      } catch (error) {
        setSaveState('error');
        setMessage(error instanceof Error ? error.message : 'Autosave failed. Export a backup before leaving.');
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [document, numbering]);

  const mutate = (updater: (current: DocumentRecord) => DocumentRecord) => {
    if (!toolStarted.current) {
      toolStarted.current = true;
      trackEvent('tool_started', { document_type: document.kind });
    }
    setDocument((current) => updater(current));
  };

  const updateDocument = <K extends keyof DocumentRecord>(key: K, value: DocumentRecord[K]) =>
    mutate((current) => ({ ...current, [key]: value }));

  const updateBusiness = (key: keyof DocumentRecord['business'], value: string | number) =>
    mutate((current) => ({ ...current, business: { ...current.business, [key]: value } }));

  const updateBusinessAddress = (key: keyof DocumentRecord['business']['address'], value: string) =>
    mutate((current) => ({
      ...current,
      business: { ...current.business, address: { ...current.business.address, [key]: value } },
    }));

  const updateClient = (key: keyof Client, value: string) =>
    mutate((current) => ({ ...current, client: { ...current.client, [key]: value } }));

  const updateClientAddress = (key: keyof Client['address'], value: string) =>
    mutate((current) => ({ ...current, client: { ...current.client, address: { ...current.client.address, [key]: value } } }));

  const updateLine = (id: string, changes: Partial<DocumentRecord['lineItems'][number]>) =>
    mutate((current) => ({
      ...current,
      lineItems: current.lineItems.map((line) => (line.id === id ? { ...line, ...changes } : line)),
    }));

  const loadClient = (id: string) => {
    const client = clients.find((item) => item.id === id);
    if (client) mutate((current) => ({ ...current, client: structuredClone(client) }));
  };

  const addCatalogItem = (id: string) => {
    const item = catalog.find((entry) => entry.id === id);
    if (!item) return;
    mutate((current) => ({
      ...current,
      lineItems: [
        ...current.lineItems,
        {
          id: crypto.randomUUID(),
          description: item.description || item.name,
          quantity: '1',
          unit: item.unit,
          unitPriceMinor: item.unitPriceMinor,
          taxBps: item.taxBps,
          discountBps: 0,
        },
      ],
    }));
  };

  const rememberItem = async (line: DocumentRecord['lineItems'][number]) => {
    if (!line.description.trim()) {
      setMessage('Add an item description before saving it to the catalog.');
      return;
    }
    const now = new Date().toISOString();
    const item: CatalogItem = {
      id: crypto.randomUUID(),
      name: line.description.slice(0, 80),
      description: line.description,
      unitPriceMinor: line.unitPriceMinor,
      taxBps: line.taxBps,
      unit: line.unit,
      createdAt: now,
      updatedAt: now,
    };
    await saveCatalogItem(item);
    setCatalog((current) => [...current, item]);
    setMessage('Item saved to your local catalog.');
  };

  const saveNow = async () => {
    setSaveState('saving');
    const isNewDocument = !knownDocumentIds.current.has(document.id);
    const nextSettings = isNewDocument && numbering
      ? nextDocumentNumber(numbering, document.kind).settings
      : numbering;
    if (isNewDocument) knownDocumentIds.current.add(document.id);
    try {
      const stamped = { ...document, updatedAt: new Date().toISOString() };
      await Promise.all([
        saveDocument(stamped),
        saveBusinessProfile(document.business),
        document.client.name.trim() ? saveClient({ ...document.client, updatedAt: new Date().toISOString() }) : Promise.resolve(),
        isNewDocument && nextSettings ? saveNumbering(nextSettings) : Promise.resolve(),
      ]);
      if (isNewDocument && nextSettings) setNumbering(nextSettings);
      setDocuments((current) => [stamped, ...current.filter((item) => item.id !== stamped.id)]);
      setClients((current) => document.client.name.trim() ? [document.client, ...current.filter((item) => item.id !== document.client.id)] : current);
      setSaveState('saved');
      setMessage(`${documentLabels[document.kind]} saved locally.`);
      trackEvent('document_saved', { document_type: document.kind });
    } catch (error) {
      if (isNewDocument) knownDocumentIds.current.delete(document.id);
      setSaveState('error');
      setMessage(error instanceof Error ? error.message : 'Could not save this document.');
    }
  };

  const newDocument = () => {
    if (!numbering) return;
    const next = createDocument(initialKind, document.business, numbering);
    if (vertical) next.projectName = vertical === 'construction' ? 'Construction project' : 'Contract project';
    setDocument(next);
    setMessage(`New ${documentLabels[initialKind].toLowerCase()} started.`);
    toolStarted.current = false;
  };

  const duplicate = async () => {
    if (!numbering) return;
    const currentIsNew = !knownDocumentIds.current.has(document.id);
    const availableSettings = currentIsNew
      ? nextDocumentNumber(numbering, document.kind).settings
      : numbering;
    const allocated = nextDocumentNumber(availableSettings, document.kind);
    const now = new Date().toISOString();
    const copy = {
      ...structuredClone(document),
      id: crypto.randomUUID(),
      number: allocated.number,
      status: 'draft' as const,
      createdAt: now,
      updatedAt: now,
    };
    await Promise.all([
      currentIsNew ? saveDocument(document) : Promise.resolve(),
      saveDocument(copy),
      saveNumbering(allocated.settings),
    ]);
    if (currentIsNew) knownDocumentIds.current.add(document.id);
    knownDocumentIds.current.add(copy.id);
    setNumbering(allocated.settings);
    setDocuments((current) => [copy, ...current]);
    setDocument(copy);
    setMessage(`Duplicated as ${copy.number}.`);
    trackEvent('document_duplicated', { document_type: copy.kind });
  };

  const convert = async () => {
    if (!conversionTarget || !numbering) return;
    const converted = convertDocument(document, conversionTarget, numbering);
    const allocated = nextDocumentNumber(numbering, conversionTarget);
    converted.number = allocated.number;
    await Promise.all([saveDocument(converted), saveNumbering(allocated.settings)]);
    knownDocumentIds.current.add(converted.id);
    setNumbering(allocated.settings);
    setDocuments((current) => [converted, ...current]);
    setDocument(converted);
    setConversionTarget('');
    setMessage(`Converted to ${documentLabels[converted.kind]} ${converted.number}.`);
    trackEvent('document_converted', {
      document_type: converted.kind,
      conversion_from: document.kind,
      conversion_to: converted.kind,
    });
  };

  const downloadPdf = async () => {
    setMessage('Preparing your PDF in this browser…');
    try {
      const { downloadDocumentPdf } = await import('@/lib/documents/pdf');
      await downloadDocumentPdf(document);
      setMessage('PDF downloaded. Your document was created on this device.');
      trackEvent('pdf_downloaded', { document_type: document.kind });
    } catch {
      setMessage('PDF creation failed. Try Print as a fallback.');
    }
  };

  const handleLogo = (file?: File) => {
    if (!file) return;
    if (!file.type.startsWith('image/') || file.size > 2_000_000) {
      setMessage('Choose a PNG, JPEG, or WebP logo smaller than 2 MB.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => updateBusiness('logoDataUrl', String(reader.result));
    reader.onerror = () => setMessage('The logo could not be read.');
    reader.readAsDataURL(file);
  };

  const clearEverything = async () => {
    if (!window.confirm('Permanently clear all locally saved business details, customers, items, and documents from this browser?')) return;
    await clearLocalData();
    localStorage.removeItem('invoice-workshop-ui');
    window.location.reload();
  };

  const removeCurrentDocument = async () => {
    if (!window.confirm(`Delete ${document.number} from this browser?`)) return;
    await deleteDocument(document.id);
    setDocuments((current) => current.filter((item) => item.id !== document.id));
    newDocument();
  };

  return (
    <section className="workspace" aria-label={`${documentLabels[initialKind]} workspace`} aria-busy={!interactive}>
      <fieldset className="workspace-gate" disabled={!interactive}>
      <div className="workspace-toolbar no-print">
        <div>
          <strong>Your local workspace</strong>
          <span className={`save-state save-state--${saveState}`} aria-live="polite">{message}</span>
        </div>
        <div className="toolbar-actions">
          <button type="button" className="button button--quiet mobile-preview-toggle" onClick={() => setPreviewVisible((value) => !value)}>
            {previewVisible ? 'Show editor' : 'Show preview'}
          </button>
          <button type="button" className="button button--quiet" onClick={newDocument}>New</button>
          <button type="button" className="button button--quiet" onClick={saveNow}>Save now</button>
          <button type="button" className="button button--primary toolbar-download-cta" onClick={downloadPdf}>Download PDF</button>
        </div>
      </div>

      <div className={`workspace-grid ${previewVisible ? 'workspace-grid--preview' : ''}`}>
        <div className="editor no-print">
          <EditorSection title="Your business" hint="Saved locally and reused next time.">
            <div className="form-grid">
              <Field label="Business name" required value={document.business.name} onChange={(value) => updateBusiness('name', value)} placeholder="Acme Studio LLC" />
              <Field label="Email" type="email" value={document.business.email} onChange={(value) => updateBusiness('email', value)} placeholder="billing@example.com" />
              <Field label="Phone" type="tel" value={document.business.phone} onChange={(value) => updateBusiness('phone', value)} />
              <Field label="Tax / business ID" value={document.business.taxId} onChange={(value) => updateBusiness('taxId', value)} />
              <Field label="Street address" value={document.business.address.line1} onChange={(value) => updateBusinessAddress('line1', value)} />
              <Field label="City" value={document.business.address.city} onChange={(value) => updateBusinessAddress('city', value)} />
              <Field label="State / region" value={document.business.address.region} onChange={(value) => updateBusinessAddress('region', value)} />
              <Field label="Postal code" value={document.business.address.postalCode} onChange={(value) => updateBusinessAddress('postalCode', value)} inputMode="numeric" />
              <label className="field field--wide">
                <span>Logo <small>PNG, JPEG or WebP · max 2 MB</small></span>
                <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => handleLogo(event.target.files?.[0])} />
              </label>
            </div>
          </EditorSection>

          <EditorSection title={document.kind === 'purchaseOrder' ? 'Supplier' : 'Customer'} hint="Choose a saved contact or enter a new one.">
            {clients.length > 0 && (
              <label className="field field--wide">
                <span>Saved contacts</span>
                <select value="" onChange={(event) => loadClient(event.target.value)}>
                  <option value="">Select a saved contact…</option>
                  {clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
                </select>
              </label>
            )}
            <div className="form-grid">
              <Field label="Name" required value={document.client.name} onChange={(value) => updateClient('name', value)} placeholder="Customer or company" />
              <Field label="Email" type="email" value={document.client.email} onChange={(value) => updateClient('email', value)} />
              <Field label="Phone" type="tel" value={document.client.phone} onChange={(value) => updateClient('phone', value)} />
              <Field label="Tax ID" value={document.client.taxId} onChange={(value) => updateClient('taxId', value)} />
              <Field label="Street address" value={document.client.address.line1} onChange={(value) => updateClientAddress('line1', value)} />
              <Field label="City" value={document.client.address.city} onChange={(value) => updateClientAddress('city', value)} />
              <Field label="State / region" value={document.client.address.region} onChange={(value) => updateClientAddress('region', value)} />
              <Field label="Postal code" value={document.client.address.postalCode} onChange={(value) => updateClientAddress('postalCode', value)} inputMode="numeric" />
            </div>
          </EditorSection>

          <EditorSection title={`${documentLabels[document.kind]} details`}>
            <div className="form-grid form-grid--three">
              <Field label="Document number" required value={document.number} onChange={(value) => updateDocument('number', value)} />
              <Field label="Issue date" type="date" value={document.issueDate} onChange={(value) => updateDocument('issueDate', value)} />
              <Field label={document.kind === 'receipt' ? 'Paid date' : 'Due / valid until'} type="date" value={document.dueDate} onChange={(value) => updateDocument('dueDate', value)} />
              <label className="field">
                <span>Currency</span>
                <select value={document.currency} onChange={(event) => updateDocument('currency', event.target.value)}>
                  {currencies.map((currency) => <option key={currency}>{currency}</option>)}
                </select>
              </label>
              <Field label="Reference / PO" value={document.reference} onChange={(value) => updateDocument('reference', value)} />
              <label className="field">
                <span>Status</span>
                <select value={document.status} onChange={(event) => updateDocument('status', event.target.value as DocumentRecord['status'])}>
                  <option value="draft">Draft</option>
                  <option value="completed">Completed</option>
                  <option value="paid">Paid</option>
                </select>
              </label>
            </div>
            {(vertical || ['workOrder', 'estimate'].includes(document.kind)) && (
              <div className="form-grid section-subgrid">
                <Field label="Project / job" value={document.projectName} onChange={(value) => updateDocument('projectName', value)} />
                <Field label="Jobsite" value={document.jobsite} onChange={(value) => updateDocument('jobsite', value)} />
                <MoneyField label="Deposit paid" minor={document.depositMinor} currency={document.currency} onChange={(value) => updateDocument('depositMinor', value)} />
                <Field label="Progress / change-order note" value={document.progressBillingNote} onChange={(value) => updateDocument('progressBillingNote', value)} />
              </div>
            )}
          </EditorSection>

          <EditorSection title="Items" hint="Totals, taxes and discounts are calculated automatically.">
            {catalog.length > 0 && (
              <label className="field catalog-picker">
                <span>Add a saved product or service</span>
                <select value="" onChange={(event) => addCatalogItem(event.target.value)}>
                  <option value="">Choose an item…</option>
                  {catalog.map((item) => <option key={item.id} value={item.id}>{item.name} · {formatMoney(item.unitPriceMinor, document.currency)}</option>)}
                </select>
              </label>
            )}
            <div className="line-items">
              {document.lineItems.map((line, index) => (
                <div className="line-item" key={line.id}>
                  <div className="line-item-heading">
                    <strong>Item {index + 1}</strong>
                    <div>
                      <button type="button" className="text-button" onClick={() => rememberItem(line)}>Save item</button>
                      {document.lineItems.length > 1 && <button type="button" className="text-button text-button--danger" onClick={() => mutate((current) => ({ ...current, lineItems: current.lineItems.filter((item) => item.id !== line.id) }))}>Remove</button>}
                    </div>
                  </div>
                  <Field label="Description" value={line.description} onChange={(value) => updateLine(line.id, { description: value })} placeholder={vertical === 'construction' ? 'Labor, materials, equipment…' : 'Product or service'} />
                  <div className="line-item-grid">
                    <Field label="Quantity" inputMode="decimal" value={line.quantity} onChange={(value) => updateLine(line.id, { quantity: value })} />
                    <Field label="Unit" value={line.unit} onChange={(value) => updateLine(line.id, { unit: value })} />
                    <MoneyField label="Unit price" minor={line.unitPriceMinor} currency={document.currency} onChange={(value) => updateLine(line.id, { unitPriceMinor: value })} />
                    <Field label="Discount %" inputMode="decimal" value={String(line.discountBps / 100)} onChange={(value) => updateLine(line.id, { discountBps: Math.max(0, Math.round(Number(value || 0) * 100)) })} />
                    <Field label="Tax %" inputMode="decimal" value={String(line.taxBps / 100)} onChange={(value) => updateLine(line.id, { taxBps: Math.max(0, Math.round(Number(value || 0) * 100)) })} />
                    <div className="line-total"><span>Line total</span><strong>{formatMoney(calculateLine(line).totalMinor, document.currency)}</strong></div>
                  </div>
                </div>
              ))}
            </div>
            <button type="button" className="button button--add" onClick={() => mutate((current) => ({ ...current, lineItems: [...current.lineItems, emptyLineItem(current.business.defaultTaxBps)] }))}>+ Add line item</button>
            <div className="form-grid totals-inputs">
              <MoneyField label="Shipping" minor={document.shippingMinor} currency={document.currency} onChange={(value) => updateDocument('shippingMinor', value)} />
              <MoneyField label="Adjustment (+/−)" minor={document.adjustmentMinor} currency={document.currency} onChange={(value) => updateDocument('adjustmentMinor', value)} />
            </div>
          </EditorSection>

          <EditorSection title="Notes and payment">
            <label className="field field--wide"><span>Notes</span><textarea rows={3} value={document.notes} onChange={(event) => updateDocument('notes', event.target.value)} placeholder="Thank you for your business." /></label>
            <label className="field field--wide"><span>Payment instructions</span><textarea rows={3} value={document.paymentInstructions} onChange={(event) => updateDocument('paymentInstructions', event.target.value)} placeholder="Bank transfer, check, or payment link details" /></label>
            <label className="field field--wide"><span>Terms</span><textarea rows={3} value={document.terms} onChange={(event) => updateDocument('terms', event.target.value)} /></label>
          </EditorSection>

          <EditorSection title="Workspace tools" hint="Backups and saved records remain on this device.">
            {documents.length > 0 && (
              <label className="field field--wide">
                <span>Open a saved document</span>
                <select value={document.id} onChange={(event) => {
                  const saved = documents.find((item) => item.id === event.target.value);
                  if (saved) setDocument(structuredClone(saved));
                }}>
                  {!documents.some((item) => item.id === document.id) && <option value={document.id}>{document.number} · current draft</option>}
                  {documents.map((item) => <option key={item.id} value={item.id}>{item.number} · {documentLabels[item.kind]} · {item.client.name || 'No customer'}</option>)}
                </select>
              </label>
            )}
            <div className="workspace-actions">
              <button type="button" className="button button--quiet" onClick={duplicate}>Duplicate</button>
              <button type="button" className="button button--quiet" onClick={() => window.print()}>Print</button>
              <button type="button" className="button button--quiet" onClick={exportWorkspace}>Export backup</button>
              {knownDocumentIds.current.has(document.id) && <button type="button" className="button button--danger" onClick={removeCurrentDocument}>Delete document</button>}
            </div>
            {conversions.length > 0 && (
              <div className="conversion-row">
                <label className="field"><span>Convert this document</span><select value={conversionTarget} onChange={(event) => setConversionTarget(event.target.value as DocumentKind)}><option value="">Choose format…</option>{conversions.map((kind) => <option key={kind} value={kind}>{documentLabels[kind]}</option>)}</select></label>
                <button type="button" className="button button--secondary" disabled={!conversionTarget} onClick={convert}>Convert</button>
              </div>
            )}
            <details className="danger-zone"><summary>Local data controls</summary><p>Clearing data permanently removes every profile, contact, catalog item, and document saved by Invoice Workshop in this browser.</p><button type="button" className="button button--danger" onClick={clearEverything}>Clear all local data</button></details>
          </EditorSection>
        </div>

        <DocumentPreview document={document} totals={totals} />
      </div>
      <div className="mobile-output-bar no-print">
        <span>Ready to finish?</span>
        <button type="button" className="button button--primary" onClick={downloadPdf}>Download PDF</button>
      </div>
      </fieldset>
    </section>
  );
}

function EditorSection({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return <fieldset className="editor-section"><legend>{title}</legend>{hint && <p className="section-hint">{hint}</p>}{children}</fieldset>;
}

function Field({ label, value, onChange, type = 'text', required, placeholder, inputMode }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
  inputMode?: 'text' | 'email' | 'tel' | 'url' | 'numeric' | 'decimal' | 'search' | 'none';
}) {
  return <label className="field"><span>{label}{required && <em aria-hidden="true"> *</em>}</span><input type={type} value={value} required={required} placeholder={placeholder} inputMode={inputMode} onChange={(event) => onChange(event.target.value)} /></label>;
}

function MoneyField({ label, minor, currency, onChange }: { label: string; minor: number; currency: string; onChange: (minor: number) => void }) {
  return <label className="field"><span>{label} <small>{currency}</small></span><input type="text" inputMode="decimal" value={moneyInputValue(minor, currency)} onChange={(event) => onChange(parseMoney(event.target.value, currency))} /></label>;
}

function DocumentPreview({ document, totals }: { document: DocumentRecord; totals: ReturnType<typeof calculateDocument> }) {
  return (
    <aside className="preview-wrap" aria-label="Live document preview">
      <div className="preview-sticky">
        <div className="preview-label no-print"><span>Live preview</span><span>Letter · PDF ready</span></div>
        <article className="document-preview" id="document-preview">
          <header className="document-header">
            <div className="business-brand">
              {document.business.logoDataUrl && <img src={document.business.logoDataUrl} alt={`${document.business.name || 'Business'} logo`} />}
              <strong>{document.business.name || 'Your business'}</strong>
              {displayAddress(document.business).map((line) => <span key={line}>{line}</span>)}
              {document.business.email && <span>{document.business.email}</span>}
              {document.business.phone && <span>{document.business.phone}</span>}
            </div>
            <div className="document-identity">
              <h2>{documentLabels[document.kind]}</h2>
              <strong>{document.number}</strong>
              <span className={`status-chip status-chip--${document.status}`}>{document.status}</span>
            </div>
          </header>
          <div className="document-parties">
            <div><small>{document.kind === 'purchaseOrder' ? 'SUPPLIER' : 'BILL TO'}</small><strong>{document.client.name || 'Customer name'}</strong>{displayAddress(document.client).map((line) => <span key={line}>{line}</span>)}{document.client.email && <span>{document.client.email}</span>}</div>
            <dl><div><dt>Issue date</dt><dd>{document.issueDate}</dd></div><div><dt>{document.kind === 'receipt' ? 'Paid date' : 'Due / valid until'}</dt><dd>{document.dueDate}</dd></div>{document.reference && <div><dt>Reference</dt><dd>{document.reference}</dd></div>}</dl>
          </div>
          {(document.projectName || document.jobsite) && <div className="project-strip"><span><small>PROJECT</small>{document.projectName}</span><span><small>JOBSITE</small>{document.jobsite}</span></div>}
          <div className="preview-table-scroll">
            <table className="preview-table">
              <thead><tr><th>Description</th><th>Qty</th><th>Rate</th><th>Tax</th><th>Amount</th></tr></thead>
              <tbody>{document.lineItems.map((line) => <tr key={line.id}><td>{line.description || 'Item description'}{line.discountBps > 0 && <small>{percentage(line.discountBps)} discount</small>}</td><td>{line.quantity} {line.unit}</td><td>{formatMoney(line.unitPriceMinor, document.currency)}</td><td>{percentage(line.taxBps)}</td><td>{formatMoney(calculateLine(line).totalMinor, document.currency)}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="preview-totals">
            <div><span>Subtotal</span><strong>{formatMoney(totals.subtotalMinor, document.currency)}</strong></div>
            {totals.discountMinor > 0 && <div><span>Discount</span><strong>−{formatMoney(totals.discountMinor, document.currency)}</strong></div>}
            <div><span>Tax</span><strong>{formatMoney(totals.taxMinor, document.currency)}</strong></div>
            {totals.shippingMinor !== 0 && <div><span>Shipping</span><strong>{formatMoney(totals.shippingMinor, document.currency)}</strong></div>}
            {totals.adjustmentMinor !== 0 && <div><span>Adjustment</span><strong>{formatMoney(totals.adjustmentMinor, document.currency)}</strong></div>}
            <div className="grand-total"><span>Total</span><strong>{formatMoney(totals.totalMinor, document.currency)}</strong></div>
            {totals.depositMinor > 0 && <><div><span>Deposit paid</span><strong>−{formatMoney(totals.depositMinor, document.currency)}</strong></div><div className="balance-due"><span>Balance due</span><strong>{formatMoney(totals.balanceDueMinor, document.currency)}</strong></div></>}
          </div>
          {(document.notes || document.paymentInstructions || document.terms) && <footer className="document-notes">
            {document.notes && <div><strong>Notes</strong><p>{document.notes}</p></div>}
            {document.paymentInstructions && <div><strong>Payment instructions</strong><p>{document.paymentInstructions}</p></div>}
            {document.terms && <div><strong>Terms</strong><p>{document.terms}</p></div>}
          </footer>}
        </article>
      </div>
    </aside>
  );
}
