import discord
from discord.ext import commands, tasks
import sys
sys.path.append('../')
from main import config_load, increment_command_counter, User, NewsPost, RS3Item, OSRSItem
import re
from datetime import datetime, timedelta
import praw
import matplotlib.pyplot as plt
from matplotlib.dates import date2num
import matplotlib.dates as mdates
from matplotlib.dates import DateFormatter
import math
from bs4 import BeautifulSoup
from utils import is_int, is_float, draw_num, xp_to_level, combat_level, draw_outline_osrs, draw_outline_rs3
from utils import level_to_xp, time_diff_to_string, osrs_combat_level
import io
import imageio
import copy
import numpy as np
import random
from youtubesearchpython import Playlist, playlist_from_channel_id
from utils import float_to_formatted_string

config = config_load()

reddit = praw.Reddit(client_id=config['redditID'],
                     client_secret=config['redditSecret'],
                     password=config['redditPW'],
                     user_agent=config['user_agent'],
                     username=config['redditName'])

graph_cache_07 = {}

graph_cache_rs3 = {}

skills_07 = ['Overall', 'Attack', 'Defence', 'Strength', 'Hitpoints', 'Ranged',
            'Prayer', 'Magic', 'Cooking', 'Woodcutting', 'Fletching', 'Fishing',
            'Firemaking', 'Crafting', 'Smithing', 'Mining', 'Herblore', 'Agility',
            'Thieving', 'Slayer', 'Farming', 'Runecraft', 'Hunter', 'Construction']

osrs_skill_emojis = ['<:Attack_icon:624387168982269952>', '<:Defence_icon:624387168655114263>', '<:Strength_icon:624387169145847808>', '<:Hitpoints_icon:624387169058029568>', '<:Ranged_icon:624387169028538378>',
            '<:Prayer_icon:624387169129332743>', '<:Magic_icon:624387168726548495>', '<:Cooking_icon:624387169066287104>', '<:Woodcutting_icon:624387168844120065>', '<:Fletching_icon:624387168885800981>', '<:Fishing_icon:624387169024213008>',
            '<:Firemaking_icon:624387169011630120>', '<:Crafting_icon:624387169003503616>', '<:Smithing_icon:624387168898383903>', '<:Mining_icon:624387168785137669>', '<:Herblore_icon:624387169053704195>', '<:Agility_icon:624387168609239048>',
            '<:Thieving_icon:624387169015955475>', '<:Slayer_icon:624387168822886435>', '<:Farming_icon:624387168990658570>', '<:Runecraft_icon:624387169041121290>', '<:Hunter_icon:624387169070350336>', '<:Construction_icon:624387168995115041>', '<:Stats_icon:624389156344430594>']

skills_rs3 = ['Overall', 'Attack', 'Defence', 'Strength', 'Constitution', 'Ranged',
            'Prayer', 'Magic', 'Cooking', 'Woodcutting', 'Fletching', 'Fishing',
            'Firemaking', 'Crafting', 'Smithing', 'Mining', 'Herblore', 'Agility',
            'Thieving', 'Slayer', 'Farming', 'Runecrafting', 'Hunter', 'Construction',
            'Summoning', 'Dungeoneering', 'Divination', 'Invention', 'Archaeology']

rs3_skill_emojis = ['<:Attack:962315037668696084>', '<:Defence:962315037396074517>', '<:Strength:962315037538668555>', '<:Constitution:962315037601562624>', '<:Ranged:962315037177970769>',
            '<:Prayer:962315037509300224>', '<:Magic:962315037207318579>', '<:Cooking:962315037563817994>', '<:Woodcutting:962315037593194516>', '<:Fletching:962315037664493568>', '<:Fishing:962315037630951484>',
            '<:Firemaking:962315037542871070>', '<:Crafting:962315037647732766>', '<:Smithing:962315037530271744>', '<:Mining:962315037526085632>', '<:Herblore:962315037563834398>', '<:Agility:962315037635121162>',
            '<:Thieving:962315037106634753>', '<:Slayer:962315037278609419>', '<:Farming:962315037484130324>', '<:Runecrafting:962315037538676736>', '<:Hunter:962315037261848607>', '<:Construction:962315037626761226>',
            '<:Summoning:962315037559631892>', '<:Dungeoneering:962315037815492648>', '<:Divination:962315037727412245>', '<:Invention:962315037723222026>', '<:Archaeology:962315037509316628>']
  
indices = [0, 3, 14, 2, 16, 13, 1, 15, 10, 4, 17, 7, 5, 12, 11, 6, 9, 8, 20, 18, 19, 22, 21]
indices_rs3 = [0, 3, 14, 2, 16, 13, 1, 15, 10, 4, 17, 7, 5, 12, 11, 6, 9, 8, 20, 18, 19, 22, 21, 23, 24, 25, 26, 27]

cb_indices_rs3 = [0, 2, 1, 3, 6, 4, 5, 23]
cb_indices_osrs = [0, 2, 1, 3, 6, 4, 5]

yellow = [255, 255, 0, 255]
orange = [255, 140, 0, 255]
white = [255, 255, 255, 255]
green = [0, 221, 0, 255]
red = [221, 0, 0, 255]

def translate_age(age):
    age = age.replace('dagen', 'days')
    age = age.replace('dag', 'day')
    age = age.replace('weken', 'weeks')
    age = age.replace('maanden', 'months')
    age = age.replace('maand', 'month')
    age = age.replace('jaren', 'years')
    age = age.replace('jaar', 'year')
    age = age.replace('geleden', 'ago')
    return age

vis_wax_embed = discord.Embed(title='Vis wax combination', colour=0x00b2ff, timestamp=datetime.utcnow(), description='Today\'s vis wax combo has not been released yet.')
vis_wax_combo = []
vis_wax_released = False
vis_wax_check_frequency = 60*15 # seconds
vis_time = 0

'''
rotation_count: number of rotations
interval: frequency of rotation changes
offset: 1 jan 1970 + offset = starting day for rot 0
'''
def get_rotation(t, rotation_count, interval, offset):
    t = t.replace(second=0, microsecond=0)
    interval = timedelta(days=interval)
    offset = timedelta(days=offset)

    t_0 = datetime(1970, 1, 1, 0, 0, 0, 0) + offset
    rotation = ((t - t_0) // interval) % rotation_count
    time_to_next = interval - ((t - t_0) % interval)

    return (rotation, time_to_next)

def araxxor(t):
    rotation, next = get_rotation(t, 3, 4, 9)
    return (['Path 1 (Minions)', 'Path 2 (Acid)', 'Path 3 (Darkness)'][rotation], time_diff_to_string(next))

def vorago(t):
    rotation, next = get_rotation(t, 6, 7, 6)
    return (['Ceiling collapse', 'Scopulus', 'Vitalis', 'Green bomb', 'Team split', 'The end'][rotation], time_diff_to_string(next))

def rots(t):
    rotations = [
        [['Dharok','Torag','Verac'],['Karil','Ahrim','Guthan']],
		[['Karil','Torag','Guthan'],['Ahrim','Dharok','Verac']],
		[['Karil','Guthan','Verac'],['Ahrim','Torag','Dharok']],
		[['Guthan','Torag','Verac'],['Karil','Ahrim','Dharok']],
		[['Karil','Torag','Verac'],['Ahrim','Guthan','Dharok']],
		[['Ahrim','Guthan','Dharok'],['Karil','Torag','Verac']],
		[['Karil','Ahrim','Dharok'],['Guthan','Torag','Verac']],
		[['Ahrim','Torag','Dharok'],['Karil','Guthan','Verac']],
		[['Ahrim','Dharok','Verac'],['Karil','Torag','Guthan']],
		[['Karil','Ahrim','Guthan'],['Torag','Dharok','Verac']],
		[['Ahrim','Torag','Guthan'],['Karil','Dharok','Verac']],
		[['Ahrim','Guthan','Verac'],['Karil','Torag','Dharok']],
		[['Karil','Ahrim','Torag'],['Guthan','Dharok','Verac']],
		[['Karil','Ahrim','Verac'],['Dharok','Torag','Guthan']],
		[['Ahrim','Torag','Verac'],['Karil','Dharok','Guthan']],
		[['Karil','Dharok','Guthan'],['Ahrim','Torag','Verac']],
		[['Dharok','Torag','Guthan'],['Karil','Ahrim','Verac']],
		[['Guthan','Dharok','Verac'],['Karil','Ahrim','Torag']],
		[['Karil','Torag','Dharok'],['Ahrim','Guthan','Verac']],
		[['Karil','Dharok','Verac'],['Ahrim','Torag','Guthan']]
    ]

    rotation, next = get_rotation(t, 20, 1, 0)
    return (rotations[rotation], time_diff_to_string(next))

class Runescape(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.vis_wax.start()

    def cog_unload(self):
        self.vis_wax.cancel()
    
    @tasks.loop(seconds=60)
    async def vis_wax(self):
        '''
        Loop to track location update activity
        '''
        global vis_time
        global vis_wax_released
        global vis_wax_check_frequency
        vis_time += 60

        if vis_wax_released:
            if vis_time > vis_wax_check_frequency:
                vis_time = 0
            else:
                return

        global vis_wax_embed
        global vis_wax_combo

        now = datetime.utcnow()
        colour = 0x00b2ff

        reset = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        if now < reset + timedelta(seconds=vis_wax_check_frequency):
            vis_wax_released = False
            vis_wax_embed = discord.Embed(title='Vis wax combination', colour=colour, timestamp=now, description='Today\'s vis wax combo has not been released yet.')

        r = await self.bot.aiohttp.get('https://warbandtracker.com/goldberg/index.php')
        async with r:
            data = await r.text()

            bs = BeautifulSoup(data, "html.parser")
            table_body = bs.find('table')
            rows = table_body.find_all('tr')
            columns = []
            for row in rows:
                cols = row.find_all('td')
                cols = [x.text.strip() for x in cols]
                columns.append(cols)
            
            first_rune, second_runes_temp = columns[1][0], columns[3]

            first_rune, acc_0 = first_rune.split('Reported by ')
            acc_0 = float(acc_0[:len(acc_0)-2])

            second_runes = []
            for rune in second_runes_temp:
                rune, acc = rune.split('Reported by ')
                second_runes.append([rune, float(acc[:len(acc)-2])])
            
            config = config_load()
            emoji_server = self.bot.get_guild(int(config['emoji_server']))
            if not emoji_server:
                return
            second_runes_temp = []
            for emoji in emoji_server.emojis:
                if emoji.name.upper() == first_rune.upper().replace(' ', '_'):
                    first_rune = f'{emoji} {first_rune}'
            for tmp in second_runes:
                second_rune = tmp[0]
                for emoji in emoji_server.emojis:
                    if emoji.name.upper() == second_rune.upper().replace(' ', '_'):
                        second_rune = f'{emoji} {second_rune}'
                        second_runes_temp.append([second_rune, tmp[1]])
            second_runes = second_runes_temp
            
            if vis_wax_released:
                vis_wax_combo = [[first_rune, acc_0], second_runes]
            else:
                if vis_wax_combo == [[first_rune, acc_0], second_runes]:
                    return
                else:
                    vis_wax_combo = [[first_rune, acc_0], second_runes]
                    vis_wax_released = True
            
            vis_wax_embed = discord.Embed(title='Vis wax combination', colour=colour, timestamp=now)
            vis_wax_embed.add_field(name='First rune', value = f'{first_rune} ({acc_0}%)')

            val = '\n'.join([f'{rune} ({acc}%)' for rune, acc in second_runes])
            vis_wax_embed.add_field(name='Second rune', value=val)

            vis_wax_embed.set_footer(text='Powered by Warband Tracker')


    @commands.command(pass_context=True, aliases=['rsn'])
    async def setrsn(self, ctx, *rsn):
        '''
        Sets your Runescape 3 RSN.
        '''
        increment_command_counter()

        name = ' '.join(rsn)

        if not name:
            user = await User.get(ctx.author.id)
            if user:
                await user.update(rsn=None).apply()
                if user.osrs_rsn is None:
                    await user.delete()
                await ctx.send(f'{ctx.author.mention} Your RSN has been removed.')
                return
            raise commands.CommandError(message=f'Required argument missing: `RSN`.')
        
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        
        user = await User.get(ctx.author.id)
        if user:
            await user.update(rsn=name).apply()
        else:
            await User.create(id=ctx.author.id, rsn=name)

        await ctx.send(f'{ctx.author.mention} Your RSN has been set to **{name}**.')

    @commands.command(pass_context=True, aliases=['07rsn'])
    async def set07rsn(self, ctx, *rsn):
        '''
        Sets your Old School Runescape RSN.
        '''
        increment_command_counter()

        name = ' '.join(rsn)

        if not name:
            user = await User.get(ctx.author.id)
            if user:
                await user.update(osrs_rsn=None).apply()
                if user.rsn is None:
                    await user.delete()
                await ctx.send(f'{ctx.author.mention} Your RSN has been removed.')
                return
            raise commands.CommandError(message=f'Required argument missing: `RSN`.')
        
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        
        user = await User.get(ctx.author.id)
        if user:
            await user.update(osrs_rsn=name).apply()
        else:
            await User.create(id=ctx.author.id, osrs_rsn=name)

        await ctx.send(f'{ctx.author.mention} Your Old School RSN has been set to **{name}**.')

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def alog(self, ctx, *username):
        '''
        Get the last 20 activities on a player's adventurer's log.
        '''
        increment_command_counter()
        await ctx.channel.typing()

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

        url = f'https://apps.runescape.com/runemetrics/profile/profile?user={name}&activities=20'.replace(' ', '%20')

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving data, please try again in a minute.')
            data = await r.json()

        if 'error' in data:
            if data['error'] == 'NO_PROFILE':
                raise commands.CommandError(message=f'Could not find adventurer\'s log for: `{name}`.')
            elif data['error'] == 'PROFILE_PRIVATE':
                raise commands.CommandError(message=f'Error: `{name}`\'s adventurer\'s log is set to private.')

        activities = data['activities']

        txt = ''
        for activity in activities:
            txt += f'[{activity["date"]}] {activity["text"]}\n'
        txt = txt.strip()
        txt = f'```{txt}```'

        embed = discord.Embed(title=f'{name}\'s Adventurer\'s log', description=txt, colour=0x00b2ff, timestamp=datetime.utcnow(), url=f'https://apps.runescape.com/runemetrics/app/overview/player/{name.replace(" ", "%20")}')
        embed.set_thumbnail(url=f'https://services.runescape.com/m=avatar-rs/{name.replace(" ", "%20")}/chat.png')

        await ctx.send(embed=embed)


    @commands.command(name='07reddit', pass_context=True, aliases=['osrsreddit'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _07reddit(self, ctx):
        '''
        Get top 5 hot posts from r/2007scape.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        submissions = reddit.subreddit('2007scape').hot(limit=5)

        colour = 0x00b2ff
        timestamp = datetime.utcnow()
        embed = discord.Embed(title=f'/r/2007scape', colour=colour, timestamp=timestamp)

        for s in submissions:
            embed.add_field(name=s.title, value=f'https://www.reddit.com{s.permalink}')

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rsreddit', 'rs3reddit'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def reddit(self, ctx):
        '''
        Get top 5 hot posts from r/runescape.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        submissions = reddit.subreddit('runescape').hot(limit=5)

        colour = 0x00b2ff
        timestamp = datetime.utcnow()
        embed = discord.Embed(title=f'/r/runescape', colour=colour, timestamp=timestamp)

        for s in submissions:
            embed.add_field(name=s.title, value=f'https://www.reddit.com{s.permalink}')

        await ctx.send(embed=embed)

    @commands.command(name='07rsw', pass_context=True, aliases=['07wiki', 'osrswiki'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _07rsw(self, ctx, *query):
        '''
        Get top 5 results for a search on OSRS Wiki.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        search = ''
        for i in query:
            search += i + '+'
        search = search[:len(search)-1]

        if not search:
            raise commands.CommandError(message=f'Required argument missing: `query`.')

        url = f'https://oldschool.runescape.wiki/api.php?action=opensearch&format=json&search={search}'

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving data, please try again in a minute.')
            data = await r.json()

        items = data[1]
        urls = data[3]

        colour = 0x00b2ff
        timestamp = datetime.utcnow()
        embed = discord.Embed(title=f'__Old School RuneScape Wiki__', colour=colour, timestamp=timestamp, url='https://oldschool.runescape.wiki/')
        embed.set_thumbnail(url='https://oldschool.runescape.wiki/images/b/bc/Wiki.png')

        if len(items) > 5:
            items = items[:5]
        elif not items:
            raise commands.CommandError(message=f'Error: no pages matching `{search}`.')

        for i, item in enumerate(items):
            embed.add_field(name=item, value=urls[i], inline=False)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rswiki', 'wiki', 'rs3wiki'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def rsw(self, ctx, *query):
        '''
        Get top 5 results for a search on RS Wiki.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        search = ''
        for i in query:
            search += i + '+'
        search = search[:len(search)-1]

        if not search:
            raise commands.CommandError(message=f'Required argument missing: `query`.')

        url = f'https://runescape.wiki/api.php?action=opensearch&format=json&search={search}'

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving data, please try again in a minute.')
            data = await r.json()

        items = data[1]
        urls = data[3]

        colour = 0x00b2ff
        timestamp = datetime.utcnow()
        embed = discord.Embed(title=f'__RuneScape Wiki__', colour=colour, timestamp=timestamp, url='https://runescape.wiki/')
        embed.set_thumbnail(url='https://runescape.wiki/images/b/bc/Wiki.png')

        if len(items) > 5:
            items = items[:5]
        elif not items:
            raise commands.CommandError(message=f'Error: could not find a page matching `{search}`.')

        for i, item in enumerate(items):
            embed.add_field(name=item, value=urls[i], inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='07news', pass_context=True, aliases=['osrsnews'])
    async def _07news(self, ctx):
        '''
        Get 5 latest OSRS news posts.
        '''
        increment_command_counter()

        news_posts = await NewsPost.query.where(NewsPost.game=='osrs').order_by(NewsPost.time.desc()).gino.all()

        embed = discord.Embed(title=f'Old School RuneScape News')

        for i, post in enumerate(news_posts):
            if i >= 5:
                break
            embed.add_field(name=post.title, value=post.link + '\n' + post.description, inline=False)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rsnews', 'rs3news'])
    async def news(self, ctx):
        '''
        Get 5 latest RS news posts.
        '''
        increment_command_counter()

        news_posts = await NewsPost.query.where(NewsPost.game=='rs3').order_by(NewsPost.time.desc()).gino.all()

        embed = discord.Embed(title=f'RuneScape News')

        for i, post in enumerate(news_posts):
            if i >= 5:
                break
            embed.add_field(name=post.title, value=post.link + '\n' + post.description, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='07price', pass_context=True, aliases=['osrsprice'])
    async def _07price(self, ctx, days='30', *item_name):
        '''
        Get the OSRS GE price for an item.
        Argument "days" is optional, default is 30.
        '''
        increment_command_counter()
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
        timestamp = datetime.utcnow()
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
    async def price(self, ctx, days='30', *item_name):
        '''
        Get the RS3 GE price for an item.
        Argument "days" is optional, default is 30.
        '''
        increment_command_counter()
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
        timestamp = datetime.utcnow()
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
    async def _07stats(self, ctx, *username):
        '''
        Get OSRS hiscores info by username.
        '''
        increment_command_counter()
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

        stats_interface = imageio.imread('images/stats_interface_empty.png')
            
        draw_num(stats_interface, levels[0], 175, 257, yellow, True)

        for i, index in enumerate(indices):
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
        timestamp = datetime.utcnow()
        embed = discord.Embed(title=name, colour=colour, timestamp=timestamp, url=hiscore_page_url)
        embed.set_author(name='Old School RuneScape HiScores', url='https://secure.runescape.com/m=hiscore_oldschool/overall', icon_url='attachment://osrs.png')
       #  player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://07stats.png')

        await ctx.send(files=[stats_image, osrs_icon], embed=embed)
    
    @commands.command(name='07compare')
    @commands.cooldown(1, 40, commands.BucketType.user)
    async def _07compare(self, ctx, name_1="", name_2=""):
        '''
        Compare two players on OSRS HiScores
        If either of the user names contain spaces, make sure you surround them by quotation marks.
        E.g.: `-07compare "Player 1" "Player 2"`
        If you have set your username via `-set07rsn`, you can give only 1 username to compare a player to yourself.
        '''
        increment_command_counter()
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

            for i, index in enumerate(indices):
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
        
        for i, index in enumerate(indices):
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
        embed = discord.Embed(title=f'{name_1}, {name_2}', colour=0x00b2ff, timestamp=datetime.utcnow(), url=hiscore_page_url)
        embed.set_author(name='Old School RuneScape HiScores', url='https://secure.runescape.com/m=hiscore_oldschool/overall', icon_url='attachment://osrs.png')
        # player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://07compare.png')

        await ctx.send(files=[compare_image, osrs_icon], embed=embed)

    @commands.command(name='07gainz', pass_context=True, aliases=['07gains', 'osrsgainz', 'osrsgains'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _07gainz(self, ctx, *username):
        '''
        Get OSRS gains by username.
        '''
        increment_command_counter()
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

        url = f'http://oldschool.runeclan.com/xp-tracker/user/{name}'.replace(' ', '+')

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not fetch xp gains for: `{name}`.')
            data = await r.text()

        try:
            bs = BeautifulSoup(data, "html.parser")
            table_body = bs.find('table')
            rows = table_body.find_all('tr')
            columns = []
            for row in rows:
                cols = row.find_all('td')
                cols = [x.text.strip() for x in cols]
                columns.append(cols)
        except:
            raise commands.CommandError(message=f'Could not find xp gains for: `{name}`. Make sure the profile is not set to private')

        cols = columns[1:]

        skill_chars = 13
        today_chars = max(max([len(col[4]) for col in cols]), len('Today'))+1
        yday_chars = max(max([len(col[5]) for col in cols]), len('Yesterday'))+1
        week_chars = max(max([len(col[6]) for col in cols]), len('This Week'))+1

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
            msg += ' '*week_whitespace + 'This Week' + ' '*week_whitespace + '| '
        else:
            msg += ' '*(math.floor(week_whitespace)) + 'This Week' + ' '*(math.ceil(week_whitespace)) + '|\n'

        msg += '|-' + '-'*skill_chars + '|-' + '-'*today_chars + '|-' + '-'*yday_chars + '|-' + '-'*week_chars + '|\n'

        for i, col in enumerate(cols):
            msg += '| ' + skills_07[i] + ' '*(skill_chars-len(skills_07[i])) + '| ' + ' '*(today_chars-len(col[4])-1) + col[4] + ' | ' + ' '*(yday_chars-len(col[5])-1) + col[5] + ' | ' + ' '*(week_chars-len(col[6])-1) + col[6] + ' |\n'

        msg += "'" + '-'*(width-2) + "'"

        msg = f'```\n{msg}\n```'

        embed = discord.Embed(title=f'OSRS gains for {name}', colour=discord.Colour.blue(), timestamp=datetime.utcnow(), description=msg, url=url)
        embed.set_author(name=f'Runeclan', url=url)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['rs3stats'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def stats(self, ctx, *username):
        '''
        Get RS3 hiscores info by username.
        '''

        increment_command_counter()
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

        for i, index in enumerate(indices_rs3):
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
        timestamp = datetime.utcnow()
        embed = discord.Embed(title=name, colour=colour, timestamp=timestamp, url=hiscore_page_url)
        embed.set_author(name='RuneScape HiScores', url='https://secure.runescape.com/m=hiscore/ranking', icon_url='attachment://rs3.png')
        # player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://rs3stats.png')

        await ctx.send(files=[stats_image, rs3_icon], embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def compare(self, ctx, name_1="", name_2=""):
        '''
        Compare two players on RuneScape HiScores
        If either of the user names contain spaces, make sure you surround them by quotation marks.
        E.g.: `-compare "Player 1" "Player 2"`
        If you have set your username via `-setrsn`, you can give only 1 username to compare a player to yourself.
        '''
        increment_command_counter()
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

            for j, index in enumerate(indices_rs3):
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
        
        for i, index in enumerate(indices_rs3):
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
        embed = discord.Embed(title=f'{name_1}, {name_2}', colour=0x00b2ff, timestamp=datetime.utcnow(), url=hiscore_page_url)
        embed.set_author(name='RuneScape HiScores', url='https://secure.runescape.com/m=hiscore/ranking', icon_url='attachment://rs3.png')
        # player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '+')
        # embed.set_thumbnail(url=player_image_url)

        embed.set_image(url='attachment://compare.png')

        await ctx.send(files=[compare_image, rs3_icon], embed=embed)

    @commands.command(pass_context=True, aliases=['gains', 'rs3gainz', 'rs3gains'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def gainz(self, ctx, *username):
        '''
        Get RS3 gains by username.
        '''
        increment_command_counter()
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

        url = f'https://runepixels.com:5000/players/{name}'.replace(' ', '-')

        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find xp gains for: `{name}`.')
            data = await r.json()

        yday_url = f'https://runepixels.com:5000/players/{data["id"]}/xp?timeperiod=1'
        r = await self.bot.aiohttp.get(yday_url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find xp gains for: `{name}`.')
            yday_data = await r.json()

        week_url = f'https://runepixels.com:5000/players/{data["id"]}/xp?timeperiod=2'
        r = await self.bot.aiohttp.get(week_url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Could not find xp gains for: `{name}`.')
            week_data = await r.json()

        skills = [data['overall']] + data['skills']
        for i, _ in enumerate(skills):
            skills[i]['xpDelta'] = float_to_formatted_string(skills[i]['xpDelta'])
            skills[i]['yday'] = float_to_formatted_string(yday_data[i]['xp'])
            skills[i]['week'] = float_to_formatted_string(week_data[i]['xp'])

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

        embed = discord.Embed(title=f'RS3 gains for {name}', colour=discord.Colour.blue(), timestamp=datetime.utcnow(), description=msg, url=f'https://runepixels.com/players/{name}/skills'.replace(' ', '-'))
        embed.set_author(name=f'RunePixels', url=f'https://runepixels.com/players/{name}/skills'.replace(' ', '-'), icon_url='https://pbs.twimg.com/profile_images/1579124090958479362/LbR9PDfv_400x400.png')

        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['gametime'])
    async def time(self, ctx):
        '''
        Get current RuneScape game time.
        '''
        increment_command_counter()

        time = datetime.utcnow()
        time = time.strftime('%H:%M')

        await ctx.send(f'Current game time is: `{time}`.')

    @commands.command(pass_context=True, aliases=['yt', 'rs3youtube', 'rsyoutube', 'rs3yt', 'rsyt'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def youtube(self, ctx):
        '''
        Get latest videos from RuneScape 3 youtube channel.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        try:
            playlist = Playlist(playlist_from_channel_id('UCGpr8LIrdwrEak3GuZLQPwg'))
            videos = playlist.videos
        except:
            raise commands.CommandError(message=f'Error fetching videos.')

        colour = 0xff0000
        timestamp = datetime.utcnow()
        embed = discord.Embed(title='RuneScape', colour=colour, timestamp=timestamp, url='https://www.youtube.com/runescape/videos')
        embed.set_thumbnail(url='https://imgur.com/JvKu58G.png')

        for i, vid in enumerate(videos):
            if i >= 5:
                break
            else:
                embed.add_field(name=vid['title'], value=vid['link']+'\n'+vid['duration'], inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='07youtube', pass_context=True, aliases=['07yt', 'osrsyoutube', 'osrsyt'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def _07youtube(self, ctx):
        '''
        Get latest videos from OSRS youtube channel.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        try:
            playlist = Playlist(playlist_from_channel_id('UC0j1MpbiTFHYrUjOTwifW_w'))
            videos = playlist.videos
        except:
            raise commands.CommandError(message=f'Error fetching videos.')

        colour = 0xff0000
        timestamp = datetime.utcnow()
        embed = discord.Embed(title='Old School RuneScape', colour=colour, timestamp=timestamp, url='https://www.youtube.com/OldSchoolRSCommunity/videos')
        embed.set_thumbnail(url='https://imgur.com/JvKu58G.png')

        for i, vid in enumerate(videos):
            if i >= 5:
                break
            else:
                embed.add_field(name=vid['title'], value=vid['link']+'\n'+vid['duration'], inline=False)

        await ctx.send(embed=embed)
    
    @commands.command(aliases=['wax', 'viswax', 'goldberg'])
    async def vis(self, ctx):
        '''
        Get today's rune combination for the Rune Goldberg machine, used to make vis wax.
        '''
        increment_command_counter()

        global vis_wax_embed
        await ctx.send(embed=vis_wax_embed)
    
    @commands.command(aliases=['lvl'])
    async def level(self, ctx, lvl=0):
        '''
        Calculate xp required for given level.
        '''
        increment_command_counter()

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
    async def experience(self, ctx, lvl_start_or_xp=0, lvl_end=0):
        '''
        Calculate level from xp or xp difference between two levels.
        '''
        increment_command_counter()

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
    async def xph(self, ctx, lvl_start=0, lvl_end=0, xp_rate=0.0):
        '''
        Calculate hours/actions required to reach a level / xp at a certain xp rate.
        '''
        increment_command_counter()

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
    async def pvm(self, ctx):
        '''
        Calculate rotations for Araxxor, Vorago, and Barrows: Rise Of The Six.
        '''
        increment_command_counter()

        araxxor_rotation, next_araxxor = araxxor(datetime.utcnow())
        vorago_rotation, next_vorago = vorago(datetime.utcnow())
        rots_rotation, next_rots = rots(datetime.utcnow())

        embed = discord.Embed(title='PVM Rotations', colour=0xff0000, timestamp=datetime.utcnow())
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
    async def dry(self, ctx, droprate='', attempts=''):
        '''
        Calculates the probability of going dry.
        Arguments: droprate, attempts
        Droprate formatting options (1/1000 used for example):
        - 1/1000
        - 1000
        - 0.001
        Formula used: (1-p)^k * 100
        '''
        increment_command_counter()

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
    async def combat(self, ctx, *username):
        '''
        Calculate the combat level of a RS3 player.
        '''
        increment_command_counter()
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

        embed = discord.Embed(title=f'Combat level', colour=0x00b2ff, timestamp=datetime.utcnow(), url=hiscore_page_url, description=description)
        embed.set_author(name=name, icon_url=f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '%20'))

        for i, lvls_required in enumerate(levels_required):
            if lvls_required > 0:
                embed.add_field(name=cb_skill_names[i], value=f'{rs3_skill_emojis[cb_indices_rs3[i]]} {lvls_required} levels', inline=True)

        await ctx.send(embed=embed)

    @commands.command(name='07combat', aliases=['07cb', 'osrscb', 'osrscombat'])
    async def _07combat(self, ctx, *username):
        '''
        Calculate the combat level of a OSRS player.
        '''
        increment_command_counter()
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

        embed = discord.Embed(title=f'Combat level', colour=0x00b2ff, timestamp=datetime.utcnow(), url=hiscore_page_url, description=description)
        embed.set_author(name=name, icon_url=f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'.replace(' ', '%20'))

        for i, lvls_required in enumerate(levels_required):
            if lvls_required > 0:
                embed.add_field(name=cb_skill_names[i], value=f'{osrs_skill_emojis[cb_indices_osrs[i]]} {lvls_required} levels', inline=True)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Runescape(bot))
