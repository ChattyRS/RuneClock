import asyncio
import logging
from typing import NoReturn, Sequence
from aiohttp import ClientResponse
from sqlalchemy import select
from src.bot import Bot
from src.database import OSRSItem, RS3Item
from src.discord_utils import get_text_channel
from src.message_queue import QueueMessage

async def price_tracking_rs3(bot: Bot) -> NoReturn:
    '''
    Function to automatically and constantly update item pricing
    '''
    # Only start once the bot has been running for at least 5 minutes. 
    # This is to avoid exceeding rate limits during frequent successive restarts, e.g. during testing of new features.
    await asyncio.sleep(300)
    
    while True:
        try:
            async with bot.async_session() as session:
                items: Sequence[RS3Item] = (await session.execute(select(RS3Item))).scalars().all()
                items = sorted(items, key=lambda i: max([int(x) for x in i.graph_data['daily']]))
                for item in items:
                    graph_url: str = f'http://services.runescape.com/m=itemdb_rs/api/graph/{item.id}.json'

                    graph_data: dict[str, dict[str, str]] = {}

                    exists = True
                    while True:
                        r: ClientResponse = await bot.aiohttp.get(graph_url)
                        async with r:
                            if r.status == 404:
                                logging.critical(f'RS3 404 error for item {item.id}: {item.name}')
                                bot.queue_message(QueueMessage(get_text_channel(bot, bot.config['testChannel']), f'RS3 404 error for item {item.id}: {item.name}'))
                                exists = False
                                break
                            elif r.status == 429:
                                msg: str = f'Rate limited in RS3 price tracking'
                                logging.critical(msg)
                                await asyncio.sleep(900)
                                continue
                            elif r.status != 200:
                                await asyncio.sleep(60)
                                continue
                            try:
                                graph_data = await r.json(content_type='text/html')
                                break
                            except Exception as e:
                                # This should only happen when the API is down
                                print(f'Unexpected error in RS3 price tracking for {item.id}: {item.name}\n{e}')
                                await asyncio.sleep(300)
                    
                    # Graph data may not be returned at times, even with status code 200
                    # Appears to be a regular occurrence, happening slightly after noon on days when a newspost is created
                    if not exists or not graph_data:
                        continue

                    prices: list[str] = []
                    for price in graph_data['daily'].values():
                        prices.append(price)
                    
                    current: str = str(prices[len(prices) - 1])
                    yesterday: str = str(prices[len(prices) - 2])
                    month_ago: str = str(prices[len(prices) - 31])
                    three_months_ago: str = str(prices[len(prices) - 91])
                    half_year_ago: str = str(prices[0])

                    today = str(int(current) - int(yesterday))
                    day30: str = '{:.1f}'.format((int(current) - int(month_ago)) / int(month_ago) * 100) + '%'
                    day90: str = '{:.1f}'.format((int(current) - int(three_months_ago)) / int(three_months_ago) * 100) + '%'
                    day180: str = '{:.1f}'.format((int(current) - int(half_year_ago)) / int(half_year_ago) * 100) + '%'
                    
                    item.current = current
                    item.today = today
                    item.day30 = day30
                    item.day90 = day90
                    item.day180 = day180
                    item.graph_data = graph_data
                    await session.commit()

                    await asyncio.sleep(6)
        except OSError as e:
            print(f'Error encountered in rs3 price tracking: {e.__class__.__name__}: {e}')
            logging.critical(f'Error encountered in rs3 price tracking: {e.__class__.__name__}: {e}')
            await asyncio.sleep(60)
        except Exception as e:
            error: str = f'Error encountered in rs3 price tracking: {e.__class__.__name__}: {e}'
            print(error)
            logging.critical(error)
            bot.queue_message(QueueMessage(get_text_channel(bot, bot.config['testChannel']), error))
            await asyncio.sleep(600)
    
async def price_tracking_osrs(bot: Bot) -> NoReturn:
    '''
    Function to automatically and constantly update item pricing
    '''
    # Only start once the bot has been running for at least 5 minutes. 
    # This is to avoid exceeding rate limits during frequent successive restarts, e.g. during testing of new features.
    await asyncio.sleep(300)
    
    while True:
        try:
            async with bot.async_session() as session:
                items: Sequence[OSRSItem] = (await session.execute(select(OSRSItem))).scalars().all()
                items = sorted(items, key=lambda i: max([int(x) for x in i.graph_data['daily']]))
                for item in items:
                    graph_url: str = f'http://services.runescape.com/m=itemdb_oldschool/api/graph/{item.id}.json'

                    graph_data: dict[str, dict[str, str]] = {}

                    exists = True
                    while True:
                        r: ClientResponse = await bot.aiohttp.get(graph_url)
                        async with r:
                            if r.status == 404:
                                msg: str = f'OSRS 404 error for item {item.id}: {item.name}'
                                logging.critical(msg)
                                bot.queue_message(QueueMessage(get_text_channel(bot, bot.config['testChannel']), msg))
                                exists = False
                                break
                            elif r.status == 429:
                                msg: str = f'Rate limited in OSRS price tracking'
                                logging.critical(msg)
                                await asyncio.sleep(900)
                                continue
                            elif r.status != 200:
                                await asyncio.sleep(60)
                                continue
                            try:
                                graph_data = await r.json(content_type='text/html')
                                break
                            except Exception as e:
                                # This should only happen when the API is down
                                print(f'Unexpected error in OSRS price tracking for {item.id}: {item.name}\n{e}')
                                await asyncio.sleep(300)
                    
                    # Graph data may not be returned at times, even with status code 200
                    # Appears to be a regular occurrence, happening slightly after noon on days when a newspost is created
                    if not exists or not graph_data:
                        continue

                    prices: list[str] = []
                    for price in graph_data['daily'].values():
                        prices.append(price)
                    
                    current: str = str(prices[len(prices) - 1])
                    yesterday: str = str(prices[len(prices) - 2])
                    month_ago: str = str(prices[len(prices) - 31])
                    three_months_ago: str = str(prices[len(prices) - 91])
                    half_year_ago: str = str(prices[0])

                    today = str(int(current) - int(yesterday))
                    day30: str = '{:.1f}'.format((int(current) - int(month_ago)) / int(month_ago) * 100) + '%'
                    day90: str = '{:.1f}'.format((int(current) - int(three_months_ago)) / int(three_months_ago) * 100) + '%'
                    day180: str = '{:.1f}'.format((int(current) - int(half_year_ago)) / int(half_year_ago) * 100) + '%'
                    
                    item.current = current
                    item.today = today
                    item.day30 = day30
                    item.day90 = day90
                    item.day180 = day180
                    item.graph_data = graph_data
                    await session.commit()

                    await asyncio.sleep(6)
        except OSError as e:
            print(f'Error encountered in osrs price tracking: {e.__class__.__name__}: {e}')
            logging.critical(f'Error encountered in osrs price tracking: {e.__class__.__name__}: {e}')
            await asyncio.sleep(60)
        except Exception as e:
            error = f'Error encountered in osrs price tracking: {e.__class__.__name__}: {e}'
            print(error)
            logging.critical(error)
            bot.queue_message(QueueMessage(get_text_channel(bot, bot.config['testChannel']), error))
            await asyncio.sleep(600)