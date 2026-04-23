"""Generate a small one-page PDF with a deliberate pricing contradiction.

This is intentionally NOT marketing fluff — it contains a plausible-looking
update that contradicts information typically found on Linear's public
pricing page. When ingested after a URL crawl of linear.app, the merge
pipeline should detect the conflict and flag the affected fact.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


BODY = [
    ("Heading1", "Linear — Partner Pricing Update (FY2026)"),
    ("BodyText", "Effective April 2026. For distribution to authorized partners only."),
    ("Heading2", "Plans and List Prices"),
    (
        "BodyText",
        # NOTE: intentional contradiction with the public pricing page:
        # Linear's public Business / Enterprise listing is very different from
        # the figures below. The point is to exercise the conflict path.
        "After this update, Linear's Business plan is priced at <b>$19 per user / "
        "month</b> when billed monthly. The Enterprise plan is priced at "
        "<b>$49 per user / month</b>, billed annually, with a minimum seat count."
    ),
    ("Heading2", "Free Tier"),
    (
        "BodyText",
        "Linear continues to offer a Free plan for small teams, which remains "
        "unchanged from prior documentation."
    ),
    ("Heading2", "Notes for Partners"),
    (
        "BodyText",
        "Partner-resold seats receive a 15% discount off the Business plan list "
        "price. Enterprise deals are non-discounted and negotiated case-by-case."
    ),
]


def build(path: Path) -> None:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Tight", parent=styles["BodyText"], spaceAfter=6))

    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        title="Linear Partner Pricing Update (FY2026)",
        author="Linear Partner Ops",
    )
    flow = []
    for style_name, text in BODY:
        flow.append(Paragraph(text, styles[style_name]))
        flow.append(Spacer(1, 6))
    doc.build(flow)


if __name__ == "__main__":
    out = Path(__file__).with_name("linear_contradiction.pdf")
    build(out)
    print(f"Wrote {out}")
