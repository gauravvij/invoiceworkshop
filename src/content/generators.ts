import type { DocumentKind } from '@/lib/documents/types';

export interface GeneratorContent {
  path: string;
  kind: DocumentKind;
  vertical?: 'construction' | 'contractor';
  /** Country preset key from lib/documents/locales.ts. */
  locale?: string;
  /** Built by the shared [slug] route rather than its own page file. */
  dynamic?: boolean;
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
      {
        heading: 'A worked invoice',
        paragraphs: [
          'The order the editor applies a discount and tax in is the part most people want to check before trusting a total to a customer. Here it is, worked through.',
        ],
        table: {
          caption: 'Invoice INV-2026-0117 — design services, one month',
          columns: ['Description', 'Qty', 'Rate', 'Amount'],
          rows: [
            ['Brand identity design', '1', '$2,400.00', '$2,400.00'],
            ['Website page templates', '6', '$310.00', '$1,860.00'],
            ['Stock photography licences', '12', '$18.50', '$222.00'],
          ],
          total: [['Subtotal', '$4,482.00'], ['Discount 5%', '\u2212$224.10'], ['Taxable amount', '$4,257.90'], ['Tax at 7.5%', '$319.34'], ['Total', '$4,577.24'], ['Deposit paid', '\u2212$1,000.00'], ['Balance due', '$3,577.24']],
          note: 'The discount comes off before tax, so tax is charged on $4,257.90 rather than on $4,482.00. Applying them the other way round overstates the tax by $16.81 and is the most common arithmetic error on a hand-built invoice.',
        },
      },
      {
        heading: 'Invoice, quotation, proforma or receipt?',
        paragraphs: [
          'These are routinely used as if they were interchangeable. They are not, and sending the wrong one is what leads to a customer treating a price as a bill or a bill as a price.',
        ],
        terms: [
          { term: 'Invoice', definition: 'A request for payment for goods or services already supplied. It enters your accounts as revenue and starts the payment clock.' },
          { term: 'Quotation', definition: 'An offer to do defined work at a stated price, sent before any commitment exists. Nothing is owed on a quotation.' },
          { term: 'Proforma invoice', definition: 'A statement of what the buyer will be charged once the sale proceeds. It is used to obtain approval, release funds or clear customs, and it is not a demand for payment.' },
          { term: 'Receipt', definition: 'Confirmation that payment was received. It comes after the money, not before it.' },
          { term: 'Credit note', definition: 'A document that reverses part or all of an invoice already issued. Issue one rather than editing an invoice the customer has already received.' },
        ],
      },
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
      { href: '/receipt-generator/', label: 'Receipt Generator', text: 'Confirm the payment once the invoice is settled.' },
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
          'A proforma is frequently the document a customs broker asks for when goods cross a border, because it states a value before a commercial invoice exists. Invoice Workshop formats the document and does the arithmetic; what a specific shipment must declare depends on the goods and the destination, so check with your broker rather than assuming this layout satisfies them.',
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
        heading: 'Retainage across a whole draw schedule',
        paragraphs: [
          'Retainage is easy on a single invoice and easy to get wrong across a project, because the withheld amount accumulates while the invoices do not. The table below runs a $120,000 contract at 10% retainage through four draws, so the figure you are owed at the end is visible from the first invoice rather than discovered at the last.',
        ],
        table: {
          caption: 'Draw schedule — $120,000 contract, 10% retainage',
          columns: ['Draw', 'Work this period', 'Retainage withheld', 'Net payable', 'Retainage held to date'],
          rows: [
            ['Draw 1 — site and foundations', '$30,000.00', '$3,000.00', '$27,000.00', '$3,000.00'],
            ['Draw 2 — framing and rough-in', '$36,000.00', '$3,600.00', '$32,400.00', '$6,600.00'],
            ['Draw 3 — finishes', '$34,000.00', '$3,400.00', '$30,600.00', '$10,000.00'],
            ['Draw 4 — final', '$20,000.00', '$2,000.00', '$18,000.00', '$12,000.00'],
          ],
          total: [['Contract value billed', '$120,000.00'], ['Received across the four draws', '$108,000.00'], ['Retainage still held at completion', '$12,000.00']],
          note: 'The release is billed as its own invoice once the contract conditions are met; it is not added to the final draw. Retainage held to date is the number to reconcile against, because each draw only shows the slice withheld that period.',
        },
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
  vatInvoiceUk: {
    path: '/vat-invoice-template-uk/', kind: 'invoice', locale: 'gb', dynamic: true,
    title: 'Free UK VAT Invoice Template & Generator | Invoice Workshop',
    description: 'Create a UK VAT invoice free: VAT registration number, 20% / 5% / 0% rates, VAT shown separately, GBP and DD/MM/YYYY dates. No signup.',
    h1: 'UK VAT Invoice Template', eyebrow: 'Set up for HMRC requirements',
    intro: 'Build a VAT invoice with your VAT registration number, UK rates and the VAT shown as its own figure, then download a PDF. The editor is set to GBP and UK date format.',
    reassurance: 'Your business and customer details stay in this browser.',
    sections: [
      {
        heading: 'What makes an invoice a VAT invoice',
        paragraphs: [
          'A VAT invoice is a specific document, not an invoice that happens to include VAT. If you are VAT registered, HMRC guidance sets out a defined set of particulars, and a customer who is also registered needs them to reclaim the VAT you charged. If you are not registered, none of this applies: you do not charge VAT and you do not issue VAT invoices.',
          'HMRC does not require the document to be headed “VAT invoice”. What matters is that the particulars are present. This generator prints the heading because it is the common convention and it helps the recipient file it, not because the wording itself is a requirement.',
        ],
        bullets: [
          'A unique, sequential invoice number',
          'Your business name, address and VAT registration number',
          'The customer’s name and address',
          'The time of supply (tax point) and the invoice date if different',
          'A description of what was supplied, with quantity and unit price',
          'The rate of VAT charged on each line',
          'The total excluding VAT, the VAT amount charged, and the total payable',
        ],
      },
      {
        heading: 'Simplified invoices under £250',
        paragraphs: [
          'Where the consideration does not exceed £250, HMRC allows a simplified VAT invoice carrying fewer particulars than the full list above. It is a genuinely shorter document rather than a relaxed version of the same one, so if most of your sales are small, it is worth reading what your situation actually requires before building a full invoice for every transaction.',
          'This generator produces a full invoice. That is never wrong — a full invoice satisfies the simplified requirements too — but it is more than a small sale strictly needs.',
        ],
      },
      {
        heading: 'A worked UK VAT invoice',
        paragraphs: [
          'Rates are per line, not per invoice, which matters more often than people expect. Printed leaflets and brochures are zero-rated in the UK while the design work that produced them is standard-rated, so one job can legitimately carry both.',
        ],
        table: {
          caption: 'Invoice 2026-118 — design studio, mixed VAT rates',
          columns: ['Description', 'Qty', 'Rate', 'VAT', 'Amount'],
          rows: [
            ['Brand and layout design', '12 hrs', '£65.00', '20%', '£780.00'],
            ['Website hosting setup', '1', '£150.00', '20%', '£150.00'],
            ['Printed leaflets, A5', '500', '£0.42', '0%', '£210.00'],
          ],
          total: [['Total excluding VAT', '£1,140.00'], ['VAT at 20% on £930.00', '£186.00'], ['Total including VAT', '£1,326.00']],
          note: 'VAT is charged on the £930.00 of standard-rated work, not on the £1,140.00 total: £780.00 + £150.00 = £930.00, and 20% of that is £186.00. The zero-rated leaflets still appear on the invoice with their rate shown, because a zero rate is a rate and not an omission.',
        },
      },
      {
        heading: 'Rates, registration and thresholds',
        paragraphs: [
          'Three numbers do most of the work in UK VAT, and mixing them up is the common error.',
        ],
        terms: [
          { term: 'Standard rate, 20%', definition: 'The default for most goods and services. This generator applies it to new lines unless you change the line.' },
          { term: 'Reduced rate, 5%', definition: 'Applies to a narrow list including domestic fuel and power and certain energy-saving installations.' },
          { term: 'Zero rate, 0%', definition: 'A taxable supply charged at nothing: most food, children’s clothing, books and printed matter. Different from exempt, which is outside VAT and cannot be reclaimed against.' },
          { term: 'Registration', definition: 'Compulsory once taxable turnover passes the threshold in a rolling twelve months, and available voluntarily below it. You cannot issue a VAT invoice or charge VAT before you are registered. The threshold changes at fiscal events, so check the current figure on GOV.UK rather than relying on a number you remember.' },
        ],
      },
      {
        heading: 'Before you send it',
        paragraphs: [
          'Check the VAT number is your own and correctly formatted, that the invoice number continues your sequence without gaps, and that each line carries the rate you actually intend.',
          'Invoice Workshop lays the document out and does the arithmetic. It does not determine whether you should be registered, which rate applies to a particular supply, or whether a transaction is zero-rated, exempt or outside the scope, and it cannot confirm that a document you produce with it satisfies HMRC in your circumstances. Rates and thresholds here were checked against GOV.UK and HMRC VAT Notice 700 on 2 September 2026; they change, and your own situation governs. Use HMRC guidance or your accountant for anything that matters.',
        ],
      },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'The general-purpose invoice workspace.' }, { href: '/invoice-template/', label: 'Invoice Template', text: 'A plain invoice layout without VAT fields.' }, { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Quote before the work starts.' }],
  },
  gstInvoiceIndia: {
    path: '/gst-invoice-format-india/', kind: 'invoice', locale: 'in', dynamic: true,
    title: 'Free GST Invoice Format India — Tax Invoice Generator | Invoice Workshop',
    description: 'Create a GST tax invoice free: GSTIN, HSN/SAC per line, CGST + SGST or IGST, 5/12/18/28% slabs, INR. No signup, nothing uploaded.',
    h1: 'GST Invoice Format (India)', eyebrow: 'Tax invoice with GSTIN and HSN/SAC',
    intro: 'Create a GST tax invoice with both parties’ GSTIN, per-line rates from the GST slabs and totals in rupees, then download a PDF.',
    reassurance: 'Your business and customer details stay in this browser.',
    sections: [
      {
        heading: 'What a GST tax invoice must carry',
        paragraphs: [
          'A tax invoice under GST is prescribed in some detail, and a customer claiming input tax credit needs the relevant parts of it. Not every particular applies to every supply: place of supply matters where the supply crosses a state boundary, and how many digits of HSN or SAC you must show depends on your turnover.',
        ],
        bullets: [
          'The words “Tax Invoice”',
          'Supplier name, address and GSTIN',
          'A consecutive invoice number and the date of issue',
          'Recipient name, address and GSTIN where registered',
          'Place of supply with state and code, where the supply is inter-State',
          'HSN code for goods or SAC code for services, to the digit depth your turnover requires',
          'Taxable value per line after any discount',
          'Rate and amount of CGST, SGST/UTGST or IGST',
          'Whether the tax is payable on reverse charge',
          'Signature or digital signature of the supplier',
        ],
      },
      {
        heading: 'A worked GST invoice',
        paragraphs: [
          'This is an intra-state supply, so the 18% splits into CGST 9% and SGST 9%. The same supply to another state would carry IGST 18% instead — one line rather than two, at the same total.',
        ],
        table: {
          caption: 'Tax Invoice INV/2026-27/0142 — intra-state supply, Maharashtra',
          columns: ['Description', 'HSN/SAC', 'Qty', 'Rate', 'Taxable value'],
          rows: [
            ['Management consulting services', 'SAC 998311', '10 hrs', '₹2,500.00', '₹25,000.00'],
            ['Software licence, annual', 'HSN 8523', '2', '₹7,500.00', '₹15,000.00'],
          ],
          total: [['Total taxable value', '₹40,000.00'], ['CGST at 9%', '₹3,600.00'], ['SGST at 9%', '₹3,600.00'], ['Total GST', '₹7,200.00'], ['Invoice total', '₹47,200.00']],
          note: 'The two halves are each 9% of ₹40,000.00, and together they are the same ₹7,200.00 that a single 18% IGST line would carry on an inter-state supply. Place of supply is what decides which of the two you issue, which is why it is a required field rather than a note.',
        },
      },
      {
        heading: 'CGST, SGST and IGST',
        paragraphs: [
          'One rate, split two ways or charged as one, depending on where the supply lands.',
        ],
        terms: [
          { term: 'Rates since 22 September 2025', definition: 'The GST Council reduced the structure to 5% and 18%, with a 40% rate on demerit goods. The 12% and 28% slabs no longer apply. This generator offers 5, 18 and 40, and you can enter any rate your classification requires.' },
          { term: 'CGST + SGST', definition: 'Intra-state supply: the rate is halved between the centre and the state. An 18% supply becomes 9% CGST and 9% SGST on the invoice.' },
          { term: 'IGST', definition: 'Inter-state supply, and exports and imports: the full rate is charged as a single integrated tax.' },
          { term: 'Place of supply', definition: 'The rule that decides which of the two applies. It is not always the customer’s address, and the rules differ for goods and for services, which is why it is stated on the invoice rather than inferred.' },
          { term: 'HSN and SAC', definition: 'HSN classifies goods, SAC classifies services. How many digits you must show depends on your turnover, so a small supplier and a large one can both be correct at different depths.' },
        ],
      },
      {
        heading: 'Before you file it',
        paragraphs: [
          'Check that the GSTIN of both parties is the full 15 characters, that the invoice number is unique within the financial year and unbroken, and that each line’s HSN or SAC is the one you actually use in your returns.',
          'Invoice Workshop formats the document and computes the totals. It does not classify your supplies, determine place of supply, decide your HSN digit depth, apply reverse charge, or produce a document guaranteed to satisfy a GST officer. The rate structure above reflects the 56th GST Council decisions effective 22 September 2025, checked on 2 September 2026 against the Government of India press release; classification and filing are matters for you or your chartered accountant.',
        ],
      },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'The general-purpose invoice workspace.' }, { href: '/proforma-invoice-generator/', label: 'Proforma Invoice Generator', text: 'Issue a proforma before the supply.' }, { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Quote a price before work begins.' }],
  },
  taxInvoiceAustralia: {
    path: '/tax-invoice-template-australia/', kind: 'invoice', locale: 'au', dynamic: true,
    title: 'Free Australian Tax Invoice Template & Generator | Invoice Workshop',
    description: 'Create an ATO-style tax invoice free: the words Tax Invoice, your ABN, GST at 10% shown separately, AUD and DD/MM/YYYY. No signup.',
    h1: 'Australian Tax Invoice Template', eyebrow: 'Set up for ATO requirements',
    intro: 'Create a tax invoice with your ABN, GST at 10% shown as its own figure and Australian date and currency formatting, then download a PDF.',
    reassurance: 'Your business and customer details stay in this browser.',
    sections: [
      {
        heading: 'What the ATO asks a tax invoice to show',
        paragraphs: [
          'For a sale under A$1,000 the list is short. The first item is easy to misread: what the ATO asks is that the document indicates it is intended to be a tax invoice. Printing the words “Tax invoice” is how almost everyone satisfies that, and this generator does, but the wording is the usual evidence of the requirement rather than the requirement itself. Above A$1,000 the buyer’s identity is needed as well.',
        ],
        bullets: [
          'That the document is intended to be a tax invoice',
          'Your identity as the seller, and your ABN',
          'The date the invoice was issued',
          'A description of the items sold, with quantity and price',
          'The GST amount payable, or a statement that the total price includes GST',
          'The extent to which each sale on the invoice is taxable',
          'The buyer’s identity or ABN, for sales of A$1,000 or more',
        ],
      },
      {
        heading: 'A worked Australian tax invoice',
        paragraphs: [
          'GST is a flat 10%, which makes the arithmetic easy to check: the GST is exactly one tenth of the GST-exclusive amount, and the total is eleven tenths of it.',
        ],
        table: {
          caption: 'Tax invoice TI-2026-0087 — building consultancy',
          columns: ['Description', 'Qty', 'Rate', 'GST', 'Amount'],
          rows: [
            ['Site inspection and photographic record', '1', 'A$450.00', '10%', 'A$450.00'],
            ['Condition report preparation', '6 hrs', 'A$140.00', '10%', 'A$840.00'],
          ],
          total: [['Total excluding GST', 'A$1,290.00'], ['GST at 10%', 'A$129.00'], ['Total including GST', 'A$1,419.00']],
          note: 'Because every line here is taxable, the invoice can also state “Total price includes GST” instead of showing the A$129.00 separately. Where a sale is partly GST-free, the extent of the taxable part has to be shown, so keeping GST on its own line is the safer habit.',
        },
      },
      {
        heading: 'ABN, GST registration and the threshold',
        paragraphs: [
          'These three are related but not the same, and only one of them is about the invoice.',
        ],
        terms: [
          { term: 'ABN', definition: 'An eleven-digit business number. Without one quoted, a business customer may be required to withhold from your payment at the top rate, subject to the exceptions in the withholding rules.' },
          { term: 'GST registration', definition: 'Separate from having an ABN. Compulsory once turnover reaches the registration threshold, and optional below it. You only charge GST once registered.' },
          { term: 'GST-free vs input-taxed', definition: 'GST-free supplies carry no GST but you can still claim credits on their inputs. Input-taxed supplies carry no GST and you cannot.' },
        ],
      },
      {
        heading: 'Before you send it',
        paragraphs: [
          'Confirm the ABN is right, that the document reads as a tax invoice, and that a sale of A$1,000 or more names the buyer.',
          'Invoice Workshop lays the document out and does the arithmetic. It does not decide whether you must be registered for GST, whether a particular supply is taxable, GST-free or input-taxed, or whether a document it produces meets the ATO’s requirements in your circumstances. The requirements above were checked against ATO guidance on 2 September 2026. The ATO or your accountant is the place to settle anything that matters.',
        ],
      },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'The general-purpose invoice workspace.' }, { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Quote a defined scope first.' }, { href: '/work-order-generator/', label: 'Work Order Generator', text: 'Record authorised work at a site.' }],
  },
  gstHstInvoiceCanada: {
    path: '/gst-hst-invoice-template-canada/', kind: 'invoice', locale: 'ca', dynamic: true,
    title: 'Free Canadian GST/HST Invoice Template & Generator | Invoice Workshop',
    description: 'Create a GST/HST invoice free: CRA business number, provincial rates from 5% GST to 15% HST, CAD, and tax shown separately. No signup.',
    h1: 'Canadian GST/HST Invoice Template', eyebrow: 'Provincial rates, handled per line',
    intro: 'Create an invoice with your CRA business number and the GST or HST rate for the province of supply, then download a PDF.',
    reassurance: 'Your business and customer details stay in this browser.',
    sections: [
      {
        heading: 'What a GST/HST invoice needs',
        paragraphs: [
          'The CRA sets out what a customer needs in order to claim an input tax credit, and the requirements grow with the size of the sale. The thresholds changed on 20 April 2021, from $30 and $150 to $100 and $500, and a good deal of published guidance still quotes the old figures.',
        ],
        bullets: [
          'Under $100: your business name, the date, and the total amount payable',
          '$100 to under $500: also your GST/HST registration number, the tax charged or a statement that it is included, the rate applying to each item, and whether each supply is taxable, zero-rated or exempt',
          '$500 or more: also the buyer’s name or trade name, the terms of payment, and a description sufficient to identify each supply',
          'For HST, show the total rate rather than the federal and provincial parts separately',
        ],
      },
      {
        heading: 'A worked GST/HST invoice',
        paragraphs: [
          'This one is billed in Ontario, where GST and the provincial component are combined into a single 13% HST. The same work billed in Alberta would carry 5% GST, and in British Columbia 5% GST with PST handled separately outside the GST system.',
        ],
        table: {
          caption: 'Invoice 2026-0231 — consulting, place of supply Ontario',
          columns: ['Description', 'Qty', 'Rate', 'HST', 'Amount'],
          rows: [
            ['Advisory work', '8 hrs', 'C$125.00', '13%', 'C$1,000.00'],
            ['Materials and printing', '1', 'C$340.00', '13%', 'C$340.00'],
          ],
          total: [['Total before tax', 'C$1,340.00'], ['HST at 13%', 'C$174.20'], ['Total', 'C$1,514.20']],
          note: 'C$130.00 on the advisory line plus C$44.20 on materials is C$174.20, which is also 13% of the C$1,340.00 subtotal. The rate follows the place of supply rather than where your business is based, which is the rule that catches out contractors working across provincial lines.',
        },
      },
      {
        heading: 'GST, HST, PST and QST',
        paragraphs: [
          'Canada runs more than one sales tax system at once, and which you charge depends on the province of supply.',
        ],
        terms: [
          { term: 'GST at 5%', definition: 'The federal tax, charged alone in provinces that have not harmonised.' },
          { term: 'HST at 13%, 14% or 15%', definition: 'Federal and provincial combined into one tax in the participating provinces, administered by the CRA: 13% in Ontario, 14% in Nova Scotia since 1 April 2025, and 15% in New Brunswick, Newfoundland and Labrador and Prince Edward Island.' },
          { term: 'PST', definition: 'A separate provincial tax in provinces such as British Columbia, Saskatchewan and Manitoba, registered for and reported separately from GST.' },
          { term: 'QST', definition: 'Quebec’s own tax, administered by Revenu Québec alongside the federal GST.' },
        ],
      },
      {
        heading: 'Before you send it',
        paragraphs: [
          'Check that the rate matches the province of supply rather than your own, that your business number appears once the sale reaches $100, and that the buyer is named at $500 or more.',
          'Invoice Workshop formats the document and does the arithmetic. It does not apply the place-of-supply rules, handle PST or QST, decide whether a supply is zero-rated or exempt, or confirm that a document it produces supports your customer’s input tax credit claim. The thresholds and rates above were checked against CRA guidance on 2 September 2026, including the April 2021 threshold change and the Nova Scotia rate reduction of 1 April 2025.',
        ],
      },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'The general-purpose invoice workspace.' }, { href: '/estimate-generator/', label: 'Estimate Generator', text: 'Price the work before committing.' }, { href: '/contractor-invoice-template/', label: 'Contractor Invoice Template', text: 'Bill independent contract work.' }],
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
      {
        heading: 'A filled-in template, worked through',
        paragraphs: [
          'The template accepts fractional quantities, so hours, months, sessions and units can sit on the same invoice. Below is one filled in, with every figure shown so you can check it against your own.',
          'Each line amount is quantity multiplied by rate. Tax is worked out on each line and rounded there, and the line taxes are then added together to give the tax on the document.',
        ],
        table: {
          caption: 'Invoice INV-2026-0244 — consulting and training, tax 6.5%',
          columns: ['Description', 'Qty', 'Rate', 'Amount', 'Tax'],
          rows: [
            ['Consulting', '7.25 hrs', '$135.00', '$978.75', '$63.62'],
            ['Support retainer', '1 month', '$450.00', '$450.00', '$29.25'],
            ['Training session', '3', '$187.50', '$562.50', '$36.56'],
            ['Printed handbooks', '14', '$12.95', '$181.30', '$11.78'],
          ],
          total: [['Subtotal', '$2,172.55'], ['Tax at 6.5%, added up from the lines', '$141.21'], ['Total', '$2,313.76']],
          note: 'The tax figure is $63.62 + $29.25 + $36.56 + $11.78 = $141.21. Applying 6.5% to the $2,172.55 subtotal in a single step instead gives $141.22, because rounding once at the end is not the same as rounding on each line. A cent either way is normal and both methods are defensible; what matters is that the invoice is internally consistent, which is exactly where a hand-totalled template usually slips.',
        },
      },
      {
        heading: 'Which kind of invoice template do you need?',
        paragraphs: [
          '“Invoice template” means four fairly different things, and the one you want depends on how often you invoice and how much arithmetic you are willing to do yourself.',
        ],
        terms: [
          { term: 'Word-processing template', definition: 'A .docx or Google Docs layout you overwrite by hand. It gives you a presentable document and nothing else: every subtotal, tax figure and total is yours to calculate and re-check on each invoice. Reasonable for a handful of invoices a year.' },
          { term: 'Spreadsheet template', definition: 'An .xlsx or Sheets file with formulas doing the totals. Faster, until the formulas are edited: a total that sums a fixed range quietly ignores rows added below it, which is the classic way a spreadsheet invoice goes out short.' },
          { term: 'Fillable PDF', definition: 'A fixed form with typeable fields. It prints exactly as designed and cannot be reflowed, so you are stuck with the number of line rows the form provides, and most such forms do not calculate anything.' },
          { term: 'Browser template', definition: 'The editor on this page. It totals as you type, keeps your business details, customers and items for reuse on this device, and generates the PDF here in the browser with no signup and no file to keep versions of.' },
        ],
      },
      { heading: 'Keep records safely', paragraphs: ['Documents persist only in this browser, so export backups as part of your normal recordkeeping. Clearing browser site data removes the saved workspace. The generated PDF can be stored or shared wherever you normally manage business records.'] },
    ],
    related: [{ href: '/', label: 'Invoice Generator', text: 'Use the primary invoice-generation page.' }, { href: '/contractor-invoice-template/', label: 'Contractor Invoice Template', text: 'Use project and deposit fields for contract work.' }, { href: '/receipt-generator/', label: 'Receipt Generator', text: 'Record the payment when it arrives.' }, { href: '/construction-invoice-template/', label: 'Construction Invoice Template', text: 'Itemize construction labor and materials.' }],
  },
  receiptGenerator: {
    path: '/receipt-generator/', kind: 'receipt', dynamic: true,
    title: 'Free Receipt Generator | Payment Receipt Maker | Invoice Workshop',
    description: 'Create a payment receipt free: amount received, payment method, transaction reference and the balance remaining. Marks PAID automatically. No signup, PDF download.',
    h1: 'Free Receipt Generator', eyebrow: 'Confirm the payment, not just the bill',
    intro: 'Record a payment you have received. Enter what was paid, how it arrived and against what, and the receipt marks itself PAID when the amount covers the total. A part payment shows the balance that is still outstanding.',
    reassurance: 'Everything stays in this browser. Your business, customers and past receipts are saved on this device only.',
    sections: [
      {
        heading: 'What a receipt does that an invoice does not',
        paragraphs: [
          'An invoice asks for money. A receipt confirms money arrived. They carry almost the same details, which is why the two are so often confused, but the fields that matter are different: a receipt has no due date and no payment terms, and it does have an amount received, a payment method and a date the money landed.',
          'That distinction is not cosmetic. A customer who is sent an invoice marked "paid" has no record of how much was paid or when, and cannot use it to close their own books. A receipt states those things.',
        ],
        bullets: [
          'Amount actually received, which may be less than the total',
          'How it was paid — transfer, card, cash, cheque, direct debit',
          'The date the money arrived, not a date it is due',
          'A transaction reference the customer can match to their bank',
          'The balance remaining, if the payment was partial',
        ],
      },
      {
        heading: 'A worked part payment',
        paragraphs: [
          'Most receipt tools assume the customer paid everything. Part payments are where a receipt earns its keep, and where the arithmetic is easiest to get wrong, so here it is worked through. Tax is calculated on each line and rounded there, then the lines are added — the same order the editor above uses.',
        ],
        table: {
          caption: 'Receipt REC-1042 — part payment against invoice INV-2026-0208',
          columns: ['Description', 'Qty', 'Rate', 'Amount'],
          rows: [
            ['Kitchen fit, labour', '38 hours', '$62.00', '$2,356.00'],
            ['Worktop and fittings', '1', '$1,180.00', '$1,180.00'],
          ],
          total: [['Subtotal', '$3,536.00'], ['Tax at 8.25%', '$291.72'], ['Total', '$3,827.72'], ['Amount received', '$2,000.00'], ['Balance remaining', '$1,827.72']],
          note: 'Tax is $194.37 on the labour line and $97.35 on the materials line, which add to $291.72. Taxing the $3,536.00 subtotal in one step gives $291.72 here as well, but the two methods diverge by a cent or two once more lines are involved, and it is the per-line figure that has to match what the customer sees.',
        },
      },
      {
        heading: 'Turn an invoice you already made into its receipt',
        paragraphs: [
          'If the invoice was created here, open it and convert it rather than retyping. The receipt keeps the customer, the line items and the totals, carries the invoice number across as the reference, sets the amount received to the invoice total and marks itself paid. Change the amount if only part of it arrived.',
          'Both documents stay in your list, so the invoice and the receipt that settles it can be produced separately when either is asked for.',
        ],
      },
      {
        heading: 'Receipt, invoice, credit note or statement?',
        paragraphs: [
          'These four get sent in place of one another constantly, and each mistake creates a different problem for the person receiving it.',
        ],
        terms: [
          { term: 'Receipt', definition: 'Confirms money has been received. Issued after payment, never before, and states the amount and method.' },
          { term: 'Invoice', definition: 'Requests payment. Carries a due date and payment terms, which a receipt does not.' },
          { term: 'Credit note', definition: 'Reverses an invoice in whole or in part, for a return, an overcharge or a cancellation. It reduces what is owed rather than recording a payment.' },
          { term: 'Statement', definition: 'Lists every invoice and payment on an account over a period. It is a summary, not a demand, and is not evidence that any single payment was made.' },
        ],
      },
      {
        heading: 'Keeping the record',
        paragraphs: [
          'Receipts are saved in this browser alongside your invoices and can be exported as a backup. Clearing site data removes them, so download the PDF for anything you need to keep. Invoice Workshop does not upload your document contents and cannot recover a workspace you have cleared.',
          'This tool produces a business receipt for a payment you have received. It is not a point-of-sale or till receipt, and it does not report anything to a tax authority. Whether a receipt is required, and what it must contain, depends on where you trade and how you are registered.',
        ],
      },
    ],
    related: [
      { href: '/', label: 'Invoice Generator', text: 'Create the invoice this receipt settles.' },
      { href: '/invoice-template/', label: 'Invoice Template', text: 'Start from a plain invoice layout.' },
      { href: '/quotation-generator/', label: 'Quotation Generator', text: 'Price the work before it is agreed.' },
      { href: '/contractor-invoice-template/', label: 'Contractor Invoice Template', text: 'Bill contract work with project and deposit fields.' },
    ],
  },
};
