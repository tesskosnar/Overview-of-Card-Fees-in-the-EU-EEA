# Card Fee Tracker

Soukromý GitHub projekt pro měsíční sledování karetních poplatků v zemích EU/EEA.

Dashboard odděluje čtyři vrstvy, které se nesmějí metodicky zaměňovat:

1. **Interchange fees** – oficiální sazby Visa a Mastercard z jejich country rate sheets.
2. **Scheme fees** – veřejně uvedené poplatky karetním schématům / sítím.
3. **Processing fees** – veřejně uvedené autorizační, clearingové nebo processingové poplatky.
4. **Merchant service charge (MSC)** – veřejně dohledatelné ceny, které platí obchodník acquirerovi; často jde o ceníkové nebo mediální údaje, nikoliv o individuálně sjednané sazby.

## Co projekt dělá

- jednou měsíčně spustí GitHub Action, vždy **1. den v měsíci v 05:00 UTC**;
- stáhne a zpracuje oficiální interchange ceníky Visa a Mastercard;
- přes **Brave Search API** vyhledá webové, mediální, regulatorní a ceníkové zmínky v angličtině i lokálních jazycích;
- jako druhou bezplatnou mediální vrstvu používá **GDELT DOC API**;
- z nalezených výsledků vytáhne jen konkrétní procenta, basis points nebo fixní částky, které jsou v blízkosti výrazu označujícího konkrétní typ poplatku;
- uchová původní odkaz, titulek, jazyk, kontext a confidence score;
- archivuje výsledky a vytváří měsíční trend;
- umožňuje filtrovat regiony včetně samostatného **CEE** filtru;
- nezobrazuje samostatný sloupec Visa nebo Mastercard, pokud pro dané zobrazení žádné údaje neexistují;
- zobrazí sloupec **Media** pouze tehdy, když jsou pro aktuální vrstvu nalezené zdroje.

## Odhadovaný reálný poplatek

Dashboard používá tento postup:

- pokud existuje veřejně uvedený **merchant service charge**, použije jej jako nejlepší veřejně dostupný odhad skutečné ceny pro obchodníka;
- jinak sestaví transparentní model:

`interchange + scheme fee + processing fee + fixní poplatky přepočtené podle hodnoty transakce + zadaná marže acquirera`

Hodnotu transakce i předpokládanou marži acquirera lze v dashboardu změnit. Pokud některá složka chybí, dashboard výsledek označí jako neúplný model. Nejde o transakčně vážený tržní průměr.

## API klíče

### Povinný pro široké webové vyhledávání

`BRAVE_SEARCH_API_KEY`

Bez něj oficiální interchange scraping stále funguje a spustí se také GDELT, ale mediální pokrytí bude výrazně užší.

### Není potřeba

- Anthropic API key
- OpenAI API key
- Google Search key

## Zprovoznění

1. Vytvoř na GitHubu nový **Private repository**.
2. Nahraj do něj celý obsah této složky včetně skryté složky `.github`.
3. V Brave Search API vytvoř klíč.
4. Na GitHubu otevři:
   `Settings → Secrets and variables → Actions → New repository secret`
5. Název secretu nastav přesně na:
   `BRAVE_SEARCH_API_KEY`
6. Otevři záložku **Actions** a ručně spusť workflow **Monthly card fee refresh**.

Podrobnější postup je v souboru [navod.md](navod.md).

## Lokální spuštění

```bash
pip install -r requirements.txt
export BRAVE_SEARCH_API_KEY="tvuj-klic"   # volitelné, ale doporučené
python3 scraper/main.py
cd docs
python3 -m http.server 8000
```

Dashboard pak otevři na `http://localhost:8000`.

## Testy

```bash
pip install -r requirements-dev.txt
pytest -q
```

Volitelný render test dashboardu:

```bash
npm install
cd docs && python3 -m http.server 8934
# v druhém terminálu z kořene projektu:
npm test
```

## Datové soubory

- `docs/data/latest.json` – aktuální dashboardový výstup;
- `docs/data/media_archive.json` – dlouhodobý archiv veřejných pozorování;
- `docs/data/history/YYYY-MM-DD.json` – měsíční snímky pro trend;
- `docs/data/history/index.json` – seznam dostupných snímků.
- `scraper/config/manual_sources.json` – volitelný registr stabilních veřejných ceníků nebo regulatorních stránek, které se mají kontrolovat každý měsíc bez ohledu na jejich pozici ve vyhledávači.

## Ručně připnuté zdroje

Pokud najdeš důležitý oficiální ceník, který má být kontrolován každý měsíc bez ohledu na výsledky vyhledávání, přidej jej do `scraper/config/manual_sources.json`:

```json
{
  "sources": [
    {
      "country": "CZ",
      "url": "https://example.org/public-card-fee-list.pdf",
      "title": "Public card fee list",
      "language": "cs",
      "fee_type_hint": "scheme fee processing fee",
      "network_hint": "Visa Mastercard",
      "card_segment_hint": "consumer commercial"
    }
  ]
}
```

Zdroj se znovu stáhne při každém měsíčním běhu a případné číselné údaje projdou stejnou extrakcí a kontrolami jako výsledky Brave a GDELT.

## Důležitá omezení

- Nelze garantovat nalezení úplně všech článků na internetu. Projekt dělá široké, vícejazyčné a opakovatelné vyhledávání, nikoliv úplný archiv webu.
- Scheme fees a MSC nejsou publikovány jednotně. Jejich průměr je jednoduchý průměr explicitně uvedených veřejných hodnot, ne efektivní průměr trhu.
- Automatická extrakce z textu může zachytit údaj, který vyžaduje lidské ověření. Proto se každý údaj zobrazuje se zdrojem a confidence score.
- Fixní poplatky se nesčítají s procentními bez zadané hodnoty transakce.
- Oficiální interchange ceníky mají metodicky vyšší váhu než mediální zmínky a zůstávají v dashboardu oddělené.

## Struktura

```text
scraper/main.py          orchestrace měsíčního běhu
scraper/media_search.py  Brave + GDELT, extrakce a archivace veřejných hodnot
scraper/search_terms.py  vícejazyčný slovník
scraper/config/manual_sources.json  ručně připnuté veřejné zdroje
scraper/discover.py      hledání aktuálních Visa/Mastercard PDF
scraper/parse_*.py       zpracování interchange rate sheets
docs/index.html          dashboard
.github/workflows/       měsíční automatizace
```
