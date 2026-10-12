# Video game heatmap kill check

Qloo heatmaps require a location (`filter.location` or `filter.location.query`); 'global' = a world WKT polygon. Country = reverse-geocoded cell centre (cells are geohash-3, ~156 km).

## Step 1: games

| Genre | Query | Qloo match | Entity ID |
|---|---|---|---|
| Cozy | Stardew Valley | Stardew Valley | 875DB771-9C4C-4DD0-9249-D2ABD95711F1 |
| Cozy | Unpacking | Unpacking | 97B46B79-891A-4580-A0F8-C1CC34F3EFF6 |
| Cozy | A Short Hike | A Short Hike | 2767F695-AC33-4A23-A3BE-425A9E74B6FA |
| Roguelike | Slay the Spire | Slay the Spire | 20BEE4A4-44C1-49CC-962D-CC0B4EE80102 |
| Roguelike | Balatro | Balatro | AF4578FE-B78B-4264-850B-A35F6F70E0B7 |
| Roguelike | Inscryption | Inscryption | 59A867E7-F6E1-4D98-986A-82586FB3109F |
| Strategy | Hearts of Iron IV | Hearts of Iron IV | BED1F7DC-A4CA-42D0-99D7-B2D3FE4C4E56 |
| Strategy | Total War: Warhammer III | Total War: WARHAMMER III | F7787FF0-716C-4706-BA28-2D59C39162C7 |
| Strategy | Manor Lords | Manor Lords | C9D947BB-FC0D-40E0-B67A-D052298F49D7 |
| Horror co-op | Phasmophobia | Phasmophobia | 82ED7F95-5D9E-4E9E-A88A-C98FDF0142C9 |
| Horror co-op | Lethal Company | Lethal Company | 3A05C2B0-20F6-4754-A470-4871F8DF9061 |
| Horror co-op | Content Warning | Content Warning | CB10CCB2-58D3-40A0-B37D-3FB145336CA5 |
| Anime/VN | Doki Doki Literature Club | Doki Doki Literature Club! | BF044CB2-86F9-47BE-8663-30A2D5BC1CFE |
| Anime/VN | Danganronpa | Danganronpa: Trigger Happy Havoc | 37A09BF7-A9DE-4B29-ADAA-BF566B8527B2 |
| Anime/VN | Steins;Gate | Steins;Gate | DF448A32-C794-486C-A7AF-3DE44155A482 |

## Sanity checks

- Same game (Stardew Valley), + `signal.demographics.age=35_and_younger`: top-50 cells CHANGED (param honored)
- Same world polygon, Stardew Valley vs Slay the Spire: cell-affinity Spearman 0.23 over 847 shared cells (game signal drives the map)
- Identical heatmaps across different games (no game-specific data): Content Warning, Lethal Company, Manor Lords

## Verdict (spec: country score = mean cell affinity, all games)

| Check | Criterion | Result | Verdict |
|---|---|---|---|
| 1. Coverage | ≥12/15 games resolved | 15/15 | PASS |
| 2. Global reach | median game in ≥20 countries | median 175 countries | PASS |
| 3. Key markets | CN JP KR BR RU PL DE each in ≥half the games | missing: none | PASS |
| 4. Genre signal | within − between Spearman ≥ 0.15 | within 0.30 (15 pairs), between -0.00 (90 pairs), diff +0.31 | PASS |

Key market coverage (games with data): CN 15/15, JP 15/15, KR 15/15, BR 15/15, RU 15/15, PL 15/15, DE 15/15

## Robust verdict (duplicate-map games dropped, countries with ≥5 cells, popularity-weighted affinity)

| Check | Criterion | Result | Verdict |
|---|---|---|---|
| 1. Coverage | ≥12/15 games resolved | 12/15 | PASS |
| 2. Global reach | median game in ≥20 countries | median 74 countries | PASS |
| 3. Key markets | CN JP KR BR RU PL DE each in ≥half the games | missing: none | PASS |
| 4. Genre signal | within − between Spearman ≥ 0.15 | within 0.50 (10 pairs), between 0.08 (56 pairs), diff +0.42 | PASS |

## Top 5 countries per game (spec)

| Game | Genre | Top 5 (mean cell affinity) |
|---|---|---|
| A Short Hike | Cozy | MS 0.986, ET 0.976, MZ 0.975, GD 0.968, TM 0.964 |
| Balatro | Roguelike | PS 0.967, CK 0.949, BY 0.896, IS 0.881, HR 0.880 |
| Content Warning | Horror co-op | MZ 0.967, SZ 0.959, BN 0.940, NE 0.939, AO 0.931 |
| Danganronpa | Anime/VN | PG 0.950, LA 0.948, BN 0.943, KZ 0.930, JP 0.929 |
| Doki Doki Literature Club | Anime/VN | FM 0.989, TM 0.956, TF 0.945, CX 0.944, SH 0.939 |
| Hearts of Iron IV | Strategy | MD 0.982, EH 0.927, IR 0.902, BY 0.892, ZW 0.881 |
| Inscryption | Roguelike | IS 0.977, AX 0.975, LT 0.910, BM 0.902, MM 0.899 |
| Lethal Company | Horror co-op | MZ 0.967, SZ 0.959, BN 0.940, NE 0.939, AO 0.931 |
| Manor Lords | Strategy | MZ 0.967, SZ 0.959, BN 0.940, NE 0.939, AO 0.931 |
| Phasmophobia | Horror co-op | CF 0.994, SH 0.993, NE 0.987, FM 0.969, TC 0.968 |
| Slay the Spire | Roguelike | RE 0.980, MQ 0.978, FI 0.967, BY 0.952, LB 0.941 |
| Stardew Valley | Cozy | FM 0.991, TM 0.951, CX 0.949, TF 0.924, CK 0.906 |
| Steins;Gate | Anime/VN | GU 0.996, MP 0.983, JP 0.956, KR 0.924, PG 0.919 |
| Total War: Warhammer III | Strategy | FK 0.913, BY 0.910, BG 0.895, AX 0.851, RU 0.849 |
| Unpacking | Cozy | SH 0.993, GQ 0.990, TD 0.986, CD 0.985, TM 0.961 |

## Top 5 countries per game (robust)

| Game | Genre | Top 5 (popularity-weighted, ≥5 cells) |
|---|---|---|
| A Short Hike | Cozy | MM 0.898, BO 0.894, IS 0.883, CN 0.834, PE 0.827 |
| Balatro | Roguelike | IS 0.927, BY 0.918, DK 0.876, FI 0.873, ES 0.853 |
| Danganronpa | Anime/VN | JP 0.920, SA 0.901, VN 0.808, PH 0.794, KR 0.784 |
| Doki Doki Literature Club | Anime/VN | CA 0.809, US 0.784, JP 0.735, ZW 0.732, AU 0.728 |
| Hearts of Iron IV | Strategy | UZ 0.916, IR 0.910, ZW 0.908, LT 0.890, BY 0.883 |
| Inscryption | Roguelike | IS 0.970, LT 0.923, EE 0.811, NZ 0.782, RU 0.768 |
| Phasmophobia | Horror co-op | PH 0.800, NI 0.781, UY 0.741, US 0.729, AR 0.728 |
| Slay the Spire | Roguelike | FI 0.957, IS 0.883, DK 0.822, NO 0.809, FR 0.794 |
| Stardew Valley | Cozy | CA 0.857, US 0.837, AU 0.759, EE 0.743, KR 0.742 |
| Steins;Gate | Anime/VN | JP 0.955, KR 0.910, TW 0.866, SA 0.859, CN 0.826 |
| Total War: Warhammer III | Strategy | BG 0.908, BY 0.900, MN 0.881, KP 0.861, RU 0.857 |
| Unpacking | Cozy | KR 0.894, AU 0.810, TW 0.792, US 0.760, JP 0.756 |

## OVERALL: PASS (spec PASS, robust PASS)

Data: 15/15 games resolved, but 3 share one identical heatmap (Content Warning, Lethal Company, Manor Lords).
Spec verdict PASS: genre diff +0.31, median 175 countries; key markets all present.
Robust verdict PASS: genre diff +0.42 (within 0.50 vs between 0.08), median 74 countries.
