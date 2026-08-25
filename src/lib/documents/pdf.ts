import type { DocumentRecord } from './types';
import { calculateDocument, calculateLine, formatMoney } from './money';
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
      pdf.addImage(document.business.logoDataUrl, 'PNG', margin, 38, 110, 46, undefined, 'FAST');
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

  pdf.setFontSize(14);
  pdf.text(document.business.name || 'Your business', margin, 112);
  pdf.setFont('helvetica', 'normal');
  pdf.setTextColor(muted);
  pdf.setFontSize(9);
  const businessLines = [
    document.business.address.line1,
    [document.business.address.city, document.business.address.region, document.business.address.postalCode].filter(Boolean).join(', '),
    document.business.email,
    document.business.phone,
    document.business.taxId ? `Tax ID: ${document.business.taxId}` : '',
  ].filter(Boolean);
  pdf.text(businessLines, margin, 130);

  pdf.setTextColor(navy);
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(9);
  pdf.text(document.kind === 'purchaseOrder' ? 'SUPPLIER' : 'BILL TO', margin, 204);
  pdf.setFont('helvetica', 'normal');
  pdf.setTextColor(muted);
  pdf.text(
    [
      document.client.name || 'Customer',
      document.client.address.line1,
      [document.client.address.city, document.client.address.region, document.client.address.postalCode].filter(Boolean).join(', '),
      document.client.email,
    ].filter(Boolean),
    margin,
    220,
  );

  pdf.setTextColor(navy);
  pdf.text(`Issued: ${document.issueDate}`, pageWidth - margin, 204, { align: 'right' });
  pdf.text(`${document.kind === 'receipt' ? 'Paid' : 'Due'}: ${document.dueDate}`, pageWidth - margin, 220, { align: 'right' });
  if (document.reference) pdf.text(`Reference: ${document.reference}`, pageWidth - margin, 236, { align: 'right' });

  autoTable(pdf, {
    startY: 276,
    margin: { left: margin, right: margin, bottom: 120 },
    head: [['Description', 'Qty', 'Rate', 'Disc.', 'Tax', 'Amount']],
    body: document.lineItems.map((line) => {
      const calculation = calculateLine(line);
      return [
        line.description || 'Item',
        `${line.quantity} ${line.unit}`,
        formatMoney(line.unitPriceMinor, document.currency),
        `${line.discountBps / 100}%`,
        `${line.taxBps / 100}%`,
        formatMoney(calculation.totalMinor, document.currency),
      ];
    }),
    theme: 'grid',
    headStyles: { fillColor: navy, textColor: '#ffffff', fontStyle: 'bold' },
    styles: { font: 'helvetica', fontSize: 8, cellPadding: 7, lineColor: '#dbe3ea', lineWidth: 0.5 },
    columnStyles: { 0: { cellWidth: 190 }, 1: { halign: 'right' }, 2: { halign: 'right' }, 3: { halign: 'right' }, 4: { halign: 'right' }, 5: { halign: 'right' } },
    showHead: 'everyPage',
    didDrawPage: () => {
      pdf.setTextColor(muted);
      pdf.setFontSize(8);
      pdf.text('Generated privately in your browser with InvoiceWorkshop.com', margin, pdf.internal.pageSize.getHeight() - 26);
      pdf.text(`Page ${pdf.getNumberOfPages()}`, pageWidth - margin, pdf.internal.pageSize.getHeight() - 26, { align: 'right' });
    },
  });

  const finalY = (pdf as typeof pdf & { lastAutoTable?: { finalY: number } }).lastAutoTable?.finalY ?? 400;
  let y = finalY + 20;
  const totalRows: Array<[string, number]> = [
    ['Subtotal', totals.subtotalMinor],
    ...(totals.discountMinor ? ([['Discount', -totals.discountMinor]] as Array<[string, number]>) : []),
    ['Tax', totals.taxMinor],
    ...(totals.shippingMinor ? ([['Shipping', totals.shippingMinor]] as Array<[string, number]>) : []),
    ...(totals.adjustmentMinor ? ([['Adjustment', totals.adjustmentMinor]] as Array<[string, number]>) : []),
    ['Total', totals.totalMinor],
    ...(totals.depositMinor ? ([['Deposit paid', -totals.depositMinor], ['Balance due', totals.balanceDueMinor]] as Array<[string, number]>) : []),
  ];
  if (y + totalRows.length * 18 > pdf.internal.pageSize.getHeight() - 100) {
    pdf.addPage();
    y = 60;
  }
  for (const [label, value] of totalRows) {
    const isTotal = label === 'Total' || label === 'Balance due';
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
    if (y > pdf.internal.pageSize.getHeight() - 150) {
      pdf.addPage();
      y = 60;
    }
    pdf.setFont('helvetica', 'normal');
    pdf.setTextColor(muted);
    pdf.setFontSize(8);
    pdf.text(pdf.splitTextToSize(footerText, pageWidth - margin * 2), margin, y + 15);
  }

  pdf.save(`${document.kind}-${safeFilename(document.number || 'draft')}.pdf`);
};
