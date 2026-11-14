# Isochrones trial: owner live run

Runbook for the one live comparison in `docs/briefs/GENIE_ISOCHRONE_TRIAL.md`
(decision record `docs/decisions/NETWORK_REACHABILITY.md`). The script
compares today's Haversine walk (`services/transit.walking_minutes`, 5 km/h)
with a Google Isochrones walk area for each origin. Paste counts only into the
table below. Never paste or commit the API key.

## 1. Cloud Console checklist

- [ ] Project: the Travel Buddy GCP project.
- [ ] Enable the Isochrones API (Preview) under APIs and Services.
- [ ] Confirm the current generate endpoint and request fields in the Google
      Isochrones docs. The script default is
      `https://isochrones.googleapis.com/v1:generate`; if the docs differ,
      pass `--endpoint <url>` (and `--field-mask <mask>` if needed).
- [ ] Restrict the key: API restriction to the Isochrones API only;
      application restriction to your IP for the run if possible.
- [ ] Set a low daily quota on the API for the trial.
- [ ] Record "Isochrones API enabled" in `docs/HOSTED_STATE.md` afterwards.

## 2. Run (PowerShell, from the repo root)

Read the key into the session without putting it in shell history:

```powershell
cd C:\Users\ariav\travel-buddy
$env:TB_GOOGLE_MAPS_API_KEY = Read-Host "Maps API key"
```

Offline check first (no key used, no network):

```powershell
python scripts/isochrone_trial.py --region zanzibar_tanzania --origin-name "House of Wonders" --minutes 30 --fixture data/isochrone_fixtures/zanzibar_30m.geojson
```

Live runs (nine calls). `--save-geojson` keeps the returned area in your temp
folder so it can become a fixture later; do not commit it without review.

```powershell
foreach ($m in 15, 30, 45) {
  python scripts/isochrone_trial.py --region zanzibar_tanzania --origin-name "House of Wonders" --minutes $m --live --save-geojson "$env:TEMP\iso_zanzibar_${m}m.geojson"
  python scripts/isochrone_trial.py --region nungwi_tanzania --origin-name "Nungwi Lighthouse" --minutes $m --live --save-geojson "$env:TEMP\iso_nungwi_${m}m.geojson"
  python scripts/isochrone_trial.py --region luang_prabang_laos --origin-name "Royal Palace Museum (Haw Kham)" --minutes $m --live --save-geojson "$env:TEMP\iso_lp_${m}m.geojson"
}
Remove-Item Env:\TB_GOOGLE_MAPS_API_KEY
```

A failed call exits non-zero with the HTTP status and a short error body; it
never falls back to fixtures. Each success prints one `counts:` line.

## 3. Results (counts only)

| Region | Minutes | both | haversine_only | isochrone_only |
| --- | --- | --- | --- | --- |
| zanzibar_tanzania | 15 | | | |
| zanzibar_tanzania | 30 | | | |
| zanzibar_tanzania | 45 | | | |
| nungwi_tanzania | 15 | | | |
| nungwi_tanzania | 30 | | | |
| nungwi_tanzania | 45 | | | |
| luang_prabang_laos | 15 | | | |
| luang_prabang_laos | 30 | | | |
| luang_prabang_laos | 45 | | | |

Decision rule (from the decision record): if disagreement is material,
especially in Stone Town, network reachability earns an implementation slice.
