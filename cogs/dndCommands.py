import discord
from discord.ext import commands, tasks
import sys
import copy
sys.path.append('../')
from main import config_load, increment_command_counter, districts
from datetime import datetime, timedelta, timezone
from utils import time_diff_to_string
from utils import item_emojis
import json
import praw
import math
from bs4 import BeautifulSoup

config = config_load()

reddit = praw.Reddit(client_id=config['redditID'],
                     client_secret=config['redditSecret'],
                     password=config['redditPW'],
                     user_agent=config['user_agent'],
                     username=config['redditName'])

nemi_embed = None
nemi_time = None

peng_embed = None
peng_time = None

wilderness_flash_events = [
    'Spider Swarm',
    'Unnatural Outcrop',
    'Demon Stragglers',
    'Butterfly Swarm',
    'King Black Dragon Rampage',
    'Forgotten Soldiers',
    'Surprising Seedlings',
    'Hellhound Pack',
    'Infernal Star',
    'Lost Souls',
    'Ramokee Incursion',
    'Displaced Energy',
    'Evil Bloodwood Tree'
]

class DNDCommands(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.init_times()
    
    def init_times(self):
        # Initialize time values for D&D notifications
        self.bot.next_warband = None
        self.bot.next_vos = None
        self.bot.next_cache = None
        self.bot.next_yews48 = None
        self.bot.next_yews140 = None
        self.bot.next_goebies = None
        self.bot.next_sinkhole = None
        self.bot.next_merchant = None
        self.bot.next_spotlight = None
        self.bot.next_wilderness_flash_event = None

        self.bot.vos = None
        self.bot.merchant = None
        self.bot.spotlight = None
        self.bot.wilderness_flash_event = None
    
    def next_update(self):
        now = datetime.utcnow()
        now = now.replace(microsecond=0)

        next_times = [self.bot.next_warband, self.bot.next_vos, self.bot.next_cache, self.bot.next_yews48, self.bot.next_yews140, 
                      self.bot.next_goebies, self.bot.next_sinkhole, self.bot.next_merchant, self.bot.next_spotlight,
                      self.bot.next_wilderness_flash_event]
        
        if all(t is None for t in next_times) and self.bot.vos is None and self.bot.merchant is None and self.bot.spotlight is None:
            # If all of the time values are None, return a timedelta of 0, indicating that the times must be updated
            return timedelta(seconds=0)
        elif all(t < now if isinstance(t, datetime) else True for t in next_times):
            # If none of the time values is after now, then reset everything
            # This should fix a strange bug where all time values are somehow set several days in the past
                self.init_times()
                self.hard_reset()
                return timedelta(seconds=1)
        
        next_time = min(next_times)
        if next_time < now:
            return timedelta(seconds=0)
        else:
            return next_time - now
    
    def cog_unload(self):
        self.track_dnds.cancel()
        self.backup_loop.cancel()

    def cog_load(self):
        self.track_dnds.start()
        self.backup_loop.start()

    def hard_reset(self):
        self.track_dnds.cancel()
        self.track_dnds.start()
    
    @tasks.loop(seconds=60)
    async def backup_loop(self):
        '''
        Resets the track_dnds loop in case it somehow breaks unexpectedly
        '''
        self.next_update()
    
    @tasks.loop(seconds=15)
    async def track_dnds(self):
        '''
        Maintains D&D statuses and timers
        '''
        next_time = self.next_update()
        if next_time.total_seconds() > 0:
            return
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)

        wiki_headers = {'x-user-agent': config['wiki_user_agent']}

        # Update vos
        try:
            if not self.bot.vos or not self.bot.next_vos or self.bot.next_vos <= now:
                vos_uri = 'https://api.weirdgloop.org/runescape/vos/history'

                r = await self.bot.aiohttp.get(vos_uri, headers=wiki_headers)
                async with r:
                    vos_data = await r.json()
                    vos_data = vos_data['data']
                    
                    vos = []
                    current = []
                    for i, data_point in enumerate(vos_data[:2]):
                        vos_time = datetime.strptime(data_point['timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=None)
                        if i == 0:
                            self.bot.next_vos = vos_time + timedelta(hours=1)
                            current.append(data_point['district1'])
                            current.append(data_point['district2'])
                        vos.append(data_point['district1'])
                        vos.append(data_point['district2'])
                    
                    next_vos = copy.deepcopy(districts)
                    indices = []
                    for i, d in enumerate(districts):
                        if d in vos:
                            indices.append(i)
                    indices.sort(reverse=True)
                    for i in indices:
                        del next_vos[i]
                    
                    self.bot.vos = {'vos': current, 'next': next_vos}
        except Exception as e:
            print(f'Error getting VOS data: {type(e).__name__} : {e}')

        # Update merchant
        if not self.bot.merchant or not self.bot.next_merchant or self.bot.next_merchant <= now:
            url = f'https://runescape.wiki/api.php?action=parse&disablelimitreport=1&format=json&prop=text&contentmodel=wikitext&text=%7B%7BTravelling+Merchant%2Fapi%7Cformat%3Dsimple%7D%7D'

            r = await self.bot.aiohttp.get(url, headers=wiki_headers)
            error = False
            async with r:
                if r.status != 200:
                    error = True
                else:
                    data = await r.json()

            if not error:
                data = data['parse']['text']['*']

                data = data.replace('<div class=\"mw-parser-output"><p>', '').replace('</p></div>', '')
                data = data.replace('@', '').replace('\n', '').replace('&amp;', '&')

                data = data.replace('Distraction & Diversion reset token (daily)', 'Daily D&D token')
                data = data.replace('Distraction & Diversion reset token (weekly)', 'Weekly D&D token')
                data = data.replace('Distraction & Diversion reset token (monthly)', 'Monthly D&D token')
                data = data.replace('Menaphite gift offering (small)', 'Small Menaphite gift offering')
                data = data.replace('Menaphite gift offering (medium)', 'Medium Menaphite gift offering')
                data = data.replace('Menaphite gift offering (large)', 'Large Menaphite gift offering')
                data = data.replace('Livid plant (Deep Sea Fishing)', 'Livid plant')
                data = data.replace('Message in a bottle (Deep Sea Fishing)', 'Message in a bottle')
                data = data.replace('Sacred clay (Deep Sea Fishing)', 'Sacred clay')

                items = ['Uncharted island map'] + data.split('¦')

                txt = ''
                for item in items:
                    for e in item_emojis:
                        if item == e[0]:
                            txt += config[e[1]] + ' '
                            break
                    txt += item + '\n'
                txt = txt.strip()

                self.bot.merchant = txt
        
        # Update spotlight and spotlight time
        try:
            if not self.bot.spotlight or not self.bot.next_spotlight or self.bot.next_spotlight <= now:
                spotlight_url = 'https://runescape.wiki/api.php?action=parse&format=json&page=Template%3AMinigame%20spotlight&prop=text'
                r = await self.bot.aiohttp.get(spotlight_url, headers=wiki_headers)
                async with r:
                    data = await r.json()

                    bs = BeautifulSoup(data['parse']['text']['*'].replace('\\"', '"'), "html.parser")
                    table_body = bs.find('table')
                    rows = table_body.find_all('tr')
                    schedule = []
                    for row in rows[:2]:
                        minigame = row.find('td').find('a').text.strip()
                        time = row.find('td').find('span').text.strip()
                        schedule.append([minigame, time])

                    next_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                    next_day_and_month = datetime.strptime(schedule[1][1], '%d %b')
                    next_date = next_date.replace(day=next_day_and_month.day, month=next_day_and_month.month)
                    if datetime.strptime('1 Jan', '%d %b') <= next_day_and_month <= datetime.strptime('3 Jan', '%d %b'):
                        next_date += timedelta(years=1)

                    self.bot.spotlight = schedule[0][0]
                    self.bot.next_spotlight = next_date
        except Exception as e:
            print(f'Error getting minigame spotlight data: {type(e).__name__} : {e}')

        # Update upcoming wilderness flash event
        t_0 = datetime(2022, 10, 19, 14, 0, 0, tzinfo=None)
        elapsed = now - t_0
        elapsed /= timedelta(hours=1)
        elapsed = math.floor(elapsed)
        current_flash_event = wilderness_flash_events[(elapsed-1)%len(wilderness_flash_events)]
        upcoming_flash_event = wilderness_flash_events[elapsed%len(wilderness_flash_events)]
        if not self.bot.wilderness_flash_event:
            self.bot.wilderness_flash_event = {'current': None, 'next': upcoming_flash_event}
        self.bot.wilderness_flash_event['current'] = current_flash_event
        self.bot.wilderness_flash_event['next'] = upcoming_flash_event
        
        # Warbands schedule repeats weekly starting monday 02:00
        next_warband_start = (now - timedelta(days=now.weekday())).replace(hour=2, minute=0, second=0, microsecond=0)
        while next_warband_start < now:
            next_warband_start += timedelta(hours=7)
        self.bot.next_warband = next_warband_start

        # Update time values
        self.bot.next_cache = now.replace(minute=0, second=0) + timedelta(hours=1)
        self.bot.next_yews48 = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
        self.bot.next_yews140 = now + timedelta(days=1) - timedelta(hours=((now.hour+7)%24), minutes=now.minute, seconds=now.second)
        self.bot.next_goebies = now + timedelta(hours=12) - timedelta(hours=(now.hour%12), minutes=now.minute, seconds=now.second)
        self.bot.next_sinkhole = now + timedelta(hours=1) - timedelta(minutes=((now.minute+30)%60), seconds=now.second)
        self.bot.next_merchant = self.bot.next_yews48
        self.bot.next_wilderness_flash_event = now + timedelta(hours=1) - timedelta(minutes=now.minute, seconds=now.second)


    @commands.command(pass_context=True)
    async def future(self, ctx: commands.Context):
        '''
        Returns the time until all future events.
        '''
        increment_command_counter()

        now = datetime.utcnow()
        now = now.replace(microsecond=0)

        msg = (f'Future:\n'
               f'{config["warbandsEmoji"]} **Wilderness warbands** will begin in {time_diff_to_string(self.bot.next_warband - now)}.\n'
               f'{config["vosEmoji"]} **Voice of Seren** will change in {time_diff_to_string(self.bot.next_vos - now)}.\n'
               f'{config["cacheEmoji"]} **Guthixian caches** will begin in {time_diff_to_string(self.bot.next_cache - now)}.\n'
               f'{config["yewsEmoji"]} **Divine yews** (w48 bu) will begin in {time_diff_to_string(self.bot.next_yews48 - now)}.\n'
               f'{config["yewsEmoji"]} **Divine yews** (w140 bu) will begin in {time_diff_to_string(self.bot.next_yews140 - now)}.\n'
               f'{config["goebiesEmoji"]} **Goebies supply run** will begin in {time_diff_to_string(self.bot.next_goebies - now)}.\n'
               f'{config["sinkholeEmoji"]} **Sinkhole** will spawn in {time_diff_to_string(self.bot.next_sinkhole - now)}.\n'
               f'{config["merchantEmoji"]} **Travelling merchant** stock will refresh in {time_diff_to_string(self.bot.next_merchant - now)}.\n'
               f'{config["spotlightEmoji"]} **Minigame spotlight** will change in {time_diff_to_string(self.bot.next_spotlight - now)}.\n'
               f'{config["wildernessflasheventsEmoji"]} **Wilderness flash event** will begin in {time_diff_to_string(self.bot.next_wilderness_flash_event - now)}.\n')
        
        await ctx.send(msg)

    @commands.command(pass_context=True)
    async def vos(self, ctx: commands.Context):
        '''
        Returns the current Voice of Seren.
        '''
        increment_command_counter()

        now = datetime.utcnow()
        now = now.replace(second=0, microsecond=0)
        time_to_vos = self.bot.next_vos - now
        time_to_vos = time_diff_to_string(time_to_vos)

        current = self.bot.vos['vos']
        next_vos = self.bot.vos['next']
        
        emoji0 = config[current[0].lower()+'Emoji']
        emoji1 = config[current[1].lower()+'Emoji']
        current_txt = f'{emoji0} {current[0]}\n{emoji1} {current[1]}'
        next_txt = f'{next_vos[0]}, {next_vos[1]}, {next_vos[2]}, {next_vos[3]}'
        title = f'Voice of Seren'
        colour = 0x00b2ff
        embed = discord.Embed(title=title, colour=colour, description=current_txt)
        embed.add_field(name=f'Up next ({time_to_vos})', value=next_txt, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(pass_context=True)
    async def merchant(self, ctx: commands.Context):
        '''
        Returns the current travelling merchant stock.
        '''
        increment_command_counter()

        now = datetime.utcnow()
        now = now.replace(microsecond=0)

        embed = discord.Embed(title='Traveling Merchant\'s Shop', colour=0x00b2ff, timestamp=datetime.utcnow(), url='https://runescape.wiki/w/Travelling_Merchant%27s_Shop', description=self.bot.merchant)
        embed.set_thumbnail(url='https://runescape.wiki/images/b/bc/Wiki.png')
        embed.set_footer(text=f'Reset in {time_diff_to_string(self.bot.next_merchant - now)}.')
        
        await ctx.send(embed=embed)

    @commands.command(pass_context=True, aliases=['warband', 'wbs'])
    async def warbands(self, ctx: commands.Context):
        '''
        Returns the time until wilderness warbands starts.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['warbandsEmoji'] + " **Wilderness warbands** will begin in " + time_diff_to_string(self.bot.next_warband - now) + "."
        
        await ctx.send(msg)

    @commands.command(pass_context=True, aliases=['caches'])
    async def cache(self, ctx: commands.Context):
        '''
        Returns the time until the next Guthixian cache.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['cacheEmoji'] + " **Guthixian caches** will begin in " + time_diff_to_string(self.bot.next_cache - now) + "."
        
        await ctx.send(msg)

    @commands.command(pass_context=True, aliases=['yew'])
    async def yews(self, ctx: commands.Context):
        '''
        Returns the time until the next divine yews event.
        '''
        increment_command_counter()

        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['yewsEmoji'] + " **Divine yews** will begin in " + time_diff_to_string(self.bot.next_yews48 - now) + " in w48 bu, and in " + time_diff_to_string(self.bot.next_yews140 - now) + " in w140 bu."
        
        await ctx.send(msg)

    @commands.command(pass_context=True, aliases=['goebie', 'goebiebands'])
    async def goebies(self, ctx: commands.Context):
        '''
        Returns the time until the next goebies supply run.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['goebiesEmoji'] + " **Goebies supply run** will begin in " + time_diff_to_string(self.bot.next_goebies - now) + "."
        
        await ctx.send(msg)

    @commands.command(pass_context=True, aliases=['sinkholes'])
    async def sinkhole(self, ctx: commands.Context):
        '''
        Returns the time until the next sinkhole.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['sinkholeEmoji'] + " **Sinkhole** will spawn in " + time_diff_to_string(self.bot.next_sinkhole - now) + "."
        
        await ctx.send(msg)

    @commands.command(pass_context=True)
    async def spotlight(self, ctx: commands.Context):
        '''
        Returns the current and next minigame spotlight.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        embed = discord.Embed(title='Minigame Spotlight', colour=0x00b2ff, description=self.bot.spotlight)
        embed.set_footer(text=time_diff_to_string(self.bot.next_spotlight - now))
        
        await ctx.send(embed=embed)

    @commands.command()
    async def nemi(self, ctx: commands.Context):
        '''
        Gets the current nemi forest layout from FC Nemi.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        global nemi_embed
        global nemi_time

        if nemi_embed and nemi_time and datetime.utcnow() < nemi_time + timedelta(minutes=5):
            await ctx.send(embed=nemi_embed)
            return

        submissions = reddit.subreddit('NemiForest').new(limit=5)

        sub = None
        for s in submissions:
            if s.url.endswith(('.jpg', '.png', '.gif', '.jpeg')) and s.title.upper().startswith('W'):
                sub = s
                break

        if not sub and not nemi_embed:
            raise commands.CommandError(message=f'No nemi forest layout found. Please try again later.')
        elif not sub:
            await ctx.send(embed=nemi_embed)
            return

        embed = discord.Embed(title=f'/r/NemiForest', colour=0x00b2ff, timestamp=datetime.utcfromtimestamp(int(sub.created_utc)), url=sub.shortlink, description=sub.title)
        embed.set_image(url=sub.url)
        embed.set_author(name=sub.author.name, icon_url=sub.author.icon_img)

        nemi_embed = embed
        nemi_time = datetime.utcnow()

        await ctx.send(embed=embed)
    
    @commands.command(aliases=['w60pengs', 'world60pengs', 'penglocs', 'penguins'])
    async def pengs(self, ctx: commands.Context):
        '''
        Gets this weeks world 60 penguin locations.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        global peng_embed
        global peng_time

        if peng_embed and peng_time and ((datetime.utcnow().weekday() != 2 and datetime.utcnow() < peng_time + timedelta(hours=1)) or (datetime.utcnow().weekday() == 2 and datetime.utcnow() < peng_time + timedelta(minutes=5))):
            await ctx.send(embed=peng_embed)
            return

        submissions = reddit.subreddit('World60Pengs').new(limit=5)

        sub = None
        for s in submissions:
            if s.is_self and s.title.lower().startswith('penguin locations v'):
                sub = s
                break
        
        if not sub and not peng_embed:
            raise commands.CommandError(message=f'No penguin locations found. Please try again later.')
        elif not sub:
            await ctx.send(embed=peng_embed)
            return

        text = sub.selftext
        text = text.split('#Please post locations below as you spy!')[0].strip()
        text = text.replace('#', '', 1)

        subtitle = ''
        locations = ''
        notes = ''

        for line in text.split('\n'):
            if not line.startswith('>') and not locations:
                subtitle += '\n' + line
            elif line.startswith('>'):
                temp = line.replace('>', '').replace('^[‡]', '‡').replace('[]', '').replace('(#small)', '')
                temp = temp.replace('(#crate)', '(#crat)').replace('(#toadstool)', '(#toad)').replace('(#cactus)', '(#cact)').replace('(#barrel)', '(#barr)')
                temp = temp.replace('(#pumpkin)', '(#pump)').replace('(#snowman)', '(#snow)')
                locations += temp + '\n'
            else:
                notes += line + '\n'
            
        locations = locations.strip().split('\n')[2:]
        notes = '\n'.join(notes.strip().split('\n')[1:])
        notes = notes.replace('__', '').replace('*', '•')

        dangerous = []
        temp = copy.deepcopy(locations)
        for i, loc in enumerate(temp):
            if '(#danger)' in loc:
                locations[i] = loc.replace('(#danger)', '')
                dangerous.append(i)

        table = [loc.split('|') for loc in locations]
        result = copy.deepcopy(table)

        for i, row in enumerate(table):
            for j, col in enumerate(row):
                result[i][j] = col.strip()

        table = copy.deepcopy(result)
        for i, row in enumerate(table):
            for j, col in enumerate(row):
                len_dif = max([len(r[j]) for r in table]) - len(col)
                result[i][j] += len_dif * ' '
        
        table = copy.deepcopy(result)
        for i, row in enumerate(table):
            temp = row[2].replace('(#rock)', '🪨')
            temp = temp.replace('(#bush)', '🌳')
            temp = temp.replace('(#crat)', '📦')
            temp = temp.replace('(#toad)', '🍄')
            temp = temp.replace('(#cact)', '🌵')
            temp = temp.replace('(#barr)', '🛢️')
            temp = temp.replace('(#pump)', '🎃')
            temp = temp.replace('(#snow)', '⛄')
            result[i][2] = temp
        
        table = copy.deepcopy(result)
        for i, row in enumerate(table):
            if i in dangerous:
                result[i][3] += ' ☠️'
        
        table = []
        for row in result:
            table.append(' '.join(row))
        table = '\n'.join(table)

        description = f'**{sub.title}**\n{subtitle}```{table}```'

        embed = discord.Embed(title=f'World 60 penguin locations', colour=0x00b2ff, timestamp=datetime.utcfromtimestamp(int(sub.created_utc)), url=sub.shortlink, description=description)
        embed.set_author(name=sub.author.name, icon_url=sub.author.icon_img)

        embed.add_field(name='Notes', value=notes)

        peng_embed = embed
        peng_time = datetime.utcnow()

        await ctx.send(embed=embed)
    
    @commands.command(aliases=['wilderness_flash_events', 'wilderness_flash_event', 'wilderness_flash', 'wildy_flash', 'wildy_flash_events', 'wildy_flash_event'])
    async def flash(self, ctx: commands.Context):
        '''
        Returns the next wilderness flash event.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        txt = f'Current: {self.bot.wilderness_flash_event["current"]}\nNext: {self.bot.wilderness_flash_event["next"]}' if self.bot.wilderness_flash_event["current"] else f'Next: {self.bot.wilderness_flash_event["next"]}'
        embed = discord.Embed(title='Wilderness flash event', colour=0x00b2ff, description=txt)
        embed.set_footer(text=time_diff_to_string(self.bot.next_wilderness_flash_event - now))
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(DNDCommands(bot))
