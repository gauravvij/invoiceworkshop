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
  sections: Array<{
    heading: string;
    paragraphs: string[];
    bullets?: string[];
    terms?: Array<{ term: string; definition: string }>;
    table?: { caption: string; columns: string[]; rows: string[][]; total: Array<[string, string]>; note?: string };
  }>;
  related: Array<{ href: string; label: string; text: string }>;
}

export const generators: Record<string, GeneratorContent> = {
  home: {
    path: '/', kind: 'invoice', title: 'Free Invoice Generator & Invoice Maker | Invoice Workshop',
    description: 'Create a professional invoice for free with saved business details, customers, line items and instant PDF download. No signup required.',
    h1: 'Free Invoice Generator', eyebrow: 'Professional invoices without the admin',
    intro: 'Create professional invoices online for free. No signup required. Add your logo, items, taxes and payment details, then download a PDF instantly.',
    reassurance: 'Your business and customer details stay saved in this browser.',
    sections: [
      { heading: 'Create an invoice online', paragraphs: ['Start with the working editor above. Add your business and customer, list the products or services supplied, set tax and discounts, then review the live preview before downloading or printing. Your draft saves automatically on this device.'] },
      { heading: 'What should an invoice include?', paragraphs: ['A clear invoice normally identifies the seller and customer, uses a unique invoice number, states issue and due dates, itemizes the work or goods, and shows the currency, taxes, discounts and amount due. Payment instructions and concise terms help the customer understand what to do next.'], bullets: ['Seller and customer contact details', 'Unique invoice number and dates', 'Item descriptions, quantities and rates', 'Subtotal, discounts, tax and total', 'Payment instructions and terms'] },
      { heading: 'No signup, but it remembers you', paragraphs: ['Return on the same browser and device to reuse your business profile, customers, common items and drafts. Invoice Workshop does not upload your document contents. Export a local backup whenever you want an extra copy.'] },
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
    description: 'Create a free proforma invoice with itemized costs, validity dates and terms, then convert it into a final invoice. No signup required.',
    h1: 'Free Proforma Invoice Generator', eyebrow: 'Set expectations before the final invoice',
    intro: 'Create a clear preliminary invoice with itemized costs, dates and terms, then download a polished PDF or convert it into a final invoice.',
    reassurance: 'Your proforma invoice and customer details stay on this device.',
    sections: [
      {
        heading: 'What is a proforma invoice?',
        paragraphs: [
          'A proforma invoice is a preliminary commercial document that describes a transaction before it happens. It tells the buyer what they will be charged, on what terms, and for how long that offer stands. It is not a demand for payment and it does not record a sale that has taken place.',
          'That distinction matters practically. A buyer can take a proforma to their finance team to raise a purchase order or release funds, and a seller can send one without it appearing in their sales ledger as revenue. Label it clearly so nobody mistakes it for the final bill.',
        ],
      },
      {
        heading: 'When a proforma is the right document',
        paragraphs: [
          'Reach for a proforma when the buyer needs a formal figure before you can issue a real invoice. Common situations:',
        ],
        bullets: [
          'The buyer needs a document to raise a purchase order',
          'Payment is required in advance of work or shipment',
          'Customs or a freight forwarder needs a declared value',
          'A grant, budget holder or finance team must pre-approve the spend',
          'Scope is agreed but the work has not yet been delivered',
          'A new customer is being set up before trading terms exist',
        ],
      },
      {
        heading: 'What to include',
        paragraphs: [
          'Identify both parties, give the document its own reference number, and make the validity period explicit — a price that has no expiry is a price you have to honour indefinitely.',
        ],
        bullets: [
          'The words "Proforma Invoice" prominently',
          'Seller and prospective buyer details',
          'Proforma number and issue date',
          'Validity or expiry date for the quoted prices',
          'Itemized goods or services with quantities',
          'Currency, unit prices and line totals',
          'Shipping, handling and any tax treatment',
          'Payment terms and accepted methods',
          'Any assumptions the price depends on',
        ],
      },
      {
        heading: 'A worked proforma',
        paragraphs: [
          'A short example for goods sold in advance of shipment. Note the validity date doing real work: it is the seller\'s protection against a price accepted three months later.',
        ],
        table: {
          caption: 'Proforma PF-2026-014 — valid 30 days from issue',
          columns: ['Description', 'Qty', 'Unit price', 'Amount'],
          rows: [
            ['Workshop bench, powder-coated steel', '6', '$418.00', '$2,508.00'],
            ['Assembly and packing', '6', '$45.00', '$270.00'],
            ['Freight to buyer\'s warehouse', '1', '$385.00', '$385.00'],
          ],
          total: [['Subtotal', '$3,163.00'], ['Tax at 6%', '$189.78'], ['Total payable in advance', '$3,352.78']],
          note: 'Prices hold until the validity date. After that the buyer should request a fresh proforma rather than assume the figures still stand.',
        },
      },
      {
        heading: 'Proforma, quotation and final invoice',
        paragraphs: [
          'These three documents are often used interchangeably and should not be. Each one does a different job at a different point in the deal.',
        ],
        terms: [
          { term: 'Quotation', definition: 'An offer to do defined work at a stated price. It invites acceptance and usually precedes any commitment.' },
          { term: 'Proforma invoice', definition: 'A formal statement of what the buyer will be charged once the sale proceeds. It is used to obtain approval, funds or customs paperwork.' },
          { term: 'Commercial invoice', definition: 'The final demand for payment, issued once goods ship or work completes. This is the document that enters the accounts.' },
        ],
      },
      {
        heading: 'Converting a proforma into the final invoice',
        paragraphs: [
          'Once the transaction is confirmed, use the conversion control in the workspace to create the final invoice without retyping the customer or line items. The new document receives its own number and type and keeps a reference to the proforma it came from.',
          'Review before sending. Quantities shipped, freight actually incurred and any price changes since the proforma was issued all need checking against reality rather than carried over on trust.',
        ],
      },
      {
        heading: 'International shipments',
        paragraphs: [
          'A proforma is frequently the document a customs broker asks for when goods cross a border, because it states a value before a commercial invoice exists. Requirements vary considerably by destination and by what is being shipped.',
          'Invoice Workshop formats the document and performs the arithmetic. It does not determine customs, export-control or tax obligations, which depend on the goods, the countries involved and your own circumstances. Check with your freight forwarder or broker for what a specific shipment needs.',
        ],
      },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'Convert an agreed proforma into the final invoice.' }, { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Use a quotation when you are proposing work or pricing.' }, { href: '/purchase-order-generator/', label: 'Purchase Order Generator', text: 'Create the buyer-side purchasing document.' }, { href: '/invoice-template/', label: 'Invoice Template', text: 'Start from a straightforward invoice layout.' }],
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
    description: 'Create a free work order with jobsite, scope, labor, materials, scheduling and sign-off, then convert completed work into an invoice.',
    h1: 'Free Work Order Generator', eyebrow: 'Turn approved scope into actionable work',
    intro: 'Document the customer, jobsite, scope, materials, labor and dates in a clear work order, then convert completed work into an invoice.',
    reassurance: 'Work orders stay saved in this browser—no account needed.',
    sections: [
      {
        heading: 'What a work order is for',
        paragraphs: [
          'A work order is the instruction that turns an agreed price into work someone can actually carry out. It answers four questions for whoever picks it up: who the customer is, where to go, what to do, and what has been authorized.',
          'It is also the record that connects the estimate to the invoice. Without one, the gap between what was quoted and what was billed is filled by memory, which is where most billing disputes begin.',
        ],
      },
      {
        heading: 'What to put on a work order',
        paragraphs: [
          'The editor above carries project and jobsite fields alongside the usual customer details. Fill the operational parts properly — a technician reading this on site cannot ask the office what "as discussed" meant.',
        ],
        bullets: [
          'Work order number and issue date',
          'Customer and billing contact',
          'Jobsite address and access notes',
          'Requested work in operational terms',
          'Labor: who, how long, what rate',
          'Materials and equipment required',
          'Scheduled date and expected duration',
          'Reference to the estimate, contract or PO',
          'Who authorized the work, and when',
          'Space for completion notes and sign-off',
        ],
      },
      {
        heading: 'A worked work order',
        paragraphs: [
          'A typical service call. The estimate reference in the last line is what lets the office check the invoice against what was actually approved.',
        ],
        table: {
          caption: 'Work order WO-2026-0412 — 22 Harbour Road, unit 3',
          columns: ['Line', 'Qty', 'Rate', 'Amount'],
          rows: [
            ['Labor — diagnostic and repair, senior technician', '3.5 hrs', '$95.00', '$332.50'],
            ['Labor — apprentice assistance', '3.5 hrs', '$48.00', '$168.00'],
            ['Materials — replacement circulation pump', '1 ea', '$264.00', '$264.00'],
            ['Materials — fittings and consumables', '1 lot', '$38.50', '$38.50'],
            ['Call-out charge', '1 ea', '$75.00', '$75.00'],
          ],
          total: [['Subtotal', '$878.00'], ['Tax at 8%', '$70.24'], ['Total authorized', '$948.24']],
          note: 'Authorized against estimate EST-2026-0388. Work beyond this scope needs a new authorization before it is carried out, not after.',
        },
      },
      {
        heading: 'Scope changes on site',
        paragraphs: [
          'The most common way a work order goes wrong is that the job turns out bigger than the paperwork. A technician finds a second failed part, fixes it because they are already there, and nobody tells the office until the invoice looks wrong.',
          'Handle it the same way a construction change order is handled: record the additional work, note who approved it and when, and reference it explicitly on the invoice. Written approval before the extra work happens is worth more than any argument afterwards.',
        ],
      },
      {
        heading: 'Work order, purchase order and estimate',
        paragraphs: [
          'These three get confused constantly, usually because the same job produces all of them.',
        ],
        terms: [
          { term: 'Estimate', definition: 'Your prediction of what the work will cost. It is an offer, and it may change as the job becomes clearer.' },
          { term: 'Work order', definition: 'The internal instruction to perform work that has been authorized. It directs and records, it does not request payment.' },
          { term: 'Purchase order', definition: 'The buyer\'s document committing to purchase. It comes from the customer, not from you.' },
          { term: 'Invoice', definition: 'The request for payment once the work is done. It should reconcile back to the work order.' },
        ],
      },
      {
        heading: 'From work order to invoice',
        paragraphs: [
          'Start uncertain work as an estimate, convert the approved version into a work order, then convert the completed work order into an invoice. Each conversion keeps the customer and line items and gives the new document its own number, type and reference back to its source.',
          'Before billing, check actual hours and quantities against what the work order authorized rather than invoicing the plan. The two are rarely identical, and the difference is exactly what the customer will scrutinise.',
        ],
      },
      {
        heading: 'Scheduling and dispatch',
        paragraphs: [
          'For teams running several jobs a day, the work order doubles as the dispatch record. Keeping the jobsite, access notes and scheduled window on the document itself means the person doing the work is not dependent on a separate system or a phone call.',
          'Invoice Workshop handles the document and the arithmetic. It does not schedule crews or track vehicles; if you need dispatch routing, keep using whatever system you already have and use the work order as the billing record.',
        ],
      },
    ],
    related: [{ href: '/estimate-generator/', label: 'Estimate Generator', text: 'Begin with an expected scope and price.' }, { href: '/', label: 'Invoice Generator', text: 'Bill the customer when work is complete.' }, { href: '/contractor-invoice-template/', label: 'Contractor Invoice Template', text: 'Use contractor-oriented billing fields.' }, { href: '/construction-invoice-template/', label: 'Construction Invoice Template', text: 'Bill labor, materials and progress draws.' }],
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
    description: 'Create construction invoices with jobsite, labor, materials, deposits, progress draws, retainage and change orders. Free, no signup, saved locally.',
    h1: 'Construction Invoice Template & Generator', eyebrow: 'Built for projects, labor and materials',
    intro: 'Create a genuine construction invoice with project and jobsite details, labor, materials, deposits, change-order references and progress notes.',
    reassurance: 'Project and customer details stay in this browser.',
    sections: [
      {
        heading: 'Invoice construction work clearly',
        paragraphs: [
          'Construction billing fails for boring reasons. The invoice arrives without a jobsite on it, the labor and materials are collapsed into one line, or the change order everybody agreed to verbally never appears in writing. Each of those gives the person approving payment a reason to put your invoice aside and ask a question instead.',
          'The editor above is set up for project work: record the project and jobsite, itemize labor, materials and equipment separately, enter any deposit already received, and note the draw or change order the charge belongs to. The totals, tax and balance are calculated as you type, and the PDF is generated in your browser.',
        ],
      },
      {
        heading: 'What a construction invoice should include',
        paragraphs: [
          'Beyond the usual business and customer details, project billing carries information a general invoice does not need. The list below covers what most general contractors, subcontractors and trades are asked for. Your contract governs what is actually required.',
        ],
        bullets: [
          'Contractor and customer details',
          'Project name and jobsite address',
          'Invoice number, issue date and due date',
          'Contract, purchase-order or draw reference',
          'Labor separated from materials',
          'Equipment, disposal and mobilization',
          'Approved change orders, referenced by number',
          'Deposit or prior draws already received',
          'Retainage withheld, if the contract provides for it',
          'Tax treatment appropriate to the work',
          'Payment instructions and terms',
        ],
      },
      {
        heading: 'A worked progress draw',
        paragraphs: [
          'Here is how a mid-project draw usually looks once labor, materials, equipment and an approved change order are separated. Notice the change order carries its own line and its own reference number rather than being folded into labor — that single habit prevents most billing disputes.',
        ],
        table: {
          caption: 'Draw 2 of 4 — bathroom remodel, 14 Alder Street',
          columns: ['Description', 'Qty', 'Rate', 'Amount'],
          rows: [
            ['Labor — framing and rough-in', '64 hrs', '$68.00', '$4,352.00'],
            ['Materials — lumber, fasteners, blocking', '1 lot', '$1,845.50', '$1,845.50'],
            ['Equipment — dumpster rental', '2 wks', '$260.00', '$520.00'],
            ['Change order CO-002 — relocate waste line', '1 ea', '$780.00', '$780.00'],
          ],
          total: [['Subtotal', '$7,497.50'], ['Tax at 8%', '$599.80'], ['Total', '$8,097.30'], ['Deposit paid', '−$2,500.00'], ['Balance due', '$5,597.30']],
          note: 'A deposit reduces the balance due without changing the invoice total, so the original amount billed stays visible on the document.',
        },
      },
      {
        heading: 'Separating labor, materials and equipment',
        paragraphs: [
          'Collapsing everything into one figure invites the customer to negotiate the whole number. Separate lines let them query one item and approve the rest, which is usually faster for both sides. It also gives you a record you can compare against the estimate when a project runs long.',
        ],
        terms: [
          { term: 'Labor', definition: 'Hours worked, at the agreed rate. Splitting by crew, trade or phase makes a long draw easier to check against a schedule of values.' },
          { term: 'Materials', definition: 'Goods supplied and installed. Bill these as a lot per phase or as individual items, depending on how much detail the contract asks for.' },
          { term: 'Equipment', definition: 'Rental, delivery, disposal and mobilization. These are frequently forgotten and then absorbed as a loss, so give them their own lines.' },
          { term: 'Subcontracted work', definition: 'Work performed by another trade under your contract. Reference the subcontractor invoice so the charge can be traced.' },
        ],
      },
      {
        heading: 'Deposits, progress draws and retainage',
        paragraphs: [
          'Three different mechanisms reduce what a customer pays today, and mixing them up is a common source of confusion on a construction invoice.',
          'A deposit is money already received. Enter it in the deposit field and the document shows the full total and then the reduced balance due, so the amount originally billed remains on the record. Progress draws bill a defined portion of a larger contract; describe which draw and which period or stage it covers in the progress note, and keep your schedule of values with the project file. Retainage is a percentage the customer withholds until completion — if your contract provides for it, record it as a negative adjustment or its own negative line so the withheld amount is stated explicitly rather than quietly missing.',
          'Whether retainage applies, how much may be held and when it must be released are contract and jurisdiction questions. Check your contract and, where the amounts matter, take professional advice.',
        ],
      },
      {
        heading: 'Handling change orders',
        paragraphs: [
          'Change orders cause more unpaid construction invoices than bad workmanship does. The pattern is familiar: work is added on site, nobody writes it down, and the extra appears for the first time on a bill weeks later, where it reads like padding.',
          'Give every change its own number, get the approval in writing before the work happens where you can, and bill it as a separate line that names the reference. If the change alters the schedule as well as the price, say so in the progress note.',
        ],
        bullets: [
          'Number each change order and keep the sequence',
          'Record who approved it and when',
          'Bill it on its own line, not inside labor',
          'Reference the number on the invoice',
          'Note any schedule impact alongside the cost',
        ],
      },
      {
        heading: 'Payment terms that actually get paid',
        paragraphs: [
          'Terms are only useful if they are specific and visible. Net 30 written nowhere on the document is not a term. State the due date, the accepted payment methods and anything the customer must do before releasing funds, such as a lien waiver, and put them where they will be read rather than in small print.',
          'For longer projects, agreeing the draw schedule before work starts is worth more than any collection tactic afterwards. Both parties then know what triggers each invoice.',
        ],
        bullets: [
          'A concrete due date, not just a term name',
          'Accepted payment methods and details',
          'Any documentation required before release',
          'Who to contact about a query',
          'What happens if payment is late',
        ],
      },
      {
        heading: 'Review before sending',
        paragraphs: [
          'Confirm that quantities reflect work actually performed, that every change order on the invoice was approved, that deposits and prior draws are represented correctly, and that the tax treatment fits your circumstances.',
          'Invoice Workshop performs the arithmetic and formatting and creates the PDF in your browser. It does not determine contract, lien, retainage, tax or other legal requirements, which vary by jurisdiction and by agreement. Treat the guidance on this page as a practical starting point rather than professional advice.',
        ],
      },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'Use the general-purpose invoice workflow.' }, { href: '/estimate-generator/', label: 'Estimate Generator', text: 'Price expected construction work first.' }, { href: '/work-order-generator/', label: 'Work Order Generator', text: 'Record authorized work at the jobsite.' }, { href: '/contractor-invoice-template/', label: 'Contractor Invoice Template', text: 'Bill independent contract work.' }, { href: '/purchase-order-generator/', label: 'Purchase Order Generator', text: 'Order materials from a supplier.' }, { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Quote a defined scope before starting.' }],
  },
  contractor: {
    path: '/contractor-invoice-template/', kind: 'invoice', vertical: 'contractor', title: 'Free Contractor Invoice Template & Generator | Invoice Workshop',
    description: 'Create a contractor invoice with job details, labor, materials, deposits, terms and instant PDF. Free and saved locally, with no signup.',
    h1: 'Contractor Invoice Template & Generator', eyebrow: 'Practical billing for independent work',
    intro: 'Bill contract work with clear project details, services, materials, tax, deposits, payment instructions and a professional PDF.',
    reassurance: 'Your contractor details stay saved in this browser.',
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
    reassurance: 'The template saves on this device. Invoice Workshop does not upload document contents.',
    sections: [
      { heading: 'An invoice template you can reuse', paragraphs: ['Unlike a static word-processing file, this browser template handles line calculations, totals and currency formatting while retaining your business details and common contacts locally. Create a new numbered document whenever you need one.'] },
      { heading: 'How to fill in the template', paragraphs: ['Add accurate seller and customer details, choose dates and currency, itemize what was supplied, then check discounts, taxes, shipping and the final amount. Finish with payment instructions and terms that match your agreement.'], bullets: ['Add your logo and business identity', 'Enter customer and invoice details', 'Itemize products or services', 'Review calculations and preview', 'Save, print or download PDF'] },
      { heading: 'Keep records safely', paragraphs: ['Documents persist only in this browser, so export backups as part of your normal recordkeeping. Clearing browser site data removes the saved workspace. The generated PDF can be stored or shared wherever you normally manage business records.'] },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'Use the primary invoice-generation page.' }, { href: '/contractor-invoice-template/', label: 'Contractor Invoice Template', text: 'Use project and deposit fields for contract work.' }, { href: '/construction-invoice-template/', label: 'Construction Invoice Template', text: 'Itemize construction labor and materials.' }],
  },
};
