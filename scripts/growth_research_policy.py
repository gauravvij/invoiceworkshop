"""Shared deterministic policy for Level-0 prospect discovery and qualification."""

CHANNEL_QUERIES = {
    "competitor_gap": (
        '"invoice generator" "resources" freelancers -freshbooks -wave -quickbooks',
        '"construction invoice template" "resources" contractor -software',
    ),
    "freelancer": (
        '"submit a resource" freelancers tools',
        '"freelancer resource directory" submit tool',
    ),
    "small_business": (
        '"submit a resource" "small business" tool',
        '"contributor guidelines" "small business" finance',
    ),
    "accounting": (
        'bookkeeping "resource library" "invoice template" contact',
        'accounting firm "resources" invoice checklist small business',
    ),
    "contractor": (
        '"editorial guidelines" contractor business finance',
        '"contributor guidelines" contractor magazine software',
    ),
    "directory": (
        '"add your product" "business software" free',
        '"submit software" small business finance free',
    ),
    "editorial": (
        '"editorial guidelines" freelancer business finance',
        '"contributor guidelines" invoicing small business',
    ),
    "community": (
        'site:reddit.com/r/freelance "invoice generator"',
        'site:news.ycombinator.com "invoice generator"',
    ),
    "linkable_asset": (
        '"construction invoice" checklist change orders retainage',
        '"invoice approval checklist" contractor resources',
    ),
}

SEARCHES_PER_SCHEDULED_RUN = 3
SEARCH_RESULTS_PER_QUERY = 10
SHORTLIST_MIN = 8
SHORTLIST_MAX = 15
QUALIFIED_TARGET_MIN = 5
QUALIFIED_TARGET_MAX = 10
