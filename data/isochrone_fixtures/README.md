# Isochrone trial fixtures

Hand-simplified walk isochrones for `scripts/isochrone_trial.py`. They exist
to prove the comparison logic offline in CI. They are NOT live Isochrones
responses and are not evidence about real walking reach; the owner's live run
(`docs/briefs/ISOCHRONE_TRIAL_OWNER_RUN.md`) replaces them as evidence.

Each file is a GeoJSON Feature with a MultiPolygon geometry ([lng, lat]
positions, RFC 7946: first ring exterior, later rings are holes). Properties
repeat the origin and duration below. No API keys are stored here.

| File | Region | Origin venue | Origin lat, lng | Minutes | Notes |
| --- | --- | --- | --- | --- | --- |
| zanzibar_15m.geojson | zanzibar_tanzania | House of Wonders | -6.16091, 39.18963 | 15 | box around the Stone Town core |
| zanzibar_30m.geojson | zanzibar_tanzania | House of Wonders | -6.16091, 39.18963 | 30 | larger box with a hole around the Old Slave Market block |
| zanzibar_45m.geojson | zanzibar_tanzania | House of Wonders | -6.16091, 39.18963 | 45 | larger box |
| nungwi_30m.geojson | nungwi_tanzania | Nungwi Lighthouse | -5.72231, 39.30331 | 30 | box along the west beach, east headland excluded |
| luang_prabang_30m.geojson | luang_prabang_laos | Royal Palace Museum (Haw Kham) | 19.89245, 102.13678 | 30 | peninsula box with a hole at the seasonal Bamboo Bridge |

Mode is WALK, direction FROM the origin.
