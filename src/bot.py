import asyncio
from datetime import datetime, timedelta, UTC
import logging
import os
from pathlib import Path
import sys
from typing import Any, Sequence
import discord
from discord.ext import commands
from sqlalchemy import delete, select
from configuration import get_config
from auth_utils import get_google_sheets_credentials
from runescape_utils import dnd_names
import string
from aiohttp import ClientSession, ClientTimeout
import gspread_asyncio
import traceback
from github import Github
from message_queue import QueueMessage, MessageQueue
from database import Guild, Role, Mute, Command, Repository, Notification, OnlineNotification, Poll, Uptime, ClanBankTransaction, CustomRoleReaction
from database import get_db_engine, get_db_session_maker, create_all_database_tables
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from discord_utils import find_text_channel, get_text_channel, find_guild_text_channel
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

    async def purge_guild(self, guild: Guild) -> None:
        '''
        Purge all data relating to a specific Guild from the database
        '''
        async with self.async_session() as session:
            await session.execute(delete(Role).where(Role.guild_id == guild.id))
            await session.execute(delete(Mute).where(Mute.guild_id == guild.id))
            await session.execute(delete(Command).where(Command.guild_id == guild.id))
            await session.execute(delete(Repository).where(Repository.guild_id == guild.id))
            await session.execute(delete(Notification).where(Notification.guild_id == guild.id))
            await session.execute(delete(OnlineNotification).where(OnlineNotification.guild_id == guild.id))
            await session.execute(delete(Poll).where(Poll.guild_id == guild.id))
            await session.execute(delete(ClanBankTransaction).where(ClanBankTransaction.guild_id == guild.id))
            await session.execute(delete(CustomRoleReaction).where(CustomRoleReaction.guild_id == guild.id))
            await session.delete(guild)
            await session.commit()
    
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
        self.loop.create_task(self.check_guilds())
        self.loop.create_task(self.role_setup())

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

    async def check_guilds(self) -> None:
        '''
        Function that is run on startup by on_ready
        Checks database for entries of guilds that the bot is no longer a member of
        Adds default prefix entry to prefixes table if guild doesn't have a prefix set
        '''
        logging.info('Checking guilds...')
        print(f'Checking guilds...')

        async with self.async_session() as session:
            guilds: Sequence[Guild] = (await session.execute(select(Guild).where(Guild.id.not_in([g.id for g in self.guilds])))).scalars().all()
            for guild in guilds:
                await self.purge_guild(guild)

        msg: str = f'{str(len(self.guilds))} guilds checked'
        print(msg)
        print('-' * 10)
        logging.info(msg)

    async def role_setup(self) -> None:
        '''
        Sets up message and reactions for role management
        Assumes that no other messages are sent in the role management channels
        Adds messages to cache to track reactions
        '''
        print(f'Initializing role management...')
        logging.info('Initializing role management...')

        guilds: Sequence[Guild]
        async with self.async_session() as session:
            guilds = (await session.execute(select(Guild).where(Guild.role_channel_id.isnot(None)))).scalars().all()

        channels: list[discord.TextChannel] = []
        for db_guild in guilds:
            channel: discord.TextChannel | None = find_text_channel(self, db_guild.role_channel_id)
            if channel:
                channels.append(channel)

        if not channels:
            msg: str = f'Sorry, I was unable to retrieve any role management channels. Role management is down.'
            print(msg)
            print('-' * 10)
            logging.critical(msg)
            logChannel: discord.TextChannel = get_text_channel(self, self.config['testChannel'])
            self.queue_message(QueueMessage(logChannel, msg))
            return
            
        msg = "React to this message with any of the following emoji to be added to the corresponding role for notifications:\n\n"
        notif_emojis: list[discord.Emoji] = []
        for r in dnd_names:
            emoji_id: int = self.config[f'{r.lower()}EmojiID']
            emoji: discord.Emoji | None = self.get_emoji(emoji_id)
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
                    message = await c.send(msg)
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

    async def on_member_join(self, member: discord.Member) -> None:
        '''
        Function to send welcome messages
        '''
        guild: Guild = await get_db_guild(self, member.guild)

        if not guild.welcome_message or not guild.welcome_channel_id:
            return
        
        welcome_channel: discord.TextChannel | None = find_guild_text_channel(member.guild, guild.welcome_channel_id)
        if not isinstance(welcome_channel, discord.TextChannel):
            return
        
        welcome_message: str = guild.welcome_message.replace('[user]', member.mention)
        welcome_message = welcome_message.replace('[server]', member.guild.name)

        self.queue_message(QueueMessage(welcome_channel, welcome_message))

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        '''
        Function to add roles on reactions
        '''
        channel: discord.TextChannel | None = find_text_channel(self, payload.channel_id)

        if not isinstance(channel, discord.TextChannel):
            return

        user: discord.Member = await channel.guild.fetch_member(payload.user_id)

        if not user or user.bot:
            return

        guild: Guild = await get_db_guild(self, channel.guild)

        if guild.role_channel_id == channel.id:
            emoji: discord.PartialEmoji = payload.emoji
            role_name: str = emoji.name
            if emoji.name in dnd_names:
                role: discord.Role | None = discord.utils.get(channel.guild.roles, name=role_name)
            elif guild.id == self.config['portablesServer'] and emoji.name in ['Fletcher', 'Crafter', 'Brazier', 'Sawmill', 'Range', 'Well', 'Workbench']:
                role = discord.utils.get(channel.guild.roles, name=role_name)
                
            if role:
                try:
                    await user.add_roles(role)
                except discord.Forbidden:
                    pass
        
        if str(payload.emoji) == '🌟' and guild.hall_of_fame_channel_id and guild.hall_of_fame_react_num:
            message: discord.Message = await channel.fetch_message(payload.message_id)
            hof_channel: discord.TextChannel | None = find_text_channel(self, guild.hall_of_fame_channel_id)
            if isinstance(hof_channel, discord.TextChannel) and message and not message.author.bot and (message.content or message.attachments):
                reactions: list[discord.Reaction] = [r for r in message.reactions if r.emoji == '🌟' and r.count >= guild.hall_of_fame_react_num]
                reaction: discord.Reaction | None = reactions[0] if reactions else None
                if reaction:
                    hof_msg: discord.Message | None = None
                    hof_embed: discord.Embed | None = None
                    async for msg in hof_channel.history(limit=1000, after=message.created_at):
                        for embed in [em for em in msg.embeds if em.footer.text and str(message.id) in em.footer.text]:
                            hof_msg = msg
                            hof_embed = embed
                            break
                        if hof_msg and hof_embed:
                            break

                    if not hof_msg or not hof_embed:
                        embed = discord.Embed(title=f'Hall of fame 🌟 {reaction.count}', description=message.content, colour=0xffd700, url=message.jump_url, timestamp=message.created_at)
                        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
                        attachments: list[discord.Attachment] = [a for a in message.attachments if a.content_type and 'image' in a.content_type]
                        attachment: discord.Attachment | None = attachments[0] if attachments else None
                        if attachment:
                            embed.set_image(url=attachment.url)
                        embed.set_footer(text=f'Message ID: {message.id}')
                        self.queue_message(QueueMessage(hof_channel, None, embed))
                    else:
                        hof_embed.title = f'Hall of fame 🌟 {reaction.count}'
                        await hof_msg.edit(embed=hof_embed)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        '''
        Function to remove roles on reactions
        '''
        channel: discord.TextChannel | None = find_text_channel(self, payload.channel_id)
        if not channel:
            return
        
        guild: Guild = await get_db_guild(self, channel.guild)
        if guild.role_channel_id == channel.id:
            return

        emoji: discord.PartialEmoji = payload.emoji
        role_name: str = emoji.name
        if emoji.name in dnd_names:
            role: discord.Role | None = discord.utils.get(channel.guild.roles, name=role_name)
        elif guild.id == self.config['portablesServer'] and emoji.name in ['Fletcher', 'Crafter', 'Brazier', 'Sawmill', 'Range', 'Well', 'Workbench']:
            role = discord.utils.get(channel.guild.roles, name=role_name)
        if not role:
            return
        
        try:
            user: discord.Member = await channel.guild.fetch_member(payload.user_id)
        except discord.NotFound:
            return
        if user.bot:
            return
        
        try:
            await user.remove_roles(role)
        except discord.Forbidden:
            return

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