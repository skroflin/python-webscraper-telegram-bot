# Osijek Stanovi Bot

`osijek-stanovi-bot` je sustav za automatizirano praćenje, prikupljanje i filtriranje oglasa za najam stanova na području grada Osijeka. Sustav prikuplja podatke s više različitih izvora (Index Oglasnik, Njuškalo, Facebook Marketplace i Facebook grupe), analizira značajke i lokaciju stanova te putem Telegram bota šalje obavijesti korisnicima u stvarnom vremenu.

## Projektna struktura

Arhitektura projekta organizirana je u više funkcionalnih modula s odvojenim logikama za prikupljanje podataka, analitiku, pohranu i Telegram sučelje.

```text
stanovi-osijek-bot/
├── analytics/
│   ├── charts.py
│   ├── feature_extractor.py
│   ├── market_stats.py
│   ├── match_scorer.py
│   ├── poi.py
│   └── user_settings.py
├── bot/
│   ├── notifier.py
│   └── telegram_bot.py
├── data/
│   └── listings.db
├── database/
│   └── database.py
├── scrapers/
│   ├── facebook.py
│   ├── health_check.py
│   ├── index_hr.py
│   └── njuskalo.py
├── scripts/
│   └── generate_fb_state.py
├── .env
├── .gitignore
├── config.py
├── Dockerfile
├── facebook_state.json
├── main.py
├── README.md
└── requirements.txt
```

### Opis modula

* **analytics/**: Modul zadužen za statističku obradu podataka, izračun ocjene podudarnosti (match score), geolokacijske proračune (POI) i generiranje dijagrama.
* **bot/**: Izvršna logika Telegram bota, rukovanje naredbama korisnika, interaktivnim tipkama i slanjem obavijesti.
* **data/**: Perzistentno spremište u kojem se nalazi SQLite baza podataka.
* **database/**: Upravljanje vezom s bazom podataka, definicija sheme i SQL upiti za unose i ažuriranja.
* **scrapers/**: Samostalni moduli za prikupljanje podataka s platformi Index.hr, Njuškalo i Facebook (Marketplace i Grupe), te logika provjere aktivnosti oglasa.
* **scripts/**: Pomoćne skripte, uključujući skriptu za lokalno generiranje autentične Facebook sesije.
* **main.py**: Središnji cjevovod (pipeline) za pokretanje svih scrapera i koordinaciju spremanja podataka.

---

## Konfiguracijska datoteka (.env)

Za rad sustava potrebno je stvoriti `.env` datoteku u korijenskom direktoriju projekta.

```text
.env
├── TELEGRAM_BOT_TOKEN       # API token dobiven od Telegram BotFather-a
├── SCRAPE_INTERVAL_MINUTES # Interval izvođenja skrepanja u minutama
├── FACEBOOK_STORAGE_STATE   # Putanja do datoteke s Facebook sesijom
└── DATABASE_PATH            # Putanja do SQLite baze podataka
```

### Primjer sadržaja `.env` datoteke

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyZ
SCRAPE_INTERVAL_MINUTES=30
FACEBOOK_STORAGE_STATE=facebook_state.json
DATABASE_PATH=data/listings.db
```

---

## Postavljanje projekta na lokalno okruženje

Slijedite navedene korake za postavljanje i pokretanje projekta na lokalnom računalu.

### Preduvjeti

* Python 3.12 ili noviji
* Git
* Docker i Docker Compose (opcionalno, za kontejnerizirani rad)

### 1. Kloniranje repozitorija

```bash
git clone https://github.com/korisnicko-ime/stanovi-osijek-bot.git
cd stanovi-osijek-bot
```

### 2. Izrada i aktivacija virtualnog okruženja

#### Windows (PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalacija ovisnosti

Instalirajte potrebne Python pakete definirane u datoteci `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 4. Instalacija Playwright preglednika

Facebook scraper koristi Playwright za rad s dinamičkim sadržajem. Potrebno je preuzeti Chromium preglednik i pripadajuće sistemske ovisnosti:

```bash
playwright install chromium --with-deps
```

### 5. Konfiguracija okruženja

Stvorite `.env` datoteku u korijenskom direktoriju prema gore navedenom predlošku i unesite vaš `TELEGRAM_BOT_TOKEN`.

### 6. Generiranje Facebook sesije

Radi izbjegavanja sigurnosnih provjera i ekrana za prijavu na Facebooku, pokrenite jednokratnu skriptu za ručnu prijavu i spremanje kolačića:

```bash
python scripts/generate_fb_state.py
```

Slijedite upute u konzoli: u otvorenom pregledniku prijavite se na Facebook račun, potvrdite dvofaktorsku autentifikaciju ako je aktivna, te pritisnite Enter u terminalu. Time će se stvoriti datoteka `facebook_state.json`.
---

## Pokretanje aplikacije

Sustav se može pokrenuti izravno putem Pythona ili unutar Docker kontejnera.

### Način 1: Izravno pokretanje (Lokalno)

Za pokretanje Telegram bota i automatskog rasporeda skrepanja pokrenite:

```bash
python bot/telegram_bot.py
```

Za jednokratno ručno izvođenje cjelokupnog cjevovoda prikupljanja podataka pokrenite:

```bash
python main.py
```

### Način 2: Pokretanje putem Docker-a

#### Izgradnja i pokretanje kontejnera

* Linux / macOS:

```bash
docker build -t osijek-stanovi-bot .

docker run -d \
  --name osijek_bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  osijek-stanovi-bot
```

* Windows (PowerShell):

```powershell
docker build -t osijek-stanovi-bot .

docker run -d `
  --name osijek_bot `
  --restart unless-stopped `
  --env-file .env `
  -v ${PWD}/data:/app/data `
  osijek-stanovi-bot
```

#### Pokretanje putem Docker Compose-a

```bash
docker compose up -d --build
```

#### Pregled zapisnika (Logs)

Za praćenje rada aplikacije u stvarnom vremenu pokrenite:

```bash
docker logs -f osijek_bot
```