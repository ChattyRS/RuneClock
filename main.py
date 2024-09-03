import asyncio
import logging
from bot import Bot

async def run() -> None:
    bot: Bot = Bot()
    try:
        await bot.start_bot()
    except KeyboardInterrupt:
        await bot.close()

if __name__ == '__main__':
    logging.basicConfig(filename='data/log.txt', level=logging.CRITICAL)

    loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    loop.run_until_complete(run())
