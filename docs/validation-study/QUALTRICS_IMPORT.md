# Importing the surveys into Qualtrics + sending the links

**Current design (self-label, 6 raters):** import the six `qualtrics_rater_0X.txt`
files — one survey per rater, 30 questions each (~25 min). Each
`qualtrics_rater_0X.txt` is a Qualtrics **Advanced Format** file: importing one
builds the whole survey in a few clicks — the intro, the name field, and all 30
comparison questions (each with the two answers and the "Response 1 / Response 2 /
About the same" choices). No per-question copy-paste.

> The old 12-team files (`qualtrics_01.txt … qualtrics_12.txt`, `version_map.csv`)
> are **superseded** by this design — don't import those.

## Steps (repeat once per rater — 6 times)

1. In Qualtrics, **Create project → Survey → Blank project.** Name it for the
   rater, e.g. `AI Answers — Rater 1`.
2. In the survey editor, open **Tools → Import/Export → Import Questions…**
   (in some accounts: the block menu ▾ → *Import questions from a file*).
3. Upload **`qualtrics_rater_01.txt`**. Qualtrics reads the Advanced Format and
   creates the intro text, the name/email field, and all 30 comparison questions.
4. Skim it, then **Publish** and grab the **Anonymous Link**
   (Distributions → Anonymous Link).
5. Paste that link into [distribution.md](distribution.md) next to Rater 1, then
   repeat for `qualtrics_rater_02.txt … qualtrics_rater_06.txt` → **6 separate
   surveys / 6 links**, one per rater. Keep them separate (don't import all 6 into
   one project, or you'd need branching logic to route each rater to their block).

## Notes

- **If the intro block doesn't import cleanly** (older Qualtrics parsers), just
  delete that first text question and paste the title/description into the survey's
  own description field — the questions are the important part.
- **One question per page** is built in (a page break after each). Remove them if
  you'd rather have everything on one page.
- Keep the **name/email** field: it's the `rater_id` the analysis joins on. Ask
  each person to put the same name they were assigned in `distribution.md`.

## Joining the results back (for the analysis)

Each question's Qualtrics **export tag = the item id with underscores**, e.g.
`itm_001` in the CSV corresponds to `itm-001` in
[rater_map.csv](rater_map.csv). To join:

- Export each rater's responses (Data & Analysis → Export → CSV).
- For each answered column `itm_0NN`, map it back to `itm-0NN`.
- Look up that `(rater, item)` row in `rater_map.csv` for its
  `response1_model` / `response2_model`.
- Convert the pick (`Response 1` / `Response 2` / `About the same`) → chosen /
  rejected model → (with `responses.jsonl`) chosen / rejected **text**.

That's the join in [analysis_plan.md](analysis_plan.md); the only wrinkle is the
underscore in the exported item id, and that the join key is now `(rater, item)`.
