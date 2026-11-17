"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems = []

    # 1. any metric value in pr["metrics"] that is NaN or inf
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k} is NaN or inf")

    # 2. len(pr["rows"]) != manifest items x len(manifest seeds)
    manifest = pr.get("manifest") or {}
    expected_row_count = int(manifest.get("items", 0)) * len(manifest.get("seeds", []))
    if len(pr.get("rows", [])) != expected_row_count:
        problems.append(f"row count {len(pr.get('rows', []))} != manifest items ({manifest.get('items')}) x seeds ({len(manifest.get('seeds', []))})")

    # 3. the (item_id, seed) set of PR differs from the baseline's
    pr_set = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows", [])}
    base_set = {(r.get("item_id"), r.get("seed")) for r in base.get("rows", [])}
    if pr_set != base_set:
        problems.append("PR (item_id, seed) set differs from baseline")

    # 4. pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is None
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s)")

    graded_metrics = [m["id"] for m in spec.get("metrics", []) if m.get("id") in GRADERS]
    for r in pr.get("rows", []):
        for m in graded_metrics:
            if r.get(m) is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has None for graded metric {m}")
                break
        if problems and problems[-1].startswith("row"):
            break

    # 5. base_spec given and a threshold in spec is LOOSER than in base_spec for the same eval-set version
    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        base_metrics = {m["id"]: m for m in base_spec.get("metrics", [])}
        for m in spec.get("metrics", []):
            mid = m["id"]
            if mid not in base_metrics:
                continue
            bm = base_metrics[mid]
            if bm.get("blocking") and not m.get("blocking"):
                problems.append(f"metric {mid} blocking changed to non-blocking")
            b_max = bm.get("threshold", {}).get("max")
            m_max = m.get("threshold", {}).get("max")
            if b_max is not None and (m_max is None or m_max > b_max):
                problems.append(f"metric {mid} max threshold loosened ({b_max} -> {m_max})")
            b_min = bm.get("threshold", {}).get("min")
            m_min = m.get("threshold", {}).get("min")
            if b_min is not None and (m_min is None or m_min < b_min):
                problems.append(f"metric {mid} min threshold loosened ({b_min} -> {m_min})")
            if bm.get("threshold", {}).get("no_significant_drop") and not m.get("threshold", {}).get("no_significant_drop"):
                problems.append(f"metric {mid} no_significant_drop was removed")

        curr_mids = {m["id"] for m in spec.get("metrics", [])}
        for bmid, bm in base_metrics.items():
            if bmid not in curr_mids and bm.get("blocking"):
                problems.append(f"blocking metric {bmid} was removed from spec")

        base_slices = {s["name"]: s for s in base_spec.get("slices", [])}
        curr_slices = {s["name"]: s for s in spec.get("slices", [])}
        for sname, bs in base_slices.items():
            if sname not in curr_slices:
                problems.append(f"slice {sname} was removed from spec")
            else:
                cs = curr_slices[sname]
                if bs.get("min") is not None and (cs.get("min") is None or cs.get("min") < bs.get("min")):
                    problems.append(f"slice {sname} min loosened")
                if bs.get("no_significant_drop") and not cs.get("no_significant_drop"):
                    problems.append(f"slice {sname} no_significant_drop was removed")

    # 6. an item's slice tags in PR rows differ from the baseline's
    base_slices_by_item = {r.get("item_id"): tuple(sorted(r.get("slices") or [])) for r in base.get("rows", [])}
    for r in pr.get("rows", []):
        iid = r.get("item_id")
        if iid in base_slices_by_item:
            pr_sl = tuple(sorted(r.get("slices") or []))
            if pr_sl != base_slices_by_item[iid]:
                problems.append(f"item {iid} slices {pr_sl} != baseline {base_slices_by_item[iid]}")
                break

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices", []):
        name = sl["name"]
        mid = sl["metric"]
        min_th = sl.get("min")
        blocking = sl.get("blocking", False)

        pr_items = per_item(pr, mid, slice_name=name)
        val = sum(pr_items.values()) / len(pr_items) if pr_items else 0.0

        verdict, note = "ok", ""
        if min_th is not None and val < min_th:
            verdict = "fail"

        if sl.get("no_significant_drop") and pr_items:
            base_items = per_item(base, mid, slice_name=name)
            keys = sorted(set(pr_items) & set(base_items))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [pr_items[k] for k in keys],
                    [base_items[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"

        slice_id = f"slice:{name}/{mid}"
        if verdict != "ok" and blocking:
            blocked.append(slice_id)
        label = "BLOCK" if (verdict != "ok" and blocking) else ("warn" if verdict != "ok" else "ok")
        lines.append(f"  {slice_id:<22} {val:<8.4f} min={min_th!s:<34} {note:<28} {label}")

    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
