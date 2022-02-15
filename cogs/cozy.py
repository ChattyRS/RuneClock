import discord
from discord.ext import commands, tasks
from discord.ext.commands import Cog
import sys
sys.path.append('../')
from main import config_load, increment_command_counter, Poll, Guild
from datetime import datetime, timedelta, timezone
import re
import copy
import gspread
from utils import cozy_council, cozy_only
from bs4 import BeautifulSoup
from gcsa.google_calendar import GoogleCalendar
import math
from utils import is_int

config = config_load()

cozy_events = []

cozy_event_reminders_sent = []

cozy_sotw_url = ''
cozy_botw_url = ''

num_emoji = ['🇦', '🇧', '🇨', '🇩', '🇪', '🇫', '🇬', '🇭', '🇮', '🇯', '🇰', '🇱', '🇲', '🇳', '🇴', '🇵', '🇶', '🇷', '🇸', '🇹']

wom_metrics = [# Skills
               "overall", "attack", "defence", "strength", "hitpoints", "ranged", "prayer", "magic", "cooking", "woodcutting", "fletching", "fishing", 
               "firemaking", "crafting", "smithing", "mining", "herblore", "agility", "thieving", "slayer", "farming", "runecrafting", "hunter", "construction",
               # Clues & minigames
               "league_points", "bounty_hunter_hunter", "bounty_hunter_rogue", "clue_scrolls_all", "clue_scrolls_beginner", "clue_scrolls_easy",
               "clue_scrolls_medium", "clue_scrolls_hard", "clue_scrolls_elite", "clue_scrolls_master", "last_man_standing", "soul_wars_zeal",
               # Bosses
               "abyssal_sire", "alchemical_hydra", "barrows_chests", "bryophyta", "callisto", "cerberus", "chambers_of_xeric", "chambers_of_xeric_challenge_mode",
               "chaos_elemental", "chaos_fanatic", "commander_zilyana", "corporeal_beast", "crazy_archaeologist", "dagannoth_prime", "dagannoth_rex", "dagannoth_supreme",
               "deranged_archaeologist", "general_graardor", "giant_mole", "grotesque_guardians", "hespori", "kalphite_queen", "king_black_dragon", "kraken", "kreearra", 
               "kril_tsutsaroth", "mimic", "nex", "nightmare", "obor", "sarachnis", "scorpia", "skotizo", "tempoross", "the_gauntlet", "the_corrupted_gauntlet", "theatre_of_blood",
               "theatre_of_blood_hard_mode", "thermonuclear_smoke_devil", "tzkal_zuk", "tztok_jad", "venenatis", "vetion", "vorkath", "wintertodt", "zalcano", "zulrah", 
               # Misc
               "ehp", "ehb"]

class Cozy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_sotw_url.start()
        self.get_updated_calendar_events.start()
        self.cozy_event_reminders.start()
        self.wom_update_all.start()
        self.update_botw_url.start()

    def cog_unload(self):
        self.update_sotw_url.cancel()
        self.get_updated_calendar_events.cancel()
        self.cozy_event_reminders.cancel()
        self.wom_update_all.cancel()
        self.update_botw_url.cancel()
    
    @tasks.loop(seconds=60)
    async def get_updated_calendar_events(self):
        '''
        updates the variable 'cozy_events' from the cozy calendar
        '''
        global cozy_events
        calendar = GoogleCalendar(config['cozy_calendar'], credentials_path='data/calendar_credentials.json')

        events = calendar.get_events(single_events=True)
        date_events = []
        datetime_events = []
        for event in events:
            try:
                _ = event.start.date()
                datetime_events.append(event)
            except:
                date_events.append(event)
        date_events = sorted(date_events, key=lambda e: e.start)
        datetime_events = sorted(datetime_events, key=lambda e: e.start)
        events = []
        if date_events and datetime_events:
            d = min(date_events[0].start, datetime_events[0].start.date())
            d_end = max(date_events[len(date_events)-1].start, datetime_events[len(datetime_events)-1].start.date())
        elif date_events:
            d = date_events[0].start
            d_end = date_events[len(date_events)-1].start
        elif datetime_events:
            d = datetime_events[0].start.date()
            d_end = datetime_events[len(datetime_events)-1].start.date()
        else:
            return
        while d <= d_end:
            for e in date_events:
                if e.start == d:
                    events.append(e)
            for e in datetime_events:
                if e.start.date() == d:
                    events.append(e)
            d += timedelta(days=1)
        
        if len(cozy_events) > 0:
            if events != cozy_events:
                channel = self.bot.get_channel(config['cozy_calendar_spam_channel'])
                for event in events:
                    if not event in cozy_events:
                        try:
                            _ = event.start.date()
                            if event.start < datetime.now(tz=timezone.utc) + timedelta(days=360):
                                await channel.send(f'A new event has been added to the Cozy Calendar!\n```Date: {event.start.date().strftime("%d %b %Y")}\nTime: {event.start.time().strftime("%I:%M %p UTC")}\nSummary: {event.summary}```')
                        except:
                            if event.start < (datetime.utcnow() + timedelta(days=360)).date():
                                await channel.send(f'A new event has been added to the Cozy Calendar!\n```Date: {event.start.date().strftime("%d %b %Y")}\nTime: All day\nSummary: {event.summary}```')

        cozy_events = events
    
    @tasks.loop(seconds=60)
    async def cozy_event_reminders(self):
        global cozy_events
        global cozy_event_reminders_sent
        if cozy_events:
            now = datetime.now(tz=timezone.utc)
            five_min_ago = now - timedelta(minutes=5)
            for event in cozy_events:
                try:
                    half_hour_before_event = event.start - timedelta(minutes=30)
                    if five_min_ago < half_hour_before_event < now:
                        if not event.event_id in cozy_event_reminders_sent:
                            channel = self.bot.get_channel(config['cozy_events_channel'])
                            await channel.send(f'Reminder: The following event will start in 30 minutes! @here\n**{event.summary}**')
                            cozy_event_reminders_sent.append(event.event_id)
                except:
                    continue
    
    @tasks.loop(seconds=300)
    async def update_sotw_url(self):
        '''
        updates the variable 'cozy_sotw_url' from a discord channel
        '''
        global cozy_sotw_url
        channel = self.bot.get_channel(config['cozy_sotw_voting_channel_id'])
        if channel:
            sotw_message = None
            wom = True
            async for message in channel.history(limit=10):
                if 'https://templeosrs.com/competitions/standings.php?id=' in message.content:
                    wom = False
                    sotw_message = message
                elif 'https://wiseoldman.net/competitions/' in message.content:
                    sotw_message = message
                if sotw_message:
                    if wom:
                        id = sotw_message.content.split('https://wiseoldman.net/competitions/')[1].split('/')[0]
                        url = f'https://wiseoldman.net/competitions/{id}'
                        if url != cozy_sotw_url:
                            api_url = "https://api.wiseoldman" + url.split('wiseoldman')[1]
                            r = await self.bot.aiohttp.get(api_url)
                            async with r:
                                if r.status != 200:
                                    sotw_message = None
                                    continue
                                data = await r.json()
                                start = datetime.strptime(data['startsAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                                end = datetime.strptime(data['endsAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                                if not (start < datetime.utcnow() < end):
                                    sotw_message = None
                                    continue
                    else:
                        id = sotw_message.content.split('https://templeosrs.com/competitions/standings.php?id=')[1][:4]
                        url = f'https://templeosrs.com/competitions/standings.php?id={id}'
                    
                    cozy_sotw_url = url
                    break
    
    @tasks.loop(seconds=300)
    async def update_botw_url(self):
        '''
        updates the variable 'cozy_botw_url' from a discord channel
        '''
        global cozy_botw_url
        channel = self.bot.get_channel(config['cozy_botw_voting_channel_id'])
        if channel:
            botw_message = None
            wom = True
            async for message in channel.history(limit=10):
                if 'https://templeosrs.com/competitions/standings.php?id=' in message.content:
                    wom = False
                    botw_message = message
                elif 'https://wiseoldman.net/competitions/' in message.content:
                    botw_message = message
                if botw_message:
                    if wom:
                        id = botw_message.content.split('https://wiseoldman.net/competitions/')[1].split('/')[0]
                        url = f'https://wiseoldman.net/competitions/{id}'
                        if url != cozy_botw_url:
                            api_url = "https://api.wiseoldman" + url.split('wiseoldman')[1]
                            r = await self.bot.aiohttp.get(api_url)
                            async with r:
                                if r.status != 200:
                                    botw_message = None
                                    continue
                                data = await r.json()
                                start = datetime.strptime(data['startsAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                                end = datetime.strptime(data['endsAt'], '%Y-%m-%dT%H:%M:%S.%fZ')
                                if not (start < datetime.utcnow() < end):
                                    botw_message = None
                                    continue
                    else:
                        id = botw_message.content.split('https://templeosrs.com/competitions/standings.php?id=')[1][:4]
                        url = f'https://templeosrs.com/competitions/standings.php?id={id}'
                    
                    cozy_botw_url = url
                    break
    

    @tasks.loop(seconds=300)
    async def wom_update_all(self):
        '''
        Updates all players in the Cozy Corner group on wiseoldman.net
        '''
        time = datetime.utcnow()
        # Update every 6 hours
        if time.hour % 6 == 0 and time.minute < 5:
            url = 'https://api.wiseoldman.net/groups/423/update-all'
            payload = {'verificationCode': config['cozy_wiseoldman_verification_code']}
            async with self.bot.aiohttp.post(url, json=payload) as r:
                if r.status != 200:
                    print(f'Error updating wiseoldman group.\nStatus: {r.status}.')
                    return
                data = await r.json()
                print(f'Wiseoldman group updated.\nResponse: {data["message"]}')
    
    @Cog.listener()
    async def on_user_update(self, before, after):
        if before.name != after.name or before.discriminator != after.discriminator:
            cozy = self.bot.get_guild(config['cozy_guild_id'])
            if cozy:
                if after.id in [member.id for member in cozy.members]:
                    guild = await Guild.get(cozy.id)
                    if guild:
                        if guild.log_channel_id:
                            channel = cozy.get_channel(guild.log_channel_id)

                            member = None
                            for m in cozy.members:
                                if m.id == after.id:
                                    member = m
                                    break
                            
                            if member:
                                beforeName = f'{before.name}#{before.discriminator}'
                                afterName = f'{after.name}#{after.discriminator}'
                                txt = f'{member.mention} {afterName}'
                                embed = discord.Embed(title=f'**Name Changed**', colour=0x00b2ff, timestamp=datetime.utcnow(), description=txt)
                                embed.add_field(name='Previously', value=beforeName, inline=False)
                                embed.set_footer(text=f'User ID: {after.id}')
                                embed.set_thumbnail(url=after.display_avatar.url)
                                try:
                                    await channel.send(embed=embed)
                                except discord.Forbidden:
                                    pass

                                agc = await self.bot.agcm.authorize()
                                ss = await agc.open_by_key(config['cozy_roster_key'])
                                roster = await ss.worksheet('Roster')

                                values = await roster.get_all_values()
                                values = values[1:]

                                found = False
                                for i, val in enumerate(values):
                                    if val[5] == beforeName:
                                        await roster.update_cell(i+2, 6, afterName)
                                        await channel.send(f'The roster has been updated with the new username: `{afterName}`.')
                                        found = True
                                        break
                                
                                if not found:
                                    await channel.send(f'The roster has **not** been updated, because the old value `{beforeName}` could not be found.')

    @commands.command(hidden=True)
    @cozy_council()
    @cozy_only()
    async def cozy_promo(self, ctx, *names):
        '''
        Promotes a rank on the Cozy CC clan roster and on Discord if applicable.
        Arguments: names (separated by commas)
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        names = ' '.join(names).strip()
        names = names.split(',')
        for i, name in enumerate(names):
            names[i] = name.strip()
        names = list(filter(None, names))

        if not names:
            raise commands.CommandError(message=f'Required argument missing: `names`.')
        if any(len(name) > 12 or re.match('^[A-z0-9 -]+$', name) is None for name in names):
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_roster_key'])
        roster = await ss.worksheet('Roster')

        header_rows = 1

        values = await roster.get_all_values()
        values = values[header_rows:]

        original_values = copy.deepcopy(values)

        full_range = f'A{header_rows+1}:I{len(values)+header_rows}'

        members = [value[0] for value in values]

        msg = ''

        for name in names:
            index = -1
            for i, m in enumerate(members):
                if (m.upper() == name.upper()):
                    index = i
                    break
            if index == -1:
                for i, m in enumerate(members):
                    if (name.upper() in m.upper()):
                        index = i
                        break
            if index == -1:
                msg += f'Could not find member: `{name}`.\n'
                continue

            name = members[index]
            row = index

            entry = values[row]

            rank = entry[1]

            ranks = ["Friend", "Squire", "Knight", "Paladin", "Sage", "Elder", "Hero", "Champion", "Council"]
            ranks_points = ['1', '2', '3', '4', '5', '6', '8', '9', '10']
            role_ids = [config['cozy_friend_role_id'],
                        config['cozy_squire_role_id'],
                        config['cozy_knight_role_id'],
                        config['cozy_paladin_role_id'],
                        config['cozy_sage_role_id'],
                        config['cozy_elder_role_id'],
                        config['cozy_hero_role_id'],
                        config['cozy_champion_role_id'],
                        config['cozy_council_role_id']]

            rank_points = 0
            old_role_id = 0
            role_id = 0

            if rank == ranks[len(ranks)-1]:
                msg += f'`{name}` cannot be promoted any further.\n'
                continue
            elif (not rank in ranks):
                msg += f'`{name}` cannot be promoted from their current rank: `{rank}`.\n'
                continue
            else:
                for i, r in enumerate(ranks):
                    if r == rank:
                        rank = ranks[i+1]
                        rank_points = ranks_points[i+1]
                        old_role_id = role_ids[i]
                        role_id = role_ids[i+1]
                        break

            values[row][1] = rank
            values[row][9] = rank_points

            msg += f'`{name}` was promoted to `{rank}`.\n'

            if entry[4] == 'Yes':
                disc_name = entry[5].strip()
                disc_account = None
                for member in ctx.guild.members:
                    if f'{member.name}#{member.discriminator}' == disc_name:
                        disc_account = member
                        break
                if disc_account:
                    old_role = ctx.guild.get_role(old_role_id)
                    role = ctx.guild.get_role(role_id)
                    roles = disc_account.roles
                    if not old_role in roles:
                        msg += f'Error: discord user `{disc_name}` for member `{name}` did not have role `{old_role.name}. Their discord account has not been promoted.`.\n'
                        continue
                    elif role in roles:
                        msg += f'Error: discord user `{disc_name}` for member `{name}` already had role `{old_role.name}. Their discord account has not been promoted further.`.\n'
                        continue
                    if old_role.id != role_ids[0]:
                        roles.remove(old_role)
                    roles.append(role)
                    try:
                        await disc_account.edit(roles=roles)
                    except:
                        msg += f'I have insufficient permissions to assign role `{role.name}` to `{name}`.'
                        continue
                    msg += f'`{disc_name}` was given role `{role.name}`.\n'
                else:
                    msg += f'Could not find discord user `{disc_name}` for member `{name}`.\n'

        values = sorted(values, key=lambda r: r[0].upper()) # sort by name
        values = sorted(values, key=lambda r: r[9], reverse=True) # sort by rank

        for i, row in enumerate(values):
            values[i] = row[:8]
        for i, row in enumerate(original_values):
            original_values[i] = row[:8]

        if (values != original_values):
            await roster.batch_update([{'range': full_range, 'values': values}])

        await ctx.send(msg)
    
    @commands.command(hidden=True)
    @cozy_council()
    @cozy_only()
    async def cozy_demo(self, ctx, *names):
        '''
        Demotes a rank on the Cozy CC clan roster and on Discord if applicable.
        Arguments: names (separated by commas)
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        admin_role = ctx.guild.get_role(config['cozy_admin_role_id'])
        is_cozy_admin = admin_role in ctx.author.roles or ctx.author.id == config['owner']

        names = ' '.join(names).strip()
        names = names.split(',')
        for i, name in enumerate(names):
            names[i] = name.strip()
        names = list(filter(None, names))

        if not names:
            raise commands.CommandError(message=f'Required argument missing: `names`.')
        if any(len(name) > 12 or re.match('^[A-z0-9 -]+$', name) is None for name in names):
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_roster_key'])
        roster = await ss.worksheet('Roster')

        header_rows = 1

        values = await roster.get_all_values()
        values = values[header_rows:]

        original_values = copy.deepcopy(values)

        full_range = f'A{header_rows+1}:I{len(values)+header_rows}'

        members = [value[0] for value in values]

        msg = ''

        for name in names:
            index = -1
            for i, m in enumerate(members):
                if (m.upper() == name.upper()):
                    index = i
                    break
            if index == -1:
                for i, m in enumerate(members):
                    if (name.upper() in m.upper()):
                        index = i
                        break
            if index == -1:
                msg += f'Could not find member: `{name}`.\n'
                continue

            name = members[index]
            row = index

            entry = values[row]

            rank = entry[1]

            ranks = ["Friend", "Squire", "Knight", "Paladin", "Sage", "Elder", "Hero", "Champion", "Council"]
            ranks_points = ['1', '2', '3', '4', '5', '6', '8', '9', '10']
            role_ids = [config['cozy_friend_role_id'],
                        config['cozy_squire_role_id'],
                        config['cozy_knight_role_id'],
                        config['cozy_paladin_role_id'],
                        config['cozy_sage_role_id'],
                        config['cozy_elder_role_id'],
                        config['cozy_hero_role_id'],
                        config['cozy_champion_role_id'],
                        config['cozy_council_role_id']]

            rank_points = 0
            old_role_id = 0
            role_id = 0

            if rank == ranks[0]:
                msg += f'`{name}` cannot be demoted any further.\n'
                continue
            elif (not rank in ranks):
                msg += f'`{name}` cannot be demoted from their current rank: `{rank}`.\n'
                continue
            else:
                for i, r in enumerate(ranks):
                    if r == rank:
                        rank = ranks[i-1]
                        rank_points = ranks_points[i-1]
                        old_role_id = role_ids[i]
                        role_id = role_ids[i-1]
                        break

            if old_role_id == config['cozy_council_role_id']:
                if not is_cozy_admin:
                    msg += f'You have insufficient permissions to demote `{name}`.'
                    continue

            values[row][1] = rank
            values[row][9] = rank_points

            msg += f'`{name}` was demoted to `{rank}`.\n'

            if entry[4] == 'Yes':
                disc_name = entry[5].strip()
                disc_account = None
                for member in ctx.guild.members:
                    if f'{member.name}#{member.discriminator}' == disc_name:
                        disc_account = member
                        break
                if disc_account:
                    old_role = ctx.guild.get_role(old_role_id)
                    role = ctx.guild.get_role(role_id)
                    roles = disc_account.roles
                    if not old_role in roles:
                        msg += f'Error: discord user `{disc_name}` for member `{name}` did not have role `{old_role.name}. Their discord account has not been demoted.`.\n'
                        continue
                    roles.remove(old_role)
                    if not role in roles:
                        roles.append(role)
                    try:
                        await disc_account.edit(roles=roles)
                    except:
                        msg += f'I have insufficient permissions to remove role `{old_role.name}` from `{name}`.'
                        continue
                    msg += f'`{disc_name}` was given role `{role.name}`.\n'
                else:
                    msg += f'Could not find discord user `{disc_name}` for member `{name}`.\n'

        values = sorted(values, key=lambda r: r[0].upper()) # sort by name
        values = sorted(values, key=lambda r: r[9], reverse=True) # sort by rank

        for i, row in enumerate(values):
            values[i] = row[:8]
        for i, row in enumerate(original_values):
            original_values[i] = row[:8]

        if (values != original_values):
            await roster.batch_update([{'range': full_range, 'values': values}])

        await ctx.send(msg)
    
    @commands.command(hidden=True)
    @cozy_council()
    @cozy_only()
    async def cozy_rename(self, ctx, *names):
        '''
        Update a Cozy Corner member's name after a name change.
        Sheet will be updated as well as discord.
        Arguments: old_name, new_name (separated by a comma)
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        names = ' '.join(names).strip()
        names = names.split(',')
        for i, name in enumerate(names):
            names[i] = name.strip()
        names = list(filter(None, names))

        if not names:
            raise commands.CommandError(message=f'Required argument missing: `names`.')
        if any(len(name) > 12 or re.match('^[A-z0-9 -]+$', name) is None for name in names):
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if not len(names) == 2:
            raise commands.CommandError(message=f'Incorrect number of arguments. This command takes exactly `2` arguments.')

        name, new_name = names

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_roster_key'])
        roster = await ss.worksheet('Roster')

        header_rows = 1

        values = await roster.get_all_values()
        values = values[header_rows:]

        original_values = copy.deepcopy(values)

        full_range = f'A{header_rows+1}:I{len(values)+header_rows}'

        members = [value[0] for value in values]

        msg = ''

        index = -1
        for i, m in enumerate(members):
            if (m.upper() == name.upper()):
                index = i
                break
        if index == -1:
            for i, m in enumerate(members):
                if (name.upper() in m.upper()):
                    index = i
                    break
        if index == -1:
            raise commands.CommandError(message=f'Could not find member: `{name}`.')

        name = members[index]
        row = index

        values[row][0] = new_name

        notes = values[row][6]
        if not notes == "" and not notes.endswith("."):
            notes += "."
        if not notes == "" and not notes.endswith(" "):
            notes += " "
        notes += f'Formerly {name}'
        values[row][6] = notes

        msg += f'`{name}`\'s name was changed to `{new_name}`.\n'

        if values[row][4] == 'Yes':
            disc_name = values[row][5].strip()
            disc_account = None
            for member in ctx.guild.members:
                if f'{member.name}#{member.discriminator}' == disc_name:
                    disc_account = member
                    break
            if disc_account:
                if not new_name in disc_account.display_name:
                    if name in disc_account.display_name:
                        try:
                            nickname = disc_account.display_name.replace(name, new_name)
                            await disc_account.edit(nick=nickname)
                            msg += f'`{disc_name}`\'s nickname was changed to `{nickname}`.\n'
                        except discord.Forbidden:
                            msg += f'I do not have permission to change `{disc_name}`\'s nickname.\n'
                    else:
                        msg += f'Could not update `{disc_name}`\'s nickname, because their nickname does not match their old name.\n'
            else:
                msg += f'Could not find discord user `{disc_name}` for member `{name}`.\n'

        values = sorted(values, key=lambda r: r[0].upper()) # sort by name
        values = sorted(values, key=lambda r: r[9], reverse=True) # sort by rank

        for i, row in enumerate(values):
            values[i] = row[:8]
        for i, row in enumerate(original_values):
            original_values[i] = row[:8]

        if (values != original_values):
            await roster.batch_update([{'range': full_range, 'values': values}])

        await ctx.send(msg)
    
    @commands.command()
    @cozy_only()
    async def cozy_sotw(self, ctx):
        '''
        Shows top-10 for the current SOTW
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        global cozy_sotw_url
        url = cozy_sotw_url

        if 'wiseoldman' in url:
            url = "https://api.wiseoldman" + url.split('wiseoldman')[1]
        else:
            raise commands.CommandError(message=f'Could not find SOTW URL.')
            
        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving data from: `{url}`.')
            
            if 'wiseoldman' in url:
                data = await r.json()

                skill = data['metric']
                skill = skill[0].upper() + skill[1:]
                top10 = data['participants'][:10]

                msg = 'No.  Name          Gain'
                for i, p in enumerate(top10):
                    msg += f'\n{i+1}.' + (4 - len(str(i+1))) * ' '
                    msg += p['displayName'] + (14 - len(p['displayName'])) * ' '
                    msg += str(p['progress']['gained'])
                
                await ctx.send(f'**{skill} SOTW**\n```{msg}```')

            elif 'templeosrs' in url:
                data = await r.text()

                bs = BeautifulSoup(data, "html.parser")
                table_body = bs.find('table')
                rows = table_body.find_all('tr')[1:]
                player_url = ''
                for i, row in enumerate(rows):
                    cols = row.find_all('td')
                    if i == 0:
                        player_urls = cols[1].find_all('a', href=True)
                        player_url = player_urls[0]['href']
                    cols = [x.text.strip() for x in cols]
                    rows[i] = cols

                skill = player_url.split('&skill=')[1]
                skill = skill.split('&')[0]
                skill = skill[0].upper() + skill[1:]

                for i, row in enumerate(rows):
                    row[1] = row[1].replace(f'{row[2]}{row[3]}{row[4]}', '')
                    rows[i] = row

                msg = 'No.  Name          Gain'
                for row in rows[:10]:
                    msg += '\n' + row[0] + (5 - len(row[0])) * ' '
                    msg += row[1] + (14 - len(row[1])) * ' '
                    msg += row[2]

                await ctx.send(f'**{skill} SOTW**\n```{msg}```')
    
    @commands.command()
    @cozy_only()
    async def cozy_botw(self, ctx):
        '''
        Shows top-10 for the current BOTW
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        global cozy_botw_url
        url = cozy_botw_url

        if 'wiseoldman' in url:
            url = "https://api.wiseoldman" + url.split('wiseoldman')[1]
        else:
            raise commands.CommandError(message=f'Could not find BOTW URL.')
            
        r = await self.bot.aiohttp.get(url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving data from: `{url}`.')
            
            if 'wiseoldman' in url:
                data = await r.json()

                boss = data['metric']
                boss = boss[0].upper() + boss[1:]
                top10 = data['participants'][:10]

                msg = 'No.  Name          Gain'
                for i, p in enumerate(top10):
                    msg += f'\n{i+1}.' + (4 - len(str(i+1))) * ' '
                    msg += p['displayName'] + (14 - len(p['displayName'])) * ' '
                    msg += str(p['progress']['gained'])
                
                await ctx.send(f'**{boss} BOTW**\n```{msg}```')

            elif 'templeosrs' in url:
                data = await r.text()

                bs = BeautifulSoup(data, "html.parser")
                table_body = bs.find('table')
                rows = table_body.find_all('tr')[1:]
                player_url = ''
                for i, row in enumerate(rows):
                    cols = row.find_all('td')
                    if i == 0:
                        player_urls = cols[1].find_all('a', href=True)
                        player_url = player_urls[0]['href']
                    cols = [x.text.strip() for x in cols]
                    rows[i] = cols

                boss = player_url.split('&skill=')[1]
                boss = boss.split('&')[0]
                boss = boss[0].upper() + boss[1:]

                for i, row in enumerate(rows):
                    row[1] = row[1].replace(f'{row[2]}{row[3]}{row[4]}', '')
                    rows[i] = row

                msg = 'No.  Name          Gain'
                for row in rows[:10]:
                    msg += '\n' + row[0] + (5 - len(row[0])) * ' '
                    msg += row[1] + (14 - len(row[1])) * ' '
                    msg += row[2]

                await ctx.send(f'**{boss} BOTW**\n```{msg}```')
    
    @commands.command()
    @cozy_only()
    async def cozy_schedule(self, ctx):
        '''
        Shows this week's planned events for Cozy Corner CC.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        calendar = GoogleCalendar(config['cozy_calendar'], credentials_path='data/calendar_credentials.json')

        monday = datetime.utcnow().date() - timedelta(days=datetime.utcnow().date().weekday())
        sunday = monday + timedelta(days=7)
        events = calendar.get_events(monday, sunday, single_events=True)
        date_events = []
        datetime_events = []
        for event in events:
            try:
                _ = event.start.date()
                datetime_events.append(event)
            except:
                date_events.append(event)
        date_events = sorted(date_events, key=lambda e: e.start)
        datetime_events = sorted(datetime_events, key=lambda e: e.start)
        events = []
        d = monday
        while d <= sunday:
            for e in date_events:
                if e.start == d:
                    events.append(e)
            for e in datetime_events:
                if e.start.date() == d:
                    events.append(e)
            d += timedelta(days=1)

        msg = ''

        d = monday - timedelta(days=1)
        for event in events:
            try:
                _ = event.start.date()
                if event.start.date() != d:
                    d = event.start.date()
                    msg += f'\n\n**{d.strftime("%A")}**'
                time = event.start.time().strftime("%I:%M %p UTC")
            except:
                if event.start != d:
                    d = event.start
                    msg += f'\n\n**{d.strftime("%A")}**'
                time = "All day"
            if time.startswith('0'):
                time = time[1:]
            msg += f'\n**{time}**: {event.summary}'
        
        await ctx.send(msg.strip())

    @commands.command()
    @cozy_council()
    async def wom_add(self, ctx, *name):
        '''
        Add a member to the Cozy Corner wiseoldman group.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ' '.join(name)

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`. Character limit exceeded.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`. Forbidden character.')

        url = 'https://api.wiseoldman.net/groups/423/add-members'

        payload = {'verificationCode': config['cozy_wiseoldman_verification_code']}
        payload['members'] = [{'username': name, 'role': 'member'}]
        async with self.bot.aiohttp.post(url, json=payload) as r:
            if r.status != 200:
                data = await r.json()
                raise commands.CommandError(message=f'Error status: {r.status}\n{data}.')
            data = await r.json()
            await ctx.send(f'Added member: {name}')
    
    @commands.command()
    @cozy_council()
    async def wom_remove(self, ctx, *name):
        '''
        Remove a member from the Cozy Corner wiseoldman group.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ' '.join(name)

        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`. Character limit exceeded.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`. Forbidden character.')
        
        url = 'https://api.wiseoldman.net/groups/423/remove-members'

        payload = {'verificationCode': config['cozy_wiseoldman_verification_code']}
        payload['members'] = [name]
        async with self.bot.aiohttp.post(url, json=payload) as r:
            if r.status != 200:
                data = await r.json()
                raise commands.CommandError(message=f'Error status: {r.status}\n{data}.')
            data = await r.json()
            await ctx.send(f'Removed member: {name}')
    
    @commands.command()
    @cozy_council()
    @cozy_only()
    async def sotw_poll(self, ctx):
        '''
        Posts a poll for the next SOTW competition.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_sotw_logging_key'])
        sotw_sheet = await ss.worksheet('SOTW')

        row = await sotw_sheet.row_values(2)
        if len(row) <= 2:
            raise commands.CommandError(message=f'Please generate the skills for the next vote by clicking the `Generate` button on the SOTW logging sheet before using this command.')
        skills = row[2:]

        if "Wildcard" in skills:
            raise commands.CommandError(message=f'Please have the previous winner choose a skill from the wildcards and replace the wildcard on the SOTW logging sheet before using this command.')
        
        if len(skills) < 2:
            raise commands.CommandError(message=f'Too few options. Please correctly generate the skills for the next vote on the SOTW logging sheet.')
        if len(skills) > 20:
            raise commands.CommandError(message=f'Too many options. Please check the SOTW logging sheet.')

        past_sotw_sheet = await ss.worksheet('Past_SOTWs')
        col = await past_sotw_sheet.col_values(2)
        next_num = len(col)

        now = datetime.utcnow()
        next_monday = now + timedelta(days=-now.weekday(), weeks=1)
        next_monday = next_monday.replace(hour=0, minute=0, second=0, microsecond=0)
        dif = next_monday - now
        hours = math.floor(dif.total_seconds() / 3600) - 1

        txt = ''
        i = 0
        for opt in skills:
            txt += f'\n{num_emoji[i]} {opt}'
            i += 1
        txt += f'\n\nThis poll will be open for {hours} hours!'

        embed = discord.Embed(title=f'**SOTW #{next_num}**', description=txt, timestamp=datetime.utcnow())
        embed.set_author(name=ctx.message.author.display_name, icon_url=ctx.message.author.display_avatar.url)

        channel = self.bot.get_channel(config['cozy_sotw_voting_channel_id'])

        msg = await channel.send(embed=embed)
        embed.set_footer(text=f'ID: {msg.id}')
        await msg.edit(embed=embed)
        for num in range(i):
            await msg.add_reaction(num_emoji[num])
        
        await Poll.create(guild_id=msg.guild.id, author_id=ctx.author.id, channel_id=channel.id, message_id=msg.id, end_time = datetime.utcnow()+timedelta(hours=hours))

        await ctx.send(f'Success! Your poll has been created. {ctx.author.mention}')
    
    @commands.command()
    @cozy_council()
    @cozy_only()
    async def botw_poll(self, ctx):
        '''
        Posts a poll for the next BOTW competition.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_botw_logging_key'])
        sotw_sheet = await ss.worksheet('BOTW')

        row = await sotw_sheet.row_values(2)
        if len(row) <= 2:
            raise commands.CommandError(message=f'Please generate the bosses for the next vote by clicking the `Generate` button on the BOTW logging sheet before using this command.')
        bosses = row[2:]

        if "Wildcard" in bosses:
            raise commands.CommandError(message=f'Please have the previous winner choose a boss as wildcard and replace the wildcard on the BOTW logging sheet before using this command.')
        
        if len(bosses) < 2:
            raise commands.CommandError(message=f'Too few options. Please correctly generate the bosses for the next vote on the BOTW logging sheet.')
        if len(bosses) > 20:
            raise commands.CommandError(message=f'Too many options. Please check the BOTW logging sheet.')

        past_botw_sheet = await ss.worksheet('Past_BOTWs')
        col = await past_botw_sheet.col_values(2)
        next_num = len(col)

        now = datetime.utcnow()
        next_monday = now + timedelta(days=-now.weekday(), weeks=1)
        next_monday = next_monday.replace(hour=0, minute=0, second=0, microsecond=0)
        dif = next_monday - now
        hours = math.floor(dif.total_seconds() / 3600) - 1

        txt = ''
        i = 0
        for opt in bosses:
            txt += f'\n{num_emoji[i]} {opt}'
            i += 1
        txt += f'\n\nThis poll will be open for {hours} hours!'

        embed = discord.Embed(title=f'**BOTW #{next_num}**', description=txt, timestamp=datetime.utcnow())
        embed.set_author(name=ctx.message.author.display_name, icon_url=ctx.message.author.display_avatar.url)

        channel = self.bot.get_channel(config['cozy_botw_voting_channel_id'])

        msg = await channel.send(embed=embed)
        embed.set_footer(text=f'ID: {msg.id}')
        await msg.edit(embed=embed)
        for num in range(i):
            await msg.add_reaction(num_emoji[num])
        
        await Poll.create(guild_id=msg.guild.id, author_id=ctx.author.id, channel_id=channel.id, message_id=msg.id, end_time = datetime.utcnow()+timedelta(hours=hours))

        await ctx.send(f'Success! Your poll has been created. {ctx.author.mention}')
    
    @commands.command()
    @cozy_council()
    @cozy_only()
    async def wom_sotw(self, ctx, num: int, *skill: str):
        '''
        Creates a SOTW competition on wiseoldman.net.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not num:
            raise commands.CommandError(message=f'Required argument missing: `num`.')
        
        if not skill:
            raise commands.CommandError(message=f'Required argument missing: `skill`.')
        skill = "_".join(skill).lower()

        if not skill in wom_metrics:
            raise commands.CommandError(message=f'Invalid argument: `{skill}`. You can see the valid metrics here under "Metrics": https://wiseoldman.net/docs/competitions')

        title = f'Cozy Corner SOTW #{num}'
        groupId = 423
        groupVerificationCode = config['cozy_wiseoldman_verification_code']

        now = datetime.utcnow()
        start = now + timedelta(days=-now.weekday(), weeks=1)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(weeks=1)

        start = start.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        start = start[:len(start)-4] + "Z"

        end = end.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end = end[:len(end)-4] + "Z"

        payload = {"title": title, "metric": skill, "startsAt": start, "endsAt": end, "groupId": groupId, "groupVerificationCode": groupVerificationCode}
        url = 'https://api.wiseoldman.net/competitions'

        async with self.bot.aiohttp.post(url, json=payload) as r:
            if r.status != 201:
                raise commands.CommandError(message=f'Error status: {r.status}.')
            data = await r.json()
            await ctx.send(f'Competition created:\n```Title: {data["title"]}\nMetric: {data["metric"]}\nStart: {data["startsAt"]}\nEnd: {data["endsAt"]}```\nhttps://wiseoldman.net/competitions/{data["id"]}/participants')
    
    @commands.command()
    @cozy_council()
    @cozy_only()
    async def wom_botw(self, ctx, num: int, *boss: str):
        '''
        Creates a BOTW competition on wiseoldman.net.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not num:
            raise commands.CommandError(message=f'Required argument missing: `num`.')
        
        if not boss:
            raise commands.CommandError(message=f'Required argument missing: `boss`.')
        boss = "_".join(boss).lower()

        if not boss in wom_metrics:
            raise commands.CommandError(message=f'Invalid argument: `{boss}`. You can see the valid metrics here under "Metrics": https://wiseoldman.net/docs/competitions')

        title = f'Cozy Corner BOTW #{num}'
        groupId = 423
        groupVerificationCode = config['cozy_wiseoldman_verification_code']

        now = datetime.utcnow()
        start = now + timedelta(days=-now.weekday(), weeks=1)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(weeks=1)

        start = start.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        start = start[:len(start)-4] + "Z"

        end = end.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end = end[:len(end)-4] + "Z"

        payload = {"title": title, "metric": boss, "startsAt": start, "endsAt": end, "groupId": groupId, "groupVerificationCode": groupVerificationCode}
        url = 'https://api.wiseoldman.net/competitions'

        async with self.bot.aiohttp.post(url, json=payload) as r:
            if r.status != 201:
                raise commands.CommandError(message=f'Error status: {r.status}.')
            data = await r.json()
            await ctx.send(f'Competition created:\n```Title: {data["title"]}\nMetric: {data["metric"]}\nStart: {data["startsAt"]}\nEnd: {data["endsAt"]}```\nhttps://wiseoldman.net/competitions/{data["id"]}/participants')
    
    @commands.command()
    @cozy_council()
    @cozy_only()
    async def cotw_poll(self, ctx):
        '''
        Creates polls for Cozy Of The Week
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_cotw_nominations_key'])
        nomination_sheet = await ss.worksheet('Nominations')

        nomination_values = await nomination_sheet.col_values(1)
        cotw_num = [int(s) for s in nomination_values[0].split() if s.isdigit()][0]
        nominees = nomination_values[2:]

        ss = await agc.open_by_key(config['cozy_roster_key'])
        roster = await ss.worksheet('Roster')

        roster_values = await roster.get_all_values()
        roster_values = roster_values[1:]

        unique_nominees = []
        for nominee in nominees:
            found = False
            for clannie in roster_values:
                if nominee.lower() in clannie[0].lower():
                    if not clannie[0] in unique_nominees:
                        unique_nominees.append(clannie[0])
                    found = True
                    break
            if not found:
                raise commands.CommandError(message=f'Could not find nominee: `{nominee}`.')
        
        normal_nominees = []
        ranked_nominees = []

        for nominee in unique_nominees:
            for clannie in roster_values:
                if nominee == clannie[0]:
                    if clannie[1] in ['Council', 'Champion', 'Hero']:
                        ranked_nominees.append(nominee)
                    else:
                        normal_nominees.append(nominee)
                    break

        if not normal_nominees:
            raise commands.CommandError(message=f'Error: could not find any non-ranked nominees.')
        if not ranked_nominees:
            raise commands.CommandError(message=f'Error: could not find any ranked nominees.')
        if len(normal_nominees) < 2:
            raise commands.CommandError(message=f'Not enough non-ranked nominees: `{len(normal_nominees)})`. At least 2 options are required to create a poll.')
        if len(ranked_nominees) < 2:
            raise commands.CommandError(message=f'Not enough ranked nominees: `{len(ranked_nominees)})`. At least 2 options are required to create a poll.')
        if len(normal_nominees) > 20:
            raise commands.CommandError(message=f'Too many non-ranked nominees: `{len(normal_nominees)})`. Polls only support up to 20 options.')
        if len(ranked_nominees) > 20:
            raise commands.CommandError(message=f'Too many ranked nominees: `{len(ranked_nominees)})`. Polls only support up to 20 options.')
        
        now = datetime.utcnow()
        end = now + timedelta(days=-now.weekday(), weeks=1)
        end = end.replace(hour=0, minute=0, second=0, microsecond=0)
        dif = end - now
        hours = math.floor(dif.total_seconds() / 3600) - 1

        txt = ''
        i = 0
        for opt in normal_nominees:
            txt += f'\n{num_emoji[i]} {opt}'
            i += 1
        txt += f'\n\nThis poll will be open for {hours} hours!'

        embed = discord.Embed(title=f'**COTW #{cotw_num}**', description=txt, timestamp=datetime.utcnow())
        embed.set_author(name=ctx.message.author.display_name, icon_url=ctx.message.author.display_avatar.url)

        channel = self.bot.get_channel(config['cozy_cotw_voting_channel_id'])

        msg = await channel.send(embed=embed)
        embed.set_footer(text=f'ID: {msg.id}')
        await msg.edit(embed=embed)
        for num in range(i):
            await msg.add_reaction(num_emoji[num])
        
        await Poll.create(guild_id=msg.guild.id, author_id=ctx.author.id, channel_id=channel.id, message_id=msg.id, end_time = datetime.utcnow()+timedelta(hours=hours))

        txt = ''
        i = 0
        for opt in ranked_nominees:
            txt += f'\n{num_emoji[i]} {opt}'
            i += 1
        txt += f'\n\nThis poll will be open for {hours} hours!'

        embed = discord.Embed(title=f'**Ranked COTW #{cotw_num}**', description=txt, timestamp=datetime.utcnow())
        embed.set_author(name=ctx.message.author.display_name, icon_url=ctx.message.author.display_avatar.url)

        msg = await channel.send(embed=embed)
        embed.set_footer(text=f'ID: {msg.id}')
        await msg.edit(embed=embed)
        for num in range(i):
            await msg.add_reaction(num_emoji[num])
        
        await Poll.create(guild_id=msg.guild.id, author_id=ctx.author.id, channel_id=channel.id, message_id=msg.id, end_time = datetime.utcnow()+timedelta(hours=hours))

        await ctx.send(f'Success! The polls for COTW #{cotw_num} have been created.')
    

    @commands.command()
    @cozy_council()
    @cozy_only()
    async def sotw_votes(self, ctx, msg_id):
        '''
        Records votes on a SOTW poll and logs them to the SOTW sheet.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not is_int(msg_id):
            raise commands.CommandError(message=f'Invalid argument: `{msg_id}`. Must be an integer.')
        msg_id = int(msg_id)

        try: 
            msg = await self.bot.get_channel(config['cozy_sotw_voting_channel_id']).fetch_message(msg_id)
        except:
            raise commands.CommandError(message=f'Error: could not find message: `{msg_id}`. Was the poll deleted?')
        
        results_emoji = {}
        for reaction in msg.reactions:
            results_emoji[str(reaction.emoji)] = reaction.count - 1
        
        num = int(msg.embeds[0].title.replace("*", "").split("#")[1])

        lines = msg.embeds[0].description.split('\n')
        lines = lines[:len(lines)-2]
        
        results = {}
        for r, v in results_emoji.items():
            for line in lines:
                split = line.split(' ')
                while '' in split:
                    split.remove('')
                e, s = split[0], ' '.join(split[1:])
                if e == r:
                    results[s] = v
                    lines.remove(line)
                    break

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_sotw_logging_key'])
        sotw_sheet = await ss.worksheet('SOTW_voting_data')

        values = await sotw_sheet.get_all_values()

        index = 0

        for i, row in enumerate(values):
            if i >= 2:
                if int(row[0]) == num:
                    if any(val != "" for val in row[2:]):
                        raise commands.CommandError(message=f'Error: there is already data present in the row for SOTW: `{num}`.')
                    index = i
                    break
        
        if not index:
            raise commands.CommandError(message=f'Error: could not find SOTW: `{num}`. Are you sure you entered the right number?')
        
        row = values[index]
        for skill, votes in results.items():
            found = False
            for i, val in enumerate(values[0]):
                if i >= 2:
                    if skill.lower() == val.lower():
                        row[i] = votes
                        found = True
                        break
            if not found:
                raise commands.CommandError(message=f'Error: could not find skill: `{skill}`. Please check the sheet.')

        vals = row[2:]
        data = {'range': f'C{index+1}:Z{index+1}', 'values': [vals]}

        await sotw_sheet.batch_update([data], value_input_option='USER_ENTERED')

        await ctx.send(f'Success! The voting data for SOTW #{num} has been logged.')
    

    @commands.command()
    @cozy_council()
    @cozy_only()
    async def botw_votes(self, ctx, msg_id):
        '''
        Records votes on a BOTW poll and logs them to the BOTW sheet.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not is_int(msg_id):
            raise commands.CommandError(message=f'Invalid argument: `{msg_id}`. Must be an integer.')
        msg_id = int(msg_id)

        try: 
            msg = await self.bot.get_channel(config['cozy_botw_voting_channel_id']).fetch_message(msg_id)
        except:
            raise commands.CommandError(message=f'Error: could not find message: `{msg_id}`. Was the poll deleted?')
        
        results_emoji = {}
        for reaction in msg.reactions:
            results_emoji[str(reaction.emoji)] = reaction.count - 1
        
        num = int(msg.embeds[0].title.replace("*", "").split("#")[1])

        lines = msg.embeds[0].description.split('\n')
        lines = lines[:len(lines)-2]
        
        results = {}
        for r, v in results_emoji.items():
            for line in lines:
                split = line.split(' ')
                while '' in split:
                    split.remove('')
                e, s = split[0], ' '.join(split[1:])
                if e == r:
                    results[s] = v
                    lines.remove(line)
                    break

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_botw_logging_key'])
        sotw_sheet = await ss.worksheet('BOTW_voting_data')

        values = await sotw_sheet.get_all_values()

        index = 0

        for i, row in enumerate(values):
            if i >= 2:
                if int(row[0]) == num:
                    if any(val != "" for val in row[2:]):
                        raise commands.CommandError(message=f'Error: there is already data present in the row for BOTW: `{num}`.')
                    index = i
                    break
        
        if not index:
            raise commands.CommandError(message=f'Error: could not find BOTW: `{num}`. Are you sure you entered the right number?')
        
        row = values[index]
        for boss, votes in results.items():
            found = False
            for i, val in enumerate(values[0]):
                if i >= 2:
                    if boss.lower() == val.lower():
                        row[i] = votes
                        found = True
                        break
            if not found:
                raise commands.CommandError(message=f'Error: could not find boss: `{boss}`. Please check the sheet.')

        vals = row[2:]
        data = {'range': f'C{index+1}:AW{index+1}', 'values': [vals]}

        await sotw_sheet.batch_update([data], value_input_option='USER_ENTERED')

        await ctx.send(f'Success! The voting data for BOTW #{num} has been logged.')
    

    @commands.command()
    @cozy_council()
    @cozy_only()
    async def get_compliments(self, ctx):
        '''
        Returns the list of compliments in a conveniently formatted text file
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_roster_key'])
        roster = await ss.worksheet('Roster')

        members = await roster.get_all_values()
        members = members[1:]

        ss = await agc.open_by_key(config['cozy_cotw_nominations_key'])
        compliment_sheet = await ss.worksheet('Nominations')

        compliments = await compliment_sheet.get_all_values()
        if (len(compliments) <= 2):
            raise commands.CommandError(message='The compliments sheet is empty.')
        compliments = compliments[2:]

        
        comps = []
        for compliment in compliments:
            c = [[compliment[0]], compliment[2]]
            dup = False
            for i, x in enumerate(comps):
                if x[1] == c[1]:
                    comps[i][0].append(c[0][0])
                    dup = True
                    break
            if not dup:
                comps.append(c)

        messages = []
        for compliment in comps:
            names, msg = compliment
            disc_names = []
            for name in names:
                disc_name = name
                for member in members:
                    member_name, disc = member[0], member[5].strip()
                    if member_name.lower() == name.lower():
                        cozy = self.bot.get_guild(config['cozy_guild_id'])
                        for m in cozy.members:
                            if f'{m.name}#{m.discriminator}' == disc:
                                disc_name = m.mention
                                break
                        break
                disc_names.append(disc_name)
            messages.append(f'{", ".join(disc_names)} - {msg}')
        
        txt = '\n\n'.join(messages)

        with open('data/compliments.txt', 'w', encoding='UTF-8') as file:
            file.write(txt)
        with open('data/compliments.txt', 'rb') as file:
            await ctx.send(file=discord.File(file, 'compliments.txt'))
    
    @commands.command()
    @cozy_council()
    @cozy_only()
    async def accept(self, ctx, member: discord.Member, *, notes = ''):
        '''
        Accepts a cozy application.
        Arguments: user (mention, id, etc.), notes (optional)
        This attempts to add the new member to the roster, set their discord display name to their RSN, and finally promote them in discord.
        '''
        increment_command_counter()
        await ctx.message.delete()
        await ctx.channel.trigger_typing()

        applicant_role = member.guild.get_role(config['cozy_applicant_role_id'])
        friends_role = member.guild.get_role(config['cozy_friend_role_id'])

        # Validation
        if not notes:
            notes = ''

        if (not applicant_role in member.roles) or (friends_role in member.roles):
            raise commands.CommandError(message=f'Error: incorrect roles for member: `{member.display_name}`. Either they are not an applicant, or they are already a friend.')

        message = None

        channel = self.bot.get_channel(config['cozy_applications_channel_id'])
        async for m in channel.history(limit=10):
            if m.author == member:
                message = m
                break

        if not message:
            raise commands.CommandError(message=f'Error: could not find application from member: `{member.display_name}`.')

        if not 'Total Level:' in message.content or not 'Are you an Ironman?:' in message.content or not 'Why do you want to join our clan?:' in message.content:
            raise commands.CommandError(message=f'Error: missing application form question. Applicants must copy and paste the questions for this command to work.')
        
        # Parse message
        rsn = message.content.replace('Cozy Application Form', '').replace('RuneScape Username:', '').strip().split('Total Level:')[0].strip()
        if not rsn:
            raise commands.CommandError(message=f'Error: could not parse username from message: `{message.id}`.')
        if len(rsn) > 12:
            raise commands.CommandError(message=f'Error: invalid RSN: `{rsn}`.')
        if re.match('^[A-z0-9 -]+$', rsn) is None:
            raise commands.CommandError(message=f'Error: invalid RSN: `{rsn}`.')

        ironman = message.content.split('Are you an Ironman?:')[1].split('Why do you want to join our clan?:')[0].strip()
        ironman = 'Ironman' if 'ye' in ironman.lower() else 'No'

        # Update roster
        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['cozy_roster_key'])
        roster = await ss.worksheet('Roster')

        members_col = await roster.col_values(1)
        rows = len(members_col)

        date_str = datetime.utcnow().strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row = [rsn, 'Friend', ironman, 'Yes', 'Yes', f'{member.display_name}#{member.discriminator}', notes, date_str]
        cell_list = [gspread.models.Cell(rows+1, i+1, value=val) for i, val in enumerate(new_row)]
        print(f'writing values:\n{new_row}\nto row {rows+1}')
        await roster.update_cells(cell_list)#, nowait=True)

        # Update member nickname and roles
        roles = member.roles
        roles.remove(applicant_role)
        roles.append(friends_role)
        await member.edit(nick=rsn, roles=roles)

        # Delete the application message
        # await message.delete()

        # Send response
        await ctx.send(f'`{member.display_name}`\'s application has been accepted.')


def setup(bot):
    bot.add_cog(Cozy(bot))
