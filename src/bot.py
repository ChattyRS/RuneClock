import asyncio
from datetime import datetime, timedelta, UTC
import logging
import os
from pathlib import Path
import sys
from typing import Any
import discord
from discord.ext import commands
from configuration import get_config
from auth_utils import get_google_sheets_credentials
import string
from aiohttp import ClientSession, ClientTimeout
import gspread_asyncio
import traceback
from github import Github
from message_queue import QueueMessage, MessageQueue
from database import Guild, Uptime
from database import get_db_engine, get_db_session_maker, create_all_database_tables
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from discord_utils import find_text_channel
from database_utils import get_db_guild, find_or_create_db_guild

class Bot(commands.AutoShardedBot):
    bot: commands.AutoShardedBot
    config: dict[str, Any]
    async_session: async_sessionmaker[AsyncSession]
    engine: AsyncEngine
    start_time: datetime
    app_info: discord.AppInfo
    aiohttp: ClientSession
    agcm: gspread_asyncio.AsyncioGspreadClientManager
    github: Github

    next_warband: datetime | None
    next_vos: datetime | None
    next_cache: datetime | None
    next_yews48: datetime | None
    next_yews140: datetime | None
    next_goebies: datetime | None
    next_sinkhole: datetime | None
    next_merchant: datetime | None
    next_spotlight: datetime | None
    next_wilderness_flash_event: datetime | None

    vos: dict[str, list[str]] | None
    merchant: str | None
    spotlight: str | None
    wilderness_flash_event: dict | None

    events_logged: int = 0
    command_counter = 0

    message_queue: MessageQueue = MessageQueue()

    def __init__(self) -> None:
        self.config = get_config()
        self.start_time = datetime.now(UTC).replace(microsecond=0)

        intents: discord.Intents = discord.Intents.all()
        super().__init__(
            max_messages = 1000000,
            command_prefix = self.get_prefix_,
            description = self.config['description'],
            case_insensitive = True,
            intents = intents
        )
        
        self.aiohttp = ClientSession(timeout=ClientTimeout(total=60))
        self.agcm = gspread_asyncio.AsyncioGspreadClientManager(get_google_sheets_credentials)
        self.github = Github(self.config['github_access_token'])
        self.bot = self

    async def start_bot(self) -> None:
        '''
        Starts the discord bot.
        '''
        await self.start(self.config['token'])
    
    async def close_database_connection(self) -> None:
        '''
        Close the database connection by disposing the engine.
        '''
        await self.engine.dispose()
    
    async def setup_hook(self) -> None:
        self.loop.create_task(self.initialize())

    def restart(self) -> None:
        '''
        Restarts the bot.
        The script runs in a loop, so by quitting, the bot will automatically restart.
        '''
        print("Restarting script...")
        os._exit(0)

    async def setup_database(self) -> None:
        '''
        Initialize the database engine and session.
        Ensure all tables are created.
        '''

        print('Setting up database connection...')

        self.engine = get_db_engine(self.config)
        self.async_session = get_db_session_maker(self.engine)
        await create_all_database_tables(self.engine)

        print('Database ready!')

    async def initialize(self) -> None:
        print(f'Initializing...')
        await asyncio.sleep(10) # Wait to ensure database is running on boot

        await self.setup_database()

        await asyncio.sleep(5) # Ensure database is up before we continue

        async with self.async_session() as session:
            session.add(Uptime(time=self.start_time, status='started'))
            await session.commit()

        self.loop.create_task(self.load_all_extensions())

        print(f'Loading Discord...')

        await self.wait_until_ready()
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='@RuneClock help'))

        channel: discord.TextChannel | None = find_text_channel(self, self.config['testChannel'])
        self.app_info = await self.application_info()
        msg = (f'Logged in to Discord as: {self.user.name if self.user else "???"}\n'
            f'Using Discord.py version: {discord.__version__}\n'
            f'Owner: {self.app_info.owner}\n'
            f'Time: {str(self.start_time)} UTC')
        print(msg)
        print('-' * 10)
        logging.critical(msg)

        if self.start_time:
            # If there is already a start time, we may just be reconnecting instead of starting.
            # In such cases, we want to avoid starting duplicate instances of the background tasks
            # Hence, we only start background tasks if the start time was in the past 5 minutes.
            if self.start_time > datetime.now(UTC) - timedelta(minutes=5):
                if channel:
                    self.queue_message(QueueMessage(channel, msg))
                self.start_background_tasks()
        else:
            self.start_background_tasks()

    def start_background_tasks(self) -> None:
        '''
        Starts the background tasks.
        '''
        self.loop.create_task(self.message_queue.send_queued_messages())

    def queue_message(self, message: QueueMessage) -> None:
        '''
        Add a message to the message queue.

        Args:
            message (QueueMessage): The message to add to the queue
        '''
        self.message_queue.append(message)
    
    def increment_command_counter(self) -> None:
        '''
        Increment global commands counter
        '''
        self.command_counter += 1
    
    def get_command_counter(self) -> int:
        '''
        Return value of global commands counter
        '''
        return self.command_counter

    async def get_prefix_(self, bot: commands.AutoShardedBot, message: discord.message.Message) -> list[str]:
        '''
        A coroutine that returns a prefix.
        Looks in database for prefix corresponding to the server the message was sent in
        If none found, return default prefix '-'

        Args:
            bot (commands.AutoShardedBot): The bot
            message (discord.message.Message): The message

        Returns:
            List[str]: list of prefixes
        '''
        guild: Guild = await get_db_guild(self, message.guild)
        prefix: str = guild.prefix if guild.prefix else '-'
        return commands.when_mentioned_or(prefix)(bot, message)

    async def load_all_extensions(self) -> None:
        '''
        Attempts to load all .py files in /cogs/ as cog extensions
        '''
        channel: discord.TextChannel | None = find_text_channel(self, self.config['testChannel'])
        cogs: list[str] = [x.stem for x in Path('cogs').glob('*.py')]
        msg: str = ''
        discord_msg: str = ''
        for extension in cogs:
            try:
                print(f'Loading {extension}...')
                await self.load_extension(f'cogs.{extension}')
                print(f'Loaded extension: {extension}')
                msg += f'Loaded extension: {extension}\n'
            except commands.ExtensionAlreadyLoaded:
                pass
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
                traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2, file=sys.stdout)
                error: str = f'{extension}\n {type(e).__name__} : {e}'
                print(f'Failed to load extension: {error}')
                msg += f'Failed to load extension: {error}\n'
                discord_msg += f'Failed to load extension: {error}\n'
        print('-' * 10)
        logging.critical(msg)

        if 'Failed' in msg and isinstance(channel, discord.TextChannel):
            self.queue_message(QueueMessage(channel, discord_msg))
            await channel.send(discord_msg)

    async def on_message(self, message: discord.Message) -> None:
        '''
        This event triggers on every message received by the bot. Including ones that it sent itself.
        Processes commands and logs processing time.
        '''
        if message.author.bot:
            return  # ignore all bots

        # For now, ignore messages that were not sent from guilds, because this might break certain commands
        if message.guild is None or not isinstance(message.channel, discord.TextChannel):
            return
        
        guild: Guild = await find_or_create_db_guild(self, message.guild)

        if guild.delete_channel_ids and message.channel.id in guild.delete_channel_ids and not message.author.id == message.guild.me.id:
            await message.delete()

        now: datetime = datetime.now(UTC)
        msg: str = message.content
        prefix: str = guild.prefix if guild.prefix else '-'

        for command_name in (guild.disabled_commands if guild.disabled_commands else []):
            if msg.startswith(f'{prefix}{command_name}') or (self.user and msg.startswith(f'{self.user.mention} {command_name}')):
                self.queue_message(QueueMessage(message.channel, f'The command `{command_name}` has been disabled in this server. Please contact a server admin to enable it.'))
                return

        if msg.startswith(prefix):
            txt: str = f'{datetime.now(UTC)}: Command \"{msg}\" received; processing...'
            logging.info(str(filter(lambda x: x in string.printable, txt)))
            print(txt)

        await self.process_commands(message)

        if msg.startswith(prefix):
            time: float = (datetime.now(UTC) - now).total_seconds() * 1000
            txt = f'Command \"{msg}\" processed in {time} ms.'
            logging.info(str(filter(lambda x: x in string.printable, txt)))
            print(txt)