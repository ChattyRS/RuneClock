from typing import Any, Iterator
from aiohttp import ClientResponse
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Cog
from imageio.core.util import Array
from sqlalchemy import select
from bot import Bot
from database import User, NewsPost, RS3Item, OSRSItem
import re
from datetime import datetime, timedelta, UTC
import matplotlib.pyplot as plt
from matplotlib.dates import date2num
import matplotlib.dates as mdates
from matplotlib.dates import DateFormatter
import math
from bs4 import BeautifulSoup, NavigableString, Tag
from number_utils import is_int, is_float, format_float
from runescape_utils import xp_to_level, level_to_xp, combat_level, osrs_combat_level
from runescape_utils import skills_07, osrs_skill_emojis, skills_rs3, rs3_skill_emojis
from runescape_utils import skill_indices, skill_indices_rs3, cb_indices_rs3, cb_indices_osrs
from runescape_utils import araxxor, vorago, rots
from graphics import draw_num, draw_outline_osrs, draw_outline_rs3
import io
import imageio
import copy
import numpy as np
import random
from praw.reddit import Subreddit, Submission
from graphics import yellow, orange, white, green, red

class Runescape(Cog):
    vis_wax_embed = discord.Embed(title='Vis wax combination', colour=0x00b2ff, timestamp=datetime.now(UTC), description='Today\'s vis wax combo has not been released yet.')
    vis_wax_combo: list = []
    vis_wax_released = False
    vis_wax_check_frequency: int = 60*15 # seconds
    vis_time = 0

    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
        self.vis_wax.start()

    def cog_unload(self) -> None:
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

        async with self.bot.async_session() as session:
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

        async with self.bot.async_session() as session:
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
            async with self.bot.async_session() as session:
                user: User | None = (await session.execute(select(User).where(User.id == ctx.author.id))).scalar_one_or_none()
            if user:
                username = user.rsn
            if not username:
                raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your username using the `setrsn` command.')

        if len(username) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{username}`.')
        if re.match('^[A-z0-9 -]+$', username) is None:
            raise commands.CommandError(message=f'Invalid argument: `{username}`.')

        url: str = f'https://apps.runescape.com/runemetrics/profile/profile?user={username}&activities=20'.replace(' ', '%20')

        r: ClientResponse = await self.bot.aiohttp.get(url)
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
            embed.add_field(name=s.title, value=f'https://www.reddit.com{s.permalink}')

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
            embed.add_field(name=s.title, value=f'https://www.reddit.com{s.permalink}')

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
    async def _07news(self, ctx: commands.Context):
        '''
        Get 5 latest OSRS news posts.
        '''
        self.bot.increment_command_counter()

        news_posts = await NewsPost.query.where(NewsPost.game=='osrs').order_by(NewsPost.time.desc()).gino.all()

        embed = discord.Embed(title=f'Old School RuneScape News')

        for i, post in enumerate(news_posts):
            if i >= 5:
                break
            embed.add_field(name=post.title, value=post.link + '\n' + post.description, inline=False)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rsnews', 'rs3news'])
    async def news(self, ctx: commands.Context):
        '''
        Get 5 latest RS news posts.
        '''
        self.bot.increment_command_counter()

        news_posts = await NewsPost.query.where(NewsPost.game=='rs3').order_by(NewsPost.time.desc()).gino.all()

        embed = discord.Embed(title=f'RuneScape News')

        for i, post in enumerate(news_posts):
            if i >= 5:
                break
            embed.add_field(name=post.title, value=post.link + '\n' + post.description, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='07price', pass_context=True, aliases=['osrsprice'])
    async def _07price(self, ctx: commands.Context, days='30', *item_name):
        '''
        Get the OSRS GE price for an item.
        Argument "days" is optional, default is 30.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if is_int(days):
            days = int(days)
            if days < 1 or days > 180:
                await ctx.send('Graph period must be between 1 and 180 days. Defaulted to 30.')
                days =  30
        else:
            item_name = list(item_name)
            item_name.insert(0, days)
            days = 30

        name = ' '.join(item_name)

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `item_name`.')
        if len(name) < 2:
            raise commands.CommandError(message=f'Invalid argument: `item_name`. Length must be at least 2 characters.')
        
        items = await OSRSItem.query.where(OSRSItem.name.ilike(f'%{name}%')).gino.all()
        if not items:
            raise commands.CommandError(message=f'Could not find item: `{name}`.')
        items = sorted(items, key=lambda i: len(i.name))
        item = items[0]

        name = item.name
        price = int(item.current.replace(' ', ''))
        price = f'{price:,}'
        icon = item.icon_url
        link = f'http://services.runescape.com/m=itemdb_oldschool/viewitem?obj={item.id}'
        description = item.description
        today = int(item.today.replace(' ', ''))
        today = f'{today:,}'
        if not today.startswith('-') and not today.startswith('+'):
            today = '+' + today
        day30 = item.day30
        if not day30.startswith('-') and not day30.startswith('+'):
            day30 = '+' + day30
        day90 = item.day90
        if not day90.startswith('-') and not day90.startswith('+'):
            day90 = '+' + day90
        day180 = item.day180
        if not day180.startswith('-') and not day180.startswith('+'):
            day180 = '+' + day180

        colour = 0x00b2ff
        timestamp = datetime.now(UTC)
        embed = discord.Embed(title=name, colour=colour, timestamp=timestamp, url=link, description=description)
        embed.set_thumbnail(url=icon)

        embed.add_field(name='Price', value=price, inline=False)
        change = ''
        if today != '0':
            change = f'**Today**: {today}\n'
        change += f'**30 days**: {day30}\n'
        change += f'**90 days**: {day90}\n'
        change += f'**180 days**: {day180}'
        embed.add_field(name='Change', value=change, inline=False)

        daily = item.graph_data['daily']

        times = []
        prices = []

        for ms, price in daily.items():
            times.append(int(ms)/1000)
            prices.append(int(price))

        last = times[len(times)-1]
        remove = []
        for i, time in enumerate(times):
            if time >= last - 86400*days:
                date = timestamp - timedelta(seconds=last-time)
                times[i] = date
            else:
                remove.append(i)
        remove.sort(reverse=True)
        for i in remove:
            del times[i]
            del prices[i]

        if days <= 60:
            loc = mdates.WeekdayLocator()
        else:
            loc = mdates.MonthLocator()

        formatter = DateFormatter('%d %b')

        plt.style.use('dark_background')

        fig, ax = plt.subplots()

        dates = date2num(times)
        plt.plot_date(dates, prices, color='#47a0ff', linestyle='-', ydate=False, xdate=True)

        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(formatter)

        ax.yaxis.grid()

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)

        locs, _ = plt.yticks()
        ylabels = []
        for l in locs:
            lab = str(int(l)).replace('000000000', '000M').replace('00000000', '00M').replace('0000000', '0M').replace('000000', 'M').replace('00000', '00K').replace('0000', '0K').replace('000', 'K')
            if not ('K' in lab or 'M' in lab):
                lab = "{:,}".format(int(lab))
            ylabels.append(lab)
        plt.yticks(locs, ylabels)

        plt.savefig('images/graph.png', transparent=True)
        plt.close(fig)

        with open('images/graph.png', 'rb') as f:
            file = io.BytesIO(f.read())
        
        image = discord.File(file, filename='graph.png')
        embed.set_image(url=f'attachment://graph.png')

        await ctx.send(file=image, embed=embed)
    
    @commands.command(pass_context=True, aliases=['rsprice', 'rs3price'])
    async def price(self, ctx: commands.Context, days='30', *item_name):
        '''
        Get the RS3 GE price for an item.
        Argument "days" is optional, default is 30.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if is_int(days):
            days = int(days)
            if days < 1 or days > 180:
                await ctx.send('Graph period must be between 1 and 180 days. Defaulted to 30.')
                days =  30
        else:
            item_name = list(item_name)
            item_name.insert(0, days)
            days = 30

        name = ' '.join(item_name)

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `item_name`.')
        if len(name) < 2:
            raise commands.CommandError(message=f'Invalid argument: `item_name`. Length must be at least 2 characters.')

        items = await RS3Item.query.where(RS3Item.name.ilike(f'%{name}%')).gino.all()
        if not items:
            raise commands.CommandError(message=f'Could not find item: `{name}`.')
        items = sorted(items, key=lambda i: len(i.name))
        item = items[0]

        name = item.name
        price = int(item.current.replace(' ', ''))
        price = f'{price:,}'
        icon = item.icon_url
        link = f'http://services.runescape.com/m=itemdb_rs/viewitem?obj={item.id}'
        description = item.description
        today = int(item.today.replace(' ', ''))
        today = f'{today:,}'
        if not today.startswith('-') and not today.startswith('+'):
            today = '+' + today
        day30 = item.day30
        if not day30.startswith('-') and not day30.startswith('+'):
            day30 = '+' + day30
        day90 = item.day90
        if not day90.startswith('-') and not day90.startswith('+'):
            day90 = '+' + day90
        day180 = item.day180
        if not day180.startswith('-') and not day180.startswith('+'):
            day180 = '+' + day180

        colour = 0x00b2ff
        timestamp = datetime.now(UTC)
        embed = discord.Embed(title=name, colour=colour, timestamp=timestamp, url=link, description=description)
        embed.set_thumbnail(url=icon)

        embed.add_field(name='Price', value=price, inline=False)
        change = ''
        if today != '0':
            change = f'**Today**: {today}\n'
        change += f'**30 days**: {day30}\n'
        change += f'**90 days**: {day90}\n'
        change += f'**180 days**: {day180}'
        embed.add_field(name='Change', value=change, inline=False)

        daily = item.graph_data['daily']

        times = []
        prices = []

        for ms, price in daily.items():
            times.append(int(ms)/1000)
            prices.append(int(price))

        last = times[len(times)-1]
        remove = []
        for i, time in enumerate(times):
            if time >= last - 86400*days:
                date = timestamp - timedelta(seconds=last-time)
                times[i] = date
            else:
                remove.append(i)
        remove.sort(reverse=True)
        for i in remove:
            del times[i]
            del prices[i]

        if days <= 60:
            loc = mdates.WeekdayLocator()
        else:
            loc = mdates.MonthLocator()

        formatter = DateFormatter('%d %b')

        plt.style.use('dark_background')

        fig, ax = plt.subplots()

        dates = date2num(times)
        plt.plot_date(dates, prices, color='#47a0ff', linestyle='-', ydate=False, xdate=True)

        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(formatter)

        ax.yaxis.grid()

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)

        locs, _ = plt.yticks()
        ylabels = []
        for l in locs:
            lab = str(int(l)).replace('000000000', '000M').replace('00000000', '00M').replace('0000000', '0M').replace('000000', 'M').replace('00000', '00K').replace('0000', '0K').replace('000', 'K')
            if not ('K' in lab or 'M' in lab):
                lab = "{:,}".format(int(lab))
            ylabels.append(lab)
        plt.yticks(locs, ylabels)

        plt.savefig('images/graph.png', transparent=True)
        plt.close(fig)

        with open('images/graph.png', 'rb') as f:
            file = io.BytesIO(f.read())
        
        image = discord.File(file, filename='graph.png')
        embed.set_image(url=f'attachment://graph.png')

        await ctx.send(file=image, embed=embed)
    
    @commands.command(name='07stats', pass_context=True, aliases=['osrsstats'])
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def _07stats(self, ctx: commands.Context, *username):
        '''
        Get OSRS hiscores info by username.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name = None
        if ctx.message.mentions:
            name = ctx.message.mentions[0].display_name
            user = await User.get(ctx.message.mentions[0].id)
            if user:
                name = user.osrs_rsn
        else:
            name = ' '.join(username)

        if not name:
            user = await User.get(ctx.author.id)
            if user:
                name = user.osrs_rsn
            if not name:
                raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your Old School username using the `set07rsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url = f'http://services.runescape.com/m=hiscore_oldschool/index_lite.ws?player={name}'.replace(' ', '%20')

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
            data = await r.text()

        lines = data.split('\n')
        try:
            lines = lines[:len(skills_07)]
        except:
            raise commands.CommandError(message=f'Error accessing hiscores, please try again later.')

        levels = []

        for i, line in enumerate(lines):
            lines[i] = line.split(',')
            levels.append(lines[i][1])

        stats_interface: Array = imageio.imread('images/stats_interface_empty.png')
            
        draw_num(stats_interface, levels[0], 175, 257, yellow, True)

        for i, index in enumerate(skill_indices):
            level = levels[1:][index]
            if index == 3:
                level = max(int(level), 10)

            x = 52 + 63 * (i % 3)
            y = 21 + 32 * (i // 3)

            draw_num(stats_interface, level, x, y, yellow, True)

            x += 13
            y += 13

            draw_num(stats_interface, level, x, y, yellow, True)

        imageio.imwrite('images/07stats.png', stats_interface)

        with open('images/07stats.png', 'rb') as f:
            stats_image = io.BytesIO(f.read())
        with open('images/osrs.png', 'rb') as f:
            osrs_icon = io.BytesIO(f.read())
        
        stats_image = discord.File(stats_image, filename='07stats.png')
        osrs_icon = discord.File(osrs_icon, filename='osrs.png')

        hiscore_page_url = f'https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={name}'.replace(' ', '+')
        colour = 0x00b2ff
        timestamp = datetime.now(UTC)
        embed = discord.Embed(title=name, colour=colour, timestamp=timestamp, url=hiscore_page_url)
        embed.set_author(name='Old School RuneScape HiScores', url='https://secure.runescape.com/m=hiscore_oldschool/overall', icon_url='attachment://osrs.png')
       #  player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://07stats.png')

        await ctx.send(files=[stats_image, osrs_icon], embed=embed)
    
    @commands.command(name='07compare')
    @commands.cooldown(1, 40, commands.BucketType.user)
    async def _07compare(self, ctx: commands.Context, name_1="", name_2=""):
        '''
        Compare two players on OSRS HiScores
        If either of the user names contain spaces, make sure you surround them by quotation marks.
        E.g.: `-07compare "Player 1" "Player 2"`
        If you have set your username via `-set07rsn`, you can give only 1 username to compare a player to yourself.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if len(ctx.message.mentions) >= 2:
            name_1 = ctx.message.mentions[0].display_name
            name_2 = ctx.message.mentions[1].display_name

            user_1 = await User.get(ctx.message.mentions[0].id)
            if user_1:
                name_1 = user_1.osrs_rsn
            user_2 = await User.get(ctx.message.mentions[1].id)
            if user_2:
                name_2 = user_2.osrs_rsn
        elif ctx.message.mentions:
            if name_1 == ctx.message.mentions[0].mention:
                name_1 = ctx.message.mentions[0].display_name
                user_1 = await User.get(ctx.message.mentions[0].id)
                if user_1:
                    name_1 = user_1.osrs_rsn
            else:
                name_2 = ctx.message.mentions[0].display_name
                user_2 = await User.get(ctx.message.mentions[0].id)
                if user_2:
                    name_2 = user_2.osrs_rsn

        if not name_1:
            raise commands.CommandError(message=f'Required argument missing: `RSN_1`. Please add a username as argument')
        elif not name_2:
            user = await User.get(ctx.author.id)
            if user:
                name_2 = name_1
                name_1 = user.osrs_rsn
            if not name_2:
                raise commands.CommandError(message=f'Required argument missing: `RSN_2`. You can set your Old School username using the `set07rsn` command, or add a second username as argument.')
        
        for name in [name_1, name_2]:
            if len(name) > 12:
                raise commands.CommandError(message=f'Invalid argument: `{name}`.')
            if re.match('^[A-z0-9 -]+$', name) is None:
                raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        
        level_list = []
        
        for name in [name_1, name_2]:
            url = f'http://services.runescape.com/m=hiscore_oldschool/index_lite.ws?player={name}'.replace(' ', '%20')

            r = await self.bot.aiohttp.get(url)
            async with r:
                if r.status != 200:
                    raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
                data = await r.text()

            lines = data.split('\n')
            lines = lines[:len(skills_07)]

            levels = []

            for i, line in enumerate(lines):
                lines[i] = line.split(',')
                levels.append(lines[i][1])
            
            level_list.append(levels)
        
        stats_interface_1 = imageio.imread('images/stats_interface_empty.png')
        stats_interface_2 = copy.deepcopy(stats_interface_1)
        interfaces = [stats_interface_1, stats_interface_2]

        for i, levels in enumerate(level_list):
            stats_interface = interfaces[i]
            draw_num(stats_interface, levels[0], 175, 257, yellow, True)

            for i, index in enumerate(skill_indices):
                level = levels[1:][index]
                if index == 3:
                    level = max(int(level), 10)

                x = 52 + 63 * (i % 3)
                y = 21 + 32 * (i // 3)

                draw_num(stats_interface, level, x, y, yellow, True)

                x += 13
                y += 13

                draw_num(stats_interface, level, x, y, yellow, True)
        
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
        
        compare_image = np.hstack((stats_interface_1, stats_interface_2))
        imageio.imwrite('images/07compare.png', compare_image)

        with open('images/07compare.png', 'rb') as f:
            compare_image = io.BytesIO(f.read())
        with open('images/osrs.png', 'rb') as f:
            osrs_icon = io.BytesIO(f.read())
        
        compare_image = discord.File(compare_image, filename='07compare.png')
        osrs_icon = discord.File(osrs_icon, filename='osrs.png')

        hiscore_page_url = f'https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={name_1}'.replace(' ', '+')
        embed = discord.Embed(title=f'{name_1}, {name_2}', colour=0x00b2ff, timestamp=datetime.now(UTC), url=hiscore_page_url)
        embed.set_author(name='Old School RuneScape HiScores', url='https://secure.runescape.com/m=hiscore_oldschool/overall', icon_url='attachment://osrs.png')
        # player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://07compare.png')

        await ctx.send(files=[compare_image, osrs_icon], embed=embed)

    @commands.command(name='07gainz', pass_context=True, aliases=['07gains', 'osrsgainz', 'osrsgains'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _07gainz(self, ctx: commands.Context, *username):
        '''
        Get OSRS gains by username.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name = None
        if ctx.message.mentions:
            name = ctx.message.mentions[0].display_name
            user = await User.get(ctx.message.mentions[0].id)
            if user:
                name = user.osrs_rsn
        else:
            name = ' '.join(username)

        if not name:
            user = await User.get(ctx.author.id)
            if user:
                name = user.osrs_rsn
            if not name:
                raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your Old School username using the `set07rsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url_day = f'https://api.wiseoldman.net/v2/players/{name}/gained?period=day'.replace(' ', '-')
        url_week = f'https://api.wiseoldman.net/v2/players/{name}/gained?period=week'.replace(' ', '-')

        r = await self.bot.aiohttp.get(url_day, headers={'x-user-agent': config['wom_user_agent'], 'x-api-key': config['wom_api_key']})
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not fetch xp gains for: `{name}`.')
            daily_data = await r.json()

        r = await self.bot.aiohttp.get(url_week, headers={'x-user-agent': config['wom_user_agent'], 'x-api-key': config['wom_api_key']})
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not fetch xp gains for: `{name}`.')
            weekly_data = await r.json()

        skills = []
        for i, (skill_name, skill_data) in enumerate(daily_data['data']['skills'].items()):
            skill = {
                'xp': format_float(skill_data['experience']['end']), 
                'today': format_float(skill_data['experience']['gained']), 
                'week': format_float(weekly_data['data']['skills'][skill_name]['experience']['gained'])
            }
            skills.append(skill)

        skill_chars = 14
        xp_chars = max(max([len(skill['xp']) for skill in skills]), len('XP'))+1
        today_chars = max(max([len(skill['today']) for skill in skills]), len('Today'))+1
        week_chars = max(max([len(skill['week']) for skill in skills]), len('This Week'))+1

        msg = '.-' + '-'*skill_chars + '--' + '-'*xp_chars + '--' + '-'*today_chars + '--' + '-'*week_chars + '.'
        width = len(msg)

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

        embed = discord.Embed(title=f'OSRS gains for {name}', colour=discord.Colour.blue(), timestamp=datetime.now(UTC), description=msg, url=f'https://wiseoldman.net/players/{name}/overview/skilling'.replace(' ', '-'))
        embed.set_author(name=f'Wise Old Man', url=f'https://wiseoldman.net/players/{name}/overview/skilling'.replace(' ', '-'), icon_url='https://wiseoldman.net/img/logo.png')

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rs3stats'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def stats(self, ctx: commands.Context, *username):
        '''
        Get RS3 hiscores info by username.
        '''

        self.bot.increment_command_counter()
        await ctx.channel.typing()
        
        name = None
        if ctx.message.mentions:
            name = ctx.message.mentions[0].display_name
            user = await User.get(ctx.message.mentions[0].id)
            if user:
                name = user.rsn
        else:
            name = ' '.join(username)

        if not name:
            user = await User.get(ctx.author.id)
            if user:
                name = user.rsn
            if not name:
                raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your username using the `setrsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url = f'http://services.runescape.com/m=hiscore/index_lite.ws?player={name}'.replace(' ', '%20')

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
            data = await r.text()

        lines = data.split('\n')
        lines = lines[:len(skills_rs3)]

        levels = []
        xp_list = []

        for i, line in enumerate(lines):
            lines[i] = line.split(',')
            levels.append(lines[i][1])
            xp_list.append(lines[i][2])

        stats_interface = imageio.imread('images/stats_interface_empty_rs3.png')
            
        draw_num(stats_interface, levels[0], 73, 290, white, False)
        
        virtual_total_delta = 0

        for i, index in enumerate(skill_indices_rs3):
            level = max(int(levels[1:][index]), 1)
            if index == 3:
                level = max(level, 10)
            xp = xp_list[1:][index]
            if index != 26:
                virtual_level = max(xp_to_level(xp), level)
                if virtual_level - level > 0:
                    virtual_total_delta += virtual_level - level
            else:
                virtual_level = level

            x = 44 + 62 * (i % 3)
            y = 14 + 27 * (i // 3)

            draw_num(stats_interface, virtual_level, x, y, orange, False)

            x += 15
            y += 12

            draw_num(stats_interface, virtual_level, x, y, orange, False)
        
        draw_num(stats_interface, int(levels[0]) + virtual_total_delta, 73, 302, green, False)

        combat = combat_level(int(levels[1]), int(levels[3]), int(levels[2]), max(int(levels[4]), 10), int(levels[7]), int(levels[5]), int(levels[6]), int(levels[24]))

        draw_num(stats_interface, combat, 165, 295, white, False)

        imageio.imwrite('images/rs3stats.png', stats_interface)

        with open('images/rs3stats.png', 'rb') as f:
            stats_image = io.BytesIO(f.read())
        with open('images/rs3.png', 'rb') as f:
            rs3_icon = io.BytesIO(f.read())
        
        stats_image = discord.File(stats_image, filename='rs3stats.png')
        rs3_icon = discord.File(rs3_icon, filename='rs3.png')

        hiscore_page_url = f'https://secure.runescape.com/m=hiscore/compare?user1={name}'.replace(' ', '+')
        colour = 0x00b2ff
        timestamp = datetime.now(UTC)
        embed = discord.Embed(title=name, colour=colour, timestamp=timestamp, url=hiscore_page_url)
        embed.set_author(name='RuneScape HiScores', url='https://secure.runescape.com/m=hiscore/ranking', icon_url='attachment://rs3.png')
        # player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://rs3stats.png')

        await ctx.send(files=[stats_image, rs3_icon], embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def compare(self, ctx: commands.Context, name_1="", name_2=""):
        '''
        Compare two players on RuneScape HiScores
        If either of the user names contain spaces, make sure you surround them by quotation marks.
        E.g.: `-compare "Player 1" "Player 2"`
        If you have set your username via `-setrsn`, you can give only 1 username to compare a player to yourself.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if len(ctx.message.mentions) >= 2:
            name_1 = ctx.message.mentions[0].display_name
            name_2 = ctx.message.mentions[1].display_name

            user_1 = await User.get(ctx.message.mentions[0].id)
            if user_1:
                name_1 = user_1.rsn
            user_2 = await User.get(ctx.message.mentions[1].id)
            if user_2:
                name_2 = user_2.rsn
        elif ctx.message.mentions:
            if name_1 == ctx.message.mentions[0].mention:
                name_1 = ctx.message.mentions[0].display_name
                user_1 = await User.get(ctx.message.mentions[0].id)
                if user_1:
                    name_1 = user_1.rsn
            else:
                name_2 = ctx.message.mentions[0].display_name
                user_2 = await User.get(ctx.message.mentions[0].id)
                if user_2:
                    name_2 = user_2.rsn

        if not name_1:
            raise commands.CommandError(message=f'Required argument missing: `RSN_1`. Please add a username as argument')
        elif not name_2:
            user = await User.get(ctx.author.id)
            if user:
                name_2 = name_1
                name_1 = user.rsn
            if not name_2:
                raise commands.CommandError(message=f'Required argument missing: `RSN_2`. You can set your username using the `setrsn` command, or add a second username as argument.')
        
        for name in [name_1, name_2]:
            if len(name) > 12:
                raise commands.CommandError(message=f'Invalid argument: `{name}`.')
            if re.match('^[A-z0-9 -]+$', name) is None:
                raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        
        level_list = []
        exp_list = []
        
        for name in [name_1, name_2]:
            url = f'http://services.runescape.com/m=hiscore/index_lite.ws?player={name}'.replace(' ', '%20')

            r = await self.bot.aiohttp.get(url)
            async with r:
                if r.status != 200:
                    raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
                data = await r.text()

            lines = data.split('\n')
            lines = lines[:len(skills_rs3)]

            levels = []
            xp_list = []

            for i, line in enumerate(lines):
                lines[i] = line.split(',')
                levels.append(lines[i][1])
                xp_list.append(lines[i][2])
            
            level_list.append(levels)
            exp_list.append(xp_list)
        
        stats_interface_1 = imageio.imread('images/stats_interface_empty_rs3.png')
        stats_interface_2 = copy.deepcopy(stats_interface_1)
        interfaces = [stats_interface_1, stats_interface_2]

        for i, levels in enumerate(level_list):
            xp_list = exp_list[i]
            stats_interface = interfaces[i]

            draw_num(stats_interface, int(levels[0]), 73, 290, white, False)

            virtual_total_delta = 0

            for j, index in enumerate(skill_indices_rs3):
                level = max(int(levels[1:][index]), 1)
                if index == 3:
                    level = max(level, 10)
                xp = int(xp_list[1:][index])
                if index != 26:
                    virtual_level = max(xp_to_level(xp), level)
                    if virtual_level - level > 0:
                        virtual_total_delta += virtual_level - level
                else:
                    virtual_level = level

                x = 44 + 62 * (j % 3)
                y = 14 + 27 * (j // 3)

                draw_num(stats_interface, virtual_level, x, y, orange, False)

                x += 15
                y += 12

                draw_num(stats_interface, virtual_level, x, y, orange, False)
            
            draw_num(stats_interface, int(levels[0]) + virtual_total_delta, 73, 302, green, False)

            combat = combat_level(int(levels[1]), int(levels[3]), int(levels[2]), max(int(levels[4]), 10), int(levels[7]), int(levels[5]), int(levels[6]), int(levels[24]))

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
        
        compare_image = np.hstack((stats_interface_1, stats_interface_2))
        imageio.imwrite('images/compare.png', compare_image)

        with open('images/compare.png', 'rb') as f:
            compare_image = io.BytesIO(f.read())
        with open('images/rs3.png', 'rb') as f:
            rs3_icon = io.BytesIO(f.read())
        
        compare_image = discord.File(compare_image, filename='compare.png')
        rs3_icon = discord.File(rs3_icon, filename='rs3.png')

        hiscore_page_url = f'https://secure.runescape.com/m=hiscore/compare?user1={name_1}'.replace(' ', '+')
        embed = discord.Embed(title=f'{name_1}, {name_2}', colour=0x00b2ff, timestamp=datetime.now(UTC), url=hiscore_page_url)
        embed.set_author(name='RuneScape HiScores', url='https://secure.runescape.com/m=hiscore/ranking', icon_url='attachment://rs3.png')
        # player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://compare.png')

        await ctx.send(files=[compare_image, rs3_icon], embed=embed)

    @commands.command(pass_context=True, aliases=['gains', 'rs3gainz', 'rs3gains'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def gainz(self, ctx: commands.Context, *username):
        '''
        Get RS3 gains by username.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name = None
        if ctx.message.mentions:
            name = ctx.message.mentions[0].display_name
            user = await User.get(ctx.message.mentions[0].id)
            if user:
                name = user.rsn
        else:
            name = ' '.join(username)

        if not name:
            user = await User.get(ctx.author.id)
            if user:
                name = user.rsn
            if not name:
                raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your username using the `setrsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url = f'https://api.runepixels.com/players/{name}'.replace(' ', '-')

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find xp gains for: `{name}`.')
            data = await r.json()

        yday_url = f'https://api.runepixels.com/players/{data["id"]}/xp?timeperiod=1'
        r = await self.bot.aiohttp.get(yday_url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find xp gains for: `{name}`.')
            yday_data = await r.json()

        week_url = f'https://api.runepixels.com/players/{data["id"]}/xp?timeperiod=2'
        r = await self.bot.aiohttp.get(week_url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find xp gains for: `{name}`.')
            week_data = await r.json()

        skills = [data['overall']] + data['skills']
        for i, _ in enumerate(skills):
            skills[i]['xpDelta'] = format_float(skills[i]['xpDelta'])
            skills[i]['yday'] = format_float(yday_data[i]['xp'])
            skills[i]['week'] = format_float(week_data[i]['xp'])

        skill_chars = 14
        today_chars = max(max([len(skill['xpDelta']) for skill in skills]), len('Today'))+1
        yday_chars = max(max([len(skill['yday']) for skill in skills]), len('Yesterday'))+1
        week_chars = max(max([len(skill['week']) for skill in skills]), len('This Week'))+1

        msg = '.-' + '-'*skill_chars + '--' + '-'*today_chars + '--' + '-'*yday_chars + '--' + '-'*week_chars + '.'
        width = len(msg)

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
    async def time(self, ctx: commands.Context):
        '''
        Get current RuneScape game time.
        '''
        self.bot.increment_command_counter()

        time = datetime.now(UTC)
        time = time.strftime('%H:%M')

        await ctx.send(f'Current game time is: `{time}`.')
    
    @commands.command(aliases=['wax', 'viswax', 'goldberg'])
    async def vis(self, ctx: commands.Context):
        '''
        Get today's rune combination for the Rune Goldberg machine, used to make vis wax.
        '''
        self.bot.increment_command_counter()

        global vis_wax_embed
        await ctx.send(embed=vis_wax_embed)
    
    @commands.command(aliases=['lvl'])
    async def level(self, ctx: commands.Context, lvl=0):
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

        xp = level_to_xp(lvl)
        xp = f'{xp:,}'

        await ctx.send(f'XP required for level `{lvl}`: `{xp}`')
    
    @commands.command(aliases=['xp', 'exp'])
    async def experience(self, ctx: commands.Context, lvl_start_or_xp=0, lvl_end=0):
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
            xp_start = lvl_start_or_xp
            level = xp_to_level(xp_start)
            level_xp = level_to_xp(level)
            xp_start = f'{xp_start:,}'
            level_xp = f'{level_xp:,}'
            next_lvl = level+1
            next_xp = level_to_xp(next_lvl)
            next_xp = f'{next_xp:,}'
            await ctx.send(f'At `{xp_start}` XP, you are level `{level}`, which requires `{level_xp}` XP.\nYou will reach level `{next_lvl}` at `{next_xp} XP.`')
        
        else:
            if lvl_start_or_xp > 126:
                xp_start = lvl_start_or_xp
            else:
                xp_start = level_to_xp(lvl_start_or_xp)
            xp_end = level_to_xp(lvl_end)
            xp_dif = xp_end - xp_start
            xp_dif = f'{xp_dif:,}'
            if lvl_start_or_xp > 126:
                await ctx.send(f'To reach level `{lvl_end}` from `{lvl_start_or_xp}` XP, you will need to gain `{xp_dif}` XP.')
            else:
                await ctx.send(f'To reach level `{lvl_end}` from level `{lvl_start_or_xp}`, you will need to gain `{xp_dif}` XP.')
            
    
    @commands.command(aliases=['actions'])
    async def xph(self, ctx: commands.Context, lvl_start=0, lvl_end=0, xp_rate=0.0):
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

        start_xp, end_xp = False, False
        if lvl_start > 126:
            start_xp = True
        if lvl_end > 126:
            end_xp = True
        if (start_xp or end_xp) and (lvl_start > 200e6 or lvl_end > 200e6):
            raise commands.CommandError(message=f'Invalid argument. Start and End xp values can be at most 200M.')

        xp_start = lvl_start if start_xp else level_to_xp(lvl_start)
        xp_end = lvl_end if end_xp else level_to_xp(lvl_end)
        if xp_start >= xp_end:
            raise commands.CommandError(message=f'Invalid arguments: Start xp must be lower than end xp.')

        xp_dif = xp_end - xp_start

        hours_or_actions = math.ceil(xp_dif / xp_rate)
        hours_or_actions = f'{hours_or_actions:,}'
        xp_dif = f'{xp_dif:,}'
        xp_rate = f'{xp_rate:,}'

        await ctx.send(f'To reach {"level " if not end_xp else ""}`{lvl_end}`{" XP" if end_xp else ""} from {"level " if not start_xp else ""}`{lvl_start}`{" XP" if start_xp else ""}, you will need to gain `{xp_dif}` XP. This will take `{hours_or_actions}` hours/actions at an XP rate of `{xp_rate}` per hour/action.')

    @commands.command()
    async def pvm(self, ctx: commands.Context):
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

        images = ['images/Araxxor.png', 'images/Vorago.png', 'images/Ahrim.png']

        with open(random.choice(images), 'rb') as f:
                file = io.BytesIO(f.read())

        image = discord.File(file, filename='pvm_boss.png')

        embed.set_thumbnail(url='attachment://pvm_boss.png')

        await ctx.send(file=image, embed=embed)
    
    @commands.command()
    async def dry(self, ctx: commands.Context, droprate='', attempts=''):
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
        if '1/' in droprate:
            droprate = droprate.replace('1/', '')
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

        result = (1-droprate)**attempts
        result *= 100

        await ctx.send(f'```Drop rate: {droprate}\nAttempts: {attempts}\nProbability of not getting the drop: {result}%```')

    @commands.command(aliases=['cb', 'rs3cb', 'rs3combat'])
    async def combat(self, ctx: commands.Context, *username):
        '''
        Calculate the combat level of a RS3 player.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name = None
        if ctx.message.mentions:
            name = ctx.message.mentions[0].display_name
            user = await User.get(ctx.message.mentions[0].id)
            if user:
                name = user.rsn
        else:
            name = ' '.join(username)

        if not name:
            user = await User.get(ctx.author.id)
            if user:
                name = user.rsn
            if not name:
                raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your username using the `setrsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url = f'http://services.runescape.com/m=hiscore/index_lite.ws?player={name}'.replace(' ', '%20')
        hiscore_page_url = f'https://secure.runescape.com/m=hiscore/compare?user1={name}'.replace(' ', '+')

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
            data = await r.text()

        lines = data.split('\n')
        lines = lines[:len(skills_rs3)]

        levels = []
        xp_list = []

        for i, line in enumerate(lines):
            lines[i] = line.split(',')
            levels.append(lines[i][1])
            xp_list.append(lines[i][2])

        attack, strength, defence, constitution, magic, ranged, prayer, summoning = int(levels[1]), int(levels[3]), int(levels[2]), max(int(levels[4]), 10), int(levels[7]), int(levels[5]), int(levels[6]), int(levels[24])
        combat = combat_level(attack, strength, defence, constitution, magic, ranged, prayer, summoning)

        cb_skills = [attack, strength, defence, constitution, magic, ranged, prayer, summoning]
        original_cb_skills = copy.deepcopy(cb_skills)
        cb_skill_names = ['Attack', 'Strength', 'Defence', 'Constitution', 'Magic', 'Ranged', 'Prayer', 'Summoning']
        levels_required = [0, 0, 0, 0, 0, 0, 0, 0]

        description = f'**{name}**\'s combat level is: `{combat}`'

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
    async def _07combat(self, ctx: commands.Context, *username):
        '''
        Calculate the combat level of a OSRS player.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        name = None
        if ctx.message.mentions:
            name = ctx.message.mentions[0].display_name
            user = await User.get(ctx.message.mentions[0].id)
            if user:
                name = user.osrs_rsn
        else:
            name = ' '.join(username)

        if not name:
            user = await User.get(ctx.author.id)
            if user:
                name = user.osrs_rsn
            if not name:
                raise commands.CommandError(message=f'Required argument missing: `RSN`. You can set your Old School username using the `set07rsn` command.')

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        url = f'http://services.runescape.com/m=hiscore_oldschool/index_lite.ws?player={name}'.replace(' ', '%20')
        hiscore_page_url = f'https://secure.runescape.com/m=hiscore_oldschool/hiscorepersonal?user1={name}'.replace(' ', '+')

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find hiscores for: `{name}`.')
            data = await r.text()

        lines = data.split('\n')
        try:
            lines = lines[:len(skills_07)]
        except:
            raise commands.CommandError(message=f'Error accessing hiscores, please try again later.')

        levels = []

        for i, line in enumerate(lines):
            lines[i] = line.split(',')
            levels.append(lines[i][1])

        attack, strength, defence, hitpoints, magic, ranged, prayer = int(levels[1]), int(levels[3]), int(levels[2]), max(int(levels[4]), 10), int(levels[7]), int(levels[5]), int(levels[6])
        combat = osrs_combat_level(attack, strength, defence, hitpoints, magic, ranged, prayer)

        cb_skills = [attack, strength, defence, hitpoints, magic, ranged, prayer]
        original_cb_skills = copy.deepcopy(cb_skills)
        cb_skill_names = ['Attack', 'Strength', 'Defence', 'Hitpoints', 'Magic', 'Ranged', 'Prayer']
        levels_required = [0, 0, 0, 0, 0, 0, 0]

        description = f'**{name}**\'s combat level is: `{combat}`'

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

async def setup(bot: Bot):
    await bot.add_cog(Runescape(bot))
