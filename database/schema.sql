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
    last_latitude REAL,
    last_longitude REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (preferred_location_id) REFERENCES locations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS saved_listings (
    user_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    saved_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, listing_id),
    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
    FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE
);

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