"""Per-activation points behind 'does FVE predict grounding?' (summarize_results.fve_vs_grounding).

For each activation, with the `full` explanation: x = FVE of the AR reconstruction,
y = share of the activation's original (validated-label) latents the judge finds stated.
Activations with fewer than 3 judged latents are dropped, as in summarize_results.py.
Writes results/fve_vs_grounding_points.csv and prints the quartile contrast.
"""
import csv, json, math

MIN_LATENTS = 3
fve = {int(r["act"]): float(r["fve_B"]) for r in csv.DictReader(open("results/per_example.csv")) if r["variant"] == "full"}
num, den = {}, {}
for r in json.load(open("results/grounding.json"))["rows"]:
    if r["variant"] != "full" or r["bucket"] not in ("shared", "lost") or r["verdict"] not in ("present", "not_present"):
        continue
    den[r["act"]] = den.get(r["act"], 0) + 1
    num[r["act"]] = num.get(r["act"], 0) + (r["verdict"] == "present")
pts = sorted((a, fve[a], num[a] / den[a], den[a]) for a in den if den[a] >= MIN_LATENTS and a in fve)
with open("results/fve_vs_grounding_points.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["act", "fve", "share_stated", "n_latents"]); w.writerows(pts)

n = len(pts); x = [p[1] for p in pts]; y = [p[2] for p in pts]
mx, my = sum(x) / n, sum(y) / n
r = sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
q = n // 4; order = sorted(range(n), key=lambda i: x[i])
lo, hi = order[:q], order[-q:]
avg = lambda v, ii: sum(v[i] for i in ii) / len(ii)
print(f"n={n} pearson r={r:.3f} FVE min={min(x):.2f} median={sorted(x)[n // 2]:.2f} max={max(x):.2f}")
print(f"bottom quartile (n={q}): mean FVE {avg(x, lo):.2f}, features stated {avg(y, lo):.1%}")
print(f"top quartile (n={q}): mean FVE {avg(x, hi):.2f}, features stated {avg(y, hi):.1%}")
