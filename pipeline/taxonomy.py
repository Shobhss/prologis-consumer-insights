"""Signal taxonomy: the closed set of signal types the extractor may assign.

Approved by Sarah Logman on 2026-10-02 with two additions: DATACENTER (both
hyperscalers and their equipment suppliers) and the ENERGY type downgraded to
peripheral because Prologis Essentials is ~3% of the business.

Edit here and the extraction prompt, docs/signal-taxonomy.md and the report all
pick up the change.
"""

SIGNALS = {
    "FOOT+": ("Footprint expansion",
              "Opening, building, leasing or acquiring logistics facilities; adding square footage; new fulfillment/distribution/delivery sites."),
    "FOOT-": ("Footprint contraction",
              "Closing, subleasing, exiting or consolidating facilities; delaying or cancelling planned sites; reducing square footage."),
    "NET": ("Network strategy shift",
            "Changes to how the logistics network is designed: regionalization, same-day hubs, inbound cross-docks, consolidation of nodes, insourcing vs 3PL."),
    "CAPEX": ("Capex guidance",
              "Stated or changed capital expenditure plans and the share going to fulfillment, logistics or infrastructure."),
    "OWN/LEASE": ("Own vs lease posture",
                  "Statements or numbers on owned vs leased property, land purchases, build-to-suit, sale-leaseback, lease term or commitment changes."),
    "GEO": ("Geographic shift",
            "Entering or exiting specific metros, states or countries; nearshoring; port or trade-lane changes that move where space is needed."),
    "DATACENTER": ("Data center demand",
                   "Data center builds, land/power acquisitions, or growth in data center suppliers (electrical, cooling, plumbing, equipment) that could use industrial space."),
    "SECT": ("Sector demand trend",
             "Category-level demand changes relevant to industrial space: grocery, cold chain, EV, returns/reverse logistics, AI hardware, healthcare."),
    "STRESS": ("Financial stress on real estate",
               "Impairments, lease terminations, restructuring charges, subleasing, headcount cuts tied to facilities, going-concern language."),
    "AUTO": ("Automation and labor",
             "Robotics or automation rollouts, labor cost or availability issues, that change building specs or headcount per facility."),
    "M&A": ("M&A / portfolio change",
            "Acquisitions, divestitures or partnerships that add or remove a logistics footprint."),
    "ENERGY": ("Power and sustainability (peripheral)",
               "On-site solar, EV fleet charging, grid or power constraints at facilities. Relevant to Prologis Essentials; secondary to real estate."),
}

CODES = list(SIGNALS.keys())


def taxonomy_markdown() -> str:
    lines = ["| Code | Signal type | Definition |", "|---|---|---|"]
    for code, (name, desc) in SIGNALS.items():
        lines.append(f"| {code} | {name} | {desc} |")
    return "\n".join(lines)
