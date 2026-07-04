# Importing the surveys into Qualtrics

Each `qualtrics_NN.txt` is a Qualtrics **Advanced Format** file. Importing one
builds an entire team survey in a few clicks — the intro, the name field, and all
9 questions (each with the two answers and the "Response 1 / Response 2 / About
the same" choices). No per-question copy-paste.

## Steps (repeat once per team survey)

1. In Qualtrics, **Create Project → Survey → Blank project.** Name it for the team,
   e.g. `AI Answers — Team 1`.
2. In the survey editor, open **Tools → Import/Export → Import Questions…**
   (in some accounts: the block menu ▾ → *Import questions from a file*).
3. Upload **`qualtrics_01.txt`**. Qualtrics reads the Advanced Format and creates
   the intro text, the name/email field, and all 9 comparison questions.
4. Skim it, then **Publish** and grab the **Anonymous Link** (Distributions → Anonymous
   Link) to share with that team.
5. Repeat for `qualtrics_02.txt … qualtrics_12.txt` → **12 separate surveys**, one
   per Code+ team. (Keep them separate — don't import all 12 into one project, or
   you'd need branching logic to route each team to its block.)

## Notes

- **If the intro block doesn't import cleanly** (older Qualtrics parsers), just
  delete that first text question and paste the title/description into the survey's
  own description field — the questions are the important part.
- **One question per page** is built in (a page break after each). Remove them if
  you'd rather have everything on one page.
- The **name/email** field is optional for raters; set it to not-required in
  Qualtrics if you want fully anonymous responses.

## Joining the results back (for the analysis)

Each question's Qualtrics **export tag = the item id with underscores**, e.g.
`itm_001` in the CSV corresponds to `itm-001` in
[version_map.csv](version_map.csv). To join:

- Export responses (Data & Analysis → Export → CSV).
- For each answered question column `itm_0NN`, map it back to `itm-0NN`.
- Look up that item's `response1_model` / `response2_model` in `version_map.csv`.
- Convert the pick (`Response 1` / `Response 2` / `About the same`) → chosen /
  rejected model → (with `responses.jsonl`) chosen / rejected **text**.

That's the same join described in [analysis_plan.md](analysis_plan.md) — the only
difference is the underscore in the exported item id.
