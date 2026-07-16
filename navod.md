# Návod: nahrání na GitHub a první spuštění

## 1. Vytvoř repozitář

1. Rozbal ZIP.
2. Na GitHubu vytvoř nový repozitář a nastav jej jako **Private**.
3. Nejjednodušší je použít GitHub Desktop a přidat rozbalenou složku jako nový lokální repozitář.
4. Publikuj jej na GitHub.

Důležité: musí se nahrát také skrytá složka `.github`, protože obsahuje měsíční automatizaci.

## 2. Přidej Brave Search API klíč

1. Zaregistruj se do Brave Search API a vytvoř API klíč.
2. Otevři svůj GitHub repozitář.
3. Klikni na `Settings`.
4. V levém menu otevři `Secrets and variables → Actions`.
5. Klikni na `New repository secret`.
6. Do pole Name napiš přesně:

```text
BRAVE_SEARCH_API_KEY
```

7. Do pole Secret vlož svůj Brave klíč a ulož jej.

Bez klíče projekt nespadne. Proběhne oficiální interchange scraping a GDELT, ale široké webové hledání nebude aktivní.

## 3. Spusť první sběr

1. Otevři záložku `Actions`.
2. Vlevo vyber `Monthly card fee refresh`.
3. Klikni na `Run workflow`.
4. Po dokončení musí být běh označen zeleným symbolem.

Workflow se potom spouští automaticky každý první den v měsíci.

## 4. Otevři dashboard

### Přes Codespaces

1. Na hlavní stránce repozitáře klikni na `Code → Codespaces → Create codespace`.
2. V terminálu spusť:

```bash
cd docs && python3 -m http.server 8000
```

3. Otevři nabídnutý port 8000 v prohlížeči.

### Na počítači

V rozbalené složce spusť:

```bash
cd docs
python3 -m http.server 8000
```

Pak otevři `http://localhost:8000`.

## 5. Co zkontrolovat po prvním běhu

- zda se načetly země Visa a Mastercard;
- zda banner neoznačuje některou síť jako stale nebo unavailable;
- zda je v dashboardu vidět počet veřejných pozorování;
- zda Brave v datovém stavu není označen jako disabled;
- zda odkazy ve sloupci Media vedou na relevantní zdroje;
- zda u extrahovaných údajů dává smysl fee type, segment a síť.

První měsíční trend bude mít pouze jeden bod. Graf začne být užitečný po dalších bězích.
