import discord
from discord.ext import commands, tasks
import sys
import copy
sys.path.append('../')
from main import config_load, increment_command_counter, districts
from datetime import datetime, timedelta
from utils import time_diff_to_string
from utils import item_emojis
import json

config = config_load()

class DNDCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Initialize time values
        self.bot.next_warband = None
        self.bot.next_vos = None
        self.bot.next_cache = None
        self.bot.next_yews48 = None
        self.bot.next_yews140 = None
        self.bot.next_goebies = None
        self.bot.next_sinkhole = None
        self.bot.next_merchant = None
        self.bot.next_spotlight = None

        self.bot.vos = None
        self.bot.merchant = None
        self.bot.spotlight = None
    
        self.track_dnds.start()
    
    def next_update(self):
        next_times = [self.bot.next_warband, self.bot.next_vos, self.bot.next_cache, self.bot.next_goebies, self.bot.next_yews48, \
                      self.bot.next_yews140, self.bot.next_goebies, self.bot.next_sinkhole, self.bot.next_merchant, self.bot.next_spotlight]
        if any(t is None for t in next_times) or self.bot.vos is None or self.bot.merchant is None or self.bot.spotlight is None:
            return timedelta(seconds=0)
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        next_time = min(next_times)
        if next_time < now:
            return timedelta(seconds=0)
        else:
            return next_time - now
    
    def cog_unload(self):
        self.track_dnds.cancel()
    
    @tasks.loop(seconds=15)
    async def track_dnds(self):
        '''
        Maintains D&D statuses and timers from Jagex tweets
        '''
        next_time = self.next_update()
        if next_time.total_seconds() > 0:
            return
        
        jagex_tweets = []

        uri = 'https://api.twitter.com/1.1/statuses/user_timeline.json?screen_name=JagexClock&count=150'
        http_method = 'GET'

        uri, headers, _ = self.bot.twitter_client.sign(uri=uri, http_method=http_method)

        r = await self.bot.aiohttp.get(uri, headers=headers)
        async with r:
            try:
                txt = await r.text()
                jagex_tweets = json.loads(txt)
            except Exception as e:
                print(f'Encountered exception while attempting to get jagex tweets: {e}')
        
        jagex_tweets = sorted(jagex_tweets, key=lambda t: datetime.strptime(t['created_at'], '%a %b %d %H:%M:%S %z %Y'), reverse=True)
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)

        # Update vos
        vos = []
        current = []
        count = 0
        for tweet in jagex_tweets:
            if not 'Voice of Seren' in tweet['text']:
                continue
            tweet_time = datetime.strptime(tweet['created_at'], '%a %b %d %H:%M:%S %z %Y').replace(tzinfo=None)
            
            count += 1
            if count == 1:
                self.bot.next_vos = tweet_time + timedelta(hours=1)
            for d in districts:
                if d in tweet['text']:
                    vos.append(d)
                    if count == 1:
                        current.append(d)
            if count == 2:
                break
        
        next_vos = copy.deepcopy(districts)
        indices = []
        for i, d in enumerate(districts):
            if d in vos:
                indices.append(i)
        indices.sort(reverse=True)
        for i in indices:
            del next_vos[i]
        
        self.bot.vos = {'vos': current, 'next': next_vos}

        # Update merchant
        url = f'https://runescape.wiki/api.php?action=parse&disablelimitreport=1&format=json&prop=text&contentmodel=wikitext&text=%7B%7BTravelling+Merchant%2Fapi%7Cformat%3Dsimple%7D%7D'

        r = await self.bot.aiohttp.get(url)
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

            data = data.replace('D&D token (daily)', 'Daily D&D token')
            data = data.replace('D&D token (weekly)', 'Weekly D&D token')
            data = data.replace('D&D token (monthly)', 'Monthly D&D token')
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
        minigame = self.bot.spotlight
        last_spotlight = self.bot.next_spotlight
        for tweet in jagex_tweets:
            if not 'spotlight' in tweet['text']:
                continue
            last_spotlight = datetime.strptime(tweet['created_at'], '%a %b %d %H:%M:%S %z %Y').replace(tzinfo=None)
            minigame = tweet['text'].replace(' is now the spotlighted minigame!', '')
            break
        self.bot.spotlight = minigame
        if not last_spotlight is None:
            self.bot.next_spotlight = last_spotlight + timedelta(days=3)
        
        # Update time values
        last_warband = now
        for tweet in jagex_tweets:
            if 'Warbands' in tweet['text']:
                last_warband = datetime.strptime(tweet['created_at'], '%a %b %d %H:%M:%S %z %Y').replace(tzinfo=None)
                last_warband = last_warband.replace(microsecond=0)
                break
        
        if last_warband + timedelta(minutes=15) > now:
            self.bot.next_warband = last_warband + timedelta(minutes=15)
        else:
            self.bot.next_warband = last_warband + timedelta(hours=7, minutes=15)
        self.bot.next_cache = now.replace(minute=0, second=0) + timedelta(hours=1)
        self.bot.next_yews48 = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
        self.bot.next_yews140 = now + timedelta(days=1) - timedelta(hours=((now.hour+7)%24), minutes=now.minute, seconds=now.second)
        self.bot.next_goebies = now + timedelta(hours=12) - timedelta(hours=(now.hour%12), minutes=now.minute, seconds=now.second)
        self.bot.next_sinkhole = now + timedelta(hours=1) - timedelta(minutes=((now.minute+30)%60), seconds=now.second)
        self.bot.next_merchant = self.bot.next_yews48


    @commands.command(pass_context=True)
    async def future(self, ctx):
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
               f'{config["spotlightEmoji"]} **Minigame spotlight** will change in {time_diff_to_string(self.bot.next_spotlight - now)}.')
        
        await ctx.send(msg)

    @commands.command(pass_context=True)
    async def vos(self, ctx):
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
    async def merchant(self, ctx):
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
    async def warbands(self, ctx):
        '''
        Returns the time until wilderness warbands starts.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['warbandsEmoji'] + " **Wilderness warbands** will begin in " + time_diff_to_string(self.bot.next_warband - now) + "."
        
        await ctx.send(msg)

    @commands.command(pass_context=True, aliases=['caches'])
    async def cache(self, ctx):
        '''
        Returns the time until the next Guthixian cache.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['cacheEmoji'] + " **Guthixian caches** will begin in " + time_diff_to_string(self.bot.next_cache - now) + "."
        
        await ctx.send(msg)

    @commands.command(pass_context=True, aliases=['yew'])
    async def yews(self, ctx):
        '''
        Returns the time until the next divine yews event.
        '''
        increment_command_counter()

        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['yewsEmoji'] + " **Divine yews** will begin in " + time_diff_to_string(self.bot.next_yews48 - now) + " in w48 bu, and in " + time_diff_to_string(self.bot.next_yews140 - now) + " in w140 bu."
        
        await ctx.send(msg)

    @commands.command(pass_context=True, aliases=['goebie', 'goebiebands'])
    async def goebies(self, ctx):
        '''
        Returns the time until the next goebies supply run.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['goebiesEmoji'] + " **Goebies supply run** will begin in " + time_diff_to_string(self.bot.next_goebies - now) + "."
        
        await ctx.send(msg)

    @commands.command(pass_context=True, aliases=['sinkholes'])
    async def sinkhole(self, ctx):
        '''
        Returns the time until the next sinkhole.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        msg = config['sinkholeEmoji'] + " **Sinkhole** will spawn in " + time_diff_to_string(self.bot.next_sinkhole - now) + "."
        
        await ctx.send(msg)

    @commands.command(pass_context=True)
    async def spotlight(self, ctx):
        '''
        Returns the current and next minigame spotlight.
        '''
        increment_command_counter()
        
        now = datetime.utcnow()
        now = now.replace(microsecond=0)
        
        embed = discord.Embed(title='Minigame Spotlight', colour=0x00b2ff, description=self.bot.spotlight)
        embed.set_footer(text=time_diff_to_string(self.bot.next_spotlight - now))
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(DNDCommands(bot))
