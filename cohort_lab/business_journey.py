"""One qualitative business introduction; no inferred customer-level path."""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

STAGES = [
    ("Discover", "Search / partner workshop", "A relevant project idea", "Vague promises"),
    ("Evaluate", "Compare membership plans", "Clear fit with a work goal", "Unclear plan differences"),
    ("Subscribe", "Choose a plan and pay", "Predictable monthly price", "Commitment concerns"),
    ("First value", "Use a template or lesson", "A useful first output", "Setup takes too long"),
    ("Regular use", "Projects / learning / add-ons", "Time saved; visible progress", "Too little time to use it"),
    ("Renew", "Review value and next bill", "A reason to return", "Benefits do not justify cost"),
]


def build_business_journey(folder: Path) -> dict:
    """Draw an original Starbucks-inspired experience map with qualitative lanes."""
    folder.mkdir(parents=True, exist_ok=True)
    source = {"title": "The Studio North membership experience", "evidence": "conceptual",
              "scope": "One broad business journey; possible benefits and friction points, not measured sentiment or a universal observed sequence.",
              "stages": [dict(zip(["stage", "touchpoint", "potential_benefit", "potential_friction"], s)) for s in STAGES],
              "vertical_position": "Qualitative placement only; no score, magnitude or probability is implied."}
    (folder / "business-journey.json").write_text(json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="670" viewBox="0 0 1500 670">',
             '<rect width="1500" height="670" fill="white"/>']
    def text(x, y, value, *, size=20, color="#202521", weight="400", anchor="middle"):
        parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}">{html.escape(value)}</text>')
    text(42, 44, source["title"], size=30, color="#185A46", weight="700", anchor="start")
    text(42, 78, "Monthly creative-work membership · templates, guided learning and optional add-ons", size=22, color="#5A625D", anchor="start")
    text(42, 155, "Potential benefits", color="#185A46", size=20, weight="700", anchor="start")
    text(42, 410, "Potential friction", color="#A3332D", size=20, weight="700", anchor="start")
    text(42, 286, "Expected", color="#5A625D", size=18, anchor="start")
    text(42, 310, "experience", color="#5A625D", size=18, anchor="start")
    parts.append('<path d="M210 295 H1460" stroke="#5A625D" stroke-width="1.5" stroke-dasharray="9 7"/>')
    for i, (stage, touchpoint, benefit, friction) in enumerate(STAGES):
        x = 300 + i * 207
        parts.append(f'<path d="M{x-100} 120 V552" stroke="#E4E9E5" stroke-width="1"/>')
        for y, label, color in [(208, benefit, "#185A46"), (375, friction, "#A3332D")]:
            parts.append(f'<circle cx="{x}" cy="{y}" r="7" fill="{color}"/>')
            # Wrap by words at an authored, fixed width; no browser-dependent measurement.
            words = label.split(); lines = [""]
            for word in words:
                if len(lines[-1]) + len(word) + 1 > 22:
                    lines.append(word)
                else:
                    lines[-1] = (lines[-1] + " " + word).strip()
            for j, line in enumerate(lines):
                text(x, y + 30 + 25*j, line, size=20, color=color)
        text(x, 492, stage, size=23, color="#185A46", weight="700")
        words=touchpoint.split(); lines=[""]
        for word in words:
            if len(lines[-1])+len(word)+1>23: lines.append(word)
            else: lines[-1]=(lines[-1]+" "+word).strip()
        for j,line in enumerate(lines): text(x, 527+24*j, line, size=19)
    parts.append('<path d="M200 470 H1450" stroke="#185A46" stroke-width="3"/>')
    text(42, 601, "A conceptual map of possible experiences, rather than measured satisfaction or a conversion funnel.", size=21, color="#5A625D", anchor="start")
    text(42, 634, "Renewal records show what customers did; event logs and feedback help investigate where value or friction arose.", size=21, color="#5A625D", anchor="start")
    parts.append('</svg>')
    svg="\n".join(parts)+"\n"
    (folder/"business-journey.svg").write_text(svg, encoding="utf-8", newline="\n")
    # The same authored vector is the browser view and the source of the print asset.
    markup='<!doctype html><html lang="en"><meta charset="utf-8"><title>Studio North business journey</title><body style="margin:0;background:white">'+svg+'</body></html>\n'
    (folder/"business-journey.html").write_text(markup,encoding="utf-8",newline="\n")
    return {"json":"diagrams/business-journey.json", "html":"diagrams/business-journey.html",
            "sha256":hashlib.sha256(markup.encode()).hexdigest(), "renderer":"Original qualitative experience-map SVG"}
