import html
GRAY, ORG, BLUE = "#8f8f87", "#e8632f", "#2f74d0"
LABELS = [("Full","explanation"),("First two","paragraphs"),("Final","paragraph")]
COLS = [GRAY, ORG, BLUE]

def bars(vals, ymax, step, fmt, title, W=300, H=190, baseline=None):
    L, R, T, B = 34, 8, 28, 38
    pw, ph = W-L-R, H-T-B
    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Times New Roman,Times,serif">']
    out.append(f'<text x="{L}" y="10" font-size="9.5" font-weight="700" fill="#222">{title}</text>')
    n = int(round(ymax/step))
    for i in range(n+1):
        v = i*step; y = T+ph-ph*v/ymax
        out.append(f'<line x1="{L}" x2="{W-R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{"#bbb" if i==0 else "#e6e6e1"}" stroke-width="{0.8 if i==0 else 0.6}"/>')
        out.append(f'<text x="{L-5}" y="{y+2.8:.1f}" font-size="7.5" text-anchor="end" fill="#777">{fmt(v,True)}</text>')
    bw = pw/3*0.55
    for i, v in enumerate(vals):
        cx = L + pw*(i+0.5)/3; h = ph*v/ymax; y = T+ph-h
        out.append(f'<rect x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{COLS[i]}"/>')
        out.append(f'<text x="{cx:.1f}" y="{y-4:.1f}" font-size="9.5" font-weight="700" text-anchor="middle" fill="#222">{fmt(v,False)}</text>')
        a, b = LABELS[i]
        out.append(f'<text x="{cx:.1f}" y="{T+ph+13}" font-size="8" text-anchor="middle" fill="#333">{a}</text>')
        out.append(f'<text x="{cx:.1f}" y="{T+ph+23}" font-size="8" text-anchor="middle" fill="#333">{b}</text>')
    if baseline is not None:
        y = T+ph-ph*baseline/ymax
        out.append(f'<line x1="{L}" x2="{W-R}" y1="{y:.1f}" y2="{y:.1f}" stroke="#222" stroke-width="0.9" stroke-dasharray="4 3"/>')
        out.append(f'<text x="{L+pw*0.335:.1f}" y="{y-9:.1f}" font-size="7.5" font-weight="700" text-anchor="middle" fill="#222">Baseline</text>')
        out.append(f'<text x="{L+pw*0.335:.1f}" y="{y-1.5:.1f}" font-size="7.5" font-weight="700" text-anchor="middle" fill="#222">4.6%</text>')
    out.append('</svg>')
    return "\n".join(out)

pct = lambda v, axis: f"{v:.0f}%"
num = lambda v, axis: (f"{v:.0f}" if axis else f"{v:.0f}")
dec = lambda v, axis: f"{v:.1f}" if axis else f"{v:.2f}"

fig2 = '<div class="pair"><div>%s</div><div>%s</div></div>' % (
    bars([134,59,73], 140, 20, num, "(A) Length: mean tokens per variant"),
    bars([0.69,0.27,0.58], 0.8, 0.2, dec, "(B) Reconstruction: mean FVE"))
fig3 = bars([70,30,59], 80, 20, pct, "Share of original SAE latents still active", W=420, H=210)
fig5 = bars([43,20,42], 50, 10, pct, "Share of original features the judge finds stated", W=420, H=210, baseline=4.6)

import csv
pts = [(float(r["fve"]), float(r["share_stated"])) for r in csv.DictReader(open("fve_vs_grounding_points.csv"))]
def scatter(pts, W=430, H=270):
    L, R, T, B = 40, 10, 22, 40; pw, ph = W-L-R, H-T-B; x0, x1 = -0.5, 1.0
    X = lambda v: L+pw*(v-x0)/(x1-x0); Y = lambda v: T+ph-ph*v
    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Times New Roman,Times,serif">']
    o.append(f'<text x="{L}" y="12" font-size="9.5" font-weight="700" fill="#222">Share of features stated vs. FVE (one point per activation)</text>')
    for i in range(6):
        v = i*0.2; y = Y(v)
        o.append(f'<line x1="{L}" x2="{W-R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{"#bbb" if i==0 else "#e6e6e1"}" stroke-width=".7"/>')
        o.append(f'<text x="{L-5}" y="{y+2.8:.1f}" font-size="7.5" text-anchor="end" fill="#777">{v*100:.0f}%</text>')
    for v in (-0.5, 0, 0.5, 1.0):
        x = X(v); o.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{T+ph}" y2="{T+ph+3}" stroke="#999" stroke-width=".7"/>')
        o.append(f'<text x="{x:.1f}" y="{T+ph+13}" font-size="7.5" text-anchor="middle" fill="#777">{v:.1f}</text>')
    o.append(f'<text x="{L+pw/2}" y="{H-6}" font-size="8.5" text-anchor="middle" fill="#333">FVE of the full explanation</text>')
    o.append(f'<text transform="translate(9,{T+ph/2}) rotate(-90)" font-size="8.5" text-anchor="middle" fill="#333">Share of features stated</text>')
    m = sum(y for _, y in pts)/len(pts)
    o.append(f'<line x1="{L}" x2="{W-R}" y1="{Y(m):.1f}" y2="{Y(m):.1f}" stroke="#222" stroke-width=".9" stroke-dasharray="4 3"/>')
    for x, y in pts:
        o.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="2.1" fill="{GRAY}" fill-opacity=".55" stroke="#4b4b46" stroke-width=".3"/>')
    o.append(f'<text x="{W-R-3}" y="{T+10}" font-size="9" text-anchor="end" font-weight="700" fill="#222">r = -0.01</text>')
    o.append('</svg>'); return "\n".join(o)
tpl = open("template.html").read()
for k, v in {"{{FIG2}}":fig2, "{{FIG3}}":fig3, "{{FIG5}}":fig5, "{{FIG6}}":scatter(pts)}.items():
    tpl = tpl.replace(k, v)
open("paper.html","w").write(tpl)
