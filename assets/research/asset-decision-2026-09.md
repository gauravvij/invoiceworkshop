# Which linkable asset to build — decision, 5 September 2026

Three candidates were on the table. One is being built. The other two are
recorded here as rejected with the evidence, so the decision does not get
re-argued from memory in a month.

## Rejected: Invoice late-payment / due-date calculator

The canonical version of this already exists and is published by the UK
government. The Office of the Small Business Commissioner runs a statutory
interest calculator built to comply with the Late Payment of Commercial Debts
(Interest) Act 1998, at
`smallbusinesscommissioner.gov.uk/help-and-guidance/interest-calculator/`.

Behind it, at least five commercial clones already rank: Paidnice, Experi,
Garfield Law, dontpaylate.uk and Landolio. The arithmetic is fixed by statute —
8% plus the Bank of England base rate, daily interest = amount × rate ÷ 365 —
so there is no version of this that is better than anyone else's, only newer.

Nobody links to the eighth calculator when the government publishes the first.
**No citation potential. Rejected.**

## Rejected: Progress draw / retainage calculator

The calculator itself is arithmetic. What earns links in this space is the
*law*: "Retainage Law in the 50 States", published by the American
Subcontractors Association, plus the 50-state surveys law firms publish
(Lexology, Kegler Brown). Those get cited because they state what each statute
permits, not because they multiply percentages.

Building the linkable version therefore means asserting the retainage rules of
50 states. We cannot verify 50 statutes from primary sources in this cycle, and
a wrong sentence about what a state permits is worse than no page at all — it is
the exact failure the instruction "do not fabricate measurements" exists to
prevent. **Rejected on fabrication risk, not on interest.**

The existing `/progress-draw-schedule/` tool stays as it is.

## Building: the free invoice generator audit

### Why this one can earn links and the other two cannot

**1. The existing corpus is vendor-authored and self-ranking.** Every page that
ranks for "best free invoice generator" is published by an invoice generator.
invoicemaker.com ranks Invoicemaker first. invoicey.io ranks Invoicey. epageusa
states it is "the only tool tested that requires zero signup" — a claim our own
first measurements already contradict, since several tools in the sample
produced a PDF with no account at all. There is no independent, reproducible
source in this category for anyone to cite.

**2. Writers in this niche cite statistics, by name.** The freelancer-invoicing
corpus is full of sentences of the form "According to the 2025 Contractor
Management Report, 85% of freelancers have invoices paid late" and "According to
Bonsai, 29% of freelance invoices are paid at least one day late." That is the
citation mechanism, and it is available to anything that produces a quotable
number with a method attached.

**3. The reproducible-comparison model demonstrably earns durable citations.**
PrivacyTests.org compares browsers on privacy, publishes its method, and is
cited and linked because anyone can re-run it. That is the template being
copied here — not the listicle.

### What makes it defensible

- The sample is drawn from live search results for a fixed, published set of
  queries. The one place a comparison is normally rigged is deciding who is in
  it, and nobody here decided.
- Every dimension is an observation, not a rating. There is no composite score,
  so there is no weighting to argue with.
- InvoiceWorkshop is measured on identical terms, appears in the table, and is
  excluded from every headline figure. It did not rank for any sampled query, so
  it is in the frame only because we put it there, and that is stated on the page.
- The first tools measured already produced results that do not flatter us:
  invoice-generator.com, the largest tool in the sample, generates its PDF
  entirely in the browser and never sent the canary anywhere.

### The one-asset-many-domains bet

One page, one CSV, one method anyone can re-run, and a small number of quotable
figures. That is what a comparison writer, a privacy blog and a freelancing
newsletter can each cite independently — as against a directory submission,
which is one link and stops.
