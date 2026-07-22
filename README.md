# Card Fee Tracker

Soukromý GitHub projekt pro měsíční sledování **interchange poplatků** Visa a Mastercard napříč 30 zeměmi EU/EEA (27 zemí EU + Island, Lichtenštejnsko, Norsko) a navíc Švýcarskem (mimo EHP, vlastní sazební režim — přidáno jako bonus 31. země).

## Co dashboard ukazuje

- **Interchange fees** (spotřebitelský debet / kredit / komerční) pro Visa a Mastercard, vždy s odkazem na oficiální zdrojový ceník.
- **Mapa** — skutečné tvary zemí, barva podle výše sazby (levnější → dražší), tečka = země má vlastní domácí platební schéma.
- **Roční trend** — graf od roku 2015 (před regulací IFR) do teď.
- **Filtry** — podle regionu (CEE / Západ / Sever / Jih) a vyhledávání konkrétní země.
- **Export do CSV** — pro otevření v Excelu, bez potřeby GitHub účtu.

## Jak se data sbírají

- **Visa** — živě, automaticky, jednou měsíčně (`scraper/pipeline.py`). Stáhne a rozparsuje oficiální PDF ceníky pro všech 30 zemí.
- **Mastercard** — **ručně**. Mastercard blokuje automatizované stahování už na úrovni hlavní stránky (potvrzeno opakovaně, HTTP 403). Data v `manual-mastercard-research.json` jsou dohledaná ručně z jejich oficiálních PDF; obnovují se stejným ručním postupem, jak byla poprvé sesbíraná (viz komentář v tom souboru).

## Automatizace

`.github/workflows/monthly-scrape.yml` spouští `scraper/main.py` 1. den každého měsíce v 5:00 UTC (nebo kdykoliv ručně přes záložku "Actions" → "Run workflow"). Ten:
1. stáhne a zpracuje aktuální Visa ceníky,
2. spojí je s ručními Mastercard daty,
3. zapíše `docs/data/latest.json` a přidá nový bod do `docs/data/history/`,
4. commitne a pushne změny zpět do repozitáře.

## Jak dashboard zobrazit

Nejjednodušší cesta bez psaní příkazů: **Code → Codespaces → "Create codespace on main"**, počkat ~1 minutu — server se spustí a otevře sám (viz `.devcontainer/devcontainer.json`).

Záložní varianta, kdyby se auto-otevření nepovedlo: v terminálu Codespace spustit `cd docs && python3 -m http.server 8000`, pak v záložce "Ports" kliknout "Open in Browser" u portu 8000.

## Struktura

```
.github/workflows/monthly-scrape.yml   -- automatizace
.devcontainer/devcontainer.json        -- auto-spuštění náhledu v Codespaces
scraper/
  pipeline.py                          -- celá scraper logika (Visa live scrape, PDF parsing, agregace)
  main.py                              -- orchestrace pro GitHub Actions (volá pipeline.py + slučuje Mastercard)
  tests/                               -- pytest sada
manual-mastercard-research.json        -- ručně dohledaná Mastercard data, viz komentář uvnitř
merge_manual_mastercard.py             -- pomocný skript pro ruční přeslučování Mastercard dat mimo automatizaci
docs/
  index.html                           -- dashboard (samostatný soubor, žádný build krok)
  data/latest.json                     -- aktuální data (přepisuje se každým během)
  data/history/                        -- měsíční snímky pro trendový graf
```
