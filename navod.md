# Návod: nahrání na GitHub

Žádný API klíč se už nikde nezadává — tahle verze na ničem takovém nestojí.

## 1. Vytvoř repozitář

1. Rozbal ZIP.
2. Na GitHubu vytvoř nový repozitář, nastav jako **Private**.
3. Nahraj VŠECHNY soubory a složky ze ZIPu — **včetně skryté složky `.github`** (obsahuje měsíční automatizaci) a **`.devcontainer`** (auto-spuštění náhledu). Drag-and-drop do webového rozhraní GitHubu je občas skryté složky nezobrazí; pokud se `.github` nebo `.devcontainer` po nahrání neobjeví v seznamu souborů, přidej je ručně přes "Add file → Create new file" a napiš celou cestu (např. `.github/workflows/monthly-scrape.yml`) do pole pro název.

## 2. Spusť první sběr dat

1. Záložka **"Actions"** nahoře na stránce repozitáře.
2. Vlevo klikni na **"Monthly card fee scrape"**.
3. **"Run workflow"** → znovu **"Run workflow"** (potvrzení).
4. Počkej ~2-5 minut, sleduj průběh kliknutím na běžící workflow.
5. Po dokončení bys měla v `docs/data/` vidět aktualizovaný `latest.json` a nový soubor v `docs/data/history/`.

Od teď už se to spouští samo, vždy 1. den v měsíci v 5:00 UTC. Dá se to i kdykoliv spustit ručně stejným postupem (krok 2).

## 3. Zobraz dashboard

**Code** (zelené tlačítko) → **Codespaces** → **"Create codespace on main"** → počkej cca minutu. Náhled by se měl otevřít sám v nové záložce.

Kdyby se neotevřel sám: v terminálu dole napiš `cd docs && python3 -m http.server 8000`, pak v záložce **"Ports"** klikni na ikonku "Open in Browser" u portu 8000.

## 4. Aktualizace ručních Mastercard dat

Mastercard blokuje automatizované stahování, takže `manual-mastercard-research.json` je ruční snímek k určitému datu (viz pole `fetched_at` v souboru). Až ho budeš chtít obnovit:

1. Přepiš obsah `manual-mastercard-research.json` novým výzkumem (stejná struktura, jen nová čísla + nové `fetched_at`).
2. V Codespace terminálu spusť: `python3 merge_manual_mastercard.py`
3. Commitni a pushni změny.

Anebo počkej na příští běh automatizace (krok 2) — ten `manual-mastercard-research.json` čte automaticky vždy, takže stačí ho jen přepsat a nechat proběhnout příští měsíční běh (nebo ho spustit ručně).
