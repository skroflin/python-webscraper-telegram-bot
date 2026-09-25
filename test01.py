import asyncio
from telegram import Bot
from telegram.error import TelegramError
from config import TELEGRAM_BOT_TOKEN

async def test_telegram_connectivity():
    """Testing validity of token and fetching basic bot info."""
    print("\U0001F64F Attempting to connect to Telegram API...")

    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)

        me = await bot.get_me()

        print("\U0001F680 Successfully connected to Telegram API!")
        print(f"\U0001F449 {me.first_name}")
        print(f"\U0001F449 {me.username}")
        print(f"\U0001F449 {me.id}")
        print(f"\U0001F449 Can access groups? {'Yes' if me.can_join_groups else 'No'}")

    except TelegramError as e:
        print(f"\n \u274C Error while trying to connect to Telegram: {e}")
    except TelegramError as e:
        print(f"\n \u274C Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(test_telegram_connectivity())