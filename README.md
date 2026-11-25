# Flip Finder

Open the link → pick your area → the salvage cars near you that should make the most money show up first.
Each car card has a photo, estimated profit, current bid, the most to bid, when it ends, and a button to the listing.

* **Sources:** Pickles salvage (all of QLD) + Manheim salvage (QLD) + Manheim Brisbane clearing cars
* **Refresh:** every hour on GitHub's servers (full scan every 3 h, live bids hourly). Your computer can be off.
* **Alerts on the page:** 🆕 new money-makers since your last visit · ⏳ good cars ending in 6 h · 🔥 bid surges · ★ your saved cars ending soon
* **Works on phones and PCs.** On a phone: Share → *Add to Home Screen* for an app icon.

---

## Put it online (about 10 minutes, free)

1. **Make a free GitHub account** at <https://github.com/signup> and sign in.
2. **Create a repository:** click **+** (top right) → **New repository** → name it `flip-finder` → choose **Public** → **Create repository**.
3. **Upload the files:** on the new repo page click **uploading an existing file**.
   * In Finder, open the unzipped `salvage-flip-cloud` folder and press **Cmd + Shift + .** so the hidden **`.github`** folder shows.
   * Select **everything inside** the folder (`.github`, `docs`, `scraper`, `README.md`, …) and drag it onto the GitHub page → **Commit changes**.
   * Check that `.github/workflows/update.yml` appears in the repo. If it doesn't, click **Add file → Create new file**, type the name `.github/workflows/update.yml`, paste the contents of `workflow-copy.yml.txt`, and commit.
4. **Turn on the website:** repo **Settings → Pages** → *Build and deployment* → Source **Deploy from a branch** → Branch **main** and folder **/docs** → **Save**.
5. **Run the first scan:** **Actions** tab → (click *I understand… enable workflows* if asked) → **Update car listings** → **Run workflow** → **Run workflow**. It takes about 5–10 minutes.
6. **Open your site:** `https://YOUR-USERNAME.github.io/flip-finder/` (also shown under Settings → Pages). Send that link to your friends.

After that it runs by itself every hour.

## Optional: push new money-makers to chat

New clean-title cars with est. profit ≥ $1,000 can be sent as cards (photo + link) to a chat:

* **Discord:** in a channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL. In the repo: **Settings → Secrets and variables → Actions → New repository secret** → name `DISCORD_WEBHOOK_URL`, paste the URL.
* **WhatsApp / SMS / email / anything else:** create a webhook in Make, Zapier or n8n, then add it as a secret named `WEBHOOK_URL`. Each run posts JSON like `{"dashboard": "...", "cars": [{"title","url","image","estProfit","maxBid","currentBid","auctionEnds",...}]}` that you can forward to WhatsApp.

## Optional settings

Repo **Settings → Secrets and variables → Actions → Variables** tab:

| Variable | Default | What it does |
|---|---|---|
| `PICKLES_AREAS` | `qld` | Pickles areas to scan, comma-separated, e.g. `qld,nsw/sydney` or `qld/brisbane` |
| `FULL_EVERY_HOURS` | `3` | Hours between full listing scans (bids still refresh hourly) |
| `NOTIFY_MIN_PROFIT` | `1000` | Minimum est. profit before a car is pushed to chat |

## If something goes wrong

* **Footer shows a source as "not reachable":** that auction site refused GitHub's servers or changed its layout. The site keeps showing the last good data. Open **Actions → latest run** to see the message.
* **No updates for a while:** open **Actions** and check the workflow is enabled. GitHub pauses scheduled jobs in repos with no activity for 60 days; this repo commits data every hour, so that shouldn't happen.
* **Change the profit maths:** `scraper/value.py` holds the price guide, repair allowances, the ~$450 extras and the $1,500 target profit.

## Good to know

* **Estimates only.** Profit = rough resale guide − likely buy price − auction fee − repair allowance − ~$450 extras. Always check the photos, damage report and real sold prices before bidding.
* "No write-offs" = Pickles *WOVR N/A* or Manheim *No WOVR Record*. Clearing cars are ordinary used cars whose WOVR status isn't stated, so check it.
* Fees used: Pickles salvage fees (checked 25 Nov 2026) and Manheim buyer fees (effective 1 June 2026).
* Be a good neighbour: the collector reads only public listing pages allowed by the sites' robots.txt, pauses between requests and runs at most hourly. Auction sites generally don't welcome automated reading, so keep this to a small group and always click through to the official listing to bid.
* The page is hidden from search engines (`noindex`), but anyone with the link can open it.

## Developers

```
python3 -m unittest scraper/test_scrape.py -v   # offline tests
python3 scraper/scrape.py --full                # real scan (needs internet)
python3 -m http.server -d docs 8000             # view at http://localhost:8000
```
