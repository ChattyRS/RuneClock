import asyncio
from datetime import datetime, timedelta, UTC
import logging
from pathlib import Path
import sys
from typing import Any, NoReturn, Sequence
import discord
from discord.abc import PrivateChannel
from discord.ext import commands
from github.Commit import Commit
from github.Repository import Repository as GitRepository
from github.AuthenticatedUser import AuthenticatedUser
from github.NamedUser import NamedUser
from github.PaginatedList import PaginatedList
from github.Repository import Repository
from sqlalchemy import delete, insert, select
from utils import get_config, get_gspread_creds, districts, notification_roles
import string
from aiohttp import ClientResponse, ClientSession, ClientTimeout
import gspread_asyncio
import feedparser
import traceback
from github import Github
from difflib import SequenceMatcher
import io
from src.message_queue import QueueMessage, MessageQueue

# Other cogs import database classes from main
# so even though some of these classes may appear not to be in use, they should not be removed here
from database import User, Guild, Role, Mute, Command, Repository, Notification, OnlineNotification, Poll, NewsPost, Uptime, RS3Item, OSRSItem, ClanBankTransaction, CustomRoleReaction, BannedGuild
from database import setup as database_setup
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

'''
Used for plagiarism check for smiley applications
'''
def similarity(a, b) -> float:
    return SequenceMatcher(None, a, b).ratio()

'''
Split a string by a list of separating characters
'''
def split(txt, seps) -> list[Any]:
    # https://stackoverflow.com/questions/4697006/python-split-string-by-list-of-separators/4697047
    default_sep = seps[0]
    # we skip seps[0] because that's the default seperator
    for sep in seps[1:]:
        txt = txt.replace(sep, default_sep)
    return [i.strip() for i in txt.split(default_sep)]

async def run() -> None:
    '''
    Where the bot gets started. If you wanted to create a database connection pool or other session for the bot to use,
    it's recommended that you create it here and pass it to the bot as a kwarg.
    '''
    config: dict[str, Any] = get_config()
    bot = Bot(description=config['description'])
    try:
        await bot.start(config['token'])
    except KeyboardInterrupt:
        await bot.close()

class Bot(commands.AutoShardedBot):
    bot: commands.AutoShardedBot
    config: dict[str, Any]
    async_session: async_sessionmaker[AsyncSession]
    engine: AsyncEngine
    start_time: datetime
    app_info: discord.AppInfo
    aiohttp: ClientSession
    agcm: gspread_asyncio.AsyncioGspreadClientManager

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
    command_counter = 0 # int to track how many commands have been processed since startup

    message_queue: MessageQueue = MessageQueue()

    def __init__(self, **kwargs) -> None:
        intents: discord.Intents = discord.Intents.all()
        super().__init__(
            max_messages = 1000000,
            command_prefix=self.get_prefix_,
            description=kwargs.pop('description'),
            case_insensitive=True,
            intents=intents
        )
        
        self.aiohttp = ClientSession(timeout=ClientTimeout(total=60))
        self.agcm = gspread_asyncio.AsyncioGspreadClientManager(get_gspread_creds)
        self.config = get_config()
        self.bot = self
    
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
    
    async def setup_hook(self) -> None:
        await self.track_start()
        self.loop.create_task(self.initialize())

    async def track_start(self) -> None:
        '''
        Waits for the bot to connect to discord and then records the time.
        Can be used to work out uptime.
        '''
        # await self.wait_until_ready()
        self.start_time = datetime.now(UTC).replace(microsecond=0)

    #region Helper methods

    def find_guild_text_channel(self, guild: discord.Guild, id: int | None) -> discord.TextChannel | None:
        channel: discord.VoiceChannel | discord.StageChannel | discord.ForumChannel | discord.TextChannel | discord.CategoryChannel | discord.Thread | PrivateChannel | None = guild.get_channel(id) if id else None
        return channel if isinstance(channel, discord.TextChannel) else None
    
    def get_guild_text_channel(self, guild: discord.Guild, id: int | None) -> discord.TextChannel:
        channel: discord.TextChannel | None = self.find_guild_text_channel(guild, id)
        if not channel:
            raise Exception(f'Guild channel with id {id if id else "None"} was not found.')
        return channel

    def find_text_channel(self, id: int | None) -> discord.TextChannel | None:
        channel: discord.VoiceChannel | discord.StageChannel | discord.ForumChannel | discord.TextChannel | discord.CategoryChannel | discord.Thread | PrivateChannel | None = self.get_channel(id) if id else None
        return channel if isinstance(channel, discord.TextChannel) else None
    
    def get_text_channel(self, id: int | None) -> discord.TextChannel:
        channel: discord.TextChannel | None = self.find_text_channel(id)
        if not channel:
            raise Exception(f'Channel with id {id if id else "None"} was not found.')
        return channel
    
    def find_role(self, guild_or_id: discord.Guild | int | None, role_id: int | None) -> discord.Role | None:
        guild: discord.Guild | None = guild_or_id if isinstance(guild_or_id, discord.Guild) else None
        if not guild and isinstance(guild_or_id, int):
            guild = self.get_guild(guild_or_id)
        if not guild:
            raise Exception(f'Channel with id {id if id else "None"} was not found.')
        role: discord.Role | None = guild.get_role(role_id) if role_id else None
        return role
    
    def get_role(self, guild_or_id: discord.Guild | int | None, role_id: int | None) -> discord.Role:
        role: discord.Role | None = self.find_role(guild_or_id, role_id)
        if not role:
            raise Exception(f'Role with id {role_id if role_id else "None"} was not found.')
        return role
    
    async def find_db_guild(self, guild_or_id: discord.Guild | int | None, session: AsyncSession | None = None) -> Guild | None:
        id: int | None = guild_or_id.id if isinstance(guild_or_id, discord.Guild) else guild_or_id
        if session:
            return (await session.execute(select(Guild).where(Guild.id == id))).scalar_one_or_none()
        async with self.async_session() as session:
            return (await session.execute(select(Guild).where(Guild.id == id))).scalar_one_or_none()

    async def get_db_guild(self, guild_or_id: discord.Guild | int | None, session: AsyncSession | None = None) -> Guild:
        id: int | None = guild_or_id.id if isinstance(guild_or_id, discord.Guild) else guild_or_id
        if not id:
            raise Exception(f'Attempted to get a guild from the database but ID was None.')
        guild: Guild | None = await self.find_db_guild(id, session)
        if not guild:
            raise Exception(f'Guild with id {id} was not found.')
        return guild
    
    async def create_db_guild(self, guild_or_id: discord.Guild | int) -> Guild:
        id: int = guild_or_id.id if isinstance(guild_or_id, discord.Guild) else guild_or_id
        async with self.async_session() as session:
            instance = Guild(id=id, prefix='-')
            session.add(instance)
            await session.commit()
        return instance
    
    async def find_or_create_db_guild(self, guild_or_id: discord.Guild | int) -> Guild:
        db_guild: Guild | None = await self.find_db_guild(guild_or_id)
        return db_guild if db_guild else await self.create_db_guild(guild_or_id)
    
    #endregion: Helper methods

    async def initialize(self) -> None:
        print(f'Initializing...')
        config: dict[str, Any] = get_config()
        await asyncio.sleep(10) # Wait to ensure database is running on boot

        await database_setup(self)

        await asyncio.sleep(5) # Ensure database is up before we continue

        async with self.async_session() as session:
            session.add(Uptime(time=self.start_time, status='started'))
            await session.commit()

        self.loop.create_task(self.load_all_extensions())

        print(f'Loading Discord...')

        await self.wait_until_ready()
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='@RuneClock help'))

        channel: discord.TextChannel | None = self.find_text_channel(config['testChannel'])
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
        self.loop.create_task(self.notify())
        self.loop.create_task(self.custom_notify())
        self.loop.create_task(self.unmute())
        self.loop.create_task(self.rsnews())
        self.loop.create_task(self.check_polls())
        self.loop.create_task(self.git_tracking())
        self.loop.create_task(self.price_tracking_rs3())
        self.loop.create_task(self.price_tracking_osrs())

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
        guild: Guild = await self.get_db_guild(message.guild)
        prefix: str = guild.prefix if guild.prefix else '-'
        return commands.when_mentioned_or(prefix)(bot, message)

    async def load_all_extensions(self) -> None:
        '''
        Attempts to load all .py files in /cogs/ as cog extensions
        '''
        # await self.wait_until_ready()
        config: dict[str, Any] = get_config()
        channel: discord.TextChannel | None = self.find_text_channel(config['testChannel'])
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
        config: dict[str, Any] = get_config()

        guilds: Sequence[Guild]
        async with self.async_session() as session:
            guilds = (await session.execute(select(Guild).where(Guild.role_channel_id.isnot(None)))).scalars().all()

        channels: list[discord.TextChannel] = []
        for db_guild in guilds:
            channel: discord.TextChannel | None = self.find_text_channel(db_guild.role_channel_id)
            if channel:
                channels.append(channel)

        if not channels:
            msg: str = f'Sorry, I was unable to retrieve any role management channels. Role management is down.'
            print(msg)
            print('-' * 10)
            logging.critical(msg)
            logChannel: discord.TextChannel = self.get_text_channel(config['testChannel'])
            self.queue_message(QueueMessage(logChannel, msg))
            return
            
        msg = "React to this message with any of the following emoji to be added to the corresponding role for notifications:\n\n"
        notif_emojis: list[discord.Emoji] = []
        for r in notification_roles:
            emoji_id: int = config[f'{r.lower()}EmojiID']
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
        guild: Guild = await self.get_db_guild(member.guild)

        if not guild.welcome_message or not guild.welcome_channel_id:
            return
        
        welcome_channel: discord.TextChannel | None = self.find_guild_text_channel(member.guild, guild.welcome_channel_id)
        if not isinstance(welcome_channel, discord.TextChannel):
            return
        
        welcome_message: str = guild.welcome_message.replace('[user]', member.mention)
        welcome_message = welcome_message.replace('[server]', member.guild.name)

        self.queue_message(QueueMessage(welcome_channel, welcome_message))

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        '''
        Function to add roles on reactions
        '''
        channel: discord.TextChannel | None = self.find_text_channel(payload.channel_id)

        if not isinstance(channel, discord.TextChannel):
            return

        user: discord.Member = await channel.guild.fetch_member(payload.user_id)

        if not user or user.bot:
            return

        guild: Guild = await self.get_db_guild(channel.guild)

        if guild.role_channel_id == channel.id:
            emoji: discord.PartialEmoji = payload.emoji
            role_name: str = emoji.name
            if emoji.name in notification_roles:
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
            hof_channel: discord.TextChannel | None = self.find_text_channel(guild.hall_of_fame_channel_id)
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
        channel: discord.TextChannel | None = self.find_text_channel(payload.channel_id)
        if not channel:
            return
        
        guild: Guild = await self.get_db_guild(channel.guild)
        if guild.role_channel_id == channel.id:
            return

        emoji: discord.PartialEmoji = payload.emoji
        role_name: str = emoji.name
        if emoji.name in notification_roles:
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
        
        guild: Guild = await self.find_or_create_db_guild(message.guild)

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
                    
    async def send_notifications(self, message: str, role_dict: dict[str, str] | None = None) -> None:
        '''
        Get coroutines to send notifications to the configured notification channels.

        Args:
            message (str): The notification message.
            role_name (str): The name of the role to mentioned (if found).

        Returns:
            _type_: A list of coroutines which can be awaited to send the notifications.
        '''

        async with self.async_session() as session:
            guilds: Sequence[Guild] = (await session.execute(select(Guild).where(Guild.notification_channel_id.is_not(None)))).scalars().all()
        
        channels: list[discord.TextChannel] = [channel for channel in [self.find_text_channel(guild.notification_channel_id) for guild in guilds] if channel]

        for c in channels:
            for role_name, text_to_replace in (role_dict if role_dict else []):
                roles: list[discord.Role] = [r for r in c.guild.roles if role_name.upper() in r.name.upper()]
                role_mention: str = roles[0].mention if roles else ''
                msg: str = message.replace(text_to_replace, role_mention)
            self.queue_message(QueueMessage(c, msg))

    async def notify(self) -> None:
        '''
        Function to send D&D notifications
        Runs every 10 s.
        Merchant and spotlight are exceptions, run every 5 min and 1 min, respectively.
        At first run, reads sent notifications to avoid duplicates on restart.
        '''
        print(f'Initializing notifications...')
        logging.info('Initializing notifications...')
        config: dict[str, Any] = get_config()
        channel: discord.TextChannel | None = self.find_text_channel(config['testNotificationChannel'])
        log_channel: discord.TextChannel | None = self.find_text_channel(config['testChannel'])
        
        if not channel:
            msg: str = 'Unable to retrieve any notification channels. Notifications are down.'
            print(msg)
            logging.critical(msg)
            if log_channel:
                self.queue_message(QueueMessage(log_channel, msg))
            return
        notified_this_hour_warbands = False
        notified_this_hour_vos = False
        notified_this_hour_cache = False
        notified_this_hour_yews_48 = False
        notified_this_hour_yews_140 = False
        notified_this_hour_goebies = False
        notified_this_hour_sinkhole = False
        notified_this_hour_wilderness_flash = False
        notified_this_day_merchant = False
        notified_this_day_spotlight = False
        reset = False
        current_time: datetime = datetime.now(UTC)
        async for m in channel.history(limit=100):
            if m.created_at.day == current_time.day:
                if 'Merchant' in m.content:
                    notified_this_day_merchant = True
                    continue
                if 'spotlight' in m.content:
                    notified_this_day_spotlight = True
                    continue
                if m.created_at.hour == current_time.hour:
                    if 'Warbands' in m.content:
                        notified_this_hour_warbands = True
                        continue
                    if any(d in m.content for d in districts):
                        if current_time.minute <= 1:
                            reset = True
                        notified_this_hour_vos = True
                        continue
                    if 'Cache' in m.content:
                        notified_this_hour_cache = True
                        continue
                    if 'yew' in m.content:
                        if '48' in m.content:
                            notified_this_hour_yews_48 = True
                        elif '140' in m.content:
                            notified_this_hour_yews_140 = True
                        continue
                    if 'Goebies' in m.content:
                        notified_this_hour_goebies = True
                        continue
                    if 'Sinkhole' in m.content:
                        notified_this_hour_sinkhole = True
                        continue
                    if 'wilderness' in m.content.lower() and 'flash' in m.content.lower():
                        notified_this_hour_wilderness_flash = True
                        continue
            else:
                break
        await asyncio.sleep(3) # Ensure values are initialized from dndCommands.py
        msg = f'Notifications ready'
        logging.info(msg)
        print(msg)
        print('-' * 10)
        i: int = 0
        while True:
            try:
                now: datetime = datetime.now(UTC)

                if not notified_this_day_merchant and now.hour <= 2 and self.next_merchant and self.next_merchant > now + timedelta(hours=1):
                    msg = f'__role_mention__\n**Traveling Merchant** stock {now.strftime("%d %b")}\n{self.merchant}'
                    await self.send_notifications(msg, {'MERCHANT': '__role_mention__'})
                    notified_this_day_merchant = True

                if not notified_this_day_spotlight and now.hour <= 1 and self.next_spotlight and self.next_spotlight > now + timedelta(days=2, hours=1):
                    msg = f'{config["spotlightEmoji"]} **{self.spotlight}** is now the spotlighted minigame. __role_mention__'
                    await self.send_notifications(msg, {'SPOTLIGHT': '__role_mention__'})
                    notified_this_day_spotlight = True

                if not notified_this_hour_vos and now.minute <= 1 and self.vos and self.next_vos and self.next_vos > now + timedelta(minutes=1):
                    msg = '\n'.join([config[f'msg{d}'] + f'__role_{d}__' for d in self.vos['vos']])
                    role_dict: dict[str, str] = {d: f'__role_{d}__' for d in self.vos['vos']}
                    await self.send_notifications(msg, role_dict)
                    notified_this_hour_vos = True
                        
                if not notified_this_hour_warbands and now.minute >= 45 and now.minute <= 46 and self.next_warband and self.next_warband - now <= timedelta(minutes=15):
                    msg = config['msgWarbands'] + '__role_mention__'
                    await self.send_notifications(msg, {'WARBAND': '__role_mention__'})
                    notified_this_hour_warbands = True
                            
                if not notified_this_hour_cache and now.minute >= 55 and now.minute <= 56:
                    msg = config['msgCache'] + '__role_mention__'
                    await self.send_notifications(msg, {'CACHE': '__role_mention__'})
                    notified_this_hour_cache = True

                if not notified_this_hour_yews_48 and now.hour == 23 and now.minute >= 45 and now.minute <= 46:
                    msg = config['msgYews48'] + '__role_mention__'
                    await self.send_notifications(msg, {'YEW': '__role_mention__'})
                    notified_this_hour_yews_48 = True

                if not notified_this_hour_yews_140 and now.hour == 16 and now.minute >= 45 and now.minute <= 46:
                    msg = config['msgYews140'] + '__role_mention__'
                    await self.send_notifications(msg, {'YEW': '__role_mention__'})
                    notified_this_hour_yews_140 = True
                    
                if not notified_this_hour_goebies and now.hour in [11, 23] and now.minute >= 45 and now.minute <= 46:
                    msg = config['msgGoebies'] + '__role_mention__'
                    await self.send_notifications(msg, {'GOEBIE': '__role_mention__'})
                    notified_this_hour_goebies = True

                if not notified_this_hour_sinkhole and now.minute >= 25 and now.minute <= 26:
                    msg = config['msgSinkhole'] + '__role_mention__'
                    await self.send_notifications(msg, {'SINKHOLE': '__role_mention__'})
                    notified_this_hour_sinkhole = True
                
                if not notified_this_hour_wilderness_flash and now.minute >= 55 and now.minute <= 56 and self.wilderness_flash_event:
                    msg = f'{config["wildernessflasheventsEmoji"]} The next **Wilderness Flash Event** will start in 5 minutes: **{self.wilderness_flash_event["next"]}**. __role_mention__'
                    await self.send_notifications(msg, {'WILDERNESSFLASHEVENT': '__role_mention__'})
                    notified_this_hour_wilderness_flash = True

                if now.minute > 1 and reset:
                    reset = False
                if now.minute == 0 and not reset:
                    notified_this_hour_warbands = False
                    notified_this_hour_vos = False
                    notified_this_hour_cache = False
                    notified_this_hour_yews_48 = False
                    notified_this_hour_yews_140 = False
                    notified_this_hour_goebies = False
                    notified_this_hour_sinkhole = False
                    notified_this_hour_wilderness_flash = False
                    if now.hour == 0:
                        notified_this_day_merchant = False
                        notified_this_day_spotlight = False
                    reset = True
                await asyncio.sleep(15)
                i = (i + 1) % 4
            except Exception as e:
                error: str = f'Encountered the following error in notification loop:\n{type(e).__name__}: {e}'
                logging.critical(error)
                print(error)
                if log_channel:
                    self.queue_message(QueueMessage(log_channel, error))
                await asyncio.sleep(5)

    async def custom_notify(self) -> NoReturn:
        '''
        Function to send custom notifications
        '''
        logging.info('Initializing custom notifications...')
        while True:
            try:
                async with self.async_session() as session:
                    deleted_from_guild_ids: list[int] = []
                    notifications: Sequence[Notification] = (await session.execute(select(Notification).where(Notification.time <= datetime.now(UTC)))).scalars().all()
                    for notification in notifications:
                        guild: discord.Guild | None = self.get_guild(notification.guild_id)
                        if not guild or not notification.message:
                            await session.delete(notification)
                            continue
                        channel: discord.TextChannel | None = self.find_guild_text_channel(guild, notification.channel_id)
                        if not channel:
                            await session.delete(notification)
                            continue
                        self.queue_message(QueueMessage(channel, notification.message))

                        interval = timedelta(seconds = notification.interval)
                        if interval.total_seconds() != 0:
                            while notification.time < datetime.now(UTC):
                                notification.time += interval
                        else:
                            deleted_from_guild_ids.append(notification.guild_id)
                            await session.delete(notification)
                    
                    for guild_id in deleted_from_guild_ids:
                        guild_notifications: Sequence[Notification] = (await session.execute(select(Notification).where(Notification.guild_id == guild_id))).scalars().all()
                        for i, notification in enumerate(guild_notifications):
                            notification.notification_id = i

                    await session.commit()

                await asyncio.sleep(30)
            except Exception as e:
                error = f'Encountered the following error in custom notification loop:\n{type(e).__name__}: {e}'
                logging.critical(error)
                print(error)
                try:
                    log_channel: discord.TextChannel | None = self.find_text_channel(self.config['testChannel'])
                    if log_channel:
                        self.queue_message(QueueMessage(log_channel, error))
                except:
                    pass
                await asyncio.sleep(30)
                

    async def unmute(self) -> NoReturn:
        '''
        Function to unmute members when mutes expire
        '''
        logging.info('Initializing unmute...')
        while True:
            to_unmute: list[tuple[discord.Member, discord.Role, discord.Guild]] = []
            async with self.async_session() as session:
                mutes: Sequence[Mute] = (await session.execute(select(Mute).where(Mute.expiration <= datetime.now(UTC)))).scalars().all()
                for mute in mutes:
                    guild: discord.Guild | None = self.get_guild(mute.guild_id)
                    member: discord.Member | None = await guild.fetch_member(mute.user_id) if guild else None
                    mute_role: discord.Role | None = discord.utils.find(lambda r: 'MUTE' in r.name.upper(), guild.roles if guild else [])
                    await session.delete(mute)
                    if not guild or not member or not mute_role or not mute_role in member.roles:
                        continue
                    to_unmute.append((member, mute_role, guild))

            for member, mute_role, guild in to_unmute:
                try:
                    await member.remove_roles(mute_role, reason='Temp mute expired.')
                    for channel in [c for c in guild.text_channels if not c.permissions_for(member).send_messages]:
                        overwrite: discord.PermissionOverwrite | None = channel.overwrites[member] if member in channel.overwrites else None
                        if overwrite and not overwrite.pair()[1].send_messages:
                            try:
                                await channel.set_permissions(member, send_messages=None)
                                channel: discord.TextChannel = self.get_guild_text_channel(guild, channel.id)
                                overwrite = channel.overwrites[member] if member in channel.overwrites else None
                                if overwrite and overwrite.is_empty():
                                    await channel.set_permissions(member, overwrite=None)
                            except discord.Forbidden:
                                pass
                except discord.Forbidden:
                    continue
            await asyncio.sleep(60)

    async def send_news(self, post: NewsPost, osrs: bool) -> None:
        '''
        Function to send a message for a runescape newspost.

        Args:
            post (NewsPost): The news post.
            osrs (bool): Denotes whether the news post is for OSRS (true) or RS3 (false).
        '''
        embed = discord.Embed(title=f'**{post.title}**', description=post.description, url=post.link, timestamp=datetime.now(UTC))
        if osrs:
            embed.set_author(name='Old School RuneScape News', url='http://services.runescape.com/m=news/archive?oldschool=1', icon_url='https://i.imgur.com/2d5RrGi.png')
        else:
            embed.set_author(name='RuneScape News', url='http://services.runescape.com/m=news/list', icon_url='https://i.imgur.com/OiV3xHn.png')
        if post.category:
            embed.set_footer(text=post.category)
        
        if post.image_url:
            embed.set_image(url=post.image_url)

        guilds: Sequence[Guild]

        async with self.async_session() as session:
            if osrs:
                guilds = (await session.execute(select(Guild).where(Guild.osrs_news_channel_id.is_not(None)))).scalars().all()
            else:
                guilds = (await session.execute(select(Guild).where(Guild.rs3_news_channel_id.is_not(None)))).scalars().all()

        for guild in guilds:
            news_channel: discord.TextChannel | None = self.find_text_channel(guild.osrs_news_channel_id) if osrs else self.find_text_channel(guild.rs3_news_channel_id)
            if news_channel:
                self.queue_message(QueueMessage(news_channel, embed=embed))

    async def rsnews(self) -> NoReturn:
        '''
        Function to send messages from Runescape news rss feed.
        '''
        await asyncio.sleep(300)
        logging.info('Initializing rs news...')
        rs3_url = 'http://services.runescape.com/m=news/latest_news.rss'
        osrs_url = 'http://services.runescape.com/m=news/latest_news.rss?oldschool=true'
        while True:
            try:
                r: ClientResponse = await self.aiohttp.get(rs3_url)
                async with r:
                    if r.status != 200:
                        await asyncio.sleep(900)
                        continue
                    content: bytes = await r.content.read()
                    rs3_data = io.BytesIO(content)

                r = await self.aiohttp.get(osrs_url)
                async with r:
                    if r.status != 200:
                        await asyncio.sleep(900)
                        continue
                    content = await r.content.read()
                    osrs_data = io.BytesIO(content)

                if not rs3_data or not osrs_data:
                    await asyncio.sleep(900)
                    continue

                rs3_feed: Any = feedparser.parse(rs3_data)
                osrs_feed: Any = feedparser.parse(osrs_data)
                
                news_posts: Sequence[NewsPost]
                async with self.async_session() as session:
                    news_posts = (await session.execute(select(NewsPost))).scalars().all()

                to_send: list[NewsPost] = []

                for post in reversed(rs3_feed.entries):
                    if not any(post.link == news_post.link for news_post in news_posts):
                        time = datetime.strptime(post.published, '%a, %d %b %Y %H:%M:%S %Z')

                        category: Any = None
                        if post.category:
                            category = post.category

                        image_url: Any = None
                        if post.enclosures:
                            enclosure: Any = post.enclosures[0]
                            if any(txt in enclosure.type for txt in ['image', 'jpeg', 'jpg', 'png']):
                                image_url = enclosure.href
                        async with self.async_session() as session:
                            session.add(NewsPost(link=post.link, game='rs3', title=post.title, description=post.description, time=time, category=category, image_url=image_url))
                            await session.commit()
                        to_send.append(news_post)
            
                for post in reversed(osrs_feed.entries):
                    if not any(post.link == news_post.link for news_post in news_posts):
                        time: datetime = datetime.strptime(post.published, '%a, %d %b %Y %H:%M:%S %Z')

                        category: Any = None
                        if post.category:
                            category = post.category

                        image_url: Any = None
                        if post.enclosures:
                            enclosure: Any = post.enclosures[0]
                            if any(txt in enclosure.type for txt in ['image', 'jpeg', 'jpg', 'png']):
                                image_url = enclosure.href

                        async with self.async_session() as session:
                            session.add(NewsPost(link=post.link, game='osrs', title=post.title, description=post.description, time=time, category=category, image_url=image_url))
                            await session.commit()
                        to_send.append(news_post)

                for news_post in to_send:
                    await self.send_news(news_post, news_post.game == 'osrs')

                # sleep for 15 min to avoid rate limits causing 404 errors
                await asyncio.sleep(900)
            except Exception as e:
                error: str = f'Encountered the following error in news loop:\n{type(e).__name__}: {e}'
                logging.critical(error)
                print(error)
                try:
                    config: dict[str, Any] = get_config()
                    log_channel: discord.TextChannel | None = self.find_text_channel(config['testChannel'])
                    if log_channel:
                        self.queue_message(QueueMessage(log_channel, error))
                except:
                    pass
                await asyncio.sleep(900)
    
    async def check_polls(self) -> NoReturn:
        '''
        Function to check if there are any polls that have to be closed.
        '''
        logging.info('Initializing polls...')
        while True:
            async with self.async_session() as session:
                polls: Sequence[Poll] = (await session.execute(select(Poll).where(Poll.end_time <= datetime.now(UTC)))).scalars().all()
                for poll in polls:
                    try:
                        guild: discord.Guild | None = self.get_guild(poll.guild_id)
                        channel: discord.TextChannel | None = self.get_guild_text_channel(guild, poll.channel_id) if guild else None
                        msg: None | discord.Message = None if not channel else await channel.fetch_message(poll.message_id)

                        if not guild or not channel or not msg or not msg.embeds:
                            raise Exception('Guild channel message was not found for poll.')

                        results: dict[str, int] = {str(reaction.emoji): reaction.count - 1 for reaction in msg.reactions}
                        votes: int = sum([reaction.count - 1 for reaction in msg.reactions])
                        
                        max_score: int = max(results.values())
                        winners: list[str] = [r for r in results.keys() if results[r] == max_score]
                        winner: str = ' and '.join(winners)
                        percentage = int((max_score)/max(1,votes)*100)

                        embed: discord.Embed = msg.embeds[0]
                        if len(winners) == 1:
                            embed.add_field(name='Results', value=f'Option {winner} won with {percentage}% of the votes!')
                        else:
                            embed.add_field(name='Results', value=f'It\'s a tie! Options {winner} each have {percentage}% of the votes!')
                        await msg.edit(embed=embed)
                    except:
                        pass
                    await session.delete(poll)
                await session.commit()
            await asyncio.sleep(60)

    async def git_tracking(self) -> NoReturn:
        '''
        Function to check tracked git repositories for new commits.
        '''
        logging.info('Initializing git tracking...')
        config: dict[str, Any] = get_config()
        while True:
            try:
                g: Github = Github(config['github_access_token'])

                async with self.async_session() as session:
                    repositories: Sequence[Repository] = (await session.execute(select(Repository))).scalars().all()
                    to_delete: list[Repository] = []
                    for repository in repositories:
                        guild: discord.Guild | None = self.get_guild(repository.guild_id)
                        channel: discord.TextChannel | None = self.get_guild_text_channel(guild, repository.channel_id) if guild else None
                        git_user: NamedUser | AuthenticatedUser | None = g.get_user(repository.user_name)
                        repos: list[GitRepository] = [r for r in git_user.get_repos() if r.name.upper() == repository.repo_name.upper()] if git_user else []
                        repo: GitRepository | None = repos[0] if repos else None

                        if not guild or not channel or not git_user or not repos or not repo:
                            to_delete.append(repository)
                            continue
                        
                        commits: PaginatedList[Commit] = repo.get_commits()
                        commit_index: int = 0
                        for i, commit in enumerate(commits):
                            if commit.sha == repository.sha:
                                commit_index = i
                                break
                        new_commits: list[Commit] = commits[:commit_index] if commit_index else []
                        
                        for i, commit in enumerate(reversed(new_commits)):
                            repository.sha = commit.sha
                            author_data: Any = commit.raw_data.get('author')
                            date: datetime = datetime.strptime(author_data.date, "%Y-%m-%dT%H:%M:%SZ")
                            
                            embed = discord.Embed(title=f'{repository.user_name}/{repository.repo_name}', colour=discord.Colour.blue(), timestamp=date, description=f'[`{commit.sha[:7]}`]({commit.url}) {commit.raw_data.get("message")}\n{commit.stats.additions} additions, {commit.stats.deletions} deletions', url=repo.url)
                            embed.set_author(name=commit.author.name, url=commit.author.url, icon_url=commit.author.avatar_url)

                            for file in commit.files:
                                embed.add_field(name=file.filename, value=f'{file.additions} additions, {file.deletions} deletions', inline=False)
                            
                            self.queue_message(QueueMessage(channel, None, embed))
                    for repository in to_delete:
                        await session.delete(repository)
                    if to_delete or any(session.is_modified(obj) for obj in repositories):
                        await session.commit()

            except:
                pass
            await asyncio.sleep(60)
    
    async def price_tracking_rs3(self) -> NoReturn:
        '''
        Function to automatically and constantly update item pricing
        '''
        await asyncio.sleep(5)
        print('Starting rs3 price tracking...')
        config: dict[str, Any] = get_config()
        channel: discord.TextChannel = self.get_text_channel(config['testChannel'])
        while True:
            try:
                async with self.async_session() as session:
                    items: Sequence[RS3Item] = (await session.execute(select(RS3Item))).scalars().all()
                    items = sorted(items, key=lambda i: max([int(x) for x in i.graph_data['daily']]))
                    for item in items:
                        graph_url: str = f'http://services.runescape.com/m=itemdb_rs/api/graph/{item.id}.json'

                        graph_data: dict[str, dict[str, str]] = {}

                        exists = True
                        while True:
                            r: ClientResponse = await self.aiohttp.get(graph_url)
                            async with r:
                                if r.status == 404:
                                    logging.critical(f'RS3 404 error for item {item.id}: {item.name}')
                                    self.queue_message(QueueMessage(channel, f'RS3 404 error for item {item.id}: {item.name}'))
                                    exists = False
                                    break
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
                        
                        current: str = prices[len(prices) - 1]
                        yesterday: str = prices[len(prices) - 2]
                        month_ago: str = prices[len(prices) - 31]
                        three_months_ago: str = prices[len(prices) - 91]
                        half_year_ago: str = prices[0]

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

                        await asyncio.sleep(5)
            except OSError as e:
                print(f'Error encountered in rs3 price tracking: {e.__class__.__name__}: {e}')
                logging.critical(f'Error encountered in rs3 price tracking: {e.__class__.__name__}: {e}')
                await asyncio.sleep(60)
            except Exception as e:
                error: str = f'Error encountered in rs3 price tracking: {e.__class__.__name__}: {e}'
                print(error)
                logging.critical(error)
                self.queue_message(QueueMessage(channel, error))
                await asyncio.sleep(600)
    
    async def price_tracking_osrs(self) -> NoReturn:
        '''
        Function to automatically and constantly update item pricing
        '''
        await asyncio.sleep(5)
        print('Starting osrs price tracking...')
        config: dict[str, Any] = get_config()
        channel: discord.TextChannel = self.get_text_channel(config['testChannel'])
        while True:
            try:
                async with self.async_session() as session:
                    items: Sequence[OSRSItem] = (await session.execute(select(OSRSItem))).scalars().all()
                    items = sorted(items, key=lambda i: max([int(x) for x in i.graph_data['daily']]))
                    for item in items:
                        graph_url: str = f'http://services.runescape.com/m=itemdb_oldschool/api/graph/{item.id}.json'

                        graph_data: dict[str, dict[str, str]] = {}

                        exists = True
                        while True:
                            r: ClientResponse = await self.aiohttp.get(graph_url)
                            async with r:
                                if r.status == 404:
                                    msg: str = f'OSRS 404 error for item {item.id}: {item.name}'
                                    logging.critical(msg)
                                    self.queue_message(QueueMessage(channel, msg))
                                    exists = False
                                    break
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
                        
                        current: str = prices[len(prices) - 1]
                        yesterday: str = prices[len(prices) - 2]
                        month_ago: str = prices[len(prices) - 31]
                        three_months_ago: str = prices[len(prices) - 91]
                        half_year_ago: str = prices[0]

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

                        await asyncio.sleep(5)
            except OSError as e:
                print(f'Error encountered in osrs price tracking: {e.__class__.__name__}: {e}')
                logging.critical(f'Error encountered in osrs price tracking: {e.__class__.__name__}: {e}')
                await asyncio.sleep(60)
            except Exception as e:
                error = f'Error encountered in osrs price tracking: {e.__class__.__name__}: {e}'
                print(error)
                logging.critical(error)
                self.queue_message(QueueMessage(channel, error))
                await asyncio.sleep(600)


if __name__ == '__main__':
    logging.basicConfig(filename='data/log.txt', level=logging.CRITICAL)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(run())
