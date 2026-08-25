# Product Principles

## No signup

The primary workflow must work immediately without registration, authentication or a trial gate. Do not make accounts a prerequisite for document creation, local saving, conversion or PDF download.

## Local first

Business profiles, customers, catalog items, numbering and documents stay in IndexedDB on the user's device. Use localStorage only for lightweight preferences. Make autosave status visible, handle storage errors, provide backup export and retain a clear-data control.

## Persistent workspace

The browser is a useful workspace, not a disposable form. Without requiring an account, remember business details, customers, catalog items and drafts on the user's device across refreshes and visits. Migrations must preserve valid existing records, while malformed records must fail safely instead of crashing the application.

## No private document transmission

Do not send document or customer content to Invoice Workshop servers, analytics, advertising systems, URLs, logs, metadata or external APIs. Analytics events may describe only abstract product actions and document types. A future feature that needs data transmission requires explicit product and privacy review before implementation.

## One connected workflow

Use the shared typed document model and preserve relevant data across:

- quotation → invoice;
- estimate → work order;
- estimate → invoice;
- work order → invoice;
- proforma invoice → invoice;
- invoice → receipt.

Converted documents receive a new ID, type and number and retain their source reference.

## Fast, simple and reliable

Prefer static delivery and browser capabilities over backend infrastructure. Calculations use integer minor units and explicit rounding. Schema migrations must protect existing local records. The interface should explain its state and never silently discard a document.

## Performance

SEO, product quality and speed are equal requirements. Keep public content static, minimize initial JavaScript, lazy-load PDF code, reserve visual space, avoid external fonts and fail releases on meaningful Core Web Vitals regressions.

## Honest presentation

Do not use fake testimonials, fake counters, deceptive download controls, keyword stuffing or claims of universal compliance. Advertising must remain visually separate from product controls, reserve its dimensions and never crowd the PDF action.
