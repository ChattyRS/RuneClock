from datetime import datetime, UTC
import os
from typing import Any
import discord
from discord.ext import commands
from src.database import Guild
from src.database_utils import get_db_guild
from src.configuration import get_config
from src.auth_utils import get_google_sheets_credentials
from aiohttp import TCPConnector, ClientSession, ClientTimeout
import gspread_asyncio
from github import Github
from src.message_queue import MessageQueue, QueueMessage
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from praw import Reddit
import certifi
import ssl

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
    reddit: Reddit

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
        
        ssl_context: ssl.SSLContext = ssl.create_default_context(cafile=certifi.where())
        connector = TCPConnector(ssl=ssl_context)
        self.aiohttp = ClientSession(timeout=ClientTimeout(total=60), connector=connector)
        self.agcm = gspread_asyncio.AsyncioGspreadClientManager(get_google_sheets_credentials)
        self.github = Github(self.config['github_access_token'])
        self.reddit = Reddit(
            client_id = self.config['redditID'], 
            client_secret = self.config['redditSecret'], 
            password = self.config['redditPW'], 
            user_agent = self.config['user_agent'], 
            username = self.config['redditName']
        )
        self.bot = self
    
    async def close_database_connection(self) -> None:
        '''
        Close the database connection by disposing the engine.
        '''
        await self.engine.dispose()

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
        guild: Guild = await get_db_guild(self.async_session, message.guild)
        prefix: str = guild.prefix if guild.prefix else '-'
        return commands.when_mentioned_or(prefix)(bot, message)
    
    def restart(self) -> None:
        '''
        Restarts the bot.
        The script runs in a loop, so by quitting, the bot will automatically restart.
        '''
        print("Restarting script...")
        os._exit(0)
    
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
    
    def queue_message(self, message: QueueMessage) -> None:
        '''
        Add a message to the message queue.

        Args:
            message (QueueMessage): The message to add to the queue
        '''
        self.message_queue.append(message)