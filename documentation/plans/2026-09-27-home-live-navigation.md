# Home and LIVE refinement

**Goal:** Implement the five UI changes from the user's September 27 screenshots.
**Approach:** Update the shared shell and landing generator; show archived top-ten forecasts for exactly the LIVE snapshot date.
**Tools:** Python, static HTML/CSS, vanilla JavaScript, pytest, Node/JSDOM, Chromium.

- [x] Remove the sidebar filter and the three redundant statistics menu shortcuts.
- [x] Point the header calendar to index.html#db-tuan-thang.
- [x] Color the hero special prize red and turn its two lower cards into statistics/results buttons.
- [x] Add three LIVE navigation buttons and two forecast columns.
- [x] Test leading zeros, date validation, partial availability, retries and late responses.
- [ ] Check the published pages, full CI, browser layouts and the complete diff; merge.

Constraints: preserve live results, verification and polling; preserve global search and mobile focus behavior; Vietnamese text and existing light/dark tokens. The LIVE forecast is two-digit statistical ranking, drawn from predict_next_{de,loto}_top10_{draw_date}.csv. Missing dates never fall back to another day. Conflict information moves to the status card.

Execution note: 70 frontend tests passed locally. The execution environment went offline during publication, so the same edits were reconstructed through the repository connector and require a fresh CI run before merging.
