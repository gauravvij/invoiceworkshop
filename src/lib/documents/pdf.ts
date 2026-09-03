import type { DocumentRecord } from './types';
import { calculateDocument, calculateLine, formatHours, formatMoney, formatUnits } from './money';
import { documentLabels } from './factory';

const safeFilename = (value: string) => value.replace(/[^a-z0-9_-]+/gi, '-').replace(/^-|-$/g, '');

export const downloadDocumentPdf = async (document: DocumentRecord): Promise<void> => {
  const [{ jsPDF }, autoTableModule] = await Promise.all([import('jspdf'), import('jspdf-autotable')]);
  const autoTable = autoTableModule.default;
  const pdf = new jsPDF({ unit: 'pt', format: 'letter', compress: true });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const margin = 44;
  const navy = '#17324d';
  const muted = '#64748b';
  const totals = calculateDocument(document);

  if (document.business.logoDataUrl) {
    try {
      const image = pdf.getImageProperties(document.business.logoDataUrl);
      const scale = Math.min(110 / image.width, 46 / image.height);
      const width = image.width * scale;
      const height = image.height * scale;
      const format = document.business.logoDataUrl.startsWith('data:image/jpeg')
        ? 'JPEG'
        : document.business.logoDataUrl.startsWith('data:image/webp')
          ? 'WEBP'
          : 'PNG';
      pdf.addImage(document.business.logoDataUrl, format, margin, 38, width, height, undefined, 'FAST');
    } catch {
      // A malformed local logo should never prevent a PDF download.
    }
  }

  pdf.setTextColor(navy);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(24);
  pdf.text(documentLabels[document.kind].toUpperCase(), pageWidth - margin, 55, { align: 'right' });
  pdf.setFontSize(11);
  pdf.text(`# ${document.number}`, pageWidth - margin, 75, { align: 'right' });
  // The mark a customer looks for first, and the reason a receipt is not just an
  // invoice with a different heading. Only where the money actually covers it.
  if (document.kind === 'receipt' && totals.balanceRemainingMinor <= 0) {
    pdf.setTextColor('#1a7f4b');
    pdf.setFontSize(13);
    pdf.text('PAID', pageWidth - margin, 93, { align: 'right' });
    pdf.setTextColor(navy);
  }

  pdf.setFontSize(14);
  const businessName = pdf.splitTextToSize(document.business.name || 'Your business', 245) as string[];
  pdf.text(businessName, margin, 112);
  pdf.setFont('helvetica', 'normal');
  pdf.setTextColor(muted);
  pdf.setFontSize(9);
  const businessLines = [
    document.business.address.line1,
    document.business.address.line2,
    [document.business.address.city, document.business.address.region, document.business.address.postalCode].filter(Boolean).join(', '),
    document.business.address.country,
    document.business.email,
    document.business.phone,
    document.business.taxId ? `Tax ID: ${document.business.taxId}` : '',
  ].filter(Boolean);
  pdf.text(businessLines, margin, 130 + Math.max(0, businessName.length - 1) * 14);

  pdf.setTextColor(navy);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text(
    document.kind === 'purchaseOrder' ? 'SUPPLIER'
      : document.kind === 'deliveryNote' ? 'DELIVER TO' : 'BILL TO',
    margin, 204,
  );
  pdf.setFont('helvetica', 'normal');
  pdf.setTextColor(muted);
  const shipTo = document.kind === 'deliveryNote' && document.deliveryAddress
    ? document.deliveryAddress : document.client.address;
  pdf.text(
    [
      document.client.name || 'Customer',
      shipTo.line1,
      shipTo.line2,
      [shipTo.city, shipTo.region, shipTo.postalCode].filter(Boolean).join(', '),
      shipTo.country,
      ...(document.kind === 'deliveryNote' ? [] : [document.client.email, document.client.phone]),
      document.kind === 'deliveryNote' ? '' :
        (document.client.taxId ? `Tax ID: ${document.client.taxId}` : ''),
    ].filter(Boolean),
    margin,
    220,
  );

  pdf.setTextColor(navy);
  pdf.text(`Issued: ${document.issueDate}`, pageWidth - margin, 204, { align: 'right' });
  const dateLabel = document.kind === 'receipt' ? 'Paid'
    : document.kind === 'creditNote' ? 'Credited' : 'Due';
  pdf.text(`${dateLabel}: ${document.dueDate}`, pageWidth - margin, 220, { align: 'right' });
  if (document.reference) {
    pdf.text(
      `${document.kind === 'receipt' ? 'Transaction ref' : document.kind === 'creditNote' ? 'Credits invoice' : 'Reference'}: ${document.reference}`,
      pageWidth - margin, 236, { align: 'right' },
    );
  }
  if (document.kind === 'receipt' && document.paymentMethod) {
    pdf.text(`Paid by: ${document.paymentMethod}`, pageWidth - margin, 252, { align: 'right' });
  }
  if (document.kind === 'creditNote' && document.creditReason) {
    pdf.text(`Reason: ${document.creditReason}`, pageWidth - margin, 252, { align: 'right' });
  }
  if (document.kind === 'deliveryNote') {
    if (document.carrier) pdf.text(`Carrier: ${document.carrier}`, pageWidth - margin, 252, { align: 'right' });
    if (document.consignmentRef) pdf.text(`Consignment: ${document.consignmentRef}`, pageWidth - margin, 268, { align: 'right' });
  }

  autoTable(pdf, {
    startY: 276,
    margin: { left: margin, right: margin, bottom: 120 },
    head: [document.kind === 'deliveryNote'
      ? ['Description', 'Ordered', 'Delivered', 'Back-ordered']
      : document.kind === 'timesheet'
        ? ['Date', 'Description', 'Hours', 'Rate', 'Disc.', 'Tax', 'Amount']
        : ['Description', 'Qty', 'Rate', 'Disc.', 'Tax', 'Amount']],
    body: document.lineItems.map((line) => {
      if (document.kind === 'deliveryNote') {
        const asked = Number.parseFloat(line.quantityOrdered ?? line.quantity) || 0;
        const shipped = Number.parseFloat(line.quantity) || 0;
        const gap = asked - shipped;
        return [
          line.description || 'Item',
          `${line.quantityOrdered ?? line.quantity} ${line.unit}`,
          `${line.quantity} ${line.unit}`,
          gap === 0 ? '—' : gap > 0 ? `${+gap.toFixed(3)}` : `+${+Math.abs(gap).toFixed(3)}`,
        ];
      }
      const calculation = calculateLine(line);
      return [
        ...(document.kind === 'timesheet' ? [line.serviceDate || '—'] : []),
        line.description || 'Item',
        `${line.quantity} ${line.unit}`,
        formatMoney(line.unitPriceMinor, document.currency),
        `${line.discountBps / 100}%`,
        `${line.taxBps / 100}%`,
        formatMoney(calculation.totalMinor, document.currency),
      ];
    }),
    theme: 'grid',
    rowPageBreak: 'avoid',
    headStyles: { fillColor: navy, textColor: '#ffffff', fontStyle: 'bold' },
    styles: { font: 'helvetica', fontSize: 8, cellPadding: 7, lineColor: '#dbe3ea', lineWidth: 0.5 },
    columnStyles: document.kind === 'deliveryNote'
      ? { 0: { cellWidth: 240 }, 1: { halign: 'right' }, 2: { halign: 'right' }, 3: { halign: 'right' } }
      : document.kind === 'timesheet'
      ? { 0: { cellWidth: 62 }, 1: { cellWidth: 150 }, 2: { halign: 'right' }, 3: { halign: 'right' }, 4: { halign: 'right' }, 5: { halign: 'right' }, 6: { halign: 'right' } }
      : { 0: { cellWidth: 190 }, 1: { halign: 'right' }, 2: { halign: 'right' }, 3: { halign: 'right' }, 4: { halign: 'right' }, 5: { halign: 'right' } },
    showHead: 'everyPage',
  });

  const finalY = (pdf as typeof pdf & { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? 400;
  let y = finalY + 20;

  // A delivery note's totals are counts, and it says in as many words that it
  // is not a request for payment. Then it stops: no subtotal, no tax, no total.
  if (document.kind === 'deliveryNote') {
    pdf.setTextColor(navy);
    for (const [label, value] of [
      ['Units ordered', formatUnits(totals.unitsOrderedMilli)],
      ['Units delivered', formatUnits(totals.unitsDeliveredMilli)],
      ...(totals.unitsBackOrderedMilli > 0
        ? [['Back-ordered', formatUnits(totals.unitsBackOrderedMilli)]] as Array<[string, string]>
        : []),
      ...(totals.unitsBackOrderedMilli < 0
        ? [['Over-delivered', formatUnits(-totals.unitsBackOrderedMilli)]] as Array<[string, string]>
        : []),
    ] as Array<[string, string]>) {
      const strong = label === 'Units delivered';
      pdf.setFont('helvetica', strong ? 'bold' : 'normal');
      pdf.setFontSize(strong ? 11 : 9);
      pdf.text(label, pageWidth - 190, y);
      pdf.text(value, pageWidth - margin, y, { align: 'right' });
      y += strong ? 22 : 16;
    }
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    pdf.setTextColor(muted);
    pdf.text('This is a delivery note. It states what was shipped and is not a request for payment.',
             margin, y + 8);
    y += 26;
  }
  const totalRows: Array<[string, number]> = document.kind === 'deliveryNote' ? [] : [
    ['Subtotal', totals.subtotalMinor],
    ...(totals.discountMinor ? ([['Discount', -totals.discountMinor]] as Array<[string, number]>) : []),
    ['Tax', totals.taxMinor],
    ...(totals.shippingMinor ? ([['Shipping', totals.shippingMinor]] as Array<[string, number]>) : []),
    ...(totals.adjustmentMinor ? ([['Adjustment', totals.adjustmentMinor]] as Array<[string, number]>) : []),
    ...(document.kind === 'creditNote'
      ? ([['Total credited', totals.creditedMinor]] as Array<[string, number]>)
      : ([['Total', totals.totalMinor]] as Array<[string, number]>)),
    ...(totals.depositMinor ? ([['Deposit paid', -totals.depositMinor], ['Balance due', totals.balanceDueMinor]] as Array<[string, number]>) : []),
    // A receipt's point is the money received and what, if anything, is left.
    ...(document.kind === 'receipt'
      ? ([
          ['Amount received', totals.amountPaidMinor],
          ...(totals.balanceRemainingMinor > 0
            ? ([['Balance remaining', totals.balanceRemainingMinor]] as Array<[string, number]>)
            : []),
          ...(totals.balanceRemainingMinor < 0
            ? ([['Overpaid', -totals.balanceRemainingMinor]] as Array<[string, number]>)
            : []),
        ] as Array<[string, number]>)
      : []),
  ];
  if (y + totalRows.length * 18 > pdf.internal.pageSize.getHeight() - 100) {
    pdf.addPage();
    y = 60;
  }
  // Hours are certified separately from the money and are not a currency
  // amount, so they are printed above the money rows rather than formatted as
  // one. A timesheet whose hours are shown as "$38.00" is worse than useless.
  if (document.kind === 'timesheet' && totals.totalHoursMilli > 0) {
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(9);
    pdf.setTextColor(navy);
    pdf.text('Total hours', pageWidth - 190, y);
    pdf.text(formatHours(totals.totalHoursMilli), pageWidth - margin, y, { align: 'right' });
    y += 18;
  }
  for (const [label, value] of totalRows) {
    const isTotal = ['Total', 'Total credited', 'Balance due', 'Balance remaining'].includes(label);
    pdf.setFont('helvetica', isTotal ? 'bold' : 'normal');
    pdf.setFontSize(isTotal ? 11 : 9);
    pdf.setTextColor(navy);
    pdf.text(label, pageWidth - 190, y);
    pdf.text(formatMoney(value, document.currency), pageWidth - margin, y, { align: 'right' });
    y += isTotal ? 22 : 16;
  }

  const footerText = [
    document.notes ? `Notes: ${document.notes}` : '',
    document.paymentInstructions ? `Payment: ${document.paymentInstructions}` : '',
    document.terms ? `Terms: ${document.terms}` : '',
  ].filter(Boolean).join('\n\n');
  if (footerText) {
    pdf.setFont('helvetica', 'normal');
    pdf.setTextColor(muted);
    pdf.setFontSize(8);
    const lines = pdf.splitTextToSize(footerText, pageWidth - margin * 2) as string[];
    y += 15;
    for (const line of lines) {
      if (y > pdf.internal.pageSize.getHeight() - 48) {
        pdf.addPage();
        y = 60;
      }
      pdf.text(line, margin, y);
      y += 11;
    }
  }

  const pageCount = pdf.getNumberOfPages();
  for (let page = 1; page <= pageCount; page += 1) {
    pdf.setPage(page);
    pdf.setTextColor(muted);
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    pdf.text(`Page ${page} of ${pageCount}`, pageWidth - margin, pdf.internal.pageSize.getHeight() - 26, { align: 'right' });
  }

  pdf.save(`${document.kind}-${safeFilename(document.number || 'draft')}.pdf`);
};
