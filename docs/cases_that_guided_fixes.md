# Cases that guided the fixes

## Clarifying-question rule (prompt v1 -> day9)
Dev-set cases that guided it: human-17, human-16, amb-07

## top_k 4 -> 8
Dev-set cases that guided it (the bot said "I don't have that information" although the document had the answer): add-001, gen-105, gap-028, human-01, human-03

## Held-out discipline
Held-out failures were visible in the `audit compare --details` output, so I cannot rule out indirect influence.

## Note
Every case ID listed above is a development-set case. Held-out cases (for example amb-04, gen-001, add-002) were scored but are not listed as guiding any fix.
