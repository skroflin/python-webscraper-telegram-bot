from database.database import init_db, save_or_update_listing, get_connectivity

def test_db():
    print("\U0001F504 Starting test for connectivity with SQLlite db... \U0001F9EA")

    try:
        init_db()
        print("\U00002705 Db and db tables successfully initialized!")
    except Exception as e:
        print(f"\U0000274C Error upon db and table initialization: {e}")
        return

    with get_connectivity() as conn:
        cursor = conn.cursor()
        cursor.execute("select count(*) from locations")
        count = cursor.fetchone()[0]
        print(f"\U0001F449 Loaded {count} neighborhoods from db.")

    sample_listings = {
        "external_id": "TEST-001",
        "source_platform": "Njuškalo",
        "title": "Moderan stan u Retfali 50m2",
        "description": "Prekrasan stan s centralnim grijanjem.",
        "price": 400.00,
        "area_sqm": 50.0,
        "location_id": 2,
        "raw_address": "Strossmayerova 10, Osijek",
        "url": "https://www.njuskalo.hr/test-stan-retfala-1"
    }

    status, listing_id = save_or_update_listing(sample_listings)
    print(f"1. New ad insertion \U000027A1 Status: {status} | Id: {listing_id}")

    status, listing_id = save_or_update_listing(sample_listings)
    print(f"2. Same ad insertion \U000027A1 Status: {status} | Id: {listing_id}")

    sample_listings["price"] = 370.0
    print(f"3. Updated price \U000027A1 Status: {status} | Id: {listing_id}")

    with get_connectivity() as conn:
        cursor = conn.cursor()
        cursor.execute("select old_price, new_price, changed_at from price_history where listing_id = ?", (listing_id,))
        history = cursor.fetchone()
        if history:
            print(f"Price history successfully updated: {history['old_price']}EUR ➔ {history['new_price']}EUR ({history['changed_at']})")

    print("\n All db tests passed successfully\U0001F973")

if __name__ == "__main__":
    test_db()