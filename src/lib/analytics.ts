import type { DocumentKind } from './documents/types';

type AnalyticsEvent =
  | 'tool_started'
  | 'document_saved'
  | 'document_duplicated'
  | 'pdf_downloaded'
  | 'document_converted'
  | 'returning_workspace_loaded';

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
  }
}

export const trackEvent = (
  event: AnalyticsEvent,
  properties: {
    document_type?: DocumentKind;
    conversion_from?: DocumentKind;
    conversion_to?: DocumentKind;
  } = {},
): void => {
  if (typeof window === 'undefined' || typeof window.gtag !== 'function') return;
  window.gtag('event', event, properties);
};
