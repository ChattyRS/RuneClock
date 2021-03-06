import discord
import asyncio
from discord.ext import commands, tasks
import sys
sys.path.append('../')
from main import config_load, addCommand
from datetime import datetime, timedelta, timezone
import re
import validators
import utils
import copy
import gspread_asyncio
import gspread
from utils import is_owner, is_admin
from utils import cozy_council
from bs4 import BeautifulSoup

config = config_load()

cozy_sotw_url = ''

class Cozy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_sotw_url.start()

    def cog_unload(self):
        self.update_sotw_url.cancel()
    
    @tasks.loop(seconds=300)
    async def update_sotw_url(self):
        '''
        updates the variable 'cozy_sotw_url' from a discord channel
        '''
        channel = self.bot.get_channel(config['cozy_sotw_voting_channel_id'])
        sotw_message = None
        async for message in channel.history(limit=10):
            if 'https://templeosrs.com/competitions/standings.php?id=' in message.content:
                sotw_message = message
                break
        if sotw_message:
            id = sotw_message.content.split('https://templeosrs.com/competitions/standings.php?id=')[1][:4]
            global cozy_sotw_url
            cozy_sotw_url = f'https://templeosrs.com/competitions/standings.php?id={id}'


    @commands.command(hidden=True)
    @cozy_council()
    async def cozy_promo(self, ctx, *names):
        '''
        Promotes a rank on the Cozy CC clan roster and on Discord if applicable.
        Arguments: names (separated by commas)
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if ctx.guild.id != config['cozy_guild_id'] and not ctx.author.id == config['owner']:
            raise commands.CommandError(message=f'This command cannot be used in this server.')

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

            ranks = ["Friend", "Squire", "Knight", "Paladin", "Hero", "Champion", "Council"]
            ranks_points = ['1', '2', '3', '4', '7', '8', '9']
            role_ids = [config['cozy_friend_role_id'],
                        config['cozy_squire_role_id'],
                        config['cozy_knight_role_id'],
                        config['cozy_paladin_role_id'],
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
                    roles.remove(old_role)
                    roles.append(role)
                    try:
                        await disc_account.edit(roles=roles)
                    except:
                        msg += f'I have insufficient permissions to assign `{role.name}` to `{name}`.'
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
    async def cozy_demo(self, ctx, *names):
        '''
        Demotes a rank on the Cozy CC clan roster and on Discord if applicable.
        Arguments: names (separated by commas)
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if ctx.guild.id != config['cozy_guild_id'] and not ctx.author.id == config['owner']:
            raise commands.CommandError(message=f'This command cannot be used in this server.')

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

            ranks = ["Friend", "Squire", "Knight", "Paladin", "Hero", "Champion", "Council"]
            ranks_points = ['1', '2', '3', '4', '7', '8', '9']
            role_ids = [config['cozy_friend_role_id'],
                        config['cozy_squire_role_id'],
                        config['cozy_knight_role_id'],
                        config['cozy_paladin_role_id'],
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
                        msg += f'I have insufficient permissions to remove `{old_role.name}` from `{name}`.'
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
    async def cozy_rename(self, ctx, *names):
        '''
        Update a Cozy Corner member's name after a name change.
        Sheet will be updated as well as discord.
        Arguments: old_name, new_name (separated by a comma)
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if ctx.guild.id != config['cozy_guild_id'] and not ctx.author.id == config['owner']:
            raise commands.CommandError(message=f'This command cannot be used in this server.')

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
    
    @commands.command(hidden=True)
    async def cozy_sotw(self, ctx):
        '''
        Shows top-10 for the current SOTW
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if ctx.guild.id != config['cozy_guild_id'] and not ctx.author.id == config['owner']:
            raise commands.CommandError(message=f'This command cannot be used in this server.')

        global cozy_sotw_url

        r = await self.bot.aiohttp.get(cozy_sotw_url)
        async with r:
            if r.status != 200:
                raise commands.CommandError(message=f'Error retrieving data from: `{cozy_sotw_url}`.')
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

def setup(bot):
    bot.add_cog(Cozy(bot))
