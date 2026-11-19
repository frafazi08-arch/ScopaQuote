# ScopaQuote

Sito che trova le quote più sbilanciate tra i bookmaker italiani (e Pinnacle) su **tiri, tiri in porta, falli commessi e falli subiti** dei giocatori. Si aggiorna da solo ogni 3 ore su GitHub, restando nel piano gratuito di OddsPapi. Lo apri da telefono o da PC senza tenere acceso niente.

## Metterlo online (una volta sola, circa 10 minuti)

1. **Crea un account** su https://github.com (gratis).
2. **Nuovo progetto**: in alto a destra **+** → **New repository**. Nome `scopaquote`, scegli **Public** (serve per avere il sito gratis), poi **Create repository**.
3. **Carica i file**: nella pagina del progetto clicca **uploading an existing file** e trascina **tutto il contenuto** di questa cartella, compresa la cartella `.github`. Poi **Commit changes**.
   - Su Mac la cartella `.github` è nascosta: nel Finder premi `Cmd + Shift + .` per vederla.
4. **Pubblica il sito**: **Settings** → **Pages** → in *Source* scegli **GitHub Actions**.
5. **Primo aggiornamento**: apri la scheda **Actions**, conferma se te lo chiede, clicca **Aggiorna quote** a sinistra → **Run workflow** → **Run workflow**. Quando compare la spunta verde il sito è online.

Dopo un paio di minuti il sito è su:
**`https://TUO-NOME-UTENTE.github.io/scopaquote/`**
Salvalo nella schermata Home del telefono e lo apri come un'app.

All'inizio il sito mostra **dati di prova** (c'è una banda gialla che lo dice).

## Collegare le quote vere

1. Crea un account su https://oddspapi.io e copia la chiave API.
2. Su GitHub: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
   Nome: `ODDSPAPI_KEY`, valore: la tua chiave. **Add secret**.
3. **Actions** → **Aggiorna quote** → **Run workflow**. Da qui in poi aggiorna da solo ogni 15 minuti.

La chiave resta segreta: non compare nel sito né nei file.

> **Piano gratuito**: 250 richieste al mese. Ogni 3 ore il programma riscarica solo le partite di Serie A che iniziano entro 12 ore (le altre restano con le quote dell'ultimo aggiornamento) e scarica il calendario una volta al giorno. Ogni partita aggiornata costa 1 richiesta (circa 200 al mese in tutto). Si ferma da solo a 240. Gli orari sono nella riga `cron` di `.github/workflows/aggiorna.yml`.

## bet365
Le quote bet365 (tiri, tiri in porta, falli commessi, falli subiti) arrivano da **Apify** (piano gratuito: $5 di credito al mese, nessuna carta). Ogni partita aggiornata costa circa $0,01: con gli aggiornamenti ogni 3 ore si spendono circa $2 al mese. Il programma si ferma da solo a $4.
Serve il segreto `APIFY_TOKEN` (Settings → Secrets and variables → Actions), con il token Apify che inizia con `apify_api_`.
Se Apify non è attivo, il sito usa le quote bet365 "da verificare" di OddsPapi (meno aggiornate).

## Come leggere il sito

| Voce | Significato |
|---|---|
| **Miglior quota** | La quota più alta trovata e su quale bookmaker |
| **Quota giusta** | La quota "senza margine" calcolata dagli altri bookmaker (o da Pinnacle) |
| **Valore** | Quanto rende in media la miglior quota rispetto a quella giusta. **Sopra +5% è interessante** |
| **Differenza** | Distanza tra quota più alta e più bassa |
| **Affidabilità** | alta = confronto con Pinnacle · media = più bookmaker concordi · bassa = pochi dati |
| **Conviene da** | La quota minima per cui vale la pena giocare (quota giusta + 5%) |

Tocca una quota per vedere tutti i bookmaker a confronto.

**Differenza alta + valore vicino a zero** = è il bookmaker più basso a sbagliare, non quello alto a regalare. In quei casi guarda l'**under** sul bookmaker basso: spesso il valore è lì.

Prima di giocare controlla sempre sul sito del bookmaker che il mercato sia identico (tiri o tiri in porta, versione "plus", regola se il giocatore parte dalla panchina).

## Impostazioni (`config.json`)

Modificabile direttamente su GitHub: apri il file e clicca la matita.
- `competizioni`: aggiungi o togli campionati
- `bookmaker`: quali bookmaker confrontare
- `soglia_valore_percento` / `soglia_differenza_percento`: quando una quota diventa "segnalazione"

Se qualcosa non va, la scheda **Actions** mostra i dettagli di ogni aggiornamento. Il file `dati/mercati_non_riconosciuti.txt` elenca i mercati giocatore che il programma non ha capito.

---
18+ · Il gioco può causare dipendenza. I bookmaker possono limitare i conti di chi vince con costanza.
