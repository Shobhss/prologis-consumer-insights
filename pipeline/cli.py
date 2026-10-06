"""Command-line entry point.

    python -m pipeline.cli fetch     --customer amazon [--only edgar,transcripts,news]
    python -m pipeline.cli normalize --customer amazon
    python -m pipeline.cli prefilter --customer amazon
    python -m pipeline.cli extract   --customer amazon [--limit N] [--sections "Item 2,Item 7"]
    python -m pipeline.cli implicate --customer amazon
    python -m pipeline.cli report    --customer amazon      # also refreshes outputs/dashboard/
    python -m pipeline.cli dashboard                        # dashboard only, all customers
    python -m pipeline.cli run       --customer amazon        # all stages
    python -m pipeline.cli status    [--customer amazon]
    python -m pipeline.cli feedback  --signal-id ID --verdict useful|not_useful|wrong [--note ...]
"""
from __future__ import annotations

import argparse
import json
import sys

import yaml

from . import normalize, prefilter, store
from .config import ROOT, get_customer


def _sources_cfg() -> dict:
    with open(ROOT / "config" / "sources.yaml") as f:
        return yaml.safe_load(f)


def cmd_fetch(args):
    customer = get_customer(args.customer)
    cfg = _sources_cfg()
    only = set(args.only.split(",")) if args.only else {"edgar", "transcripts", "news"}
    from .fetch import edgar, news, transcripts
    with store.connect() as con:
        for name, mod, key in (("edgar", edgar, "edgar"), ("transcripts", transcripts, "transcripts"), ("news", news, "news")):
            if name not in only:
                continue
            print(f"[{name}] fetching for {customer['name']} ...", flush=True)
            try:
                stats = mod.fetch(customer, con, cfg.get(key, {}))
                con.commit()
                print(f"[{name}] {json.dumps(stats)}", flush=True)
            except Exception as e:  # keep going; one source failing should not block others
                con.commit()
                print(f"[{name}] FAILED: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        print(json.dumps(store.doc_counts(con, customer["slug"]), indent=1))


def cmd_normalize(args):
    with store.connect() as con:
        n = normalize.build_chunks(con, args.customer, rebuild=args.rebuild)
        print(f"chunks created: {n}")


def cmd_prefilter(args):
    with store.connect() as con:
        print(json.dumps(prefilter.run(con, args.customer, force=args.force)))


def cmd_extract(args):
    from . import extract
    with store.connect() as con:
        print(json.dumps(extract.run(con, args.customer, limit=args.limit, sections=args.sections), indent=1))


def cmd_implicate(args):
    from . import implicate
    with store.connect() as con:
        print(json.dumps(implicate.run(con, args.customer, limit=args.limit), indent=1))


def cmd_report(args):
    from . import report
    with store.connect() as con:
        paths = report.run(con, args.customer, min_confidence=args.min_confidence)
    for p in paths:
        print(p)


def cmd_dashboard(args):
    from . import dashboard
    with store.connect() as con:
        print(dashboard.run(con, min_confidence=args.min_confidence))


def cmd_run(args):
    for fn in (cmd_fetch, cmd_normalize, cmd_prefilter, cmd_extract, cmd_implicate, cmd_report):
        fn(args)


def cmd_status(args):
    with store.connect() as con:
        print("documents:")
        print(json.dumps(store.doc_counts(con, args.customer), indent=1))
        q = "SELECT COUNT(*) n, SUM(COALESCE(relevant,0)) rel, SUM(extracted_at IS NOT NULL) done FROM chunks c JOIN documents d ON d.doc_id=c.doc_id"
        a = ()
        if args.customer:
            q += " WHERE d.customer=?"
            a = (args.customer,)
        r = con.execute(q, a).fetchone()
        print(f"chunks: total={r['n']} relevant={r['rel']} extracted={r['done']}")
        q = "SELECT signal_code, COUNT(*) n, ROUND(AVG(confidence),2) conf FROM signals"
        if args.customer:
            q += " WHERE customer=?"
        q += " GROUP BY signal_code ORDER BY n DESC"
        print("signals:")
        for row in con.execute(q, a):
            print(f"  {row['signal_code']:<10} {row['n']:>4}  avg conf {row['conf']}")


def cmd_feedback(args):
    with store.connect() as con:
        con.execute("INSERT INTO feedback(signal_id, verdict, note, reviewer, created_at) VALUES (?,?,?,?,?)",
                    (args.signal_id, args.verdict, args.note, args.reviewer, store.now_iso()))
    print("recorded")


def main(argv=None):
    p = argparse.ArgumentParser(prog="pipeline", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, customer_required=True):
        sp = sub.add_parser(name)
        sp.add_argument("--customer", required=customer_required, help="slug from config/customers.yaml")
        sp.set_defaults(fn=fn)
        return sp

    s = add("fetch", cmd_fetch); s.add_argument("--only", help="comma list: edgar,transcripts,news")
    s = add("normalize", cmd_normalize); s.add_argument("--rebuild", action="store_true")
    s = add("prefilter", cmd_prefilter); s.add_argument("--force", action="store_true")
    s = add("extract", cmd_extract); s.add_argument("--limit", type=int); s.add_argument("--sections", help="comma list of section label prefixes")
    s = add("implicate", cmd_implicate); s.add_argument("--limit", type=int)
    s = add("report", cmd_report); s.add_argument("--min-confidence", type=float, default=0.0)
    s = add("dashboard", cmd_dashboard, customer_required=False); s.add_argument("--min-confidence", type=float, default=0.0)
    s = add("run", cmd_run)
    for a, kw in (("--only", {}), ("--rebuild", {"action": "store_true"}), ("--force", {"action": "store_true"}),
                  ("--limit", {"type": int}), ("--sections", {}), ("--min-confidence", {"type": float, "default": 0.0})):
        s.add_argument(a, **kw)
    add("status", cmd_status, customer_required=False)
    s = add("feedback", cmd_feedback, customer_required=False)
    s.add_argument("--signal-id", required=True); s.add_argument("--verdict", required=True, choices=["useful", "not_useful", "wrong"])
    s.add_argument("--note"); s.add_argument("--reviewer")

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
