PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    latitude REAL,
    longitude REAL
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    source_platform TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,
    area_sqm REAL,
    location_id INTEGER,
    raw_address TEXT,
    url TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_url ON listings(url);
CREATE INDEX IF NOT EXISTS idx_listings_hash ON listings(content_hash);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL,
    old_price REAL NOT NULL,
    new_price REAL NOT NULL,
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    first_name TEXT,
    max_price REAL,
    min_area REAL,
    preferred_location_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (preferred_location_id) REFERENCES locations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS user_locations (
    user_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, location_id),
    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
    FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS saved_listings (
    user_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    saved_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, listing_id),
    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
    FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_saved_listings (
    user_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, listing_id),
    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
    FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pois (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_name TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL
);

INSERT OR IGNORE INTO user_saved_listings (user_id, listing_id, created_at)
SELECT user_id, listing_id, saved_at FROM saved_listings;

INSERT OR IGNORE INTO locations (name, latitude, longitude) VALUES
('Centar', 45.5550, 18.6955),
('Retfala', 45.5600, 18.6500),
('Sjenjak', 45.5500, 18.7100),
('Jug 2', 45.5400, 18.7150),
('Donji Grad', 45.5580, 18.7200),
('Tvrđa', 45.5610, 18.6960),
('Industrijska četvrt', 45.5420, 18.6750),
('Vatrogasno naselje', 45.5480, 18.6850),
('Gornji Grad', 45.5570, 18.6800),
('Novi Grad', 45.5450, 18.7000);

INSERT OR IGNORE INTO pois (key_name, name, category, latitude, longitude) VALUES
('portanova', 'TC Portanova', 'shopping', 45.5615, 18.6280),
('mall_osijek', 'Mall Osijek', 'shopping', 45.5418, 18.7088),
('konzum_super_svacicova', 'Super Konzum (Svačićeva)', 'supermarket', 45.5528, 18.6945),
('konzum_centar', 'Konzum Centar (Trg)', 'supermarket', 45.5605, 18.6792),
('konzum_retfala', 'Konzum (Retfala / Strossmayerova)', 'supermarket', 45.5618, 18.6520),
('interspar_dakovstina', 'Interspar (Đakovština)', 'supermarket', 45.5525, 18.6705),
('interspar_retfala', 'Interspar (Retfala)', 'supermarket', 45.5622, 18.6435),
('lidl_retfala', 'Lidl (Retfala)', 'supermarket', 45.5620, 18.6410),
('lidl_svacicova', 'Lidl (Svačićeva / Kampus)', 'supermarket', 45.5515, 18.6990),
('lidl_donji_grad', 'Lidl (Donji Grad)', 'supermarket', 45.5565, 18.7250),
('kaufland_retfala', 'Kaufland (Retfala)', 'supermarket', 45.5625, 18.6480),
('eurospin_gacka', 'Eurospin (Gacka)', 'supermarket', 45.5450, 18.6930),
('plodine_huttlerova', 'Plodine (Huttlerova)', 'supermarket', 45.5505, 18.7180),
('kbc_bolnica', 'KBC Osijek (Bolnica)', 'health', 45.5582, 18.7115),
('dom_zdravlja_centar', 'Dom zdravlja Centar', 'health', 45.5590, 18.6870),
('dom_zdravlja_retfala', 'Dom zdravlja Retfala', 'health', 45.5610, 18.6490),
('dom_zdravlja_donji_grad', 'Dom zdravlja Donji Grad', 'health', 45.5595, 18.7220),
('dom_zdravlja_jug2', 'Dom zdravlja Jug 2', 'health', 45.5410, 18.7140),
('dom_zdravlja_industrial', 'Dom zdravlja Industrijska', 'health', 45.5435, 18.6770),
('kampus_faks', 'Sveučilišni kampus', 'education', 45.5542, 18.7032),
('ffos', 'Filozofski fakultet (FFOS)', 'education', 45.5574, 18.6806),
('efos', 'Ekonomski fakultet (EFOS)', 'education', 45.5570, 18.6850),
('pravos', 'Pravni fakultet (PRAVOS)', 'education', 45.5560, 18.6810),
('ferit_trpimirova', 'FERIT (Trpimirova)', 'education', 45.5535, 18.7025),
('mefos', 'Medicinski fakultet (MEFOS)', 'education', 45.5585, 18.7120),
('gradnos', 'Građevinski i arhitektonski (GRADNOS)', 'education', 45.5540, 18.7040),
('autobusni_kolodvor', 'Autobusni kolodvor', 'transport', 45.5528, 18.6758),
('zeljeznicki_kolodvor', 'Željeznički kolodvor', 'transport', 45.5522, 18.6765),
('centar_trg', 'Trg Ante Starčevića', 'landmark', 45.5601, 18.6789),
('tvrda', 'Tvrđa', 'landmark', 45.5610, 18.6960),
('opus_arena', 'Opus Arena (Pampas)', 'sports', 45.5650, 18.6380),
('gradski_vrt', 'Dvorana / Stadion Gradski vrt', 'sports', 45.5445, 18.6970),
('copacabana', 'Copacabana (Kopa)', 'recreation', 45.5670, 18.6820);

-- @migrations
ALTER TABLE listings ADD COLUMN image_url TEXT;
ALTER TABLE users ADD COLUMN must_have_lift INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN must_have_pet INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN must_have_parking INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN last_latitude REAL;
ALTER TABLE users ADD COLUMN last_longitude REAL;
ALTER TABLE users ADD COLUMN location_focus TEXT DEFAULT 'none';