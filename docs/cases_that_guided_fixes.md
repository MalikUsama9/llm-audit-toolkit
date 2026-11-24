\# Cases that guided the fixes



\## Clarifying-question rule (prompt v1 -> day9)

Dev-set cases that guided it: <dev case IDs, e.g. amb-04, human-16>



\## top\_k 4 -> 8

Dev-set cases that guided it (the bot said "I don't have that information" although the document had the answer): <dev case IDs, e.g. gen-001, add-001>



\## Held-out discipline

<Keep ONE line and delete the other>

\- I did not read held-out failures when choosing fixes.

\- Held-out failures were visible in the `audit compare --details` output, so I cannot rule out indirect influence.



\## Note

Only development-set failures were used to choose fixes. Held-out cases were scored but not used to design changes.

