from typing import Any, Iterator
from aiohttp import ClientResponse
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Cog
import copy
from src.bot import Bot
from datetime import datetime, timedelta, UTC
from src.runescape_utils import prif_districts, wilderness_flash_events, item_emojis
from src.date_utils import timedelta_to_string
import praw
import math
from bs4 import BeautifulSoup, NavigableString, Tag

class DNDCommands(Cog):
    nemi_embed: discord.Embed | None = None
    nemi_time: datetime | None = None

    peng_embed: discord.Embed | None = None
    peng_time: datetime | None = None

    reddit: praw.Reddit

    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
        self.reddit = praw.Reddit(
            client_id = self.bot.config['redditID'],
            client_secret = self.bot.config['redditSecret'],
            password = self.bot.config['redditPW'],
            user_agent = self.bot.config['user_agent'],
            username = self.bot.config['redditName']
        )
        self.init_times()
    
    def init_times(self) -> None:
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
    
    def next_update(self) -> timedelta:
        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)

        next_times: list[datetime | None] = [
            self.bot.next_warband, 
            self.bot.next_vos, 
            self.bot.next_cache, 
            self.bot.next_yews48, 
            self.bot.next_yews140, 
            self.bot.next_goebies, 
            self.bot.next_sinkhole, 
            self.bot.next_merchant, 
            self.bot.next_spotlight,
            self.bot.next_wilderness_flash_event
        ]
        
        if all(t is None for t in next_times) and self.bot.vos is None and self.bot.merchant is None and self.bot.spotlight is None:
            # If all of the time values are None, return a timedelta of 0, indicating that the times must be updated
            return timedelta(seconds=0)
        elif all(t < now if isinstance(t, datetime) else True for t in next_times):
            # If none of the time values is after now, then reset everything
            # This should fix a strange bug where all time values are somehow set several days in the past
                self.init_times()
                self.hard_reset()
                return timedelta(seconds=1)
        
        next_time: datetime = min([time for time in next_times if time])
        if next_time < now:
            return timedelta(seconds=0)
        else:
            return next_time - now
    
    async def cog_unload(self) -> None:
        self.track_dnds.cancel()
        self.backup_loop.cancel()

    async def cog_load(self) -> None:
        self.track_dnds.start()
        self.backup_loop.start()

    def hard_reset(self) -> None:
        self.track_dnds.cancel()
        self.track_dnds.start()
    
    @tasks.loop(seconds=60)
    async def backup_loop(self) -> None:
        '''
        Resets the track_dnds loop in case it somehow breaks unexpectedly
        '''
        self.next_update()
    
    @tasks.loop(seconds=15)
    async def track_dnds(self) -> None:
        '''
        Maintains D&D statuses and timers
        '''
        next_time: timedelta = self.next_update()
        if next_time.total_seconds() > 0:
            return
        
        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)

        wiki_headers: dict[str, Any] = {'x-user-agent': self.bot.config['wiki_user_agent']}

        # Update vos
        try:
            if not self.bot.vos or not self.bot.next_vos or self.bot.next_vos <= now:
                vos_uri = 'https://api.weirdgloop.org/runescape/vos/history'

                r: ClientResponse = await self.bot.aiohttp.get(vos_uri, headers=wiki_headers)
                async with r:
                    vos_data: Any = await r.json()
                    vos_data = vos_data['data']
                    
                    vos: list[str] = []
                    current: list[str] = []
                    for i, data_point in enumerate(vos_data[:2]):
                        vos_time: datetime = datetime.strptime(data_point['timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=UTC)
                        if i == 0:
                            self.bot.next_vos = vos_time + timedelta(hours=1)
                            current.append(data_point['district1'])
                            current.append(data_point['district2'])
                        vos.append(data_point['district1'])
                        vos.append(data_point['district2'])
                    
                    next_vos: list[str] = copy.deepcopy(prif_districts)
                    indices: list[int] = []
                    for i, d in enumerate(prif_districts):
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
            url: str = f'https://runescape.wiki/api.php?action=parse&disablelimitreport=1&format=json&prop=text&contentmodel=wikitext&text=%7B%7BTravelling+Merchant%2Fapi%7Cformat%3Dsimple%7D%7D'

            r = await self.bot.aiohttp.get(url, headers=wiki_headers)
            error = False
            data: Any = None
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

                items: list = ['Uncharted island map'] + data.split('¦')

                txt: str = ''
                for item in items:
                    for e in item_emojis:
                        if item == e[0]:
                            txt += self.bot.config[e[1]] + ' '
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
                    table_body: Tag | NavigableString | None = bs.find('table')
                    rows: list = table_body.find_all('tr') if table_body and isinstance(table_body, Tag) else []
                    schedule: list[list[str]] = []
                    for row in rows[:2]:
                        minigame: str = row.find('td').find('a').text.strip()
                        time: str = row.find('td').find('span').text.strip()
                        schedule.append([minigame, time])

                    next_date: datetime = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
                    next_day_and_month: datetime = datetime.strptime(schedule[1][1], '%d %b')
                    next_date = next_date.replace(day=next_day_and_month.day, month=next_day_and_month.month)
                    if datetime.strptime('1 Jan', '%d %b') <= next_day_and_month <= datetime.strptime('3 Jan', '%d %b'):
                        next_date = next_date.replace(year=next_date.year+1)

                    self.bot.spotlight = schedule[0][0]
                    self.bot.next_spotlight = next_date
        except Exception as e:
            print(f'Error getting minigame spotlight data: {type(e).__name__} : {e}')

        # Update upcoming wilderness flash event
        t_0 = datetime(2022, 10, 19, 14, 0, 0, tzinfo=UTC)
        elapsed: timedelta | float | int = now - t_0
        elapsed /= timedelta(hours=1)
        elapsed = math.floor(elapsed)
        current_flash_event = wilderness_flash_events[(elapsed-1)%len(wilderness_flash_events)]
        upcoming_flash_event = wilderness_flash_events[elapsed%len(wilderness_flash_events)]
        if not self.bot.wilderness_flash_event:
            self.bot.wilderness_flash_event = {'current': None, 'next': upcoming_flash_event}
        self.bot.wilderness_flash_event['current'] = current_flash_event
        self.bot.wilderness_flash_event['next'] = upcoming_flash_event
        
        # Warbands schedule repeats weekly starting monday 02:00
        next_warband_start: datetime = (now - timedelta(days=now.weekday())).replace(hour=2, minute=0, second=0, microsecond=0)
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


    @commands.command()
    async def future(self, ctx: commands.Context) -> None:
        '''
        Returns the time until all future events.
        '''
        self.bot.increment_command_counter()

        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)

        msg: str = (
            f'Future:\n'
            f'{self.bot.config["warbandsEmoji"]} **Wilderness warbands** will begin in {timedelta_to_string(self.bot.next_warband - now) if self.bot.next_warband else 'N/A'}.\n'
            f'{self.bot.config["vosEmoji"]} **Voice of Seren** will change in {timedelta_to_string(self.bot.next_vos - now) if self.bot.next_vos else 'N/A'}.\n'
            f'{self.bot.config["cacheEmoji"]} **Guthixian caches** will begin in {timedelta_to_string(self.bot.next_cache - now) if self.bot.next_cache else 'N/A'}.\n'
            f'{self.bot.config["yewsEmoji"]} **Divine yews** (w48 bu) will begin in {timedelta_to_string(self.bot.next_yews48 - now) if self.bot.next_yews48 else 'N/A'}.\n'
            f'{self.bot.config["yewsEmoji"]} **Divine yews** (w140 bu) will begin in {timedelta_to_string(self.bot.next_yews140 - now) if self.bot.next_yews140 else 'N/A'}.\n'
            f'{self.bot.config["goebiesEmoji"]} **Goebies supply run** will begin in {timedelta_to_string(self.bot.next_goebies - now) if self.bot.next_goebies else 'N/A'}.\n'
            f'{self.bot.config["sinkholeEmoji"]} **Sinkhole** will spawn in {timedelta_to_string(self.bot.next_sinkhole - now) if self.bot.next_sinkhole else 'N/A'}.\n'
            f'{self.bot.config["merchantEmoji"]} **Travelling merchant** stock will refresh in {timedelta_to_string(self.bot.next_merchant - now) if self.bot.next_merchant else 'N/A'}.\n'
            f'{self.bot.config["spotlightEmoji"]} **Minigame spotlight** will change in {timedelta_to_string(self.bot.next_spotlight - now) if self.bot.next_spotlight else 'N/A'}.\n'
            f'{self.bot.config["wildernessflasheventsEmoji"]} **Wilderness flash event** will begin in {timedelta_to_string(self.bot.next_wilderness_flash_event - now) if self.bot.next_wilderness_flash_event else 'N/A'}.\n'
        )
        
        await ctx.send(msg)

    @commands.command()
    async def vos(self, ctx: commands.Context) -> None:
        '''
        Returns the current Voice of Seren.
        '''
        self.bot.increment_command_counter()

        now: datetime = datetime.now(UTC)
        now = now.replace(second=0, microsecond=0)
        time_to_vos: timedelta | str = (self.bot.next_vos if self.bot.next_vos else datetime.now(UTC)) - now
        time_to_vos = timedelta_to_string(time_to_vos)

        current: list[str] | None = self.bot.vos['vos'] if self.bot.vos else None
        next_vos: list[str] | None = self.bot.vos['next'] if self.bot.vos else None

        if not current or not next_vos:
            raise commands.CommandError('Voice of Seren status not found. Please try again and contact an administrator if the problem persists.')
        
        emoji0: str = self.bot.config[current[0].lower()+'Emoji']
        emoji1: str = self.bot.config[current[1].lower()+'Emoji']
        current_txt: str = f'{emoji0} {current[0]}\n{emoji1} {current[1]}'
        next_txt: str = f'{next_vos[0]}, {next_vos[1]}, {next_vos[2]}, {next_vos[3]}'
        title: str = f'Voice of Seren'
        colour = 0x00b2ff
        embed = discord.Embed(title=title, colour=colour, description=current_txt)
        embed.add_field(name=f'Up next ({time_to_vos})', value=next_txt, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    async def merchant(self, ctx: commands.Context) -> None:
        '''
        Returns the current travelling merchant stock.
        '''
        self.bot.increment_command_counter()

        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)

        embed = discord.Embed(title='Traveling Merchant\'s Shop', colour=0x00b2ff, timestamp=datetime.now(UTC), url='https://runescape.wiki/w/Travelling_Merchant%27s_Shop', description=self.bot.merchant)
        embed.set_thumbnail(url='https://runescape.wiki/images/b/bc/Wiki.png')
        embed.set_footer(text=f'Reset in {timedelta_to_string((self.bot.next_merchant if self.bot.next_merchant else datetime.now(UTC)) - now)}.')
        
        await ctx.send(embed=embed)

    @commands.command(aliases=['warband', 'wbs'])
    async def warbands(self, ctx: commands.Context) -> None:
        '''
        Returns the time until wilderness warbands starts.
        '''
        self.bot.increment_command_counter()
        
        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)
        
        msg: str = self.bot.config['warbandsEmoji'] + " **Wilderness warbands** will begin in " + timedelta_to_string((self.bot.next_warband if self.bot.next_warband else datetime.now(UTC)) - now) + "."
        
        await ctx.send(msg)

    @commands.command(aliases=['caches'])
    async def cache(self, ctx: commands.Context) -> None:
        '''
        Returns the time until the next Guthixian cache.
        '''
        self.bot.increment_command_counter()
        
        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)
        
        msg: str = self.bot.config['cacheEmoji'] + " **Guthixian caches** will begin in " + timedelta_to_string((self.bot.next_cache if self.bot.next_cache else datetime.now(UTC)) - now) + "."
        
        await ctx.send(msg)

    @commands.command(aliases=['yew'])
    async def yews(self, ctx: commands.Context) -> None:
        '''
        Returns the time until the next divine yews event.
        '''
        self.bot.increment_command_counter()

        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)
        
        msg: str = (
            self.bot.config['yewsEmoji'] + " **Divine yews** will begin in " + 
            timedelta_to_string((self.bot.next_yews48 if self.bot.next_yews48 else datetime.now(UTC)) - now) + " in w48 bu, and in " + 
            timedelta_to_string((self.bot.next_yews140 if self.bot.next_yews140 else datetime.now(UTC)) - now) + " in w140 bu."
        )
        
        await ctx.send(msg)

    @commands.command(aliases=['goebie', 'goebiebands'])
    async def goebies(self, ctx: commands.Context) -> None:
        '''
        Returns the time until the next goebies supply run.
        '''
        self.bot.increment_command_counter()
        
        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)
        
        msg: str = self.bot.config['goebiesEmoji'] + " **Goebies supply run** will begin in " + timedelta_to_string((self.bot.next_goebies if self.bot.next_goebies else datetime.now(UTC)) - now) + "."
        
        await ctx.send(msg)

    @commands.command(aliases=['sinkholes'])
    async def sinkhole(self, ctx: commands.Context):
        '''
        Returns the time until the next sinkhole.
        '''
        self.bot.increment_command_counter()
        
        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)
        
        msg: str = self.bot.config['sinkholeEmoji'] + " **Sinkhole** will spawn in " + timedelta_to_string((self.bot.next_sinkhole if self.bot.next_sinkhole else datetime.now(UTC)) - now) + "."
        
        await ctx.send(msg)

    @commands.command()
    async def spotlight(self, ctx: commands.Context) -> None:
        '''
        Returns the current and next minigame spotlight.
        '''
        self.bot.increment_command_counter()
        
        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)
        
        embed = discord.Embed(title='Minigame Spotlight', colour=0x00b2ff, description=self.bot.spotlight)
        embed.set_footer(text=timedelta_to_string((self.bot.next_spotlight if self.bot.next_spotlight else datetime.now(UTC)) - now))
        
        await ctx.send(embed=embed)

    @commands.command()
    async def nemi(self, ctx: commands.Context) -> None:
        '''
        Gets the current nemi forest layout from FC Nemi.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if self.nemi_embed and self.nemi_time and datetime.now(UTC) < self.nemi_time + timedelta(minutes=5):
            await ctx.send(embed=self.nemi_embed)
            return

        subreddit: praw.reddit.Subreddit = self.reddit.subreddit('NemiForest')
        submissions: Iterator[praw.reddit.Submission] = subreddit.new(limit=5)

        sub: praw.reddit.Submission | None = None
        for s in [subm for subm in submissions if isinstance(subm, praw.reddit.Submission)]:
            if isinstance(s.url, str) and s.url.endswith(('.jpg', '.png', '.gif', '.jpeg')) and isinstance(s.title, str) and s.title.upper().startswith('W'):
                sub = s
                break

        if not sub and isinstance(self.nemi_embed, discord.Embed):
            await ctx.send(embed=self.nemi_embed)
            return
        elif not sub:
            raise commands.CommandError(message=f'No nemi forest layout found. Please try again later.')

        embed = discord.Embed(title=f'/r/NemiForest', colour=0x00b2ff, timestamp=datetime.fromtimestamp(int(sub.created_utc), UTC), url=sub.shortlink, description=sub.title)
        embed.set_image(url=sub.url)
        embed.set_author(name=sub.author.name, icon_url=sub.author.icon_img)

        self.nemi_embed = embed
        self.nemi_time = datetime.now(UTC)

        await ctx.send(embed=embed)
    
    @commands.command(aliases=['w60pengs', 'world60pengs', 'penglocs', 'penguins'])
    async def pengs(self, ctx: commands.Context) -> None:
        '''
        Gets this weeks world 60 penguin locations.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if self.peng_embed and self.peng_time and ((datetime.now(UTC).weekday() != 2 and datetime.now(UTC) < self.peng_time + timedelta(hours=1)) or (datetime.now(UTC).weekday() == 2 and datetime.now(UTC) < self.peng_time + timedelta(minutes=5))):
            await ctx.send(embed=self.peng_embed)
            return

        subreddit: praw.reddit.Subreddit = self.reddit.subreddit('World60Pengs')
        submissions: Iterator[praw.reddit.Submission] = subreddit.new(limit=5)

        sub: praw.reddit.Submission | None = None
        for s in [subm for subm in submissions if isinstance(subm, praw.reddit.Submission)]:
            if s.is_self and isinstance(s.title, str) and s.title.lower().startswith('penguin locations v'):
                sub = s
                break
        
        if not sub and isinstance(self.peng_embed, discord.Embed):
            await ctx.send(embed=self.peng_embed)
            return
        elif not sub:
            raise commands.CommandError(message=f'No penguin locations found. Please try again later.')

        text: str = sub.selftext
        text = text.split('#Please post locations below as you spy!')[0].strip()
        text = text.replace('#', '', 1)

        subtitle: str = ''
        locations: str | list[str] = ''
        notes: str = ''

        for line in text.split('\n'):
            if not line.startswith('>') and not locations:
                subtitle += '\n' + line
            elif line.startswith('>'):
                temp: str = line.replace('>', '').replace('^[‡]', '‡').replace('[]', '').replace('(#small)', '')
                temp = temp.replace('(#crate)', '(#crat)').replace('(#toadstool)', '(#toad)').replace('(#cactus)', '(#cact)').replace('(#barrel)', '(#barr)')
                temp = temp.replace('(#pumpkin)', '(#pump)').replace('(#snowman)', '(#snow)')
                locations += temp + '\n'
            else:
                notes += line + '\n'
            
        locations = locations.strip().split('\n')[2:]
        notes = '\n'.join(notes.strip().split('\n')[1:])
        notes = notes.replace('__', '').replace('*', '•')

        dangerous: list[int] = []
        temp_locs: list[str] = copy.deepcopy(locations)
        for i, loc in enumerate(temp_locs):
            if '(#danger)' in loc:
                locations[i] = loc.replace('(#danger)', '')
                dangerous.append(i)

        table: list[list[str]] | list[str] | str = [loc.split('|') for loc in locations]
        result: list[list[str]] = copy.deepcopy(table)

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

        description: str = f'**{sub.title}**\n{subtitle}```{table}```'

        embed = discord.Embed(title=f'World 60 penguin locations', colour=0x00b2ff, timestamp=datetime.utcfromtimestamp(int(sub.created_utc)), url=sub.shortlink, description=description)
        embed.set_author(name=sub.author.name, icon_url=sub.author.icon_img)

        embed.add_field(name='Notes', value=notes)

        self.peng_embed = embed
        self.peng_time = datetime.now(UTC)

        await ctx.send(embed=embed)
    
    @commands.command(aliases=['wilderness_flash_events', 'wilderness_flash_event', 'wilderness_flash', 'wildy_flash', 'wildy_flash_events', 'wildy_flash_event'])
    async def flash(self, ctx: commands.Context) -> None:
        '''
        Returns the next wilderness flash event.
        '''
        self.bot.increment_command_counter()
        
        now: datetime = datetime.now(UTC)
        now = now.replace(microsecond=0)

        if not self.bot.wilderness_flash_event:
            raise commands.CommandError('Wilderness flash event status not found. Please try again and contact an administrator if the problem persists.')
        
        txt: str = f'Current: {self.bot.wilderness_flash_event["current"]}\nNext: {self.bot.wilderness_flash_event["next"]}' if self.bot.wilderness_flash_event["current"] else f'Next: {self.bot.wilderness_flash_event["next"]}'
        embed = discord.Embed(title='Wilderness flash event', colour=0x00b2ff, description=txt)
        embed.set_footer(text=timedelta_to_string((self.bot.next_wilderness_flash_event if self.bot.next_wilderness_flash_event else datetime.now(UTC)) - now))
        
        await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    await bot.add_cog(DNDCommands(bot))
