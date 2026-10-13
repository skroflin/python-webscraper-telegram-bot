import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OUTPUT_PATH = "facebook_state.json"


async def main():
    async with async_playwright() as p:
        logging.info("\U0001F310 Pokretanje preglednika (vidljivi način rada)...")
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(locale="hr-HR")
        page = await context.new_page()

        logging.info("\U0001F517 Otvaranje Facebook stranice za prijavu...")
        await page.goto("https://www.facebook.com/login")

        print("\n" + "=" * 60)
        print("1. Prijavite se ručno na svoj Facebook račun u otvorenom pregledniku.")
        print("2. Ako postoji 2FA / dvostruka autentifikacija, potvrdite je.")
        print("3. Kada se uspješno učita vaš Facebook News Feed (naslovna stranica),")
        print("   VRATITE SE U OVAJ TERMINAL I PRITISNITE 'ENTER'.")
        print("=" * 60 + "\n")

        input("\U0001F449 Pritisnite ENTER nakon što ste se uspješno prijavili...")

        await context.storage_state(path=OUTPUT_PATH)
        logging.info(f"\U0001F44D Stanje sesije (kolačići) uspješno je spremljeno u '{OUTPUT_PATH}'!")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())