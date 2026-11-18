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
from lab9.eval import SPEC, aggregate, load_spec, per_item
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
    problems: list[str] = []
    for name, rep in (("PR", pr), ("baseline", base)):
        if not isinstance(rep.get("rows"), list) or not rep["rows"]:
            problems.append(f"{name} report has no rows")
    if problems:
        return problems
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]

    # 1. Metric values must be finite numbers (NaN < min is False: a naive gate passes it).
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} = {v} (not a finite number)")
        elif v is not None and not isinstance(v, (int, float)):
            problems.append(f"metric {k} = {v!r} (not a number)")

    # 2. Row count and the (item, seed) grid: no dropped, duplicated or cherry-picked rows.
    m_pr, m_base = pr.get("manifest") or {}, base.get("manifest") or {}
    try:
        want = int(m_pr.get("items")) * len(m_pr.get("seeds") or [])
    except (TypeError, ValueError):
        want = -1
    if len(pr["rows"]) != want:
        problems.append(f"{len(pr['rows'])} rows != manifest {m_pr.get('items')} items x {len(m_pr.get('seeds') or [])} seeds")
    keys = [(r.get("item_id"), r.get("seed")) for r in pr["rows"]]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        problems.append(f"{len(dups)} duplicated (item, seed) row(s), first {dups[0]}")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base["rows"]}
    if set(keys) != base_keys:
        missing, extra = base_keys - set(keys), set(keys) - base_keys
        problems.append(f"(item, seed) set differs from baseline: {len(missing)} missing, {len(extra)} extra")
    for field in ("items", "seeds"):
        if m_pr.get(field) != m_base.get(field):
            problems.append(f"manifest {field} {m_pr.get(field)!r} != baseline {m_base.get(field)!r}")

    # 3. Graders must have scored every row: a crash must not drop out of the mean.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    if "evaluator_failures" not in pr:
        problems.append("report has no evaluator_failures field")
    for m in graded:
        bad = [r for r in pr["rows"] if not isinstance(r.get(m), bool)]
        if bad:
            problems.append(f"{len(bad)} row(s) without a {m} score (None/NaN/missing), first {bad[0].get('item_id')}@{bad[0].get('seed')}")

    # 4. Headline metrics must be the ones the rows produce (hand-edited numbers).
    if not problems:
        k_values = spec.get("pass_k", [])
        has_cost = all("cost" in r for r in pr["rows"])
        rows = [{**r, "cost": float(r.get("cost") or 0.0)} for r in pr["rows"]]
        redo = aggregate(rows, [m for m in graded if m in rows[0]], k_values=k_values)
        if not has_cost:
            redo.pop("cost_per_success", None)
        for k, v in redo.items():
            got = (pr.get("metrics") or {}).get(k)
            if k in (pr.get("metrics") or {}) and not _close(got, v):
                problems.append(f"metric {k} = {got} but its rows give {v}")

    # 5. An item's slice tags must not change between baseline and PR.
    tags_base = {r.get("item_id"): sorted(r.get("slices") or []) for r in base["rows"]}
    moved = sorted({r.get("item_id") for r in pr["rows"]
                    if r.get("item_id") in tags_base and sorted(r.get("slices") or []) != tags_base[r.get("item_id")]}, key=str)
    if moved:
        problems.append(f"slice tags changed vs baseline for {len(moved)} item(s), first {moved[0]}")

    # 6. Ratchet: on the same eval-set version, thresholds may only get stricter.
    if base_spec is not None:
        problems += ratchet_check(spec, base_spec)
    return problems


def _close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return isinstance(a, (int, float)) and math.isfinite(a) and abs(float(a) - float(b)) <= 1e-3


def _looser(th: dict, base_th: dict) -> list[str]:
    out = []
    for key, bv in base_th.items():
        if key not in th:
            out.append(f"{key} removed")
        elif key in ("max", "max_increase") and th[key] > bv:
            out.append(f"{key} {bv} -> {th[key]}")
        elif key == "min" and th[key] < bv:
            out.append(f"min {bv} -> {th[key]}")
        elif key == "no_significant_drop" and bv and not th[key]:
            out.append("no_significant_drop dropped")
    return out


def ratchet_check(spec: dict, base_spec: dict) -> list[str]:
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []                      # new eval-set version = new baseline, thresholds restart
    problems = []
    metrics = {m["id"]: m for m in spec.get("metrics", [])}
    for bm in base_spec.get("metrics", []):
        m = metrics.get(bm["id"])
        if m is None:
            problems.append(f"ratchet: metric {bm['id']} removed from the spec")
            continue
        if bm.get("blocking") and not m.get("blocking"):
            problems.append(f"ratchet: metric {bm['id']} no longer blocking")
        problems += [f"ratchet: metric {bm['id']} {x}" for x in _looser(m.get("threshold") or {}, bm.get("threshold") or {})]
    slices = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        s = slices.get((bs["name"], bs["metric"]))
        if s is None:
            problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} removed from the spec")
            continue
        if bs.get("blocking") and not s.get("blocking"):
            problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} no longer blocking")
        th = {k: v for k, v in s.items() if k in ("min", "max", "no_significant_drop")}
        bth = {k: v for k, v in bs.items() if k in ("min", "max", "no_significant_drop")}
        problems += [f"ratchet: slice {bs['name']}/{bs['metric']} {x}" for x in _looser(th, bth)]
    for key in ("seeds", "bootstrap"):
        if spec.get(key) != base_spec.get(key):
            problems.append(f"ratchet: spec {key} changed on the same eval-set version")
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
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", f"n={len(a)} item"
        if val is None:
            verdict = "missing"                 # a slice that vanished cannot be called healthy
        elif "min" in s and val < s["min"]:
            verdict = "fail"
        if s.get("no_significant_drop") and a:
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note += f" Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<36} {note:<36} {label}")
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
