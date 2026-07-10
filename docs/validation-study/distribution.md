# Survey distribution — 6 raters

Fill this in as you publish each Qualtrics survey (see
[QUALTRICS_IMPORT.md](QUALTRICS_IMPORT.md)). One survey → one rater → one link.

**Important:** ask each person to enter, in the survey's name/email field, the
**exact name you put in the "Assigned to" column** — that's the `rater_id` the
analysis joins on. If names don't match, the labels can't be attributed.

| Rater | Survey to import | Assigned to (name) | Anonymous link | Sent? |
|-------|------------------|--------------------|----------------|-------|
| 01 | `qualtrics_rater_01.txt` | _________ | _paste link_ | ☐ |
| 02 | `qualtrics_rater_02.txt` | _________ | _paste link_ | ☐ |
| 03 | `qualtrics_rater_03.txt` | _________ | _paste link_ | ☐ |
| 04 | `qualtrics_rater_04.txt` | _________ | _paste link_ | ☐ |
| 05 | `qualtrics_rater_05.txt` | _________ | _paste link_ | ☐ |
| 06 | `qualtrics_rater_06.txt` | _________ | _paste link_ | ☐ |

Each survey is **30 questions, ~25 minutes** (fine to do in two sittings). Every
question is also answered by 2 other raters, so each gets 3 independent labels.

## Message you can send each rater

> Hi [name] — thanks for helping validate our AI evaluator! This is a ~25-minute
> survey (feel free to split it across two sittings). You'll see two AI answers to
> the same small task and just pick the one you think is better, or "About the
> same." There are no right answers — go with your honest first impression.
>
> **Your link:** [paste this rater's anonymous link]
>
> One ask: in the first field, please enter your name exactly as **[the name in
> the Assigned-to column]** so we can match your answers. Thank you!

## After everyone finishes

Export each rater's responses to CSV (Data & Analysis → Export → CSV) and drop the
6 files somewhere `analyze.py` can read them — it joins on `rater_map.csv` to
produce the κ, bias, ranking, and DPO outputs.
