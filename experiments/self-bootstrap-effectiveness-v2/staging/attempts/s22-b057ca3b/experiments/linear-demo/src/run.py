from __future__ import annotations

import csv
import json
from pathlib import Path


root = Path(__file__).resolve().parent.parent
with (root / "data" / "raw" / "points.csv").open(newline="", encoding="utf-8") as stream:
    rows = [{key: float(value) for key, value in row.items()} for row in csv.DictReader(stream)]

xs = [row["x"] for row in rows]
ys = [row["y"] for row in rows]
x_mean = sum(xs) / len(xs)
y_mean = sum(ys) / len(ys)
slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / sum(
    (x - x_mean) ** 2 for x in xs
)
intercept = y_mean - slope * x_mean
residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
results = {
    "n": len(rows),
    "slope": slope,
    "intercept": intercept,
    "slope_absolute_error": abs(slope - 2.0),
    "intercept_absolute_error": abs(intercept - 1.0),
    "max_absolute_residual": max(abs(value) for value in residuals),
}

artifacts = root / "artifacts"
artifacts.mkdir(exist_ok=True)
(artifacts / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

points = "\n".join(
    f'<circle cx="{40 + x * 80:.1f}" cy="{260 - y * 30:.1f}" r="5" fill="#2563eb"/>'
    for x, y in zip(xs, ys)
)
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="360" height="300" viewBox="0 0 360 300">
<rect width="360" height="300" fill="white"/>
<path d="M40 260H330M40 260V20" stroke="#64748b" stroke-width="1"/>
<path d="M40 {260-intercept*30:.1f} L280 {260-(slope*3+intercept)*30:.1f}" stroke="#dc2626" stroke-width="2"/>
{points}
<text x="180" y="292" text-anchor="middle" font-family="sans-serif" font-size="13">y = {slope:.1f}x + {intercept:.1f}</text>
</svg>'''
(artifacts / "fit.svg").write_text(svg, encoding="utf-8")

