from typing import Any, Iterator, Sequence
from aiohttp import ClientResponse
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Cog
from imageio.core.util import Array
from matplotlib.axis import Tick
from matplotlib.text import Text
from sqlalchemy import select
from src.bot import Bot
from src.database import User, NewsPost, RS3Item, OSRSItem
import re
from datetime import datetime, timedelta, UTC
import matplotlib.pyplot as plt
from matplotlib.dates import date2num
import matplotlib.dates as mdates
from matplotlib.dates import DateFormatter
import math
from bs4 import BeautifulSoup, NavigableString, Tag
from src.number_utils import is_int, is_float, format_float
from src.runescape_utils import xp_to_level, level_to_xp, combat_level, osrs_combat_level
from src.runescape_utils import skills_07, osrs_skill_emojis, skills_rs3, rs3_skill_emojis
from src.runescape_utils import skill_indices, skill_indices_rs3, cb_indices_rs3, cb_indices_osrs
from src.runescape_utils import araxxor, vorago, rots, runescape_api_cooldown_key
from src.graphics import draw_num, draw_outline_osrs, draw_outline_rs3
import io
import imageio
import copy
import numpy as np
import random
from praw.reddit import Subreddit, Submission
from src.graphics import yellow, orange, white, green, red
from imageio.core.format import Format

class Runescape(Cog):
    vis_wax_embed = discord.Embed(title='Vis wax combination', colour=0x00b2ff, timestamp=datetime.now(UTC), description='Today\'s vis wax combo has not been released yet.')
    vis_wax_combo: list = []
    vis_wax_released = False
    vis_wax_check_frequency: int = 60*15 # seconds
    vis_time = 0
    stats_interface_osrs: Array
    stats_interface_rs3: Array

    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
        self.stats_interface_osrs: Array = imageio.imread('assets/stats_interface_empty_osrs.png')
        self.stats_interface_rs3: Array = imageio.imread('assets/stats_interface_empty_rs3.png')

    async def cog_load(self) -> None:
        self.vis_wax.start()

    async def cog_unload(self) -> None:
        self.vis_wax.cancel()
    
    @tasks.loop(seconds=60)
    async def vis_wax(self) -> None:
        '''
        Loop to track location update activity
        '''
        self.vis_time += 60

        if self.vis_wax_released:
            if self.vis_time > self.vis_wax_check_frequency:
                self.vis_time = 0
            else:
                return

        now: datetime = datetime.now(UTC)
        colour = 0x00b2ff

        reset: datetime = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        if now < reset + timedelta(seconds=self.vis_wax_check_frequency):
            self.vis_wax_released = False
            self.vis_wax_embed = discord.Embed(title='Vis wax combination', colour=colour, timestamp=now, description='Today\'s vis wax combo has not been released yet.')

        r: ClientResponse = await self.bot.aiohttp.get('https://warbandtracker.com/goldberg/index.php')
        async with r:
            data: str = await r.text()

            bs = BeautifulSoup(data, "html.parser")
            table_body: Tag | NavigableString | None = bs.find('table')
            rows: list[Any] = table_body.find_all('tr') if isinstance(table_body, Tag) else []
            columns: list[Any] = []
            for row in rows:
                cols: list[Any] = row.find_all('td')
                cols = [x.text.strip() for x in cols]
                columns.append(cols)
            
            first_rune: str = columns[1][0]
            second_runes_known: list[str] = columns[3]

            first_rune, acc_0 = first_rune.split('Reported by ')
            acc_0 = float(acc_0[:len(acc_0)-2])

            second_runes: list[Any] = []
            for rune in second_runes_known:
                rune, acc = rune.split('Reported by ')
                second_runes.append([rune, float(acc[:len(acc)-2])])
            
            emoji_server: discord.Guild | None = self.bot.get_guild(int(self.bot.config['emoji_server']))
            if not emoji_server:
                return
            second_runes_temp: list = []
            for emoji in emoji_server.emojis:
                if emoji.name.upper() == first_rune.upper().replace(' ', '_'):
                    first_rune = f'{emoji} {first_rune}'
            for tmp in second_runes:
                second_rune: str = tmp[0]
                for emoji in emoji_server.emojis:
                    if emoji.name.upper() == second_rune.upper().replace(' ', '_'):
                        second_rune = f'{emoji} {second_rune}'
                        second_runes_temp.append([second_rune, tmp[1]])
            second_runes = second_runes_temp
            
            if self.vis_wax_released:
                self.vis_wax_combo = [[first_rune, acc_0], second_runes]
            else:
                if self.vis_wax_combo == [[first_rune, acc_0], second_runes]:
                    return
                else:
                    self.vis_wax_combo = [[first_rune, acc_0], second_runes]
                    self.vis_wax_released = True
            
            self.vis_wax_embed = discord.Embed(title='Vis wax combination', colour=colour, timestamp=now)
            self.vis_wax_embed.add_field(name='First rune', value = f'{first_rune} ({acc_0}%)')

            val: str = '\n'.join([f'{rune} ({acc}%)' for rune, acc in second_runes])
            self.vis_wax_embed.add_field(name='Second rune', value=val)

            self.vis_wax_embed.set_footer(text='Powered by Warband Tracker')

    @commands.command(pass_context=True, aliases=['rsn'])
    async def setrsn(self, ctx: commands.Context, *, rsn: str | None) -> None:
        '''
        Sets your Runescape 3 RSN.
        '''
        self.bot.increment_command_counter()

        if rsn and len(rsn) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{rsn}`.')
        elif rsn and re.match(r'^[A-z0-9 -]+$', rsn) is None:
            raise commands.CommandError(message=f'Invalid argument: `{rsn}`.')

        async with self.bot.get_session() as session:
            user: User | None = (await session.execute(select(User).where(User.id == ctx.author.id))).scalar_one_or_none()

            if not user and not rsn:
                raise commands.CommandError(message=f'Required argument missing: `RSN`.')
            
            if user:
                user.rsn = rsn
            
            await session.commit()
        
        if rsn:
            await ctx.send(f'{ctx.author.mention} Your RSN has been set to **{rsn}**.')
        else:
            await ctx.send(f'{ctx.author.mention} Your RSN has been removed.')

    @commands.command(pass_context=True, aliases=['07rsn'])
    async def set07rsn(self, ctx: commands.Context, *, rsn: str | None) -> None:
        '''
        Sets your Old School Runescape RSN.
        '''
        self.bot.increment_command_counter()

        if rsn and len(rsn) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{rsn}`.')
        elif rsn and re.match(r'^[A-z0-9 -]+$', rsn) is None:
            raise commands.CommandError(message=f'Invalid argument: `{rsn}`.')

        async with self.bot.get_session() as session:
            user: User | None = (await session.execute(select(User).where(User.id == ctx.author.id))).scalar_one_or_none()

            if not user and not rsn:
                raise commands.CommandError(message=f'Required argument missing: `RSN`.')
            
            if user:
                user.osrs_rsn = rsn
            
            await session.commit()
        
        if rsn:
            await ctx.send(f'{ctx.author.mention} Your Old School RSN has been set to **{rsn}**.')
        else:
            await ctx.send(f'{ctx.author.mention} Your Old School RSN has been removed.')

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def alog(self, ctx: commands.Context, *, username: str | None) -> None:
        '''
        Get the last 20 activities on a player's adventurer's log.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not username:
            async with self.bot.get_session() as session:
                user: User | None = (await session.execute(select(User).where(User.id == ctx.author.id))).scalar_one_or_none()
            if user:
                username = user.rsn
            if not username:
                raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your username using the `setrsn` command.')

        if len(username) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{username}`.')
        if re.match(r'^[A-z0-9 -]+$', username) is None:
            raise commands.CommandError(message=f'Invalid argument: `{username}`.')

        url: str = f'https://apps.runescape.com/runemetrics/profile/profile?user={username}&activities=20'.replace(' ', '%20')

        r: ClientResponse = await self.bot.aiohttp.get(url, headers={ 'User-agent': self.bot.config['wiki_user_agent'] })
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving data, please try again in a minute.')
            data: dict = await r.json()

        if 'error' in data:
            if data['error'] == 'NO_PROFILE':
                raise commands.CommandError(message=f'Could not find adventurer\'s log for: `{username}`.')
            elif data['error'] == 'PROFILE_PRIVATE':
                raise commands.CommandError(message=f'Error: `{username}`\'s adventurer\'s log is set to private.')

        activities: list[dict[str, Any]] = data['activities']

        txt: str = ''
        for activity in activities:
            txt += f'[{activity["date"]}] {activity["text"]}\n'
        txt = txt.strip()
        txt = f'```{txt}```'

        embed = discord.Embed(title=f'{username}\'s Adventurer\'s log', description=txt, colour=0x00b2ff, timestamp=datetime.now(UTC), url=f'https://apps.runescape.com/runemetrics/app/overview/player/{username.replace(" ", "%20")}')
        embed.set_thumbnail(url=f'https://services.runescape.com/m=avatar-rs/{username.replace(" ", "%20")}/chat.png')

        await ctx.send(embed=embed)

    @commands.command(name='07reddit', pass_context=True, aliases=['osrsreddit'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _07reddit(self, ctx: commands.Context) -> None:
        '''
        Get top 5 hot posts from r/2007scape.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        subreddit: Subreddit = self.bot.reddit.subreddit('2007scape')
        submissions: Iterator[Submission] = subreddit.hot(limit=5)

        colour = 0x00b2ff
        timestamp: datetime = datetime.now(UTC)
        embed = discord.Embed(title=f'/r/2007scape', colour=colour, timestamp=timestamp)

        for s in submissions:
            embed.add_field(name=s.title, value=f'https://www.reddit.com{s.permalink}', inline=False)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rsreddit', 'rs3reddit'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def reddit(self, ctx: commands.Context) -> None:
        '''
        Get top 5 hot posts from r/runescape.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        subreddit: Subreddit = self.bot.reddit.subreddit('runescape')
        submissions: Iterator[Submission] = subreddit.hot(limit=5)

        colour = 0x00b2ff
        timestamp: datetime = datetime.now(UTC)
        embed = discord.Embed(title=f'/r/runescape', colour=colour, timestamp=timestamp)

        for s in submissions:
            embed.add_field(name=s.title, value=f'https://www.reddit.com{s.permalink}', inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='07rsw', pass_context=True, aliases=['07wiki', 'osrswiki'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _07rsw(self, ctx: commands.Context, *, query: str) -> None:
        '''
        Get top 5 results for a search on OSRS Wiki.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        query = query.replace(' ', '+')

        if not query:
            raise commands.CommandError(message=f'Required argument missing: `query`.')

        url: str = f'https://oldschool.runescape.wiki/api.php?action=opensearch&format=json&search={query}'

        r: ClientResponse = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving data, please try again in a minute.')
            data: list = await r.json()

        items: list[str] = data[1]
        urls: list[str] = data[3]

        colour = 0x00b2ff
        timestamp = datetime.now(UTC)
        embed = discord.Embed(title=f'__Old School RuneScape Wiki__', colour=colour, timestamp=timestamp, url='https://oldschool.runescape.wiki/')
        embed.set_thumbnail(url='https://oldschool.runescape.wiki/images/b/bc/Wiki.png')

        if len(items) > 5:
            items = items[:5]
        elif not items:
            raise commands.CommandError(message=f'Error: no pages matching `{query}`.')

        for i, item in enumerate(items):
            embed.add_field(name=item, value=urls[i], inline=False)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rswiki', 'wiki', 'rs3wiki'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def rsw(self, ctx: commands.Context, *, query: str) -> None:
        '''
        Get top 5 results for a search on RS Wiki.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        query = query.replace(' ', '+')

        if not query:
            raise commands.CommandError(message=f'Required argument missing: `query`.')

        url: str = f'https://runescape.wiki/api.php?action=opensearch&format=json&search={query}'

        r: ClientResponse = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving data, please try again in a minute.')
            data: list = await r.json()

        items: list[str] = data[1]
        urls: list[str] = data[3]

        timestamp: datetime = datetime.now(UTC)
        embed = discord.Embed(title=f'__RuneScape Wiki__', colour=0x00b2ff, timestamp=timestamp, url='https://runescape.wiki/')
        embed.set_thumbnail(url='https://runescape.wiki/images/b/bc/Wiki.png')

        if len(items) > 5:
            items = items[:5]
        elif not items:
            raise commands.CommandError(message=f'Error: could not find a page matching `{query}`.')

        for i, item in enumerate(items):
            embed.add_field(name=item, value=urls[i], inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='07news', pass_context=True, aliases=['osrsnews'])
    async def _07news(self, ctx: commands.Context) -> None:
        '''
        Get 5 latest OSRS news posts.
        '''
        self.bot.increment_command_counter()

        async with self.bot.get_session() as session:
            news_posts: Sequence[NewsPost] = (await session.execute(select(NewsPost).where(NewsPost.game == 'osrs').order_by(NewsPost.time.desc()).fetch(5))).scalars().all()

        embed = discord.Embed(title=f'Old School RuneScape News')

        for post in news_posts:
            embed.add_field(name=post.title, value=post.link + '\n' + post.description, inline=False)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rsnews', 'rs3news'])
    async def news(self, ctx: commands.Context) -> None:
        '''
        Get 5 latest RS news posts.
        '''
        self.bot.increment_command_counter()

        async with self.bot.get_session() as session:
            news_posts: Sequence[NewsPost] = (await session.execute(select(NewsPost).where(NewsPost.game == 'rs3').order_by(NewsPost.time.desc()).fetch(5))).scalars().all()

        embed = discord.Embed(title=f'RuneScape News')

        for post in news_posts:
            embed.add_field(name=post.title, value=post.link + '\n' + post.description, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='07price', pass_context=True, aliases=['osrsprice'])
    async def _07price(self, ctx: commands.Context, days_or_item: str = '30', *, item_name: str | None) -> None:
        '''
        Get the OSRS GE price for an item.
        Argument "days" is optional, default is 30.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if is_int(days_or_item):
            days: int = int(days_or_item)
            if days < 1 or days > 180:
                await ctx.send('Graph period must be between 1 and 180 days. Defaulted to 30.')
                days = 30
        else:
            item_name = days_or_item + (' ' + item_name if item_name else '')
            days = 30

        if not item_name:
            raise commands.CommandError(message=f'Required argument missing: `item_name`.')
        if len(item_name) < 2:
            raise commands.CommandError(message=f'Invalid argument: `item_name`. Length must be at least 2 characters.')
        
        async with self.bot.get_session() as session:
            items: Sequence[OSRSItem] = (await session.execute(select(OSRSItem).where(OSRSItem.name.ilike(f'%{item_name}%')))).scalars().all()
        if not items:
            raise commands.CommandError(message=f'Could not find item: `{item_name}`.')
        items = sorted(items, key=lambda i: len(i.name))
        item: OSRSItem = items[0]

        item_name = item.name
        price: str = f'{int(item.current.replace(' ', '')):,}'
        link: str = f'http://services.runescape.com/m=itemdb_oldschool/viewitem?obj={item.id}'
        today: str = f'{int(item.today.replace(' ', '')):,}'
        if not today.startswith('-') and not today.startswith('+'):
            today = '+' + today
        day30: str = item.day30
        if not day30.startswith('-') and not day30.startswith('+'):
            day30 = '+' + day30
        day90: str = item.day90
        if not day90.startswith('-') and not day90.startswith('+'):
            day90 = '+' + day90
        day180: str = item.day180
        if not day180.startswith('-') and not day180.startswith('+'):
            day180 = '+' + day180

        timestamp: datetime = datetime.now(UTC)
        embed = discord.Embed(title=item_name, colour=0x00b2ff, timestamp=timestamp, url=link, description=item.description)
        embed.set_thumbnail(url=item.icon_url)

        embed.add_field(name='Price', value=price, inline=False)
        change: str = ''
        if today != '0':
            change = f'**Today**: {today}\n'
        change += f'**30 days**: {day30}\n'
        change += f'**90 days**: {day90}\n'
        change += f'**180 days**: {day180}'
        embed.add_field(name='Change', value=change, inline=False)

        daily: dict = item.graph_data['daily']

        timestamps: list[int] = []
        prices: list[int] = []

        for ms, price in daily.items():
            timestamps.append(round(int(ms) / 1000))
            prices.append(int(price))

        times: list[datetime] = []

        last: int = timestamps[len(timestamps)-1]
        remove: list[int] = []
        for i, time in enumerate(timestamps):
            if time >= last - 86400 * days:
                date: datetime = timestamp - timedelta(seconds=last-time)
                times.append(date)
            else:
                remove.append(i)
        remove.sort(reverse=True)
        for i in remove:
            del prices[i]

        if days <= 60:
            loc = mdates.WeekdayLocator()
        else:
            loc = mdates.MonthLocator()

        formatter = DateFormatter('%d %b')

        plt.style.use('dark_background')

        fig, ax = plt.subplots()

        dates: np.ndarray = date2num(times)
        plt.plot_date(dates, prices, color='#47a0ff', linestyle='-', ydate=False, xdate=True)

        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(formatter)

        ax.yaxis.grid()

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)

        locs: tuple[list[Tick] | np.ndarray, list[Text]] = plt.yticks()
        ylabels: list[str] = []
        for l in locs[1]:
            lab: str = str(int(l.get_position()[1])).replace('000000000', '000M').replace('00000000', '00M').replace('0000000', '0M').replace('000000', 'M').replace('00000', '00K').replace('0000', '0K').replace('000', 'K')
            if not ('K' in lab or 'M' in lab):
                lab = "{:,}".format(int(lab))
            ylabels.append(lab)
        plt.yticks(locs[0], ylabels) # type: ignore

        image = io.BytesIO()
        plt.savefig(image, transparent=True)
        plt.close(fig)
        image.seek(0)
        
        file = discord.File(image, filename='graph.png')
        embed.set_image(url=f'attachment://graph.png')

        await ctx.send(file=file, embed=embed)
    
    @commands.command(pass_context=True, aliases=['rsprice', 'rs3price'])
    async def price(self, ctx: commands.Context, days_or_item: str = '30', *, item_name: str | None) -> None:
        '''
        Get the RS3 GE price for an item.
        Argument "days" is optional, default is 30.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if is_int(days_or_item):
            days: int = int(days_or_item)
            if days < 1 or days > 180:
                await ctx.send('Graph period must be between 1 and 180 days. Defaulted to 30.')
                days = 30
        else:
            item_name = days_or_item + (' ' + item_name if item_name else '')
            days = 30

        if not item_name:
            raise commands.CommandError(message=f'Required argument missing: `item_name`.')
        if len(item_name) < 2:
            raise commands.CommandError(message=f'Invalid argument: `item_name`. Length must be at least 2 characters.')

        async with self.bot.get_session() as session:
            items: Sequence[RS3Item] = (await session.execute(select(RS3Item).where(RS3Item.name.ilike(f'%{item_name}%')))).scalars().all()
        if not items:
            raise commands.CommandError(message=f'Could not find item: `{item_name}`.')
        items = sorted(items, key=lambda i: len(i.name))
        item: RS3Item = items[0]

        item_name = item.name
        price: str = f'{int(item.current.replace(' ', '')):,}'
        link: str = f'http://services.runescape.com/m=itemdb_rs/viewitem?obj={item.id}'
        today: str = f'{int(item.today.replace(' ', '')):,}'
        if not today.startswith('-') and not today.startswith('+'):
            today = '+' + today
        day30: str = item.day30
        if not day30.startswith('-') and not day30.startswith('+'):
            day30 = '+' + day30
        day90: str = item.day90
        if not day90.startswith('-') and not day90.startswith('+'):
            day90 = '+' + day90
        day180: str = item.day180
        if not day180.startswith('-') and not day180.startswith('+'):
            day180 = '+' + day180

        timestamp: datetime = datetime.now(UTC)
        embed = discord.Embed(title=item_name, colour=0x00b2ff, timestamp=timestamp, url=link, description=item.description)
        embed.set_thumbnail(url=item.icon_url)

        embed.add_field(name='Price', value=price, inline=False)
        change: str = ''
        if today != '0':
            change = f'**Today**: {today}\n'
        change += f'**30 days**: {day30}\n'
        change += f'**90 days**: {day90}\n'
        change += f'**180 days**: {day180}'
        embed.add_field(name='Change', value=change, inline=False)

        daily: dict = item.graph_data['daily']

        timestamps: list[int] = []
        prices: list[int] = []

        for ms, price in daily.items():
            timestamps.append(round(int(ms) / 1000))
            prices.append(int(price))

        times: list[datetime] = []
        last: int = timestamps[len(timestamps)-1]
        remove: list[int] = []
        for i, time in enumerate(timestamps):
            if time >= last - 86400 * days:
                date: datetime = timestamp - timedelta(seconds=last-time)
                times.append(date)
            else:
                remove.append(i)
        remove.sort(reverse=True)
        for i in remove:
            del prices[i]

        if days <= 60:
            loc = mdates.WeekdayLocator()
        else:
            loc = mdates.MonthLocator()

        formatter = DateFormatter('%d %b')

        plt.style.use('dark_background')

        fig, ax = plt.subplots()

        dates: np.ndarray = date2num(times)
        plt.plot_date(dates, prices, color='#47a0ff', linestyle='-', ydate=False, xdate=True)

        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(formatter)

        ax.yaxis.grid()

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)

        locs: tuple[list[Tick] | np.ndarray, list[Text]] = plt.yticks()
        ylabels: list[str] = []
        for l in locs[1]:
            lab: str = str(int(l.get_position()[1])).replace('000000000', '000M').replace('00000000', '00M').replace('0000000', '0M').replace('000000', 'M').replace('00000', '00K').replace('0000', '0K').replace('000', 'K')
            if not ('K' in lab or 'M' in lab):
                lab = "{:,}".format(int(lab))
            ylabels.append(lab)
        plt.yticks(locs[0], ylabels) # type: ignore

        image = io.BytesIO()
        plt.savefig(image, transparent=True)
        plt.close(fig)
        image.seek(0)
        
        file = discord.File(image, filename='graph.png')
        embed.set_image(url=f'attachment://graph.png')

        await ctx.send(file=file, embed=embed)
    
    @commands.command(name='07stats', pass_context=True, aliases=['osrsstats'])
    @commands.cooldown(1, 5, runescape_api_cooldown_key)
    async def _07stats(self, ctx: commands.Context, *, username: discord.User | str | None) -> None:
        '''
        Get OSRS hiscores info by username.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name: str | None = None
        disc_user: discord.User | None = username if isinstance(username, discord.User) else None
        if not disc_user and not username:
            disc_user = ctx.author if isinstance(ctx.author, discord.User) else ctx.author._user
        if disc_user:
            async with self.bot.get_session() as session:
                user: User | None = (await session.execute(select(User).where(User.id == disc_user.id))).scalar_one_or_none()
            name = user.osrs_rsn if user and user.osrs_rsn else disc_user.display_name
        if not name:
            name = username if isinstance(username, str) else None
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your Old School username using the `set07rsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url: str = f'http://services.runescape.com/m=hiscore_oldschool/index_lite.ws?player={name}'.replace(' ', '%20')

        r: ClientResponse = await self.bot.aiohttp.get(url, headers={ 'User-agent': self.bot.config['wiki_user_agent'] })
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
            data: str = await r.text()

        lines: list[str] = data.split('\n')
        try:
            lines = lines[:len(skills_07)]
        except:
            raise commands.CommandError(message=f'Error accessing hiscores, please try again later.')

        levels: list[int] = []

        for i, _ in enumerate(lines):
            levels.append(int(lines[i].split(',')[1]))

        stats_interface: Array = copy.deepcopy(self.stats_interface_osrs)
            
        draw_num(stats_interface, levels[0], 175, 257, yellow, True)

        for i, index in enumerate(skill_indices):
            level: int = levels[1:][index]
            if index == 3:
                level = max(int(level), 10)

            x: int = 52 + 63 * (i % 3)
            y: int = 21 + 32 * (i // 3)

            draw_num(stats_interface, level, x, y, yellow, True)

            x += 13
            y += 13

            draw_num(stats_interface, level, x, y, yellow, True)

        stats_image = io.BytesIO()
        format: Format = 'PNG-PIL' # type: ignore
        imageio.imwrite(stats_image, stats_interface, format=format)
        stats_image.seek(0)

        with open('assets/osrs.png', 'rb') as f:
            osrs_icon_image = io.BytesIO(f.read())
        
        stats_file = discord.File(stats_image, filename='07stats.png')
        osrs_icon_file = discord.File(osrs_icon_image, filename='osrs.png')

        hiscore_page_url: str = f'https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={name}'.replace(' ', '+')
        timestamp: datetime = datetime.now(UTC)
        embed = discord.Embed(title=name, colour=0x00b2ff, timestamp=timestamp, url=hiscore_page_url)
        embed.set_author(name='Old School RuneScape HiScores', url='https://secure.runescape.com/m=hiscore_oldschool/overall', icon_url='attachment://osrs.png')
        # player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://07stats.png')

        await ctx.send(files=[stats_file, osrs_icon_file], embed=embed)
    
    @commands.command(name='07compare')
    @commands.cooldown(1, 5, runescape_api_cooldown_key)
    async def _07compare(self, ctx: commands.Context, name_1: discord.User | str = "", name_2: discord.User | str | None = "") -> None:
        '''
        Compare two players on OSRS HiScores
        If either of the user names contain spaces, make sure you surround them by quotation marks.
        E.g.: `-07compare "Player 1" "Player 2"`
        If you have set your username via `-set07rsn`, you can give only 1 username to compare a player to yourself.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        user_1: User | None = None
        user_2: User | None = None
        async with self.bot.get_session() as session:
            if isinstance(name_1, discord.User):
                user_1 = (await session.execute(select(User).where(User.id == name_1.id))).scalar_one_or_none()
            if isinstance(name_2, discord.User):
                user_2 = (await session.execute(select(User).where(User.id == name_2.id))).scalar_one_or_none()

            username_1: str = user_1.osrs_rsn if user_1 and user_1.osrs_rsn else (name_1.display_name if isinstance(name_1, discord.User) else name_1)
            username_2: str | None = user_2.osrs_rsn if user_2 and user_2.osrs_rsn else (name_2.display_name if isinstance(name_2, discord.User) else name_2)

            if not username_2:
                user_2 = (await session.execute(select(User).where(User.id == ctx.author.id))).scalar_one_or_none()
                if user_2 and user_2.osrs_rsn:
                    username_2 = username_1
                    username_1 = user_2.osrs_rsn
        
        if not username_2:
            raise commands.CommandError(message=f'Required argument missing: `RSN_2`. You can set your Old School username using the `set07rsn` command, or add a second username as argument.')
        
        for name in [username_1, username_2]:
            if len(name) > 12:
                raise commands.CommandError(message=f'Invalid argument: `{name}`.')
            if re.match(r'^[A-z0-9 -]+$', name) is None:
                raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        
        level_list: list[list[str]] = []
        
        for name in [username_1, username_2]:
            url: str = f'http://services.runescape.com/m=hiscore_oldschool/index_lite.ws?player={name}'.replace(' ', '%20')

            r: ClientResponse = await self.bot.aiohttp.get(url, headers={ 'User-agent': self.bot.config['wiki_user_agent'] })
            async with r:
                if r.status != 200:
                    raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
                data: str = await r.text()

            lines: list[str] = data.split('\n')
            lines = lines[:len(skills_07)]

            levels: list[str] = []

            for line in lines:
                levels.append(line.split(',')[1])
            
            level_list.append(levels)
        
        stats_interface_1: Array = copy.deepcopy(self.stats_interface_osrs)
        stats_interface_2: Array = copy.deepcopy(self.stats_interface_osrs)
        interfaces: tuple[Array, Array] = (stats_interface_1, stats_interface_2)

        for i, levels in enumerate(level_list):
            stats_interface: Array = interfaces[i]
            draw_num(stats_interface, int(levels[0]), 175, 257, yellow, True)

            for i, index in enumerate(skill_indices):
                level = int(levels[1:][index])
                if index == 3:
                    level: int = max(level, 10)

                x: int = 52 + 63 * (i % 3)
                y: int = 21 + 32 * (i // 3)

                draw_num(stats_interface, level, x, y, yellow, True)
                draw_num(stats_interface, level, x+13, y+13, yellow, True)
        
        if int(level_list[0][0]) > int(level_list[1][0]):
            draw_outline_osrs(stats_interface_1, 8+63*2, 8+32*7, green)
            draw_outline_osrs(stats_interface_2, 8+63*2, 8+32*7, red)
        elif int(level_list[0][0]) < int(level_list[1][0]):
            draw_outline_osrs(stats_interface_1, 8+63*2, 8+32*7, red)
            draw_outline_osrs(stats_interface_2, 8+63*2, 8+32*7, green)
        
        for i, index in enumerate(skill_indices):
            level_1 = int(level_list[0][1:][index])
            level_2 = int(level_list[1][1:][index])

            x = 8 + 63 * (i % 3)
            y = 8 + 32 * (i // 3)

            if level_1 > level_2:
                draw_outline_osrs(stats_interface_1, x, y, green)
                draw_outline_osrs(stats_interface_2, x, y, red)
            elif level_2 > level_1:
                draw_outline_osrs(stats_interface_1, x, y, red)
                draw_outline_osrs(stats_interface_2, x, y, green)
        
        compare_image: np.ndarray = np.hstack((stats_interface_1, stats_interface_2))
        compare_image_bytes = io.BytesIO()
        format: Format = 'PNG-PIL' # type: ignore
        imageio.imwrite(compare_image_bytes, compare_image, format=format)
        compare_image_bytes.seek(0)

        with open('assets/osrs.png', 'rb') as f:
            osrs_icon = io.BytesIO(f.read())
        
        compare_image_file = discord.File(compare_image_bytes, filename='07compare.png')
        osrs_icon = discord.File(osrs_icon, filename='osrs.png')

        hiscore_page_url: str = f'https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={username_1}'.replace(' ', '+')
        embed = discord.Embed(title=f'{username_1}, {username_2}', colour=0x00b2ff, timestamp=datetime.now(UTC), url=hiscore_page_url)
        embed.set_author(name='Old School RuneScape HiScores', url='https://secure.runescape.com/m=hiscore_oldschool/overall', icon_url='attachment://osrs.png')
        # player_image_url: str = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://07compare.png')

        await ctx.send(files=[compare_image_file, osrs_icon], embed=embed)

    @commands.command(name='07gainz', pass_context=True, aliases=['07gains', 'osrsgainz', 'osrsgains'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _07gainz(self, ctx: commands.Context, *, username: discord.User | str | None) -> None:
        '''
        Get OSRS gains by username.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name: str | None = None
        disc_user: discord.User | None = username if isinstance(username, discord.User) else None
        if not disc_user and not username:
            disc_user = ctx.author if isinstance(ctx.author, discord.User) else ctx.author._user
        if disc_user:
            async with self.bot.get_session() as session:
                user: User | None = (await session.execute(select(User).where(User.id == disc_user.id))).scalar_one_or_none()
            name = user.osrs_rsn if user and user.osrs_rsn else disc_user.display_name
        if not name:
            name = username if isinstance(username, str) else None
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your Old School username using the `set07rsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url_day: str = f'https://api.wiseoldman.net/v2/players/{name}/gained?period=day'.replace(' ', '-')
        url_week: str = f'https://api.wiseoldman.net/v2/players/{name}/gained?period=week'.replace(' ', '-')

        r: ClientResponse = await self.bot.aiohttp.get(url_day, headers={'x-user-agent': self.bot.config['wom_user_agent'], 'x-api-key': self.bot.config['wom_api_key']})
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not fetch xp gains for: `{name}`.')
            daily_data = await r.json()

        r = await self.bot.aiohttp.get(url_week, headers={'x-user-agent': self.bot.config['wom_user_agent'], 'x-api-key': self.bot.config['wom_api_key']})
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not fetch xp gains for: `{name}`.')
            weekly_data = await r.json()

        skills: list[dict[str, str]] = []
        for i, (skill_name, skill_data) in enumerate(daily_data['data']['skills'].items()):
            skill: dict[str, str] = {
                'xp': format_float(skill_data['experience']['end']), 
                'today': format_float(skill_data['experience']['gained']), 
                'week': format_float(weekly_data['data']['skills'][skill_name]['experience']['gained'])
            }
            skills.append(skill)

        skill_chars = 14
        xp_chars: int = max(max([len(skill['xp']) for skill in skills]), len('XP'))+1
        today_chars: int = max(max([len(skill['today']) for skill in skills]), len('Today'))+1
        week_chars: int = max(max([len(skill['week']) for skill in skills]), len('This Week'))+1

        msg: str = '.-' + '-'*skill_chars + '--' + '-'*xp_chars + '--' + '-'*today_chars + '--' + '-'*week_chars + '.'
        width: int = len(msg)

        msg = '.' + '-'*(width-2) + '.\n'

        skill_whitespace = float((skill_chars-len('Skill'))/2)
        if skill_whitespace.is_integer():
            skill_whitespace = int(skill_whitespace)
            msg += '| ' + ' '*skill_whitespace + 'Skill' + ' '*skill_whitespace + '| '
        else:
            msg += '| ' + ' '*(math.floor(skill_whitespace)) + 'Skill' + ' '*(math.ceil(skill_whitespace)) + '| '
        xp_whitespace = float((xp_chars-len('XP'))/2)
        if xp_whitespace.is_integer():
            xp_whitespace = int(xp_whitespace)
            msg += ' '*xp_whitespace + 'XP' + ' '*xp_whitespace + '| '
        else:
            msg += ' '*(math.floor(xp_whitespace)) + 'XP' + ' '*(math.ceil(xp_whitespace)) + '| '
        today_whitespace = float((today_chars-len('Today'))/2)
        if today_whitespace.is_integer():
            today_whitespace = int(today_whitespace)
            msg += ' '*today_whitespace + 'Today' + ' '*today_whitespace + '| '
        else:
            msg += ' '*(math.floor(today_whitespace)) + 'Today' + ' '*(math.ceil(today_whitespace)) + '| '
        week_whitespace = float((week_chars-len('This Week'))/2)
        if week_whitespace.is_integer():
            week_whitespace = int(week_whitespace)
            msg += ' '*week_whitespace + 'This Week' + ' '*week_whitespace + '|\n'
        else:
            msg += ' '*(math.floor(week_whitespace)) + 'This Week' + ' '*(math.ceil(week_whitespace)) + '|\n'

        msg += '|-' + '-'*skill_chars + '|-' + '-'*xp_chars + '|-' + '-'*today_chars + '|-' + '-'*week_chars + '|\n'

        for i, skill in enumerate(skills):
            msg += '| ' + skills_07[i] + ' '*(skill_chars-len(skills_07[i])) + '| ' + ' '*(xp_chars-len(skill['xp'])-1) + skill['xp'] + ' | ' + ' '*(today_chars-len(skill['today'])-1) + skill['today'] + ' | ' + ' '*(week_chars-len(skill['week'])-1) + skill['week'] + ' |\n'

        msg += "'" + '-'*(width-2) + "'"

        msg = f'```\n{msg}\n```'

        embed = discord.Embed(title=f'OSRS gains for {name}', colour=discord.Colour.blue(), timestamp=datetime.now(UTC), description=msg, url=f'https://wiseoldman.net/players/{name}/gained'.replace(' ', '-'))
        embed.set_author(name=f'Wise Old Man', url=f'https://wiseoldman.net/players/{name}/gained'.replace(' ', '-'), icon_url='https://wiseoldman.net/img/logo.png')

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rs3stats'])
    @commands.cooldown(1, 5, runescape_api_cooldown_key)
    async def stats(self, ctx: commands.Context, *, username: discord.User | str | None) -> None:
        '''
        Get RS3 hiscores info by username.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()
        
        name: str | None = None
        disc_user: discord.User | None = username if isinstance(username, discord.User) else None
        if not disc_user and not username:
            disc_user = ctx.author if isinstance(ctx.author, discord.User) else ctx.author._user
        if disc_user:
            async with self.bot.get_session() as session:
                user: User | None = (await session.execute(select(User).where(User.id == disc_user.id))).scalar_one_or_none()
            name = user.rsn if user and user.rsn else disc_user.display_name
        if not name:
            name = username if isinstance(username, str) else None
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your Old School username using the `setrsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url: str = f'http://services.runescape.com/m=hiscore/index_lite.ws?player={name}'.replace(' ', '%20')

        r: ClientResponse = await self.bot.aiohttp.get(url, headers={ 'User-agent': self.bot.config['wiki_user_agent'] })
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
            data: str = await r.text()

        lines: list[str] = data.split('\n')
        lines = lines[:len(skills_rs3)]

        levels: list[str] = []
        xp_list: list[str] = []

        for i, line in enumerate(lines):
            split: list[str] = line.split(',')
            levels.append(split[1])
            xp_list.append(split[2])

        stats_interface: Array = copy.deepcopy(self.stats_interface_rs3)
            
        draw_num(stats_interface, int(levels[0]), 73, 290, white, False)
        
        virtual_total_delta = 0

        for i, index in enumerate(skill_indices_rs3):
            level: int = max(int(levels[1:][index]), 1)
            if index == 3:
                level = max(level, 10)
            xp: int = int(xp_list[1:][index])
            if index != 26:
                virtual_level = max(xp_to_level(xp), level)
                if virtual_level - level > 0:
                    virtual_total_delta += virtual_level - level
            else:
                virtual_level = level

            x: int = 44 + 62 * (i % 3)
            y: int = 14 + 27 * (i // 3)

            draw_num(stats_interface, virtual_level, x, y, orange, False)
            draw_num(stats_interface, virtual_level, x+15, y+12, orange, False)
        
        draw_num(stats_interface, int(levels[0]) + virtual_total_delta, 73, 302, green, False)

        combat = int(combat_level(int(levels[1]), int(levels[3]), int(levels[2]), max(int(levels[4]), 10), int(levels[7]), int(levels[5]), int(levels[6]), int(levels[24])))

        draw_num(stats_interface, combat, 165, 295, white, False)

        stats_image = io.BytesIO()
        format: Format = 'PNG-PIL' # type: ignore
        imageio.imwrite(stats_image, stats_interface, format=format)
        stats_image.seek(0)

        with open('assets/rs3.png', 'rb') as f:
            rs3_icon_image = io.BytesIO(f.read())
        
        stats_file = discord.File(stats_image, filename='rs3stats.png')
        rs3_icon_file = discord.File(rs3_icon_image, filename='rs3.png')

        hiscore_page_url: str = f'https://secure.runescape.com/m=hiscore/compare?user1={name}'.replace(' ', '+')
        colour = 0x00b2ff
        timestamp: datetime = datetime.now(UTC)
        embed = discord.Embed(title=name, colour=colour, timestamp=timestamp, url=hiscore_page_url)
        embed.set_author(name='RuneScape HiScores', url='https://secure.runescape.com/m=hiscore/ranking', icon_url='attachment://rs3.png')
        # player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://rs3stats.png')

        await ctx.send(files=[stats_file, rs3_icon_file], embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 5, runescape_api_cooldown_key)
    async def compare(self, ctx: commands.Context, name_1: discord.User | str = "", name_2: discord.User | str | None = "") -> None:
        '''
        Compare two players on RuneScape HiScores
        If either of the user names contain spaces, make sure you surround them by quotation marks.
        E.g.: `-compare "Player 1" "Player 2"`
        If you have set your username via `-setrsn`, you can give only 1 username to compare a player to yourself.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        user_1: User | None = None
        user_2: User | None = None
        async with self.bot.get_session() as session:
            if isinstance(name_1, discord.User):
                user_1 = (await session.execute(select(User).where(User.id == name_1.id))).scalar_one_or_none()
            if isinstance(name_2, discord.User):
                user_2 = (await session.execute(select(User).where(User.id == name_2.id))).scalar_one_or_none()

            username_1: str = user_1.rsn if user_1 and user_1.rsn else (name_1.display_name if isinstance(name_1, discord.User) else name_1)
            username_2: str | None = user_2.rsn if user_2 and user_2.rsn else (name_2.display_name if isinstance(name_2, discord.User) else name_2)

            if not username_2:
                user_2 = (await session.execute(select(User).where(User.id == ctx.author.id))).scalar_one_or_none()
                if user_2 and user_2.rsn:
                    username_2 = username_1
                    username_1 = user_2.rsn
        
        if not username_2:
            raise commands.CommandError(message=f'Required argument missing: `RSN_2`. You can set your Old School username using the `setrsn` command, or add a second username as argument.')
        
        for name in [username_1, username_2]:
            if len(name) > 12:
                raise commands.CommandError(message=f'Invalid argument: `{name}`.')
            if re.match(r'^[A-z0-9 -]+$', name) is None:
                raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        
        level_list: list[list[str]] = []
        exp_list: list[list[str]] = []
        
        for name in [username_1, username_2]:
            url: str = f'http://services.runescape.com/m=hiscore/index_lite.ws?player={name}'.replace(' ', '%20')

            r: ClientResponse = await self.bot.aiohttp.get(url, headers={ 'User-agent': self.bot.config['wiki_user_agent'] })
            async with r:
                if r.status != 200:
                    raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
                data: str = await r.text()

            lines: list[str] = data.split('\n')
            lines = lines[:len(skills_rs3)]

            levels: list[str] = []
            xp_list: list[str] = []

            for line in lines:
                split: list[str] = line.split(',')
                levels.append(split[1])
                xp_list.append(split[2])
            
            level_list.append(levels)
            exp_list.append(xp_list)
        
        stats_interface_1: Array = copy.deepcopy(self.stats_interface_rs3)
        stats_interface_2: Array = copy.deepcopy(self.stats_interface_rs3)
        interfaces: tuple[Array, Array] = (stats_interface_1, stats_interface_2)

        for i, levels in enumerate(level_list):
            xp_list = exp_list[i]
            stats_interface: Array = interfaces[i]

            draw_num(stats_interface, int(levels[0]), 73, 290, white, False)

            virtual_total_delta = 0

            for j, index in enumerate(skill_indices_rs3):
                level: int = max(int(levels[1:][index]), 1)
                if index == 3:
                    level = max(level, 10)
                xp = int(xp_list[1:][index])
                if index != 26:
                    virtual_level: int = max(xp_to_level(xp), level)
                    if virtual_level - level > 0:
                        virtual_total_delta += virtual_level - level
                else:
                    virtual_level = level

                x: int = 44 + 62 * (j % 3)
                y: int = 14 + 27 * (j // 3)

                draw_num(stats_interface, virtual_level, x, y, orange, False)
                draw_num(stats_interface, virtual_level, x+15, y+12, orange, False)
            
            draw_num(stats_interface, int(levels[0]) + virtual_total_delta, 73, 302, green, False)

            combat = int(combat_level(int(levels[1]), int(levels[3]), int(levels[2]), max(int(levels[4]), 10), int(levels[7]), int(levels[5]), int(levels[6]), int(levels[24])))

            draw_num(stats_interface, combat, 165, 295, white, False)
        
        for i, index in enumerate(skill_indices_rs3):
            xp_1 = int(exp_list[0][1:][index])
            xp_2 = int(exp_list[1][1:][index])

            x = 6 + 62 * (i % 3)
            y = 5 + 27 * (i // 3)

            if xp_1 > xp_2:
                draw_outline_rs3(stats_interface_1, x, y, green)
                draw_outline_rs3(stats_interface_2, x, y, red)
            elif xp_2 > xp_1:
                draw_outline_rs3(stats_interface_1, x, y, red)
                draw_outline_rs3(stats_interface_2, x, y, green)
        
        compare_image: np.ndarray = np.hstack((stats_interface_1, stats_interface_2))
        compare_image_bytes = io.BytesIO()
        format: Format = 'PNG-PIL' # type: ignore
        imageio.imwrite(compare_image_bytes, compare_image, format=format)
        compare_image_bytes.seek(0)

        with open('assets/rs3.png', 'rb') as f:
            rs3_icon_image = io.BytesIO(f.read())
        
        compare_image_file = discord.File(compare_image_bytes, filename='compare.png')
        rs3_icon_file = discord.File(rs3_icon_image, filename='rs3.png')

        hiscore_page_url: str = f'https://secure.runescape.com/m=hiscore/compare?user1={username_1}'.replace(' ', '+')
        embed = discord.Embed(title=f'{username_1}, {username_2}', colour=0x00b2ff, timestamp=datetime.now(UTC), url=hiscore_page_url)
        embed.set_author(name='RuneScape HiScores', url='https://secure.runescape.com/m=hiscore/ranking', icon_url='attachment://rs3.png')
        # player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://compare.png')

        await ctx.send(files=[compare_image_file, rs3_icon_file], embed=embed)

    @commands.command(pass_context=True, aliases=['gains', 'rs3gainz', 'rs3gains'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def gainz(self, ctx: commands.Context, *, username: discord.User | str | None) -> None:
        '''
        Get RS3 gains by username.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name: str | None = None
        disc_user: discord.User | None = username if isinstance(username, discord.User) else None
        if not disc_user and not username:
            disc_user = ctx.author if isinstance(ctx.author, discord.User) else ctx.author._user
        if disc_user:
            async with self.bot.get_session() as session:
                user: User | None = (await session.execute(select(User).where(User.id == disc_user.id))).scalar_one_or_none()
            name = user.rsn if user and user.rsn else disc_user.display_name
        if not name:
            name = username if isinstance(username, str) else None
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your username using the `setrsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url: str = f'https://api.runepixels.com/players/{name}'.replace(' ', '-')

        r: ClientResponse = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find xp gains for: `{name}`.')
            data: dict = await r.json()

        yday_url = f'https://api.runepixels.com/players/{data["id"]}/xp?timeperiod=1'
        r = await self.bot.aiohttp.get(yday_url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find xp gains for: `{name}`.')
            yday_data: list[dict[str, Any]] = await r.json()

        week_url = f'https://api.runepixels.com/players/{data["id"]}/xp?timeperiod=2'
        r = await self.bot.aiohttp.get(week_url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find xp gains for: `{name}`.')
            week_data = await r.json()

        skills: list = [data['overall']] + data['skills']
        for i, _ in enumerate(skills):
            skills[i]['xpDelta'] = format_float(skills[i]['xpDelta'])
            skills[i]['yday'] = format_float(yday_data[i]['xp'])
            skills[i]['week'] = format_float(week_data[i]['xp'])

        skill_chars = 14
        today_chars: int = max(max([len(skill['xpDelta']) for skill in skills]), len('Today'))+1
        yday_chars: int = max(max([len(skill['yday']) for skill in skills]), len('Yesterday'))+1
        week_chars: int = max(max([len(skill['week']) for skill in skills]), len('This Week'))+1

        msg: str = '.-' + '-'*skill_chars + '--' + '-'*today_chars + '--' + '-'*yday_chars + '--' + '-'*week_chars + '.'
        width: int = len(msg)

        msg = '.' + '-'*(width-2) + '.\n'

        skill_whitespace = float((skill_chars-len('Skill'))/2)
        if skill_whitespace.is_integer():
            skill_whitespace = int(skill_whitespace)
            msg += '| ' + ' '*skill_whitespace + 'Skill' + ' '*skill_whitespace + '| '
        else:
            msg += '| ' + ' '*(math.floor(skill_whitespace)) + 'Skill' + ' '*(math.ceil(skill_whitespace)) + '| '
        today_whitespace = float((today_chars-len('Today'))/2)
        if today_whitespace.is_integer():
            today_whitespace = int(today_whitespace)
            msg += ' '*today_whitespace + 'Today' + ' '*today_whitespace + '| '
        else:
            msg += ' '*(math.floor(today_whitespace)) + 'Today' + ' '*(math.ceil(today_whitespace)) + '| '
        yday_whitespace = float((yday_chars-len('Yesterday'))/2)
        if yday_whitespace.is_integer():
            yday_whitespace = int(yday_whitespace)
            msg += ' '*yday_whitespace + 'Yesterday' + ' '*yday_whitespace + '| '
        else:
            msg += ' '*(math.floor(yday_whitespace)) + 'Yesterday' + ' '*(math.ceil(yday_whitespace)) + '| '
        week_whitespace = float((week_chars-len('This Week'))/2)
        if week_whitespace.is_integer():
            week_whitespace = int(week_whitespace)
            msg += ' '*week_whitespace + 'This Week' + ' '*week_whitespace + '|\n'
        else:
            msg += ' '*(math.floor(week_whitespace)) + 'This Week' + ' '*(math.ceil(week_whitespace)) + '|\n'

        msg += '|-' + '-'*skill_chars + '|-' + '-'*today_chars + '|-' + '-'*yday_chars + '|-' + '-'*week_chars + '|\n'

        for i, skill in enumerate(skills):
            msg += '| ' + skills_rs3[i] + ' '*(skill_chars-len(skills_rs3[i])) + '| ' + ' '*(today_chars-len(skill['xpDelta'])-1) + skill['xpDelta'] + ' | ' + ' '*(yday_chars-len(skill['yday'])-1) + skill['yday'] + ' | ' + ' '*(week_chars-len(skill['week'])-1) + skill['week'] + ' |\n'

        msg += "'" + '-'*(width-2) + "'"

        msg = f'```\n{msg}\n```'

        embed = discord.Embed(title=f'RS3 gains for {name}', colour=discord.Colour.blue(), timestamp=datetime.now(UTC), description=msg, url=f'https://runepixels.com/players/{name}/skills'.replace(' ', '-'))
        embed.set_author(name=f'RunePixels', url=f'https://runepixels.com/players/{name}/skills'.replace(' ', '-'), icon_url='https://pbs.twimg.com/profile_images/1579124090958479362/LbR9PDfv_400x400.png')

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['gametime'])
    async def time(self, ctx: commands.Context) -> None:
        '''
        Get current RuneScape game time.
        '''
        self.bot.increment_command_counter()

        time: datetime = datetime.now(UTC)
        time_str: str = time.strftime('%H:%M')

        await ctx.send(f'Current game time is: `{time_str}`.')
    
    @commands.command(aliases=['wax', 'viswax', 'goldberg'])
    async def vis(self, ctx: commands.Context) -> None:
        '''
        Get today's rune combination for the Rune Goldberg machine, used to make vis wax.
        '''
        self.bot.increment_command_counter()
        await ctx.send(embed=self.vis_wax_embed)
    
    @commands.command(aliases=['lvl'])
    async def level(self, ctx: commands.Context, lvl: int | str = 0) -> None:
        '''
        Calculate xp required for given level.
        '''
        self.bot.increment_command_counter()

        if not lvl:
            raise commands.CommandError(message=f'Required argument missing: `level`')
        elif not is_int(lvl):
            raise commands.CommandError(message=f'Invalid argument level: `{lvl}``. Level must be an integer.')
        lvl = int(lvl)
        if lvl < 1 or lvl > 126:
            raise commands.CommandError(message=f'Invalid argument level: `{lvl}``. Level must be between 1 and 126.')

        xp: int = level_to_xp(lvl)
        xp_str = f'{xp:,}'

        await ctx.send(f'XP required for level `{lvl}`: `{xp_str}`')
    
    @commands.command(aliases=['xp', 'exp'])
    async def experience(self, ctx: commands.Context, lvl_start_or_xp: int | str = 0, lvl_end: int | str = 0) -> None:
        '''
        Calculate level from xp or xp difference between two levels.
        '''
        self.bot.increment_command_counter()

        if not lvl_start_or_xp:
            raise commands.CommandError(message=f'Required argument missing: `level`')
        elif not is_int(lvl_start_or_xp) or not is_int(lvl_end):
            raise commands.CommandError(message=f'Invalid argument: `level`. Level must be an integer.')
        lvl_start_or_xp = int(lvl_start_or_xp)
        lvl_end = int(lvl_end)
        if lvl_start_or_xp < 1 or lvl_start_or_xp > 200e6:
            raise commands.CommandError(message=f'Invalid argument: `level`. Levels must be between 1 and 126. XP must be between between 1 and 200M.')
        elif (lvl_start_or_xp <= 126 and lvl_start_or_xp >= lvl_end and lvl_end > 0) or (lvl_start_or_xp > 126 and xp_to_level(lvl_start_or_xp) >= lvl_end and lvl_end > 0):
            raise commands.CommandError(message=f'Invalid arguments: Start level must be lower than end level.')

        if not lvl_end:
            xp_start: int = lvl_start_or_xp
            level: int = xp_to_level(xp_start)
            level_xp: int = level_to_xp(level)
            xp_start_str: str = f'{xp_start:,}'
            level_xp_str: str = f'{level_xp:,}'
            next_lvl: int = level+1
            next_xp: int = level_to_xp(next_lvl)
            next_xp_str: str = f'{next_xp:,}'
            await ctx.send(f'At `{xp_start_str}` XP, you are level `{level}`, which requires `{level_xp_str}` XP.\nYou will reach level `{next_lvl}` at `{next_xp_str} XP.`')
        
        else:
            if lvl_start_or_xp > 126:
                xp_start = lvl_start_or_xp
            else:
                xp_start = level_to_xp(lvl_start_or_xp)
            xp_end: int = level_to_xp(lvl_end)
            xp_dif: int = xp_end - xp_start
            xp_dif_str = f'{xp_dif:,}'
            if lvl_start_or_xp > 126:
                await ctx.send(f'To reach level `{lvl_end}` from `{lvl_start_or_xp}` XP, you will need to gain `{xp_dif_str}` XP.')
            else:
                await ctx.send(f'To reach level `{lvl_end}` from level `{lvl_start_or_xp}`, you will need to gain `{xp_dif_str}` XP.')
    
    @commands.command(aliases=['actions'])
    async def xph(self, ctx: commands.Context, lvl_start: int | str = 0, lvl_end: int | str = 0, xp_rate: float | str = 0.0) -> None:
        '''
        Calculate hours/actions required to reach a level / xp at a certain xp rate.
        '''
        self.bot.increment_command_counter()

        if not lvl_start or not lvl_end or not xp_rate:
            raise commands.CommandError(message=f'Required argument missing.')
        elif not is_int(lvl_start) or not is_int(lvl_end):
            raise commands.CommandError(message=f'Invalid argument(s): LEVEL. Must be of type integer.')
        elif not is_float(xp_rate):
            raise commands.CommandError(message=f'Invalid argument XP_RATE: `{xp_rate}`. Must be of type float.')

        lvl_start = int(lvl_start)
        lvl_end = int(lvl_end)
        xp_rate = round(float(xp_rate) * 2) / 2 # round to nearest half
        if xp_rate == int(xp_rate):
            xp_rate = int(xp_rate)

        if lvl_start < 1 or lvl_end < 1 or xp_rate <= 0:
            raise commands.CommandError(message=f'Invalid argument. Levels must be between 1 and 126 and XP rate must be positive.')

        start_xp: bool = False
        end_xp: bool = False
        if lvl_start > 126:
            start_xp = True
        if lvl_end > 126:
            end_xp = True
        if (start_xp or end_xp) and (lvl_start > 200e6 or lvl_end > 200e6):
            raise commands.CommandError(message=f'Invalid argument. Start and End xp values can be at most 200M.')

        xp_start: int = lvl_start if start_xp else level_to_xp(lvl_start)
        xp_end: int = lvl_end if end_xp else level_to_xp(lvl_end)
        if xp_start >= xp_end:
            raise commands.CommandError(message=f'Invalid arguments: Start xp must be lower than end xp.')

        xp_dif: int = xp_end - xp_start

        hours_or_actions: int = math.ceil(xp_dif / xp_rate)
        hours_or_actions_str: str = f'{hours_or_actions:,}'
        xp_dif_str: str = f'{xp_dif:,}'
        xp_rate = f'{xp_rate:,}'

        await ctx.send(f'To reach {"level " if not end_xp else ""}`{lvl_end}`{" XP" if end_xp else ""} from {"level " if not start_xp else ""}`{lvl_start}`{" XP" if start_xp else ""}, you will need to gain `{xp_dif_str}` XP. This will take `{hours_or_actions_str}` hours/actions at an XP rate of `{xp_rate}` per hour/action.')

    @commands.command()
    async def pvm(self, ctx: commands.Context) -> None:
        '''
        Calculate rotations for Araxxor, Vorago, and Barrows: Rise Of The Six.
        '''
        self.bot.increment_command_counter()

        araxxor_rotation, next_araxxor = araxxor(datetime.now(UTC))
        vorago_rotation, next_vorago = vorago(datetime.now(UTC))
        rots_rotation, next_rots = rots(datetime.now(UTC))

        embed = discord.Embed(title='PVM Rotations', colour=0xff0000, timestamp=datetime.now(UTC))
        embed.add_field(name='Araxxor', value=f'Blocked path: **{araxxor_rotation}**\nThe next path will close in `{next_araxxor}`.', inline=False)
        embed.add_field(name='Vorago', value=f'Current rotation: **{vorago_rotation}**\nThe next rotation will start in `{next_vorago}`.', inline=False)
        embed.add_field(name='Barrows: Rise Of The Six', value=f'Current rotation:\nWest: **{", ".join(rots_rotation[0])}**\nEast: **{", ".join(rots_rotation[1])}**\nThe next rotation will start in `{next_rots}`.', inline=False)

        images: list[str] = ['assets/Araxxor.png', 'assets/Vorago.png', 'assets/Ahrim.png']

        with open(random.choice(images), 'rb') as f:
            file = io.BytesIO(f.read())

        image = discord.File(file, filename='pvm_boss.png')

        embed.set_thumbnail(url='attachment://pvm_boss.png')

        await ctx.send(file=image, embed=embed)
    
    @commands.command()
    async def dry(self, ctx: commands.Context, droprate: float | int | str, attempts: int | str) -> None:
        '''
        Calculates the probability of going dry.
        Arguments: droprate, attempts
        Droprate formatting options (1/1000 used for example):
        - 1/1000
        - 1000
        - 0.001
        Formula used: (1-p)^k * 100
        '''
        self.bot.increment_command_counter()

        if not droprate:
            raise commands.CommandError(message=f'Required argument missing: `droprate`')
        if not attempts:
            raise commands.CommandError(message=f'Required argument missing: `attempts`')
        if not is_int(attempts):
            raise commands.CommandError(message=f'Invalid argument: `{attempts}`. Must be an integer.')
        attempts = int(attempts)
        if attempts <= 0:
            raise commands.CommandError(message=f'Invalid argument: `{attempts}`. Must be greater than 0.')
        if '1/' in str(droprate):
            droprate = str(droprate).replace('1/', '')
        if is_int(droprate):
            droprate = int(droprate)
            if droprate <= 0:
                raise commands.CommandError(message=f'Invalid argument: `{droprate}`. Must be greater than 0 if integer.')
            droprate = 1/droprate
        elif is_float(droprate):
            droprate = float(droprate)
            if droprate <= 0 or droprate > 1:
                raise commands.CommandError(message=f'Invalid argument: `{droprate}`. Must be greater than 0 and less than or equal to 1 if float.')
        else:
            raise commands.CommandError(message=f'Invalid argument: `{droprate}`. Must be int, float, or string of the form `1/x` where x is a positive integer.')

        result: float = (1-droprate)**attempts
        result *= 100

        await ctx.send(f'```Drop rate: {droprate}\nAttempts: {attempts}\nProbability of not getting the drop: {result}%```')

    @commands.command(aliases=['cb', 'rs3cb', 'rs3combat'])
    @commands.cooldown(1, 5, runescape_api_cooldown_key)
    async def combat(self, ctx: commands.Context, *, username: discord.User | str | None) -> None:
        '''
        Calculate the combat level of a RS3 player.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name: str | None = None
        disc_user: discord.User | None = username if isinstance(username, discord.User) else None
        if not disc_user and not username:
            disc_user = ctx.author if isinstance(ctx.author, discord.User) else ctx.author._user
        if disc_user:
            async with self.bot.get_session() as session:
                user: User | None = (await session.execute(select(User).where(User.id == disc_user.id))).scalar_one_or_none()
            name = user.rsn if user and user.rsn else disc_user.display_name
        if not name:
            name = username if isinstance(username, str) else None
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your username using the `setrsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url: str = f'http://services.runescape.com/m=hiscore/index_lite.ws?player={name}'.replace(' ', '%20')
        hiscore_page_url: str = f'https://secure.runescape.com/m=hiscore/compare?user1={name}'.replace(' ', '+')

        r: ClientResponse = await self.bot.aiohttp.get(url, headers={ 'User-agent': self.bot.config['wiki_user_agent'] })
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
            data: str = await r.text()

        lines: list[str] = data.split('\n')
        lines = lines[:len(skills_rs3)]

        levels: list[str] = []
        xp_list: list[str] = []

        for line in lines:
            levels.append(line.split(',')[1])
            xp_list.append(line.split(',')[2])

        attack = int(levels[1])
        strength = int(levels[3])
        defence = int(levels[2])
        constitution = max(int(levels[4]), 10)
        magic = int(levels[7])
        ranged = int(levels[5])
        prayer = int(levels[6])
        summoning = int(levels[24])
        combat: float = combat_level(attack, strength, defence, constitution, magic, ranged, prayer, summoning)

        cb_skills: list[int] = [attack, strength, defence, constitution, magic, ranged, prayer, summoning]
        original_cb_skills: list[int] = copy.deepcopy(cb_skills)
        cb_skill_names: list[str] = ['Attack', 'Strength', 'Defence', 'Constitution', 'Magic', 'Ranged', 'Prayer', 'Summoning']
        levels_required: list[int] = [0, 0, 0, 0, 0, 0, 0, 0]

        description: str = f'**{name}**\'s combat level is: `{combat}`'

        if combat < 138:
            for i, cb_skill in enumerate(original_cb_skills):
                cb_skills = copy.deepcopy(original_cb_skills)
                while cb_skill < 99:
                    cb_skill += 1
                    cb_skills[i] = cb_skill
                    if (math.floor(combat_level(*cb_skills)) > math.floor(combat)):
                        levels_required[i] = cb_skill - original_cb_skills[i]
                        break
        
        if (any([lvls_required > 0 for lvls_required in levels_required])):
            description += '\nYou can level up by getting any of the following levels:'

        embed = discord.Embed(title=f'Combat level', colour=0x00b2ff, timestamp=datetime.now(UTC), url=hiscore_page_url, description=description)
        embed.set_author(name=name, icon_url=f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '%20'))

        for i, lvls_required in enumerate(levels_required):
            if lvls_required > 0:
                embed.add_field(name=cb_skill_names[i], value=f'{rs3_skill_emojis[cb_indices_rs3[i]]} {lvls_required} levels', inline=True)

        await ctx.send(embed=embed)

    @commands.command(name='07combat', aliases=['07cb', 'osrscb', 'osrscombat'])
    @commands.cooldown(1, 5, runescape_api_cooldown_key)
    async def _07combat(self, ctx: commands.Context, *, username: discord.User | str | None) -> None:
        '''
        Calculate the combat level of a OSRS player.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name: str | None = None
        disc_user: discord.User | None = username if isinstance(username, discord.User) else None
        if not disc_user and not username:
            disc_user = ctx.author if isinstance(ctx.author, discord.User) else ctx.author._user
        if disc_user:
            async with self.bot.get_session() as session:
                user: User | None = (await session.execute(select(User).where(User.id == disc_user.id))).scalar_one_or_none()
            name = user.rsn if user and user.rsn else disc_user.display_name
        if not name:
            name = username if isinstance(username, str) else None
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your Old School username using the `set07rsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url: str = f'http://services.runescape.com/m=hiscore_oldschool/index_lite.ws?player={name}'.replace(' ', '%20')
        hiscore_page_url: str = f'https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={name}'.replace(' ', '+')

        r: ClientResponse = await self.bot.aiohttp.get(url, headers={ 'User-agent': self.bot.config['wiki_user_agent'] })
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
            data: str = await r.text()

        lines: list[str] = data.split('\n')
        try:
            lines = lines[:len(skills_07)]
        except:
            raise commands.CommandError(message=f'Error accessing hiscores, please try again later.')

        levels: list[str] = []

        for line in lines:
            levels.append(line.split(',')[1])

        attack = int(levels[1])
        strength = int(levels[3])
        defence = int(levels[2])
        hitpoints = max(int(levels[4]), 10)
        magic = int(levels[7])
        ranged = int(levels[5])
        prayer = int(levels[6])
        
        combat: int = osrs_combat_level(attack, strength, defence, hitpoints, magic, ranged, prayer)

        cb_skills: list[int] = [attack, strength, defence, hitpoints, magic, ranged, prayer]
        original_cb_skills: list[int] = copy.deepcopy(cb_skills)
        cb_skill_names: list[str] = ['Attack', 'Strength', 'Defence', 'Hitpoints', 'Magic', 'Ranged', 'Prayer']
        levels_required: list[int] = [0, 0, 0, 0, 0, 0, 0]

        description: str = f'**{name}**\'s combat level is: `{combat}`'

        if combat < 126:
            for i, cb_skill in enumerate(original_cb_skills):
                cb_skills = copy.deepcopy(original_cb_skills)
                while cb_skill < 99:
                    cb_skill += 1
                    cb_skills[i] = cb_skill
                    if (math.floor(osrs_combat_level(*cb_skills)) > math.floor(combat)):
                        levels_required[i] = cb_skill - original_cb_skills[i]
                        break
        
        if (any([lvls_required > 0 for lvls_required in levels_required])):
            description += '\nYou can level up by getting any of the following levels:'

        embed = discord.Embed(title=f'Combat level', colour=0x00b2ff, timestamp=datetime.now(UTC), url=hiscore_page_url, description=description)
        embed.set_author(name=name, icon_url=f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '%20'))

        for i, lvls_required in enumerate(levels_required):
            if lvls_required > 0:
                embed.add_field(name=cb_skill_names[i], value=f'{osrs_skill_emojis[cb_indices_osrs[i]]} {lvls_required} levels', inline=True)

        await ctx.send(embed=embed)

async def setup(bot: Bot) -> None:
    await bot.add_cog(Runescape(bot))