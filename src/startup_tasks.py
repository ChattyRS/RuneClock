import asyncio
import logging
from typing import Sequence
import discord
from sqlalchemy import select
from src.bot import Bot
from src.database import Guild
from src.discord_utils import find_text_channel, get_text_channel
from src.message_queue import QueueMessage
from src.runescape_utils import dnd_names
from src.database_utils import purge_guild

async def role_setup(bot: Bot) -> None:
    '''
    Sets up message and reactions for role management if no message is sent in the channel yet
    Adds messages to cache to track reactions
    '''
    await bot.wait_until_ready()
    print(f'Initializing role management...')
    logging.info('Initializing role management...')

    guilds: Sequence[Guild]
    async with bot.db.get_session() as session:
        guilds = (await session.execute(select(Guild).where(Guild.role_channel_id.isnot(None)))).scalars().all()

    channels: list[discord.TextChannel] = []
    for db_guild in guilds:
        channel: discord.TextChannel | None = find_text_channel(bot, db_guild.role_channel_id)
        if channel:
            channels.append(channel)

    if not channels:
        msg: str = f'Sorry, I was unable to retrieve any role management channels. Role management is down.'
        print(msg)
        print('-' * 10)
        logging.critical(msg)
        logChannel: discord.TextChannel = get_text_channel(bot, bot.config['testChannel'])
        bot.queue_message(QueueMessage(logChannel, msg))
        return
        
    msg = "React to this message with any of the following emoji to be added to the corresponding role for notifications:\n\n"
    notif_emojis: list[discord.Emoji] = []
    for r in dnd_names:
        emoji_id: int = bot.config[f'{r.lower()}EmojiID']
        emoji: discord.Emoji | None = bot.get_emoji(emoji_id)
        if emoji:
            notif_emojis.append(emoji)
            msg += str(emoji) + ' ' + r + '\n'
    msg += "\nIf you wish to stop receiving notifications, simply remove your reaction. If your reaction isn't there anymore, then you can add a new one and remove it."
    for c in channels:
        try:
            messages = 0
            async for message in c.history(limit=1):
                messages += 1
            if not messages:
                message: discord.Message = await c.send(msg)
                try:
                    for emoji in notif_emojis:
                        await message.add_reaction(emoji)
                except Exception as e:
                    print(f'Exception: {e}')
        except discord.Forbidden:
            continue

    msg = f'Role management ready'
    print(msg)
    print('-' * 10)
    logging.info(msg)

async def check_guilds(bot: Bot) -> None:
    '''
    Function that is run on startup by on_ready
    Checks database for entries of guilds that the bot is no longer a member of
    Adds default prefix entry to prefixes table if guild doesn't have a prefix set
    '''
    await bot.wait_until_ready()

    logging.info('Checking guilds...')
    print(f'Checking guilds...')

    async with bot.db.get_session() as session:
        db_guilds: Sequence[Guild] = (await session.execute(select(Guild).where(Guild.id.not_in([g.id for g in bot.guilds])))).scalars().all()
        for db_guild in db_guilds:
            await purge_guild(session, db_guild)
        await session.commit()

    msg: str = f'{str(len(bot.guilds))} guilds checked'
    print(msg)
    print('-' * 10)
    logging.info(msg)