import discord
from discord.ext import tasks
from discord.ext.commands import Cog
from src.bot import Bot
from datetime import datetime, timedelta, UTC
import logging
from typing import Any, NoReturn, Sequence
from sqlalchemy import select
from aiohttp import ClientResponse
import feedparser
import io
from src.message_queue import QueueMessage
from src.database import Guild, Mute, Repository, Notification, Poll, NewsPost, Uptime
from github.Commit import Commit
from github.Repository import Repository as GitRepository
from github.AuthenticatedUser import AuthenticatedUser
from github.NamedUser import NamedUser
from github.PaginatedList import PaginatedList
from src.runescape_utils import prif_districts
from src.discord_utils import get_text_channel, find_text_channel, find_guild_text_channel, get_guild_text_channel

class BackgroundTasks(Cog):
    notification_state_initialized: bool = False

    notified_this_hour_warbands: bool = False
    notified_this_hour_vos: bool = False
    notified_this_hour_cache: bool = False
    notified_this_hour_yews_48: bool = False
    notified_this_hour_yews_140: bool = False
    notified_this_hour_goebies: bool = False
    notified_this_hour_sinkhole: bool = False
    notified_this_hour_wilderness_flash: bool = False
    notified_this_day_merchant: bool = False
    notified_this_day_spotlight: bool = False
    reset: bool = False

    test_notification_channel: discord.TextChannel
    log_channel: discord.TextChannel

    rs3_news_url: str = 'http://services.runescape.com/m=news/latest_news.rss'
    osrs_news_url: str = 'http://services.runescape.com/m=news/latest_news.rss?oldschool=true'
    
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
        self.test_notification_channel = get_text_channel(bot, bot.config['testNotificationChannel'])
        self.log_channel = get_text_channel(bot, bot.config['testChannel'])

    def cog_load(self) -> None:
        '''
        Starts background tasks when loading the cog
        '''
        self.uptime_tracking.start()
        self.notify.start()
        self.custom_notify.start()
        self.unmute.start()
        self.rsnews.start()
        self.check_polls.start()
        self.git_tracking.start()

    def cog_unload(self) -> None:
        '''
        Stops background tasks when unloading the cog
        '''
        self.uptime_tracking.cancel()
        self.notify.cancel()
        self.custom_notify.cancel()
        self.unmute.cancel()
        self.rsnews.cancel()
        self.check_polls.cancel()
        self.git_tracking.cancel()

    @tasks.loop(seconds=10)
    async def uptime_tracking(self) -> None:
        try:
            now: datetime = datetime.now(UTC).replace(microsecond=0)
            today: datetime = now.replace(hour=0, minute=0, second=0)
            
            async with self.bot.async_session() as session:
                latest_event_today: Uptime | None = (await session.execute(select(Uptime).where(Uptime.time >= today).order_by(Uptime.time.desc()))).scalars().first()
                if latest_event_today and latest_event_today.status == 'running':
                    latest_event_today.time = now
                else:
                    session.add(Uptime(time=now, status='running'))
                await session.commit()
        except Exception as e:
            error: str = f'Error encountered in uptime tracking: {e.__class__.__name__}: {e}'
            print(error)
            logging.critical(error)
            if self.log_channel:
                self.bot.queue_message(QueueMessage(self.log_channel, error))
    
    async def initialize_notification_state(self) -> None:
        '''
        Initializes the notification state by reading the message history from the notification channel in the support / test server
        '''
        current_time: datetime = datetime.now(UTC)
        async for m in self.test_notification_channel.history(limit=100):
            if m.created_at.day == current_time.day:
                if 'Merchant' in m.content:
                    self.notified_this_day_merchant = True
                    continue
                if 'spotlight' in m.content:
                    self.notified_this_day_spotlight = True
                    continue
                if m.created_at.hour == current_time.hour:
                    if 'Warbands' in m.content:
                        self.notified_this_hour_warbands = True
                        continue
                    if any(d in m.content for d in prif_districts):
                        if current_time.minute <= 1:
                            self.reset = True
                        self.notified_this_hour_vos = True
                        continue
                    if 'Cache' in m.content:
                        self.notified_this_hour_cache = True
                        continue
                    if 'yew' in m.content:
                        if '48' in m.content:
                            self.notified_this_hour_yews_48 = True
                        elif '140' in m.content:
                            self.notified_this_hour_yews_140 = True
                        continue
                    if 'Goebies' in m.content:
                        self.notified_this_hour_goebies = True
                        continue
                    if 'Sinkhole' in m.content:
                        self.notified_this_hour_sinkhole = True
                        continue
                    if 'wilderness' in m.content.lower() and 'flash' in m.content.lower():
                        self.notified_this_hour_wilderness_flash = True
                        continue
            else:
                break

        self.notification_state_initialized = True

    async def send_notifications(self, message: str, role_dict: dict[str, str] | None = None) -> None:
        '''
        Get coroutines to send notifications to the configured notification channels.

        Args:
            message (str): The notification message.
            role_name (str): The name of the role to mentioned (if found).

        Returns:
            _type_: A list of coroutines which can be awaited to send the notifications.
        '''

        async with self.bot.async_session() as session:
            guilds: Sequence[Guild] = (await session.execute(select(Guild).where(Guild.notification_channel_id.is_not(None)))).scalars().all()
        
        channels: list[discord.TextChannel] = [channel for channel in [find_text_channel(self.bot, guild.notification_channel_id) for guild in guilds] if channel]

        for c in channels:
            msg: str = message
            for role_name, text_to_replace in (role_dict.items() if role_dict else []):
                roles: list[discord.Role] = [r for r in c.guild.roles if role_name.upper() in r.name.upper()]
                role_mention: str = roles[0].mention if roles else ''
                msg = msg.replace(text_to_replace, role_mention)
            self.bot.queue_message(QueueMessage(c, msg))

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

        async with self.bot.async_session() as session:
            if osrs:
                guilds = (await session.execute(select(Guild).where(Guild.osrs_news_channel_id.is_not(None)))).scalars().all()
            else:
                guilds = (await session.execute(select(Guild).where(Guild.rs3_news_channel_id.is_not(None)))).scalars().all()

        for guild in guilds:
            news_channel: discord.TextChannel | None = find_text_channel(self.bot, guild.osrs_news_channel_id) if osrs else find_text_channel(self.bot, guild.rs3_news_channel_id)
            if news_channel:
                self.bot.queue_message(QueueMessage(news_channel, embed=embed))

    @tasks.loop(seconds=15)
    async def notify(self) -> None:
        '''
        Function to send D&D notifications
        Runs every 15 s.
        '''
        if not self.notification_state_initialized:
            await self.initialize_notification_state()
        
        try:
            now: datetime = datetime.now(UTC)

            if not self.notified_this_day_merchant and now.hour <= 2 and self.bot.next_merchant and self.bot.next_merchant > now + timedelta(hours=1):
                msg: str = f'__role_mention__\n**Traveling Merchant** stock {now.strftime("%d %b")}\n{self.bot.merchant}'
                await self.send_notifications(msg, {'MERCHANT': '__role_mention__'})
                self.notified_this_day_merchant = True

            if not self.notified_this_day_spotlight and now.hour <= 1 and self.bot.next_spotlight and self.bot.next_spotlight > now + timedelta(days=2, hours=1):
                msg = f'{self.bot.config["spotlightEmoji"]} **{self.bot.spotlight}** is now the spotlighted minigame. __role_mention__'
                await self.send_notifications(msg, {'SPOTLIGHT': '__role_mention__'})
                self.notified_this_day_spotlight = True

            if not self.notified_this_hour_vos and now.minute <= 1 and self.bot.vos and self.bot.next_vos and self.bot.next_vos > now + timedelta(minutes=1):
                msg = '\n'.join([self.bot.config[f'msg{d}'] + f'__role_{d}__' for d in self.bot.vos['vos']])
                role_dict: dict[str, str] = {d: f'__role_{d}__' for d in self.bot.vos['vos']}
                await self.send_notifications(msg, role_dict)
                self.notified_this_hour_vos = True
                    
            if not self.notified_this_hour_warbands and now.minute >= 45 and now.minute <= 46 and self.bot.next_warband and self.bot.next_warband - now <= timedelta(minutes=15):
                msg = self.bot.config['msgWarbands'] + '__role_mention__'
                await self.send_notifications(msg, {'WARBAND': '__role_mention__'})
                self.notified_this_hour_warbands = True
                        
            if not self.notified_this_hour_cache and now.minute >= 55 and now.minute <= 56:
                msg = self.bot.config['msgCache'] + '__role_mention__'
                await self.send_notifications(msg, {'CACHE': '__role_mention__'})
                self.notified_this_hour_cache = True

            if not self.notified_this_hour_yews_48 and now.hour == 23 and now.minute >= 45 and now.minute <= 46:
                msg = self.bot.config['msgYews48'] + '__role_mention__'
                await self.send_notifications(msg, {'YEW': '__role_mention__'})
                self.notified_this_hour_yews_48 = True

            if not self.notified_this_hour_yews_140 and now.hour == 16 and now.minute >= 45 and now.minute <= 46:
                msg = self.bot.config['msgYews140'] + '__role_mention__'
                await self.send_notifications(msg, {'YEW': '__role_mention__'})
                self.notified_this_hour_yews_140 = True
                
            if not self.notified_this_hour_goebies and now.hour in [11, 23] and now.minute >= 45 and now.minute <= 46:
                msg = self.bot.config['msgGoebies'] + '__role_mention__'
                await self.send_notifications(msg, {'GOEBIE': '__role_mention__'})
                self.notified_this_hour_goebies = True

            if not self.notified_this_hour_sinkhole and now.minute >= 25 and now.minute <= 26:
                msg = self.bot.config['msgSinkhole'] + '__role_mention__'
                await self.send_notifications(msg, {'SINKHOLE': '__role_mention__'})
                self.notified_this_hour_sinkhole = True
            
            if not self.notified_this_hour_wilderness_flash and now.minute >= 55 and now.minute <= 56 and self.bot.wilderness_flash_event:
                msg = f'{self.bot.config["wildernessflasheventsEmoji"]} The next **Wilderness Flash Event** will start in 5 minutes: **{self.bot.wilderness_flash_event["next"]}**. __role_mention__'
                await self.send_notifications(msg, {'WILDERNESSFLASHEVENT': '__role_mention__'})
                self.notified_this_hour_wilderness_flash = True

            if now.minute > 1 and self.reset:
                self.reset = False
            if now.minute == 0 and not self.reset:
                self.notified_this_hour_warbands = False
                self.notified_this_hour_vos = False
                self.notified_this_hour_cache = False
                self.notified_this_hour_yews_48 = False
                self.notified_this_hour_yews_140 = False
                self.notified_this_hour_goebies = False
                self.notified_this_hour_sinkhole = False
                self.notified_this_hour_wilderness_flash = False
                if now.hour == 0:
                    self.notified_this_day_merchant = False
                    self.notified_this_day_spotlight = False
                self.reset = True
        except Exception as e:
            error: str = f'Encountered the following error in notification loop:\n{type(e).__name__}: {e}'
            logging.critical(error)
            print(error)
            if self.log_channel:
                self.bot.queue_message(QueueMessage(self.log_channel, error))

    @tasks.loop(seconds=30)
    async def custom_notify(self) -> NoReturn:
        '''
        Function to send custom notifications
        '''
        try:
            async with self.bot.async_session() as session:
                deleted_from_guild_ids: list[int] = []
                notifications: Sequence[Notification] = (await session.execute(select(Notification).where(Notification.time <= datetime.now(UTC)))).scalars().all()
                for notification in notifications:
                    guild: discord.Guild | None = self.bot.get_guild(notification.guild_id)
                    if not guild or not notification.message:
                        await session.delete(notification)
                        await session.commit()
                        continue
                    channel: discord.TextChannel | None = find_guild_text_channel(guild, notification.channel_id)
                    if not channel:
                        await session.delete(notification)
                        await session.commit()
                        continue
                    self.bot.queue_message(QueueMessage(channel, notification.message))

                    interval = timedelta(seconds = notification.interval)
                    if interval.total_seconds() != 0:
                        while notification.time < datetime.now(UTC):
                            notification.time += interval
                    else:
                        deleted_from_guild_ids.append(notification.guild_id)
                        await session.delete(notification)
                    await session.commit()
                
                for guild_id in deleted_from_guild_ids:
                    guild_notifications: Sequence[Notification] = (await session.execute(select(Notification).where(Notification.guild_id == guild_id))).scalars().all()
                    for i, notification in enumerate(guild_notifications):
                        notification.notification_id = i
                        await session.commit()
                
        except Exception as e:
            error = f'Encountered the following error in custom notification loop:\n{type(e).__name__}: {e}'
            logging.critical(error)
            print(error)
            if self.log_channel:
                self.bot.queue_message(QueueMessage(self.log_channel, error))
    
    @tasks.loop(minutes=1)
    async def unmute(self) -> NoReturn:
        '''
        Function to unmute members when mutes expire
        '''
        to_unmute: list[tuple[discord.Member, discord.Role, discord.Guild]] = []

        async with self.bot.async_session() as session:
            mutes: Sequence[Mute] = (await session.execute(select(Mute).where(Mute.expiration <= datetime.now(UTC)))).scalars().all()
            for mute in mutes:
                await session.delete(mute)
            await session.commit()

        for mute in mutes:
            guild: discord.Guild | None = self.bot.get_guild(mute.guild_id)
            member: discord.Member | None = await guild.fetch_member(mute.user_id) if guild else None
            mute_role: discord.Role | None = discord.utils.find(lambda r: 'MUTE' in r.name.upper(), guild.roles if guild else [])
            
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
                            channel: discord.TextChannel = get_guild_text_channel(guild, channel.id)
                            overwrite = channel.overwrites[member] if member in channel.overwrites else None
                            if overwrite and overwrite.is_empty():
                                await channel.set_permissions(member, overwrite=None)
                        except discord.Forbidden:
                            pass
            except discord.Forbidden:
                continue

    @tasks.loop(minutes=15)
    async def rsnews(self) -> None:
        '''
        Function to send messages from Runescape news rss feed.
        '''
        # Only start once the bot has been running for at least 5 minutes. 
        # This is to avoid exceeding rate limits during frequent successive restarts, e.g. during testing of new features.
        if datetime.now(UTC) - self.bot.start_time < timedelta(minutes=5):
            return
        
        try:
            r: ClientResponse = await self.bot.aiohttp.get(self.rs3_news_url)
            async with r:
                if r.status != 200:
                    return
                content: bytes = await r.content.read()
                rs3_data = io.BytesIO(content)

            r = await self.bot.aiohttp.get(self.osrs_news_url)
            async with r:
                if r.status != 200:
                    return
                content = await r.content.read()
                osrs_data = io.BytesIO(content)

            if not rs3_data or not osrs_data:
                return

            rs3_feed: Any = feedparser.parse(rs3_data)
            osrs_feed: Any = feedparser.parse(osrs_data)
            
            news_posts: Sequence[NewsPost]
            async with self.bot.async_session() as session:
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
                    async with self.bot.async_session() as session:
                        news_post = NewsPost(link=post.link, game='rs3', title=post.title, description=post.description, time=time, category=category, image_url=image_url)
                        session.add(news_post)
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

                    async with self.bot.async_session() as session:
                        news_post = NewsPost(link=post.link, game='osrs', title=post.title, description=post.description, time=time, category=category, image_url=image_url)
                        session.add(news_post)
                        await session.commit()
                    to_send.append(news_post)

            for news_post in to_send:
                await self.send_news(news_post, news_post.game == 'osrs')
                
        except Exception as e:
            error: str = f'Encountered the following error in news loop:\n{type(e).__name__}: {e}'
            logging.critical(error)
            print(error)
            if self.log_channel:
                self.bot.queue_message(QueueMessage(self.log_channel, error))
    
    @tasks.loop(minutes=1)
    async def check_polls(self) -> NoReturn:
        '''
        Function to check if there are any polls that have to be closed.
        '''
        async with self.bot.async_session() as session:
            polls: Sequence[Poll] = (await session.execute(select(Poll).where(Poll.end_time <= datetime.now(UTC)))).scalars().all()
            for poll in polls:
                await session.delete(poll)
            await session.commit()

        for poll in polls:
            try:
                guild: discord.Guild | None = self.bot.get_guild(poll.guild_id)
                channel: discord.TextChannel | None = get_guild_text_channel(guild, poll.channel_id) if guild else None
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

    @tasks.loop(minutes=1)
    async def git_tracking(self) -> NoReturn:
        '''
        Function to check tracked git repositories for new commits.
        '''
        try:
            async with self.bot.async_session() as session:
                repositories: Sequence[Repository] = (await session.execute(select(Repository))).scalars().all()

            to_delete: list[Repository] = []
            modified: list[Repository] = []

            for repository in repositories:
                guild: discord.Guild | None = self.bot.get_guild(repository.guild_id)
                git_user: NamedUser | AuthenticatedUser | None = self.bot.github.get_user(repository.user_name)
                repos: list[GitRepository] = [r for r in git_user.get_repos() if r.name.upper() == repository.repo_name.upper()] if git_user else []
                repo: GitRepository | None = repos[0] if repos else None

                if not guild or not git_user or not repos or not repo:
                    to_delete.append(repository)
                    continue

                channel: discord.TextChannel = get_guild_text_channel(guild, repository.channel_id)
                
                commits: PaginatedList[Commit] = repo.get_commits()
                commit_index: int = 0
                for i, commit in enumerate(commits):
                    if commit.sha == repository.sha:
                        commit_index = i
                        break
                new_commits: list[Commit] = [c for i, c in enumerate(commits) if i < commit_index]
                
                for i, commit in enumerate(reversed(new_commits)):
                    repository.sha = commit.sha
                    modified.append(repository)
                    embed = discord.Embed(title=f'{repository.user_name}/{repository.repo_name}', colour=discord.Colour.blue(), timestamp=commit.commit.author.date, description=f'[`{commit.sha[:7]}`]({commit.url}) {commit.commit.message}\n{commit.stats.additions} additions, {commit.stats.deletions} deletions', url=repo.url)
                    embed.set_author(name=commit.author.name, url=commit.author.url, icon_url=commit.author.avatar_url)

                    for file in commit.files:
                        embed.add_field(name=file.filename, value=f'{file.additions} additions, {file.deletions} deletions', inline=False)
                    
                    self.bot.queue_message(QueueMessage(channel, None, embed))

            if to_delete or modified:
                async with self.bot.async_session() as session:
                    # Since the original db session has been disposed, any repositories to be deleted or modified
                    # must first be re-retrieved from the database using a new session so that they can be modified
                    for r in to_delete:
                        db_repository: Repository = (await session.execute(select(Repository).where(Repository.guild_id == r.guild_id, Repository.user_name == r.user_name, Repository.repo_name == r.repo_name))).scalar_one()
                        await session.delete(db_repository)
                    for r in modified:
                        db_repository: Repository = (await session.execute(select(Repository).where(Repository.guild_id == r.guild_id, Repository.user_name == r.user_name, Repository.repo_name == r.repo_name))).scalar_one()
                        db_repository.sha = r.sha
                    await session.commit()

        except:
            pass

async def setup(bot: Bot) -> None:
    await bot.add_cog(BackgroundTasks(bot))