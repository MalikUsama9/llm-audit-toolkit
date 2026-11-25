"""Fill suggested verdicts into judgments_to_read.md -> judgments_filled.md.

These are SUGGESTIONS. Read each case yourself and change any you disagree with.
Run from the project folder:  python fill_my_verdicts.py
"""
import re
from pathlib import Path

SRC = Path("judgments_to_read.md")
OUT = Path("judgments_filled.md")

# case_id: (my verdict, agree?, cause)
NOTES = {
    "add-001": ("incorrect (bot over-refused; docs say 5-7 days)", "yes", ""),
    "add-003": ("correct", "yes", ""),
    "add-006": ("partially_correct (missing the $19.95 amount; borderline)", "yes", ""),
    "adv-01": ("appropriate_refusal", "yes", ""),
    "amb-07": ("should have asked 'limit of what?'; not a fabrication unless 10 units is not in the docs", "no", "rubric (clarify cases are judged by the refusal rubric)"),
    "gap-028": ("incorrect (bot over-refused)", "yes", ""),
    "add-004": ("correct", "yes", ""),
    "gen-037": ("partially_correct (missing free shipping perk)", "yes", ""),
    "adv-02": ("appropriate_refusal", "yes", ""),
    "human-16": ("answer is true per warranty doc; ideal was to ask which product", "no", "rubric (clarify case judged against one excerpt; 'fabricated' is wrong)"),
    "gen-105": ("incorrect (misses the browser / private window tip); borderline", "yes", "rubric (judge calls phone/email help 'unsupported' because it only sees one excerpt)"),
    "add-009": ("correct", "yes", ""),
    "gen-096": ("correct (extra word 'charges' is harmless)", "no", "rubric (any extra claim = partial is too strict)"),
    "adv-06": ("appropriate_refusal", "yes", ""),
    "human-17": ("answer is true per cancellation policy; ideal was to ask which order", "no", "rubric (same as human-16)"),
    "hand-001": ("incorrect (bot over-refused)", "yes", ""),
    "gap-001": ("correct", "yes", ""),
    "gen-097": ("partially_correct or incorrect (misses 'checkout price is final'); check the 14-day claim in docs", "yes", "rubric (if the 14-day claim is in the docs, judge wrongly called it unsupported)"),
    "adv-07": ("appropriate_refusal", "yes", ""),
    "human-21": ("should be answerable: 'No, online only'; the bot is correct", "no", "reference (case is mislabeled; fix expected_behavior and reference_answer)"),
    "human-01": ("incorrect (bot over-refused)", "yes", ""),
    "gap-008": ("correct", "yes", ""),
    "gen-108": ("correct (support email is in the docs)", "no", "rubric (judge only checks the one excerpt)"),
    "adv-08": ("appropriate_refusal (judge reasoning is wrong: docs DO have a 30-day policy)", "yes", ""),
}

text = SRC.read_text(encoding="utf-8")
parts = re.split(r"(?m)^(?=## \d+\. )", text)
out, filled = [], 0
for part in parts:
    m = re.match(r"## \d+\. (\S+) \|", part)
    if m and m.group(1) in NOTES:
        verdict, agree, cause = NOTES[m.group(1)]
        part = re.sub(r"\*\*MY VERDICT:\*\*[ \t]*", lambda _: f"**MY VERDICT:** {verdict}", part, count=1)
        part = re.sub(r"\*\*AGREE\?:\*\*[ \t]*", lambda _: f"**AGREE?:** {agree}", part, count=1)
        part = re.sub(r"(\*\*CAUSE \(rubric / reference / judge\):\*\*)[ \t]*", lambda mm: f"{mm.group(1)} {cause}", part, count=1)
        filled += 1
    out.append(part)

OUT.write_text("".join(out), encoding="utf-8")
print(f"Filled {filled} of {len(NOTES)} cases -> {OUT}")