from datetime import datetime, UTC
import logging
from pathlib import Path
import sys
from typing import Sequence
import discord
from discord.ext import commands
from sqlalchemy import select
from src.bot import Bot
import string
import traceback
from src.price_tracking import price_tracking_osrs, price_tracking_rs3
from src.message_queue import QueueMessage
from src.database import Guild, Uptime
from src.database import get_db_engine, get_db_session_maker, create_all_database_tables
from src.discord_utils import find_text_channel, get_custom_command
from src.database_utils import find_or_create_db_guild
from src.startup_tasks import role_setup, check_guilds

class RuneClock(Bot):
    def __init__(self) -> None:
        super().__init__()
    
    async def setup_hook(self) -> None:
        '''
        Initializes the bot.
        '''
        self.loop.create_task(self.initialize())
        self.loop.create_task(self.message_queue.send_queued_messages())

        # Start fire-and-forget background tasks
        self.loop.create_task(role_setup(self))
        self.loop.create_task(check_guilds(self))

        # Price tracking is still done in a while true loop due to more complex scheduling logic to avoid rate limits
        self.loop.create_task(price_tracking_rs3(self))
        self.loop.create_task(price_tracking_osrs(self))

    async def start_bot(self) -> None:
        '''
        Starts the discord bot.
        '''
        await self.start(self.config['token'])

    async def setup_database(self) -> None:
        '''
        Initialize the database engine and session.
        Ensure all tables are created.
        '''
        print('Setting up database connection...')

        try:
            self.create_db_engine()
            await create_all_database_tables(self.engine)
        except Exception as e:
            error: str = f'Error encountered while setting up database: \n{type(e).__name__}: {e}'
            logging.critical(error)
            print(error)
            raise e

        print('Database ready!')

    async def initialize(self) -> None:
        '''
        Initializes the bot.
        '''
        print(f'Initializing...')

        await self.setup_database()

        async with self.get_session() as session:
            session.add(Uptime(time=self.start_time, status='started'))
            await session.commit()

        # Initialize guild cache
        # This is used to keep track of guild prefixes without needing to perform database requests for each message
        guilds: Sequence[Guild] = []
        async with self.get_session() as session:
            guilds: Sequence[Guild] = (await session.execute(select(Guild))).scalars().all()
        for g in guilds:
            self.db_guild_cache[g.id] = g

        print(f'Loading Discord...')

        await self.wait_until_ready()
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='@RuneClock help'))

        await self.load_all_extensions()

        channel: discord.TextChannel | None = find_text_channel(self, self.config['testChannel'])
        self.app_info = await self.application_info()
        msg: str = (f'Logged in to Discord as: {self.user.name if self.user else "???"}\n'
            f'Using Discord.py version: {discord.__version__}\n'
            f'Owner: {self.app_info.owner}\n'
            f'Time: {str(self.start_time)} UTC')
        print(msg)
        print('-' * 10)
        logging.critical(msg)
        if channel:
            self.queue_message(QueueMessage(channel, msg))

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

                if extension == 'custom_commands':
                    await self.refresh_custom_command_aliases()

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

    async def refresh_custom_command_aliases(self) -> None:
        custom_command: commands.Command = get_custom_command(self.bot)
        self.bot.remove_command(custom_command.name)
        custom_command.aliases = await self.get_custom_command_aliases()
        self.bot.add_command(custom_command)

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
        
        # Get guild from cache, or fetch it from the database / create it if it is not cached yet
        # This can happen e.g. if the bot was added to the guild while it was down, such that it was unable to receive the on_guild_join event
        guild: Guild
        if message.guild.id in self.db_guild_cache:
            guild = self.db_guild_cache[message.guild.id]
        else:
            async with self.get_session() as session:
                guild = await find_or_create_db_guild(session, message.guild)
            self.db_guild_cache[guild.id] = guild

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