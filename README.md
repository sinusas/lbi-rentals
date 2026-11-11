# LBI rentals: summer 2027

Map of rental options in Beach Haven and Holgate (Long Beach Island, NJ) for the week of Aug 7–14, 2027.

- `index.html` is the main page (Sarah's picks). `ai/index.html` is a separate page at `/lbi-rentals/ai/` that adds the A.I.'s (unchecked) search results; it is not linked from the main page.
- Each page is self-contained. House details are in the `HOUSES` list near the top of the script.
- `all/index.html` (`/lbi-rentals/all/`) lists every south-LBI rental sleeping 8+ that could be scraped: all of lbi.vacations plus Van Dyk Group houses its calendar shows open Aug 7–14. Data is in `all/houses.json`; refresh it with `python3 build_all.py --fresh` (raw pages cache in `.cache/`, which is git-ignored).
- `build_routes.py` refetches the walking/bike/drive routes (OpenStreetMap routing) after you add or move a house or point of interest: `python3 build_routes.py` (or `python3 build_routes.py ai/index.html` for the A.I. page)

## Votes & comments setup (one time)

The page stores votes and comments in a Google Sheet through a small Apps Script web app (`apps-script/Code.gs`).

1. Create a new Google Sheet (sheets.new), e.g. "LBI 2027 votes".
2. **Extensions → Apps Script**. Replace everything in `Code.gs` with the contents of `apps-script/Code.gs`, then save.
3. **Deploy → New deployment** → gear icon → **Web app**. Execute as: **Me**. Who has access: **Anyone**. Click Deploy and approve the permissions. Google warns that the app isn't verified: choose Advanced → Go to (project).
4. Copy the **Web app URL** (ends in `/exec`) and paste it into `const FEEDBACK_URL = "";` near the top of the script in `index.html`, then commit and push.

Votes and comments appear as rows in the `votes` and `comments` tabs; delete a row to remove one. If you edit `Code.gs` later, use **Deploy → Manage deployments → Edit → New version** so the URL stays the same.

## "Suggest a house" form (one time)

1. In the Sheet's Apps Script editor, paste the latest `apps-script/Code.gs` and save.
2. Pick `createSuggestionForm` in the function dropdown and click **Run** (approve the Forms permission).
3. Copy the "Share link" from the Execution log into `const SUGGEST_URL = "";` in `index.html`.

Suggestions land in a "Form Responses" tab of the same Sheet. Nothing updates the map automatically.
