import type { DocumentKind } from '@/lib/documents/types';

export interface GeneratorContent {
  path: string;
  kind: DocumentKind;
  vertical?: 'construction' | 'contractor';
  title: string;
  description: string;
  h1: string;
  intro: string;
  eyebrow: string;
  reassurance: string;
  sections: Array<{ heading: string; paragraphs: string[]; bullets?: string[] }>;
  related: Array<{ href: string; label: string; text: string }>;
}

export const generators: Record<string, GeneratorContent> = {
  home: {
    path: '/', kind: 'invoice', title: 'Free Invoice Generator & Invoice Maker | Invoice Workshop',
    description: 'Create a professional invoice for free with saved business details, customers, line items and instant PDF download. No signup required.',
    h1: 'Free Invoice Generator', eyebrow: 'Professional invoices without the admin',
    intro: 'Create professional invoices online for free. No signup required. Add your logo, items, taxes and payment details, then download a PDF instantly.',
    reassurance: 'Your business and customer data stays in your browser.',
    sections: [
      { heading: 'Create an invoice online', paragraphs: ['Start with the working editor above. Add your business and customer, list the products or services supplied, set tax and discounts, then review the live preview before downloading or printing. Your draft saves automatically on this device.'] },
      { heading: 'What should an invoice include?', paragraphs: ['A clear invoice normally identifies the seller and customer, uses a unique invoice number, states issue and due dates, itemizes the work or goods, and shows the currency, taxes, discounts and amount due. Payment instructions and concise terms help the customer understand what to do next.'], bullets: ['Seller and customer contact details', 'Unique invoice number and dates', 'Item descriptions, quantities and rates', 'Subtotal, discounts, tax and total', 'Payment instructions and terms'] },
      { heading: 'No signup, but it remembers you', paragraphs: ['Invoice Workshop stores substantive workspace data in your browser using IndexedDB. Return on the same browser and device to reuse your business profile, customers and common items. Nothing is uploaded to an Invoice Workshop server in this version. Export a local backup whenever you want an extra copy.'] },
      { heading: 'Invoice generator vs. invoice template', paragraphs: ['A static template gives you a layout to edit manually. This invoice maker calculates totals, maintains reusable records, previews the finished document and creates a PDF. It keeps the speed of a template while behaving more like persistent invoicing software—without an account.'] },
    ],
    related: [
      { href: '/proforma-invoice-generator/', label: 'Proforma Invoice Generator', text: 'Prepare a preliminary invoice and convert it later.' },
      { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Send a clear business quotation before work begins.' },
      { href: '/estimate-generator/', label: 'Estimate Generator', text: 'Outline expected work and pricing, then convert it.' },
      { href: '/work-order-generator/', label: 'Work Order Generator', text: 'Document approved work and turn it into an invoice.' },
      { href: '/purchase-order-generator/', label: 'Purchase Order Generator', text: 'Create purchasing paperwork for a supplier.' },
      { href: '/construction-invoice-template/', label: 'Construction Invoice Template', text: 'Bill labor, materials, deposits and project work.' },
      { href: '/contractor-invoice-template/', label: 'Contractor Invoice Template', text: 'Create a practical contractor-specific invoice.' },
    ],
  },
  proforma: {
    path: '/proforma-invoice-generator/', kind: 'proforma', title: 'Free Proforma Invoice Generator | Invoice Workshop',
    description: 'Create a free proforma invoice, save it privately in your browser and convert it into a final invoice when ready. No signup required.',
    h1: 'Free Proforma Invoice Generator', eyebrow: 'Set expectations before the final invoice',
    intro: 'Create a clear preliminary invoice with itemized costs, dates and terms, then download a polished PDF or convert it into a final invoice.',
    reassurance: 'Your proforma invoice and customer details stay on this device.',
    sections: [
      { heading: 'What is a proforma invoice?', paragraphs: ['A proforma invoice is a preliminary commercial document that outlines an expected transaction before a final invoice is issued. It can communicate anticipated products, services, prices, shipping, tax and terms, but it should be labeled clearly so the recipient does not mistake it for the final demand for payment.'] },
      { heading: 'What to include', paragraphs: ['Identify both parties, give the proforma a reference number and date, describe each item, state the currency, and make any validity period or assumptions clear. For international transactions, businesses may also need shipment or customs information appropriate to their situation.'], bullets: ['Seller and prospective buyer', 'Proforma number, issue date and validity date', 'Items, quantities and expected prices', 'Shipping, tax and other adjustments', 'Terms and a clear proforma label'] },
      { heading: 'Proforma invoice vs. final invoice', paragraphs: ['The proforma describes an expected sale; a final invoice records the actual amount being billed. Once the details are confirmed, use the conversion control in the workspace to create a final invoice without retyping the customer or line items. Review the converted document before sending it.'] },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'Convert an agreed proforma into the final invoice.' }, { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Use a quotation when you are proposing work or pricing.' }, { href: '/purchase-order-generator/', label: 'Purchase Order Generator', text: 'Create the buyer-side purchasing document.' }],
  },
  quotation: {
    path: '/quotation-generator/', kind: 'quotation', title: 'Free Quotation Generator | Invoice Workshop',
    description: 'Make a professional business quotation online for free, save customers locally and convert an approved quote into an invoice.',
    h1: 'Free Quotation Generator', eyebrow: 'Present pricing clearly and professionally',
    intro: 'Build an itemized business quotation, add your logo and terms, download a PDF, and convert an approved quotation into an invoice.',
    reassurance: 'No signup. Quotations and customer records remain in your browser.',
    sections: [
      { heading: 'Create a business quotation', paragraphs: ['Use the editor to describe the proposed products or services, quantities, rates, taxes, discounts and the period for which pricing is valid. A focused quotation helps a prospective customer understand the offer before approving it.'] },
      { heading: 'What belongs in a quotation?', paragraphs: ['Include a unique quotation number, both parties, a date and validity period, a precise scope, itemized pricing, assumptions and clear acceptance or payment terms. Avoid vague descriptions that could create different expectations.'], bullets: ['Quotation number and validity date', 'Customer and business details', 'Scope, deliverables and exclusions', 'Itemized prices and taxes', 'Acceptance and payment terms'] },
      { heading: 'Quotation, estimate and invoice', paragraphs: ['A quotation generally presents defined pricing for a proposed scope, while an estimate communicates an expected cost that may change as details develop. An invoice is issued to bill for goods or completed work. When a quotation is approved, convert it into an invoice using the saved fields above.'] },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'Turn an accepted quotation into an invoice.' }, { href: '/estimate-generator/', label: 'Estimate Generator', text: 'Use an estimate when cost or scope is still developing.' }, { href: '/work-order-generator/', label: 'Work Order Generator', text: 'Document the work that has been authorized.' }],
  },
  workOrder: {
    path: '/work-order-generator/', kind: 'workOrder', title: 'Free Work Order Generator | Invoice Workshop',
    description: 'Create a free professional work order with scope, jobsite, items and terms. Save locally and convert completed work into an invoice.',
    h1: 'Free Work Order Generator', eyebrow: 'Turn approved scope into actionable work',
    intro: 'Document the customer, jobsite, scope, materials, labor and dates in a clear work order, then convert completed work into an invoice.',
    reassurance: 'Work orders autosave privately in your browser—no account needed.',
    sections: [
      { heading: 'What is a work order?', paragraphs: ['A work order records work that is requested or authorized. It gives the person doing the work a practical reference for the customer, location, tasks, materials, pricing and timing. It can also help connect the original estimate to the final invoice.'] },
      { heading: 'Information to include', paragraphs: ['Use a unique work-order number and identify the customer and jobsite. Describe the scope in operational terms, itemize labor and materials when helpful, and record relevant dates, references, approvals and completion notes.'], bullets: ['Customer, project and jobsite', 'Requested work and deliverables', 'Labor, materials and quantities', 'Schedule and reference numbers', 'Terms, notes and completion status'] },
      { heading: 'Estimate vs. work order vs. invoice', paragraphs: ['An estimate predicts the likely cost, a work order directs or records the approved work, and an invoice requests payment. You can convert an estimate into a work order, then use this tool to convert the completed work order into an invoice. Always review actual quantities before billing.'] },
    ],
    related: [{ href: '/estimate-generator/', label: 'Estimate Generator', text: 'Begin with an expected scope and price.' }, { href: '/', label: 'Invoice Generator', text: 'Bill the customer when work is complete.' }, { href: '/contractor-invoice-template/', label: 'Contractor Invoice Template', text: 'Use contractor-oriented billing fields.' }],
  },
  purchaseOrder: {
    path: '/purchase-order-generator/', kind: 'purchaseOrder', title: 'Free Purchase Order Generator | Invoice Workshop',
    description: 'Create a professional purchase order online for free with supplier details, items, taxes and PDF download. Saved locally, no signup.',
    h1: 'Free Purchase Order Generator', eyebrow: 'Clear purchasing paperwork, ready to send',
    intro: 'Create a numbered purchase order for a supplier, itemize what you are buying, add delivery notes and download a professional PDF.',
    reassurance: 'Supplier and purchase details remain on your device.',
    sections: [
      { heading: 'Create a purchase order', paragraphs: ['A purchase order communicates what a buyer intends to purchase from a supplier. Use the generator to identify both parties, assign a PO number, list goods or services, and show expected pricing, tax, delivery charges and terms.'] },
      { heading: 'What should a purchase order contain?', paragraphs: ['Useful purchase orders make fulfillment and matching easier. Include the supplier, buyer, ship-to information where needed, order date, requested delivery date, line items, currency and instructions.'], bullets: ['Buyer and supplier information', 'Unique PO number and dates', 'Descriptions, quantities and unit prices', 'Tax, shipping and order total', 'Delivery and payment instructions'] },
      { heading: 'Purchase order vs. invoice', paragraphs: ['A purchase order originates with the buyer and authorizes or proposes a purchase. An invoice normally comes from the seller and requests payment. They may reference each other, but they serve different parts of the transaction and should retain their own numbers.'] },
    ],
    related: [{ href: '/proforma-invoice-generator/', label: 'Proforma Invoice Generator', text: 'Prepare the seller-side preliminary document.' }, { href: '/', label: 'Invoice Generator', text: 'Create an invoice that references a PO.' }, { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Present proposed products and pricing.' }],
  },
  estimate: {
    path: '/estimate-generator/', kind: 'estimate', title: 'Free Estimate Generator | Invoice Workshop',
    description: 'Create a free professional estimate, save it in your browser, and convert it to a work order or invoice without retyping.',
    h1: 'Free Estimate Generator', eyebrow: 'Set a clear expected scope and cost',
    intro: 'Prepare a detailed estimate with labor, products, tax and terms, then download a PDF or convert it as the job progresses.',
    reassurance: 'No signup. Estimates are stored locally on this browser.',
    sections: [
      { heading: 'Make an estimate online', paragraphs: ['Describe the expected work or products, use realistic quantities and rates, and state assumptions that could affect the final price. The live totals and preview make it easy to spot missing items before sharing the estimate.'] },
      { heading: 'What should an estimate include?', paragraphs: ['A useful estimate identifies the parties, scope, expected costs, dates and conditions. Where the final amount may vary, explain why rather than presenting uncertain pricing as fixed.'], bullets: ['Estimate number and validity period', 'Expected scope and deliverables', 'Labor, material or product lines', 'Tax, discounts and estimated total', 'Assumptions, exclusions and terms'] },
      { heading: 'Move from estimate to completed work', paragraphs: ['When the customer proceeds, convert the estimate into a work order to guide delivery or directly into an invoice when appropriate. The conversion keeps relevant fields and line items while giving the new document its own type and number.'] },
    ],
    related: [{ href: '/work-order-generator/', label: 'Work Order Generator', text: 'Turn an approved estimate into actionable work.' }, { href: '/', label: 'Invoice Generator', text: 'Convert the final amount into an invoice.' }, { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Use a quotation for a more defined offer.' }],
  },
  construction: {
    path: '/construction-invoice-template/', kind: 'invoice', vertical: 'construction', title: 'Free Construction Invoice Template & Generator | Invoice Workshop',
    description: 'Create construction invoices with jobsite, labor, materials, deposits, progress notes and PDF download. Free and saved locally.',
    h1: 'Construction Invoice Template & Generator', eyebrow: 'Built for projects, labor and materials',
    intro: 'Create a genuine construction invoice with project and jobsite details, labor, materials, deposits, change-order references and progress notes.',
    reassurance: 'Project and customer data stays in your browser.',
    sections: [
      { heading: 'Invoice construction work clearly', paragraphs: ['Construction billing benefits from visible project context. Record the jobsite and project, separate labor, materials and equipment into useful line items, and reference the estimate, contract or change order that supports the charge.'] },
      { heading: 'Construction-specific fields', paragraphs: ['Use the project fields above for site and progress information. Deposits reduce the displayed balance without changing the original invoice total. For progress billing, describe the stage or period being billed and keep supporting records with your project files.'], bullets: ['Project name and jobsite', 'Labor, materials and equipment', 'Deposit paid and balance due', 'Progress-billing note', 'Contract or change-order reference'] },
      { heading: 'Review before sending', paragraphs: ['Confirm that quantities reflect actual work, the tax treatment fits your circumstances, and deposits or prior payments are represented correctly. Invoice Workshop performs arithmetic and formatting but does not determine contract, lien, tax or legal requirements.'] },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'Use the general-purpose invoice workflow.' }, { href: '/estimate-generator/', label: 'Estimate Generator', text: 'Price expected construction work first.' }, { href: '/work-order-generator/', label: 'Work Order Generator', text: 'Record authorized work at the jobsite.' }],
  },
  contractor: {
    path: '/contractor-invoice-template/', kind: 'invoice', vertical: 'contractor', title: 'Free Contractor Invoice Template & Generator | Invoice Workshop',
    description: 'Create a contractor invoice with job details, labor, materials, deposits, terms and instant PDF. Free, private and no signup.',
    h1: 'Contractor Invoice Template & Generator', eyebrow: 'Practical billing for independent work',
    intro: 'Bill contract work with clear project details, services, materials, tax, deposits, payment instructions and a professional PDF.',
    reassurance: 'Your contractor workspace is saved only on this device.',
    sections: [
      { heading: 'Create a contractor invoice', paragraphs: ['Identify the customer and job, describe what was delivered, and separate services, hours, materials or reimbursable costs so the invoice is easy to check. Add the agreed payment terms and a useful reference to the proposal or work order.'] },
      { heading: 'Useful contractor invoice details', paragraphs: ['The exact requirements depend on your work and location, but clear business details and an itemized scope help customers process payment. Use the deposit field for money already received and the notes for concise completion or change information.'], bullets: ['Contractor and customer details', 'Project, jobsite or reference', 'Hours, services and materials', 'Tax, deposit and balance due', 'Payment instructions and terms'] },
      { heading: 'Keep the workflow connected', paragraphs: ['Start uncertain work with an estimate, record approved delivery in a work order, and convert the finished information into an invoice. Keeping each document’s role clear gives both parties a more understandable paper trail.'] },
    ],
    related: [{ href: '/estimate-generator/', label: 'Estimate Generator', text: 'Outline expected contractor costs.' }, { href: '/work-order-generator/', label: 'Work Order Generator', text: 'Record the approved scope.' }, { href: '/', label: 'Invoice Generator', text: 'Create a general business invoice.' }],
  },
  invoiceTemplate: {
    path: '/invoice-template/', kind: 'invoice', title: 'Free Invoice Template Online | Invoice Workshop',
    description: 'Use a free editable invoice template with automatic totals, local saving, live preview and professional PDF download. No signup.',
    h1: 'Free Editable Invoice Template', eyebrow: 'A reusable template that does the math',
    intro: 'Fill in this professional invoice template online, calculate totals automatically, reuse saved details and download a clean PDF.',
    reassurance: 'The template saves in your browser, not on our servers.',
    sections: [
      { heading: 'An invoice template you can reuse', paragraphs: ['Unlike a static word-processing file, this browser template handles line calculations, totals and currency formatting while retaining your business details and common contacts locally. Create a new numbered document whenever you need one.'] },
      { heading: 'How to fill in the template', paragraphs: ['Add accurate seller and customer details, choose dates and currency, itemize what was supplied, then check discounts, taxes, shipping and the final amount. Finish with payment instructions and terms that match your agreement.'], bullets: ['Add your logo and business identity', 'Enter customer and invoice details', 'Itemize products or services', 'Review calculations and preview', 'Save, print or download PDF'] },
      { heading: 'Keep records safely', paragraphs: ['Documents persist only in this browser, so export backups as part of your normal recordkeeping. Clearing browser site data removes the saved workspace. The generated PDF can be stored or shared wherever you normally manage business records.'] },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'Use the primary invoice-generation page.' }, { href: '/contractor-invoice-template/', label: 'Contractor Invoice Template', text: 'Use project and deposit fields for contract work.' }, { href: '/construction-invoice-template/', label: 'Construction Invoice Template', text: 'Itemize construction labor and materials.' }],
  },
};
