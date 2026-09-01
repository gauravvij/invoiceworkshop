"""Deterministic policy for the aggressive backlink opportunity engine.

Discovery is broad; qualification is not. Everything here is data, not
capability: no rule in this module can cause an outbound action.
"""

from __future__ import annotations

# Canonical InvoiceWorkshop targets. The SEO architecture is frozen, so this is
# the complete set an opportunity may point at.
TARGETS = {
    "home": "https://invoiceworkshop.com/",
    "invoice_template": "https://invoiceworkshop.com/invoice-template/",
    "construction": "https://invoiceworkshop.com/construction-invoice-template/",
    "contractor": "https://invoiceworkshop.com/contractor-invoice-template/",
    "quotation": "https://invoiceworkshop.com/quotation-generator/",
    "estimate": "https://invoiceworkshop.com/estimate-generator/",
    "work_order": "https://invoiceworkshop.com/work-order-generator/",
    "purchase_order": "https://invoiceworkshop.com/purchase-order-generator/",
    "proforma": "https://invoiceworkshop.com/proforma-invoice-generator/",
}

# Ordered most specific first: the first matching rule wins.
TARGET_RULES = (
    (("retainage", "jobsite", "general contractor", "construction invoic", "construction billing",
      "progress draw", "change order"), TARGETS["construction"]),
    (("contractor invoic", "subcontractor", "trades invoic", "handyman invoic",
      "independent contractor billing"), TARGETS["contractor"]),
    (("purchase order", " po number", "procurement"), TARGETS["purchase_order"]),
    (("work order", "job order", "dispatch"), TARGETS["work_order"]),
    (("proforma", "pro forma"), TARGETS["proforma"]),
    (("quotation", "quote template", "sales quote"), TARGETS["quotation"]),
    (("estimate template", "job estimate", "cost estimate"), TARGETS["estimate"]),
    (("invoice template", "invoice sample", "invoice example", "invoice format"),
     TARGETS["invoice_template"]),
)
DEFAULT_TARGET = TARGETS["home"]

# Direct invoicing/accounting products. Used both as competitor seeds for the
# gap channel and as a hard exclusion for outreach targets.
COMPETITORS = (
    "freshbooks.com", "waveapps.com", "invoiceninja.com", "zoho.com", "xero.com",
    "quickbooks.intuit.com", "bill.com", "paymoapp.com", "harvestapp.com",
    "hiveage.com", "invoicely.com", "invoicesimple.com", "zohoinvoice.com",
    "billdu.com", "invoicehome.com", "jobber.com", "joist.com", "buildertrend.com",
    "invoice-generator.com", "refrens.com", "zintego.com", "invoiceberry.com",
    "sumup.com", "square.com", "myinvoices.com", "vantazo.com", "invoicefly.com",
    "billingo.com", "zervant.com", "invoicequick.com", "hellobonsai.com",
    "moonclerk.com", "and.co", "invoice2go.com", "sage.com", "myob.com",
    "canva.com", "microsoft.com", "office.com", "smartsheet.com", "template.net",
    "vertex42.com", "jotform.com", "pandadoc.com", "docusign.com",
)

# Never contacted and never counted as an opportunity.
BLOCKED_DOMAINS = set(COMPETITORS) | {
    "bing.com", "google.com", "duckduckgo.com", "yahoo.com", "baidu.com",
    "facebook.com", "instagram.com", "linkedin.com", "pinterest.com", "tiktok.com",
    "youtube.com", "x.com", "twitter.com", "medium.com", "wordpress.com",
    "blogspot.com", "wixsite.com", "amazon.com", "ebay.com", "etsy.com",
    "apple.com", "microsoft.com", "adobe.com", "wikipedia.org", "archive.org",
    "stripe.com", "paypal.com", "squareup.com", "sap.com", "oracle.com",
    "producthunt.com", "crunchbase.com", "g2.com", "capterra.com", "trustpilot.com",
    "kaskus.co.id", "indeed.com", "glassdoor.com", "coursera.org", "udemy.com",
    "scribd.com", "slideshare.net", "issuu.com", "yumpu.com", "academia.edu",
    "researchgate.net", "quizlet.com", "chegg.com", "cloud.microsoft",
}

# Channel 10 platforms. Discovery only; posting is never automated.
COMMUNITY_DOMAINS = (
    "reddit.com", "indiehackers.com", "news.ycombinator.com", "quora.com",
    "stackexchange.com", "contractortalk.com", "diychatroom.com",
)

CHANNEL_QUERIES: dict[str, tuple[str, ...]] = {
    # Channel 1 — competitor backlink gaps.
    "competitor_gap": (
        '"invoice generator" "resources for" freelancers -site:freshbooks.com',
        '"free invoice" tools list "we recommend" small business',
        '"invoice software" "useful resources" accountant links',
        '"recommended tools" invoicing freelancers resources page',
        '"tools we use" invoicing small business resources',
        '"invoice template" "other resources" contractor',
        '"helpful links" invoicing self-employed resources',
        '"resources" "invoice generator" OR "invoice maker" small business',
        'Find resource pages that recommend invoicing software to freelancers or small businesses',
    ),
    # Channel 2 — resource pages.
    "resource_pages": (
        '"resources for freelancers" tools invoicing',
        '"small business resources" free tools invoice',
        '"useful resources" self-employed invoicing tools',
        '"business admin" resources tools freelancers',
        '"getting paid" resources freelancers invoice',
        '"resource library" small business finance templates',
        '"tools and resources" independent contractor business',
        '"free resources" solopreneur invoicing admin',
        '"resource page" consultants business tools',
        '"agency resources" freelance tools invoicing',
        'Find resource pages for freelancers that recommend invoicing, billing or small-business tools',
        'Find pages that list free online tools for self-employed people to send invoices and get paid',
    ),
    # Channel 3 — broken / outdated tool replacement.
    "broken_replacement": (
        '"invoice generator" "no longer available" resources',
        '"free invoice tool" discontinued OR "shut down" resources list',
        '"this tool is no longer" invoice resources page',
        '"invoice generator" "page not found" resources links',
        '"formerly free" invoice tool now paid resources',
        '"invoice maker" "dead link" OR "broken link" resources',
        'Find resource pages that link to invoicing tools which have shut down or become paid only',
    ),
    # Channel 4 — accounting and bookkeeping.
    "accounting": (
        'bookkeeping firm "resources" "invoice template" clients',
        'accountant "resource centre" small business templates',
        '"bookkeeping resources" free templates invoicing',
        'accounting practice "client resources" downloads invoice',
        '"small business finance" guide resources invoice template',
        'bookkeeper blog "free tools" invoicing clients',
        '"accountants" association resources small business tools',
        'Find bookkeeping and accounting firm websites that publish free downloadable resources for small business clients',
    ),
    # Channel 5 — contractor and construction.
    "contractor": (
        'contractor association "resources" business tools members',
        '"construction business" resources invoicing paperwork',
        '"contractor resources" free templates invoice estimate',
        'construction bookkeeping "resources" retainage invoicing',
        '"trade association" contractor business admin resources',
        'electrician OR plumber OR hvac "business resources" invoicing',
        '"construction accounting" resources templates change orders',
        'contractor magazine "business tools" invoicing resources',
        'Find contractor or construction-business resource pages that could reasonably include a free construction invoice tool',
    ),
    # Channel 6 — freelancer / consultant / creator.
    "freelancer": (
        'freelancer association "member resources" business tools',
        '"consultant resources" invoicing templates independent',
        '"creator business" resources invoicing getting paid',
        'freelance community "resources" tools invoice template',
        '"independent worker" resources finances invoicing',
        '"freelance toolkit" resources business admin',
        '"for freelancers" resources page tools finance',
        'Find freelancer association and community pages listing practical business admin tools',
    ),
    # Channel 7 — legitimate directories / tool discovery.
    "directory": (
        '"submit your tool" free business software directory',
        '"add your product" small business software free listing',
        '"free tools directory" business submit',
        '"submit a tool" no-signup web apps directory',
        '"tool directory" invoicing accounting submit free',
    ),
    # Channel 8 — editorial roundups.
    "editorial_roundup": (
        '"best free invoice" tools freelancers 2026',
        '"free invoicing tools" small business roundup updated',
        '"tools for freelancers" invoicing list updated 2026',
        '"accounting tools" small business list free 2026',
        '"invoice apps" free comparison freelancers',
        '"contractor apps" OR "contractor tools" invoicing list',
        '"getting paid" tools freelancers article 2026',
        'Find recently updated articles listing free invoicing tools for freelancers and small businesses',
    ),
    # Channel 9 — unlinked mentions.
    "unlinked_mention": (
        '"InvoiceWorkshop"',
        '"Invoice Workshop" invoice generator',
        '"invoiceworkshop.com"',
    ),
    # Channel 10 — community discussion (research + draft only).
    "community": (
        'site:reddit.com/r/freelance invoice tool recommendation',
        'site:reddit.com/r/smallbusiness free invoice generator',
        'site:reddit.com/r/Contractors invoice template software',
        'site:indiehackers.com invoicing tool free',
        'site:news.ycombinator.com "invoice generator"',
        'site:reddit.com/r/bookkeeping invoice template free tool',
        'Find Reddit discussions where freelancers or small business owners are looking for an invoice generator',
        'Find forum threads asking for a free invoicing tool that needs no signup',
    ),
    # Channel 11 — expert contribution requests (escalate, never impersonate).
    "expert_contribution": (
        '"looking for" experts invoicing small business quotes journalist',
        '"seeking contributors" freelance finance invoicing',
        '"expert commentary" small business billing request',
        '"source request" freelancer invoicing advice',
    ),
}

# Channels whose output is deliberately not an editorial backlink prospect.
COMMUNITY_CHANNEL = "community"
ESCALATION_CHANNEL = "expert_contribution"

# ---------------------------------------------------------------------------
# Throughput targets for one substantial discovery cycle.
# ---------------------------------------------------------------------------
RAW_TARGET_MIN = 100
RAW_TARGET_MAX = 300
FILTERED_TARGET_MIN = 20
FILTERED_TARGET_MAX = 50
QUALIFIED_TARGET_MIN = 5
QUALIFIED_TARGET_MAX = 15
SEARCH_RESULTS_PER_QUERY = 12
EXTRACT_LIMIT = 50

# ---------------------------------------------------------------------------
# Part D scoring ceilings. Deliberately weighted away from raw link value.
# ---------------------------------------------------------------------------
SCORE_CEILINGS = {
    "relevance": 25,
    "audience": 20,
    "legitimacy": 15,
    "resource_fit": 15,
    "likelihood": 10,
    "referral": 10,
    "seo": 5,
}

TIER_A_MIN = 72
TIER_B_MIN = 55
TIER_C_MIN = 40

# ---------------------------------------------------------------------------
# Part K spam policy. A match is a hard reject, never a score penalty.
# ---------------------------------------------------------------------------
SPAM_PATTERNS = (
    r"\bbuy (?:quality )?backlinks?\b", r"\blink building (?:service|package)\b",
    r"\bpbn\b", r"\blink farm\b", r"\bguest post(?:ing)? (?:service|package|marketplace)\b",
    r"\bpay(?:ment)? (?:for|per) (?:a )?(?:do)?follow\b", r"\bsponsored (?:post|link) price\b",
    r"\bda\s*\d{2,}\b", r"\bdr\s*\d{2,}\b", r"\bdomain authority\s*\d{2,}\b",
    r"\bsubmit to (?:hundreds|thousands) of directories\b",
    r"\bbulk (?:directory )?submission\b", r"\breciprocal link (?:required|exchange)\b",
    r"\blink exchange\b", r"\bwe accept paid (?:guest )?posts\b",
    r"\bwrite for us\b.{0,80}\b(?:fee|charge|payment|\$\d)",
)

# Signals that a listing costs money or demands a link back.
PAID_PATTERNS = (
    r"\bpaid (?:listing|placement|submission|review)\b",
    r"\blisting fee\b", r"\bpremium listing\b", r"\bsponsored listing\b",
    r"\bpay(?:ment)? required\b", r"\b\$\d+\s*(?:per|/)\s*(?:listing|month|year)\b",
)
RECIPROCAL_PATTERNS = (
    r"\breciprocal\b", r"\blink back to us\b", r"\bmust link to\b",
    r"\bexchange links\b",
)
ACCOUNT_PATTERNS = (
    r"\bcreate an account\b", r"\bsign up to submit\b", r"\bregister to submit\b",
    r"\blog in to submit\b",
)
CAPTCHA_PATTERNS = (r"\bcaptcha\b", r"\brecaptcha\b", r"\bhcaptcha\b", r"\bcf-turnstile\b")

# Why a competitor link exists. Only the first group is worth chasing.
ACTIONABLE_LINK_REASONS = (
    "resource_recommendation", "tool_roundup", "editorial_recommendation",
    "freelancer_resource", "small_business_resource", "contractor_resource",
    "accounting_resource", "template_collection", "educational_resource",
)
REJECTED_LINK_REASONS = (
    "funding_or_news", "affiliate", "unrelated_partnership", "login_portal",
    "paid_placement", "spam",
)

LINK_REASON_RULES = (
    (("raised", "funding", "series a", "acquisition", "press release", "announces"), "funding_or_news"),
    (("affiliate", "commission", "referral bonus", "ref="), "affiliate"),
    (("sign in", "log in", "customer portal", "client login"), "login_portal"),
    (("sponsored", "paid placement", "advertisement"), "paid_placement"),
    (("best free", "top 10", "top ten", "roundup", "comparison", "alternatives"), "tool_roundup"),
    (("template", "printable", "download"), "template_collection"),
    (("bookkeeping", "accounting", "accountant"), "accounting_resource"),
    (("contractor", "construction", "trades"), "contractor_resource"),
    (("freelance", "independent worker", "solopreneur"), "freelancer_resource"),
    (("small business", "smb", "entrepreneur"), "small_business_resource"),
    (("guide", "how to", "tutorial", "learn"), "educational_resource"),
    (("we recommend", "recommended", "useful", "helpful"), "resource_recommendation"),
    (("resources", "tools"), "resource_recommendation"),
)


def target_for(text: str) -> str:
    """Pick the single canonical target that best fits an external page."""
    lowered = text.lower()
    for needles, target in TARGET_RULES:
        if any(needle in lowered for needle in needles):
            return target
    return DEFAULT_TARGET


def classify_link_reason(text: str) -> str:
    lowered = text.lower()
    for needles, reason in LINK_REASON_RULES:
        if any(needle in lowered for needle in needles):
            return reason
    return "unknown"


# ---------------------------------------------------------------------------
# Search-independent discovery.
#
# The free Bing RSS endpoint ignores `site:` and quoted-phrase operators, so
# keyword discovery alone cannot reliably reach a named organisation's resource
# page. Crawl seeds are membership bodies, associations and public resource hubs
# whose audiences bill clients directly. The crawler reads their own resource
# sections and the outbound resource lists they publish. Read-only GETs only.
# ---------------------------------------------------------------------------
CRAWL_SEEDS = (
    # Freelancer / independent-worker bodies
    ("freelancer", "https://www.nase.org/business-help"),
    ("freelancer", "https://www.ipse.co.uk/advice.html"),
    ("freelancer", "https://www.the-efa.org/resources/"),
    ("freelancer", "https://www.graphicartistsguild.org/resources/"),
    ("freelancer", "https://www.aiga.org/resources"),
    ("freelancer", "https://www.asja.org/"),
    ("freelancer", "https://www.authorsguild.org/resources/"),
    # Small-business support organisations
    ("small_business", "https://www.score.org/resources"),
    ("small_business", "https://www.sba.gov/business-guide"),
    ("small_business", "https://www.nfib.com/tools-resources/"),
    ("small_business", "https://www.uschamber.com/co/run/finance"),
    ("small_business", "https://smallbiztrends.com/category/finance"),
    ("small_business", "https://www.fsb.org.uk/resources.html"),
    # Contractor / construction trade associations
    ("contractor", "https://www.nari.org/"),
    ("contractor", "https://www.nahb.org/"),
    ("contractor", "https://www.agc.org/"),
    ("contractor", "https://www.abc.org/"),
    ("contractor", "https://www.nawic.org/"),
    ("contractor", "https://www.phccweb.org/"),
    ("contractor", "https://www.necanet.org/"),
    ("contractor", "https://www.acca.org/"),
    ("contractor", "https://www.fmb.org.uk/"),
    ("contractor", "https://www.constructionexec.com/"),
    # Accounting / bookkeeping bodies and trade press
    ("accounting", "https://www.accountingweb.com/"),
    ("accounting", "https://www.accountingtoday.com/"),
    ("accounting", "https://www.icb.org.uk/"),
    ("accounting", "https://www.aat.org.uk/"),
    ("accounting", "https://www.bookkeepers.com/"),
    ("accounting", "https://www.journalofaccountancy.com/"),
)

# A crawled link is only worth keeping if its anchor or path looks like a
# resource listing rather than navigation furniture.
CRAWL_SKIP_PATH = (
    "/login", "/signin", "/sign-in", "/register", "/cart", "/checkout", "/donate",
    "/privacy", "/terms", "/cookie", "/search", "/tag/", "/category/", "/author/",
    "/wp-admin", "/feed", ".pdf", ".zip", ".doc",
)
CRAWL_MAX_LINKS_PER_SEED = 25


# Pages whose subject is something other than running/billing a business. A
# relevant audience is not enough: an invoicing tool does not belong on a health
# insurance guide or a student-loan page.
OFF_TOPIC_PATTERNS = (
    r"\bhealth insurance\b", r"\bdental\b", r"\bstudent loan", r"\bretirement\b",
    r"\b401\(?k\)?", r"\bpension\b", r"\bfile (?:a )?complaint\b",
    r"\bllc formation\b", r"\bincorporat(?:e|ion)\b", r"\bvisa\b", r"\bimmigration\b",
    r"\bmember(?:ship)? perks?\b", r"\bdiscount code\b", r"\bjob board\b",
    r"\bfind work\b", r"\bhiring\b", r"\bcourse\b", r"\bwebinar replay\b",
    r"\bevent(?:s)? calendar\b", r"\bpress release\b", r"\bannual report\b",
    # A single narrative story is not a resource list, however relevant the site.
    r"\bcase study\b", r"\bsuccess story\b", r"\bmember story\b",
    r"\bwon \S{0,3}\d", r"\bmeet the member\b", r"\baward winner\b",
    r"\binterview with\b", r"\bsponsored content\b",
)

