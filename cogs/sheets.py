import discord
import asyncio
from discord.ext import commands, tasks
import sys
sys.path.append('../')
from main import config_load, increment_command_counter
from datetime import datetime, timedelta, timezone
import re
from dateutil.relativedelta import relativedelta
import validators
import utils
import copy
import gspread_asyncio
import gspread
from utils import is_owner, is_admin, portables_leader, portables_admin, is_mod, is_rank, is_helper, portables_only
from utils import cozy_council
import logging

config = config_load()

dxp_active = True
locations = ["LM", "LC", "BA", "SP", "BU", "CW", "PRIF", "MG", "IMP", "GE", "MEI", "ITH", "POF", "BDR", "WG", "BE"]
portables_names = ['Fletcher', 'Crafter', 'Brazier', 'Sawmill', 'Range', 'Well', 'Workbench']
portables_names_upper = ['FLETCHERS', 'CRAFTERS', 'BRAZIERS', 'SAWMILLS', 'RANGES', 'WELLS', 'WORKBENCHES']
busyLocs = [[84, "LM"], [99, "LM"], [100, "SP"]]
forbidden_locs = [[2, "BU"]]
highest_world = 259
forbidden_worlds = [13, 47, 55, 75, 90, 93, 94, 95, 101, 102, 107, 109, 110, 111, 112, 113, 118, 121, 122, 125, 126, 127, 128, 129, 130, 131, 132, 133]
f2p_worlds = [3, 7, 8, 11, 17, 19, 20, 29, 33, 34, 38, 41, 43, 57, 61, 80, 81, 108, 120, 135, 136, 141, 210, 215, 225, 236, 239, 245, 249, 250, 255, 256]
total_worlds = [[86, " (1500+)"], [114, " (1500+)"], [30, " (2000+)"], [48, " (2600+)"], [52, " (VIP)"]]

portable_aliases = [['fletcher', 'fletchers', 'fletch', 'fl', 'f'],
                   ['crafter', 'crafters', 'craft', 'cr', 'c'],
                   ['brazier', 'braziers', 'braz', 'br', 'b'],
                   ['sawmill', 'sawmills', 'saw', 'sa', 's', 'mill', 'mi', 'm'],
                   ['range', 'ranges', 'ra', 'r'],
                   ['well', 'wells', 'we'],
                   ['workbench', 'workbenches', 'benches', 'bench', 'wb', 'wo']]

rank_titles = ['Sergeants', 'Corporals', 'Recruits', 'New']

fletchers_channel_id = config['fletchers_channel_id']
crafters_channel_id = config['crafters_channel_id']
braziers_channel_id = config['braziers_channel_id']
sawmills_channel_id = config['sawmills_channel_id']
ranges_channel_id = config['ranges_channel_id']
wells_channel_id = config['wells_channel_id']
workbenches_channel_id = config['workbenches_channel_id']

portables_channel_ids = [fletchers_channel_id,
                         crafters_channel_id,
                         braziers_channel_id,
                         sawmills_channel_id,
                         ranges_channel_id,
                         wells_channel_id,
                         workbenches_channel_id]

portables_channel_mentions = [f'<#{id}>' for id in portables_channel_ids]
portables_channel_mention_string = ', '.join(portables_channel_mentions[:len(portables_channel_mentions) - 1]) + ', or ' + portables_channel_mentions[len(portables_channel_mentions) - 1]

def get_ports(input):
    '''
    Gets portable locations from a string, and returns them in the following format:
    [[[world1, world2, ...], location1], [[world3, world4, ...], location2], ...]
    '''
    input = input.upper().replace('F2P', '~')
    input = input.replace('~RIF', 'F2PRIF')
    input = input.replace('~OF', 'F2POF')
    input = input.replace('~', '').strip()
    for world in total_worlds:
        total = world[1]
        input = input.replace(total, '')

    # Get indices of all occurrences of locations
    indices = []
    for loc in locations:
        i = [m.start() for m in re.finditer(loc, input)] # https://stackoverflow.com/questions/4664850/find-all-occurrences-of-a-substring-in-python
        if i:
            for index in i:
                indices.append([loc, index])
    indices.sort(key=lambda x: x[1]) # https://stackoverflow.com/questions/17555218/python-how-to-sort-a-list-of-lists-by-the-fourth-element-in-each-list

    # Fill array ports with [worlds, location] for every location
    ports = []
    i = -1
    for index in indices:
        i += 1
        beginIndex = 0
        if i:
            beginIndex = indices[i-1][1]
        endIndex = index[1]
        substring = input[beginIndex:endIndex]
        worlds = [int(s) for s in re.findall(r'\d+', substring)] # https://stackoverflow.com/questions/4289331/python-extract-numbers-from-a-string
        ports.append([worlds, indices[i][0]])

    ports_copy = copy.deepcopy(ports)
    duplicates = []
    # Add worlds from duplicate locations to the first occurrence of the location
    for i, port1 in enumerate(ports_copy):
        loc1 = port1[1]
        for j, port2 in enumerate(ports_copy):
            if j <= i:
                continue
            loc2 = port2[1]
            if loc1 == loc2:
                for world in ports_copy[j][0]:
                    ports_copy[i][0].append(world)
                if not j in duplicates:
                    duplicates.append(j)

    # Delete duplicate locations
    duplicates.sort(reverse=True)
    for i in duplicates:
        del ports_copy[i]

    # Remove duplicates from arrays of worlds and sort worlds
    for i, port in enumerate(ports_copy):
        ports_copy[i][0] = sorted(list(set(port[0])))

    return ports_copy


def only_f2p(ports):
    for item in ports:
        worlds, loc = item[0], item[1]
        for world in worlds:
            if not world in f2p_worlds:
                return False
    return True


def add_port(world, loc, ports):
    '''
    Adds a specific pair (world, location) to a set of portable locations, and returns the result.
    '''
    new_ports = copy.deepcopy(ports)
    for i, port in enumerate(new_ports):
        if port[1] == loc:
            if world in new_ports[i][0]:
                return new_ports
            new_ports[i][0].append(world)
            new_ports[i][0].sort()
            return new_ports
    new_ports.append([[world], loc])
    return new_ports

def add_ports(current, new):
    '''
    Adds a set of new portable locations to a set of current portable locations, and returns the resulting set.
    Uses addPort() for every location.
    '''
    ports = copy.deepcopy(current)
    for port in new:
        loc = port[1]
        for world in port[0]:
            ports = add_port(world, loc, ports)
    return ports

def remove_port(world, loc, ports):
    '''
    Removes a specific pair (world, location) from a set of portable locations, and returns the result.
    Similar to addPort()
    '''
    new_ports = copy.deepcopy(ports)
    for i, port in enumerate(new_ports):
        if port[1] == loc:
            if world in new_ports[i][0]:
                new_ports[i][0].remove(world)
                if not new_ports[i][0]:
                    del new_ports[i]
                return new_ports
    return new_ports

def remove_ports(current, old):
    '''
    Removes a set of new portable locations from a set of current portable locations, and returns the resulting set.
    Uses removePort() for every location.
    Similar to addPorts()
    '''
    ports = copy.deepcopy(current)
    for port in old:
        loc = port[1]
        for world in port[0]:
            ports = remove_port(world, loc, ports)
    return ports

def format(ports):
    '''
    Returns a string that represents a set of portable locations.
    '''
    txt = "" # initialize empty string to be returned
    f2p_ports = [] # initialize empty set for f2p locations, these will be added at the end of the string

    # for every location in the set of portables
    for i, port in enumerate(ports):
        worlds = port[0] # get the set of worlds corresponding to this location
        loc = port[1] # get the location
        count = 0 # initialize count of worlds
        f2p_locs = [] # initialize set of f2p worlds
        # for every world corresponding to the current location
        for w in worlds:
            if w in f2p_worlds: # if this is an f2p world, add it to the set of f2p worlds
                f2p_locs.append(w)
            else: # if it is a members world, increment counter, and generate text for the world
                count += 1
                if count > 1: # for all but the first world, add a comma
                    txt += ', '
                elif txt: # if this is the first world, and there is already text in the string, add a separating character
                    txt += ' | '
                txt += str(w) # add the world number
                # if this (world, location) pair corresponds to a busy location, add a star
                for busyLoc in busyLocs:
                    if w == busyLoc[0] and loc == busyLoc[1]:
                        txt += '*'
                        break
                # if this world is a total level world, add the total level required to join
                if loc != "MG": # total level is irrelevant if location is max guild
                    for totalWorld in total_worlds:
                        if w == totalWorld[0]:
                            txt += totalWorld[1]
                            break
        if count: # if there were worlds for this location, add the location
            txt += ' ' + loc
        if f2p_locs: # if there were f2p worlds for this location, add them to the set of f2p locations
            f2p_ports.append([f2p_locs, loc])

    if f2p_ports: # if there are f2p locations, add them to the string, similar to above
        if txt:
            txt += ' | '
        txt += 'F2P '
        for i, port in enumerate(f2p_ports):
            worlds = port[0]
            loc = port[1]
            count = 0
            for w in worlds:
                count += 1
                if count > 1:
                    txt += ', '
                elif i > 0:
                    txt += ' | '
                txt += str(w)
                for busyLoc in busyLocs:
                    if w == busyLoc[0] and loc == busyLoc[1]:
                        txt += '*'
                        break
                for totalWorld in total_worlds:
                    if w == totalWorld[0]:
                        txt += totalWorld[1]
                        break
            if count:
                txt += ' ' + loc

    if not txt: # if there were no locations at all, return 'N/A'
        return 'N/A'

    # replace some locations for nicer formatting
    txt = txt.replace('PRIF', 'Prif').replace('MEI', 'Meilyr').replace('ITH', 'Ithell')

    return txt # return the final result

async def update_sheet(agcm, col, new_val, timestamp, name, is_rank):
    '''
    Update a given column of the location row (i.e. a cell) on the sheets with:
    new_val, new value for the cell (string)
    timestamp, the time for in the time cell (string)
    name, the name of the editor for in the credit cell (string) (if is_rank)
    is_rank, Boolean value that represents whether the editor is a rank
    '''
    agc = await agcm.authorize()
    ss = await agc.open(config['sheetName'])
    sheet = await ss.worksheet('Home')

    if col and new_val:
        await sheet.update_cell(21, col, new_val, nowait=True) # update location cell
        await sheet.update_cell(31+col, 2, new_val, nowait=True) # update mobile location cell
    await sheet.update_cell(22, 3, timestamp, nowait=True) # update time cell
    if is_rank:
        await sheet.update_cell(22, 5, name, nowait=True) # update editor name
        await sheet.update_cell(39, 2, name, nowait=True) # update mobile editor name

async def update_sheet_row(agcm, ports_row, timestamp, name, is_rank):
    '''
    Update the entire row of locations on the sheets, where:
    ports_row: list of length 6 with strings denoting the value for each cell.
    timestamp: string representing the time for in the time cell.
    name: the name of the editor.
    is_rank: bollean value that denotes whether or not the editor is a rank.
    '''
    agc = await agcm.authorize()
    ss = await agc.open(config['sheetName'])
    sheet = await ss.worksheet('Home')

    cell_list = [gspread.models.Cell(21, i+1, value=val) for i, val in enumerate(ports_row)]
    mobile_cell_list = [gspread.models.Cell(32+i, 2, value=val) for i, val in enumerate(ports_row)]
    await sheet.update_cells(cell_list, nowait=True)
    await sheet.update_cells(mobile_cell_list, nowait=True)
    await sheet.update_cell(22, 3, timestamp, nowait=True) # update time cell
    if is_rank:
        await sheet.update_cell(22, 5, name, nowait=True) # update editor name
        await sheet.update_cell(39, 2, name, nowait=True) # update mobile editor name

async def add_activity(agcm, name, date, sheet_activity=False):
    '''
    Note a player as active for a given date
    '''
    agc = await agcm.authorize()
    ss = await agc.open(config['adminSheetName'])
    sheet = await ss.worksheet('Rank Reports')

    sheet_month_cell = await sheet.cell(3, 1)
    sheet_month = sheet_month_cell.value
    if sheet_month.upper() != date.strftime("%B").upper():
        await write_error(agcm, name, date, f"Could not track {'fc' if not sheet_activity else 'sheet'} activity: month out of sync")
        return
    
    day = str(date.day)
    ranks = await sheet.col_values(1)
    for i, r in enumerate(ranks):
        if r.upper() == name.upper():
            row = i+1
            if not sheet_activity:
                dates = (await sheet.row_values(row) + [""]*100)[3:33]
            else:
                dates = (await sheet.row_values(row) + [""]*100)[34:64]
            if not dates:
                if not sheet_activity:
                    col = 4
                else:
                    col = 35
                await sheet.update_cell(row, col, day, nowait=True)
                return
            else:
                for j, d in enumerate(dates):
                    if not sheet_activity:
                        col = j+1+3
                    else:
                        col = j+1+34
                    if d == day:
                        return
                    elif d == "":
                        await sheet.update_cell(row, col, day, nowait=True)
                        return
        elif i == len(ranks) - 1:
            await write_error(agcm, name, date, f"Could not track {'fc' if not sheet_activity else 'sheet'} activity: name not found")
            return

async def write_error(agcm, name, date, msg):
    '''
    Write an error message to the error tab on the admin sheets.
    '''
    agc = await agcm.authorize()
    ss = await agc.open(config['adminSheetName'])
    sheet = await ss.worksheet('Errors')

    values = [name, str(date), msg]

    errors = await sheet.col_values(1)
    for i, e in enumerate(errors):
        if e == "":
            row = i+1
            cell_list = [gspread.models.Cell(row, col, value=values[col-1]) for col in range(1,4)]
            await sheet.update_cells(cell_list, nowait=True)
            return
        elif i == len(errors)-1:
            await sheet.insert_row(values, i+2)


async def get_port_row(agcm):
    '''
    Returns the current row of portable locations on the sheets.
    '''
    agc = await agcm.authorize()
    ss = await agc.open(config['sheetName'])
    sheet = await ss.worksheet('Home')
    ports = await sheet.row_values(21)
    ports = ports[:7]
    return ports

def check_ports(new_ports, ports):
    '''
    Checks the validity of a given set of new portable locations, given a set of current locations.
    Returns a string with an error message, empty string if no error.
    '''
    for port in new_ports:
        loc = port[1]
        for world in port[0]:
            if world < 1 or world > highest_world:
                return f'Sorry, **{str(world)}** is not a valid world. Please enter a number between 1 and 141.'
            if world in forbidden_worlds:
                return f'Sorry, world **{str(world)}** is not called because it is either a pking world or a bounty hunter world, or it is not on the world list.'
            for forbiddenLoc in forbidden_locs:
                if world == forbiddenLoc[0] and loc == forbiddenLoc[1]:
                    return f'Sorry, **{str(world)} {loc}** is a forbidden location.'
            if loc == 'GE' and world not in f2p_worlds:
                return 'Sorry, we only call the location **GE** in F2P worlds.'
            port_names = []
            count = 0
            i = 0
            for p in ports:
                i += 1
                for entry in p:
                    if loc != entry[1]:
                        continue
                    if world in entry[0]:
                        port_names.append(portables_names[i-1])
                        count += 1
                        break
            '''
            if count >= 3 and not dxp_active:
                msg_ports = ""
                i = 0
                for p in port_names:
                    i += 1
                    msg_ports += '**' + p + '**'
                    if i < len(port_names):
                        msg_ports += ", "
                        if i == len(port_names) - 1:
                            msg_ports += "and "
                return f'Sorry, there cannot be more than 3 portables at the same location.\nThe location **{str(world)} {loc}** already has a {msg_ports}.'
            '''
    return ''

def get_port_type(input, channel=None):
    if 'FL' in input or input.startswith('F'):
        return ['fletcher', 1]
    elif 'CR' in input or (input.startswith('C') and not (input.startswith('CA') or input.startswith('CW'))):
        return ['crafter', 2]
    elif 'BR' in input or (input.startswith('B') and not (input.startswith('BE') or input.startswith('BA') or input.startswith('BU'))):
        return ['brazier', 3]
    elif 'SAW' in input or 'MIL' in input or (input.startswith('M') and not (input.startswith('MG') or input.startswith('MEI'))) or input.startswith('S'):
        return ['sawmill', 4]
    elif 'RAN' in input or input.startswith('R'):
        return ['range', 5]
    elif 'WEL' in input or input.startswith('WE'):
        return ['well', 6]
    elif 'WOR' in input or 'BEN' in input or input.startswith('WO') or input.startswith('WB'):
        return ['workbench', 7]
    else:
        if channel.id in portables_channel_ids:
            return [portables_names[portables_channel_ids.index(channel.id)].lower(), portables_channel_ids.index(channel.id) + 1]
        return ['', -1]
    
last_ports = None

def get_last_ports():
    return last_ports

def set_last_ports(ports):
    global last_ports
    last_ports = ports

def get_editors(credit):
    '''
    Get list of editor names from credit cell string
    '''
    separators = [',', '/', '&', '|', '+', ' - ']
    names = split(credit, separators)
    return names

def split(txt, seps):
    # https://stackoverflow.com/questions/4697006/python-split-string-by-list-of-separators/4697047
    default_sep = seps[0]
    # we skip seps[0] because that's the default seperator
    for sep in seps[1:]:
        txt = txt.replace(sep, default_sep)
    return [i.strip() for i in txt.split(default_sep)]

class Sheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.track_location_updates.start()

    def cog_unload(self):
        self.track_location_updates.cancel()
    
    @tasks.loop(seconds=10)
    async def track_location_updates(self):
        '''
        Loop to track location update activity
        '''
        try:
            agc = await self.bot.agcm.authorize()
            ss = await agc.open(config['sheetName'])
            home = await ss.worksheet('Home')

            last_ports = get_last_ports()
            if last_ports is None:
                last_ports = await home.range('A20:I22')
                set_last_ports(last_ports)
                return

            ports = await home.range('A20:I22')
            
            if not any(ports[i].value != l_p.value for i, l_p in enumerate(last_ports)):
                return
            else:
                set_last_ports(ports)

                top_row_old, mid_row_old, bot_row_old = last_ports[:9], last_ports[9:18], last_ports[18:]
                top_row, mid_row, bot_row = ports[:9], ports[9:18], ports[18:]

                role_ids = [config['fletcher_role'], config['crafter_role'], config['brazier_role'], config['sawmill_role'], config['range_role'], config['well_role'], config['workbench_role']]
                port_server = self.bot.get_guild(config['portablesServer'])
                if port_server:
                    roles = []
                    for role_id in role_ids:
                        role = port_server.get_role(role_id)
                        roles.append(role)

                    for i, cell in enumerate(mid_row[:7]):
                        old_cell = mid_row_old[i]
                        val = cell.value
                        old_val = old_cell.value
                        current_locs = get_ports(val)
                        old_locs = get_ports(old_val)
                        
                        if only_f2p(old_locs):
                            if not only_f2p(current_locs):
                                role = roles[i]
                                if role:
                                    channel_id = portables_channel_ids[i]
                                    loc_channel = port_server.get_channel(channel_id)
                                    if loc_channel:
                                        await loc_channel.send(f'{role.mention} active at **{format(current_locs)}**')
        except Exception as e:
            error = f'Error encountered portable locations tracking: {e}'
            print(error)
            logging.critical(error)

            try:
                channel = self.get_channel(config['testChannel'])
                await channel.send(error)
            except:
                pass

    @commands.command(aliases=['box'])
    async def boxes(self, ctx):
        '''
        Get portable bank deposit box locations.
        Only available during DXP.
        '''
        increment_command_counter()
        if not dxp_active:
            raise commands.CommandError(message='This command is only enabled during DXP.')

        loc_channel = self.bot.get_channel(config['locChannel'])
        admin_commands_channel = self.bot.get_channel(config['adminCommandsChannel'])

        if ctx.guild == self.bot.get_guild(config['portablesServer']):
            if ctx.channel != loc_channel and ctx.channel != admin_commands_channel:
                raise commands.CommandError(message=f'Error: Incorrect channel. Use {loc_channel.mention}.')
        
        last_ports = get_last_ports()
        boxes = last_ports[17].value

        embed = discord.Embed(title='__Deposit boxes__', description=boxes, colour=0xff0000, url=config['publicSheets'], timestamp=datetime.utcnow())
        embed.set_thumbnail(url='https://i.imgur.com/Hccdnts.png')

        await ctx.send(embed=embed)

    @commands.command(aliases=['p', 'portable'] + [item for sublist in portable_aliases for item in sublist])
    async def portables(self, ctx, portable='', *input):
        '''
        Get portable locations.
        '''
        increment_command_counter()

        if ctx.invoked_with in [item for sublist in portable_aliases for item in sublist]:
            input = (portable,) + input
            portable = ctx.invoked_with
        
        if any(thing for thing in input):
            edit_command = commands.Bot.get_command(self.bot, 'edit')
            try:
                for check in edit_command.checks:
                    if not await check(ctx):
                        raise commands.CommandError(message=f'Insufficient permissions: `Portables helper`.')
                await edit_command.callback(self, ctx, portable, *input)
                return
            except commands.CommandError as e:
                raise e

        admin_commands_channel = self.bot.get_channel(config['adminCommandsChannel'])
        if admin_commands_channel:
            if ctx.guild == self.bot.get_guild(config['portablesServer']):
                if ctx.channel != admin_commands_channel and not ctx.channel.id in portables_channel_ids and not ctx.author.id == config['owner']:
                    raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {portables_channel_mention_string}.')

        last_ports = get_last_ports()
        if last_ports is None:
            return
        top_row, mid_row, bot_row = last_ports[:9], last_ports[9:18], last_ports[18:]

        now = datetime.utcnow()
        time_val = str(now.year) + " " + bot_row[2].value + ":" + str(now.second)
        time = datetime.strptime(time_val, '%Y %d %b, %H:%M:%S')

        embed = discord.Embed(title='__Portables FC Locations__', colour=0xff0000, url=config['publicSheets'], timestamp=time)

        if (not portable or not any(portable.upper() in port_name for port_name in portables_names_upper)) and not portable.upper() == 'WB':
            for i in range(len(top_row)-2):
                embed.add_field(name=top_row[i].value, value=mid_row[i].value.replace('*', '\*'), inline=True)

            notes = mid_row[7].value
            embed.add_field(name='Notes', value=notes, inline=False)
        else:
            index = 0
            if portable.upper() == 'WB':
                index = 6
            else:
                for i, port_name in enumerate(portables_names_upper):
                    if port_name.startswith(portable.upper()):
                        index = i
                        break
                if not index:
                    for i, port_name in enumerate(portables_names_upper):
                        if portable.upper() in port_name:
                            index = i
                            break
            # Check for correct portable channel
            if ctx.guild == self.bot.get_guild(config['portablesServer']) and admin_commands_channel:
                if ctx.channel.id in portables_channel_ids:
                    port_channel_index = portables_channel_ids.index(ctx.channel.id)
                    if index != port_channel_index:
                        correct_channel = ctx.guild.get_channel(portables_channel_ids[index])
                        if correct_channel:
                            raise commands.CommandError(message=f'Error: `Incorrect channel for {portables_names_upper[index].lower()}`. Please use {correct_channel.mention}.')
            embed.add_field(name=top_row[index].value, value=mid_row[index].value.replace('*', '\*'))

        embed.set_thumbnail(url='https://i.imgur.com/Hccdnts.png')

        names = bot_row[4].value
        name = names.split(',')[0].split('&')[0].split('/')[0].split('|')[0].strip()
        pattern = re.compile('([^\s\w]|_)+')
        name = pattern.sub('', name).replace(' ', '%20')
        player_image_url = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'
        embed.set_author(name=names, url=config['publicSheets'], icon_url=player_image_url)

        await ctx.send(embed=embed)
    
    @commands.command()
    @is_helper()
    async def update_time(self, ctx):
        '''
        Updates the time on the Portables sheet.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        timestamp = datetime.utcnow().strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        portables = self.bot.get_guild(config['portablesServer'])
        if not portables:
            raise commands.CommandError(message=f'Error: could not find Portables server.')
        member = await portables.fetch_member(ctx.author.id)

        adminCommandsChannel = self.bot.get_channel(config['adminCommandsChannel'])
        if adminCommandsChannel:
            if ctx.guild == self.bot.get_guild(config['portablesServer']):
                if ctx.channel != adminCommandsChannel and not ctx.channel.id in portables_channel_ids:
                    raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {portables_channel_mention_string}.')

        name = '' # initialize empty name of user
        is_rank = False # boolean value representing whether or not the user is a rank
        rank_role = discord.utils.get(portables.roles, id=config['rankRole'])
        if rank_role in member.roles: # if the rank role is in the set of roles corresponding to the user
            is_rank = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        await update_sheet(self.bot.agcm, 0, "", timestamp, name, is_rank) # update the sheet

        await ctx.send(f'The time has been updated to `{timestamp}`.')

    @commands.command(aliases=['banlist'], hidden=True)
    @is_mod()
    async def addban(self, ctx, name="", *reasons):
        '''
        Adds a player to the banlist (Mod+) (Portables only).
        Arguments: name, reason, screenshot (optional).
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        Constraints: name must be a valid RSN.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = re.sub('[^A-z0-9 -]', '', name).replace('`', '').strip()
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if not reasons:
            raise commands.CommandError(message=f'Required argument missing: `reason`.')
        screenshot = ''
        reasons = list(reasons)
        if validators.url(reasons[len(reasons)-1]):
            screenshot = reasons[len(reasons)-1]
            del reasons[len(reasons)-1]
        reason = ""
        for i, r in enumerate(reasons):
            reason += r
            if i < len(reasons) - 1:
                reason += ' '

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Bans')

        header_rows = 5
        banlist = await sheet.col_values(1)
        banlist = banlist[header_rows:]
        durations = await sheet.col_values(2)
        durations = durations[header_rows:]

        perma_ban_index = durations.index('Permanent') + 1
        temp_bans = []
        perma_bans = []
        ex_bans = []
        for i, player in enumerate(banlist):
            if not player:
                temp_bans = banlist[:i]
                break
        for i, player in enumerate(banlist):
            if i < perma_ban_index:
                continue
            if not player:
                perma_bans = banlist[perma_ban_index:i]
                ex_bans = banlist[i+1:]
                break
        for player in temp_bans:
            if name.upper() == player.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the banlist.')
        for player in perma_bans:
            if name.upper() == player.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the banlist.')
        row = header_rows + len(temp_bans) + 1
        count = 1
        for player in ex_bans:
            if name.upper() == player.upper():
                count += 1
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        end_time = (datetime.utcnow() + relativedelta(days=+14)).strftime("%b %#d, %Y")
        username = ctx.author.display_name
        username = re.sub('[^A-z0-9 -]', '', username).replace('`', '').strip()
        values = [name, '2 weeks', timestamp, end_time, reason, username, 'Pending', '', screenshot]

        await sheet.insert_row(values, row)

        await ctx.send(f'**{name}** has been added to the banlist ({str(count)}).')
        admin_channel = self.bot.get_channel(config['adminChannel'])
        await admin_channel.send(f'**{name}** has been added to the banlist with status **Pending**.')

    @commands.command(hidden=True)
    @is_rank()
    async def helper(self, ctx, *name_parts):
        '''
        Adds a helper, or notes activity for an existing helper (Rank+) (Portables only).
        Arguments: name
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Helpers')

        smileys_sheet = await ss.worksheet('Smileys')

        smileys = await smileys_sheet.col_values(1)
        smileys = smileys[4:]
        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                smileys = smileys[:i]
                break
        
        if any(smiley.lower().strip() == name.lower() for smiley in smileys):
            raise commands.CommandError(message=f'Error: `{name}` is on the Smileys list. Please note their activity instead using the `smileyactivity` command.')

        header_rows = 3
        helpers = await sheet.col_values(1)
        helpers = helpers[header_rows:]
        for i, helper in enumerate(helpers):
            if not helper:
                helpers = helpers[:i]
                break

        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        username = ctx.author.display_name
        username = re.sub('[^A-z0-9 -]', '', username).replace('`', '').strip()

        on_list = False
        row = 0
        pattern = re.compile('[\W_]+')
        for i, helper in enumerate(helpers):
            if pattern.sub('', name.upper()) == pattern.sub('', helper.upper()):
                name = helper
                row = i + header_rows + 1
                on_list = True
                break
        if not on_list:
            row = header_rows + len(helpers) + 1
            values = [name, 'Helper', timestamp, username]
            await sheet.insert_row(values, row)
            await ctx.send(f'**{name}** has been added to the helper sheet.')
            return
        else:
            activity = await sheet.row_values(row)
            activity = activity[2:8]
            for i in [5, 3, 1]:
                if len(activity) - 1 >= i:
                    del activity[i]
            for i in [2,1,0]:
                if len(activity) - 1 >= i:
                    if not activity[i]:
                        del activity[i]
            if timestamp in activity:
                raise commands.CommandError(message=f'`{name}` has already been noted as active for today.')
            if len(activity) >= 3:
                raise commands.CommandError(message=f'Error: `{name}` already has a full activity row.')
            time_col = 3 + len(activity) * 2
            credit_col = time_col + 1
            await sheet.update_cell(row, time_col, timestamp)
            await sheet.update_cell(row, credit_col, username)
            await ctx.send(f'**{name}** has been noted as active for **{timestamp}**.')

    @commands.command(hidden=True)
    @is_rank()
    async def smileyactivity(self, ctx, *name_parts):
        '''
        Notes activity for a smiley on sheets (Rank+) (Portables only).
        Arguments: name
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Smileys')

        header_rows = 4
        smileys = await sheet.col_values(1)
        smileys = smileys[header_rows:]
        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                smileys = smileys[:i]
                break
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        username = ctx.author.display_name
        username = re.sub('[^A-z0-9 -]', '', username).replace('`', '').strip()

        row = 0
        for i, smiley in enumerate(smileys):
            if name.upper() == smiley.upper():
                row = i + header_rows + 1
                name = smiley
                break
        if not row:
            for i, smiley in enumerate(smileys):
                if name.upper() in smiley.upper():
                    row = i + header_rows + 1
                    name = smiley
                    break
        if not row:
            raise commands.CommandError(message=f'Could not find smiley: `{name}`.')

        activity = await sheet.row_values(row)
        status = activity[1]
        activity = activity[4:12]
        if 'alt' in status:
            raise commands.CommandError(message=f'`{name}` is an alt account, you do not need to track its activity.')
        for i in [7, 5, 3, 1]:
            if len(activity) - 1 >= i:
                del activity[i]
        for i in [3,2,1,0]:
            if len(activity) - 1 >= i:
                if activity[i] is None or not activity[i]:
                    del activity[i]
        if timestamp in activity:
            raise commands.CommandError(message=f'`{name}` has already been noted as active for today.')
        if len(activity) >= 4:
            raise commands.CommandError(message=f'Error: `{name}` already has a full activity row.')
        time_col = 5 + len(activity) * 2
        credit_col = time_col + 1
        await sheet.update_cell(row, time_col, timestamp)
        await sheet.update_cell(row, credit_col, username)
        await ctx.send(f'**{name}** has been noted as active for **{timestamp}**.')

    @commands.command(pass_context=True, hidden=True)
    @portables_admin()
    async def addsmiley(self, ctx, *name_parts):
        '''
        Adds a smiley to the sheets (Admin+) (Portables only).
        Arguments: name.
        Constraints: name must be a valid RSN.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        leader_role = discord.utils.get(ctx.guild.roles, id=config['leaderRole'])

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Smileys')

        header_rows = 4
        smileys = await sheet.col_values(1)
        smileys = smileys[header_rows:]

        current_smileys = []
        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                current_smileys = smileys[:i]
                break
        for smiley in current_smileys:
            if name.upper() == smiley.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the smiley list.')
        row = 0
        for i, smiley in enumerate(smileys):
            if name.upper() == smiley.upper():
                row = i + header_rows + 1
                break
        if row:
            await sheet.delete_row(row)
        row = header_rows + len(current_smileys) + 1
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        end_time = (datetime.utcnow() + relativedelta(months=+1)).strftime("%b %#d, %Y")
        values = [name, 'No', 'Applied', '', '', '', '', '', '', '', '', '', '', 'Pending', timestamp, end_time]
        await sheet.insert_row(values, row)
        await ctx.send(f'**{name}** has been added to the smileys sheet.')
        if ctx.author.top_role <= leader_role:
            admin_channel = self.bot.get_channel(config['adminChannel'])
            await admin_channel.send(f'**{name}** has been added to the smileys sheet with status **Pending**.')

    @commands.command(pass_context=True, hidden=True)
    @portables_leader()
    async def activatesmiley(self, ctx, *name_parts):
        '''
        Sets smiley status to active (Leader+) (Portables only).
        Arguments: name.
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Smileys')

        header_rows = 4
        smileys = await sheet.col_values(1)
        smileys = smileys[header_rows:]

        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                smileys = smileys[:i]
                break
        row = 0
        for i, smiley in enumerate(smileys):
            if name.upper() == smiley.upper():
                row = i + header_rows + 1
                name = smiley
                break
        if not row:
            for i, smiley in enumerate(smileys):
                if name.upper() in smiley.upper():
                    row = i + header_rows + 1
                    name = smiley
                    break
        if not row:
            raise commands.CommandError(message=f'Could not find smiley: `{name}`.')
        col = 14
        status = await sheet.cell(row, col)
        status = status.value
        if status == 'Active':
            raise commands.CommandError(message=f'Error: `{name}`\'s status was already set to active.')
        await sheet.update_cell(row, col, 'Active')

        await ctx.send(f'**{name}**\'s status has been set to active.')

    @commands.command(pass_context=True, hidden=True)
    @portables_admin()
    async def addalt(self, ctx, name="", member=""):
        '''
        Adds a rank alt to the sheets (Admin+) (Portables only).
        Arguments: name, member.
        Member can be either a name or a mention.
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        Constraints: name must be a valid RSN, member must be a rank.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if not member:
            raise commands.CommandError(message=f'Required argument missing: `member`.')
        rank_role = discord.utils.get(ctx.guild.roles, id=config['rankRole'])
        if ctx.message.mentions:
            member = ctx.message.mentions[0]
        else:
            pattern = re.compile('[\W_]+')
            member_name = pattern.sub('', member).upper()
            member = discord.utils.find(lambda m: utils.is_name(member_name, m) and m.top_role >= rank_role, ctx.guild.members)
            if not member:
                raise commands.CommandError(message=f'Could not find rank: `{member_name}`.')
        member_name = member.display_name
        member_name = re.sub('[^A-z0-9 -]', '', member_name).replace('`', '').strip()
        type = ''
        mod_role = discord.utils.get(ctx.guild.roles, id=config['modRole'])
        admin_role = discord.utils.get(ctx.guild.roles, id=config['adminRole'])
        leader_role = discord.utils.get(ctx.guild.roles, id=config['leaderRole'])
        if member.top_role >= admin_role:
            type = 'Admin+ alt'
        elif member.top_role >= mod_role:
            type = 'Moderator alt'
        else:
            type = 'Rank alt'
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Smileys')

        header_rows = 4
        smileys = await sheet.col_values(1)
        smileys = smileys[header_rows:]
        types = await sheet.col_values(2)
        types = types[header_rows:]

        current_smileys = []
        for i, smiley in enumerate(smileys):
            if not smiley:
                current_smileys = smileys[:i]
                types = types[:i]
                break
        for smiley in current_smileys:
            if name.upper() == smiley.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the smiley list.')
        row = 0
        if 'Rank' in type:
            for i, t in enumerate(types):
                if not 'ALT' in t.upper():
                    row = i + header_rows + 1
                    break
        elif 'Mod' in type:
            for i, t in enumerate(types):
                if not 'ADMIN' in t.upper() and not 'MODERATOR' in t.upper():
                    row = i + header_rows + 1
                    break
        elif 'Admin' in type:
            for i, t in enumerate(types):
                if not 'ADMIN' in t.upper():
                    row = i + header_rows + 1
                    break
        if not row:
            raise commands.CommandError(message=f'Unexpected error: Could not find row in spreadsheet.')
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        end_time = ''
        values = [name, type, f'{member_name} alt', '', '', '', '', '', '', '', '', '', '', 'Pending', timestamp, end_time]

        await sheet.insert_row(values, row)

        await ctx.send(f'**{member_name}**\'s alt, **{name}**, has been added to the smileys sheet.')
        if ctx.author.top_role < leader_role:
            admin_channel = self.bot.get_channel(config['adminChannel'])
            await admin_channel.send(f'**{member_name}**\'s alt, **{name}**, has been added to the smileys sheet with status **Pending**.')

    @commands.command(pass_context=True, aliases=['a'], ignore_extra=True)
    @portables_only()
    async def add(self, ctx):
        """
        Add portable locations (Portables only).
        Arguments: portable, worlds, location, worlds, location, etc...
        Constraints: This command can only be used in the locations channel. Only approved locations, and worlds are allowed. Additionally, worlds must be a valid world. No more than 3 portables per location.
        """
        increment_command_counter()
        await ctx.channel.trigger_typing() # send 'typing...' status

        portables = self.bot.get_guild(config['portablesServer'])
        if not portables:
            raise commands.CommandError(message=f'Error: could not find Portables server.')
        member = await portables.fetch_member(ctx.author.id)

        adminCommandsChannel = self.bot.get_channel(config['adminCommandsChannel'])
        if adminCommandsChannel:
            if ctx.guild == self.bot.get_guild(config['portablesServer']):
                if ctx.channel != adminCommandsChannel and not ctx.channel.id in portables_channel_ids:
                    raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {portables_channel_mention_string}.')

        input = ctx.message.content.upper().replace(ctx.prefix.upper(), '', 1).replace(ctx.invoked_with.upper(), '', 1).strip() # get the input corresponding to this message
        if not input: # if there was no input, return
            raise commands.CommandError(message=f'Required argument missing: `location`.')

        # get the portable type corresponding to the input
        portable, col = get_port_type(input, ctx.channel)
        if col == -1: # if no portable type was given, return
            raise commands.CommandError(message=f'Required argument missing: `portable`.')

        # replace some portable types due to incompatibilities with location abbreviations
        input = input.replace('RANGE', '')
        input = input.replace('WORKBENCH', '')
        new_ports = get_ports(input) # get the set of portable locations corresponding to the input

        if not new_ports: # if there were no locations, return
            raise commands.CommandError(message=f'Invalid argument: `location`.')

        ports = await get_port_row(self.bot.agcm) # get the current portable locations from the sheet

        val = ports[col-1] # get the string corresponding to our portable type
        ports[col-1] = "" # set value for our portable type to empty
        for i, p in enumerate(ports): # for each portable, get the set of portable locations
            ports[i] = get_ports(p)

        error = check_ports(new_ports, ports) # check for errors in the set of portables
        if error: # if there was an error, send the error message and return
            raise commands.CommandError(message=error)

        new_ports_text = format(new_ports).replace('*', '\*') # string representing portables to be added
        current_ports = get_ports(val) # current portables on sheets
        sum_ports = add_ports(current_ports, new_ports) # set of portables after adding given portables
        new_val = format(sum_ports) # string representing the new set of portable locations

        # check whether multiple portables were added
        multiple = False
        if len(new_ports) > 1:
            multiple = True
        elif len(new_ports[0][0]) > 1:
            multiple = True

        # if no change, raise an error
        if new_val == val:
            if multiple:
                raise commands.CommandError(message=f'The `{portable}` locations `{format(new_ports)}` were already on the sheet.')
            else:
                raise commands.CommandError(message=f'The `{portable}` location `{format(new_ports)}` was already on the sheet.')

        timestamp = datetime.utcnow().strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        name = '' # initialize empty name of user
        is_helper = False # boolean value representing whether or not the user is a rank
        helper_role = discord.utils.get(portables.roles, id=config['helperRole'])
        if helper_role in member.roles: # if the rank role is in the set of roles corresponding to the user
            is_helper = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        await update_sheet(self.bot.agcm, col, new_val, timestamp, name, is_helper) # update the sheet

        # send confirmation message
        if multiple:
            await ctx.send(f'The **{portable}** locations **{new_ports_text}** have been added.')
        else:
            await ctx.send(f'The **{portable}** location **{new_ports_text}** has been added.')

    @commands.command(pass_context=True, aliases=['rem'], ignore_extra=True)
    @portables_only()
    async def remove(self, ctx):
        """
        Remove portable locations (Portables only).
        Arguments: portable, worlds, location, worlds, location, etc...
        Constraints: This command can only be used in the locations channel. Only approved locations, and worlds are allowed. Additionally, worlds must be a valid world. No more than 3 portables per location.
        """
        increment_command_counter() # increment global commands counter
        await ctx.channel.trigger_typing() # send 'typing...' status

        portables = self.bot.get_guild(config['portablesServer'])
        if not portables:
            raise commands.CommandError(message=f'Error: could not find Portables server.')
        member = await portables.fetch_member(ctx.author.id)

        admin_commands_channel = self.bot.get_channel(config['adminCommandsChannel'])
        if admin_commands_channel:
            if ctx.guild == self.bot.get_guild(config['portablesServer']):
                if ctx.channel != admin_commands_channel and not ctx.channel.id in portables_channel_ids:
                    raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {portables_channel_mention_string}.')

        # get the input corresponding to this message
        input = ctx.message.content.upper().replace(ctx.prefix.upper(), '', 1).replace(ctx.invoked_with.upper(), '', 1).strip() # get the input corresponding to this message

        if not input: # if there was no input, return
            raise commands.CommandError(message=f'Required argument missing: `location`.')

        # get the portable type corresponding to the input
        portable, col = get_port_type(input, ctx.channel)
        if col == -1: # if no portable type was given, return
            raise commands.CommandError(message=f'Required argument missing: `portable`.')

        # replace some portable types due to incompatibilities with location abbreviations
        input = input.replace('RANGE', '')
        input = input.replace('WORKBENCH', '')
        old_ports = get_ports(input) # get the set of portable locations corresponding to the input

        if not old_ports: # if there were no locations, return=
            raise commands.CommandError(message=f'Invalid argument: `location`.')

        for port in old_ports: # if the input contains an invalid world, return
            for world in port[0]:
                if world < 1:
                    raise commands.CommandError(message=f'Invalid argument: world `{str(world)}`.')

        # get the current locations for this portable from the sheet
        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Home')
        val = await sheet.cell(21, col)
        val = val.value

        old_ports_text = format(old_ports).replace('*', '\*') # string representing portables to be removed
        current_ports = get_ports(val) # current portables on sheets
        dif_ports = remove_ports(current_ports, old_ports) # set of portables after removing given portables
        new_val = format(dif_ports) # string representing the new set of portable locations

        # check whether multiple portables were removed
        multiple = False
        if len(old_ports) > 1:
            multiple = True
        elif len(old_ports[0][0]) > 1:
            multiple = True
        
        # if no change, raise an error
        if new_val == val:
            if multiple:
                raise commands.CommandError(message=f'The `{portable}` locations `{format(old_ports)}` weren\'t found.')
            else:
                raise commands.CommandError(message=f'The `{portable}` location `{format(old_ports)}` was not found.')

        timestamp = datetime.utcnow().strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        name = '' # initialize empty name of user
        is_helper = False # boolean value representing whether or not the user is a rank
        helper_role = discord.utils.get(portables.roles, id=config['helperRole'])
        if helper_role in member.roles: # if the rank role is in the set of roles corresponding to the user
            is_helper = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        await update_sheet(self.bot.agcm, col, new_val, timestamp, name, is_helper) # update the sheet

        # send confirmation message
        if multiple:
            await ctx.send(f'The **{portable}** locations **{old_ports_text}** have been removed.')
        else:
            await ctx.send(f'The **{portable}** location **{old_ports_text}** has been removed.')

    @commands.command(aliases=['rall'], ignore_extra=True)
    @is_helper()
    async def removeall(self, ctx, *input):
        '''
        Removes all instances of a given location, or all locations of a given portable. (Helper+) (Portables only)
        Arguments: [portable] / [worlds][locations]
        Constraints: If calling the command with a portable, you can only do one portable at a time.
        Example: `-removeall range` / `-removeall 84 ca`
        '''
        increment_command_counter() # increment global commands counter
        await ctx.channel.trigger_typing() # send 'typing...' status

        portables = self.bot.get_guild(config['portablesServer'])
        member = await portables.fetch_member(ctx.author.id)

        admin_commands_channel = self.bot.get_channel(config['adminCommandsChannel'])
        if admin_commands_channel:
            if ctx.guild == self.bot.get_guild(config['portablesServer']):
                if ctx.channel != admin_commands_channel and not ctx.channel.id in portables_channel_ids:
                    raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {portables_channel_mention_string}.')

        if input:
            input = ' '.join(input).upper().strip()
        if not input:
            raise commands.CommandError(message=f'Required argument missing: `portable/location`.')

        to_remove = get_ports(input)
        if format(to_remove) == 'N/A':
            to_remove = []
        if not to_remove:
            port = ''
            index = 0
            for i, aliases in enumerate(portable_aliases):
                if input.lower() in aliases:
                    port = aliases[0]
                    index = i
                    break
            if not port:
                if ctx.channel.id in portables_channel_ids:
                    port = portables_names[portables_channel_ids.index(ctx.channel.id)].lower()
            if not port:
                raise commands.CommandError(message=f'Invalid argument: `{input}`.')


        current_values = await get_port_row(self.bot.agcm)
        current = [get_ports(i) for i in current_values]

        if to_remove:
            new_values = [format(remove_ports(cur, to_remove)) for cur in current]
        else:
            new_values = [format(cur) for cur in current]
            new_values[index] = 'N/A'

        # if no change, raise an error
        if new_values == current_values:
            if to_remove:
                raise commands.CommandError(message=f'Location(s) `{format(to_remove)}` were not found on the sheet.')
            else:
                raise commands.CommandError(message=f'Portable `{port}` had no locations listed.')

        timestamp = datetime.utcnow().strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        name = '' # initialize empty name of user
        is_rank = False # boolean value representing whether or not the user is a rank
        rank_role = discord.utils.get(portables.roles, id=config['rankRole'])
        if rank_role in member.roles: # if the rank role is in the set of roles corresponding to the user
            is_rank = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        await update_sheet_row(self.bot.agcm, new_values, timestamp, name, is_rank)

        if to_remove:
            await ctx.send(f'All instances of the location(s) `{format(to_remove)}` have been removed.')
        else:
            await ctx.send(f'All locations for the portable `{port}` have been removed.')



    @commands.command(pass_context=True, ignore_extra=True)
    @is_helper()
    async def edit(self, ctx, portable='', *input_locs):
        '''
        Edit portable locations (Helper+) (Portables only).
        Arguments: portable, worlds, location, worlds, location, etc...
        Alternatively, you can directly use -portable [arguments], e.g.: -fletch 100 ca
        Constraints: This command can only be used in the locations channel. Only approved locations and worlds are allowed. Additionally, worlds must be a valid world. No more than 3 portables per location.
        '''
        increment_command_counter() # increment global commands counter
        await ctx.channel.trigger_typing() # send 'typing...' status

        portables = self.bot.get_guild(config['portablesServer'])
        member = await portables.fetch_member(ctx.author.id)

        admin_commands_channel = self.bot.get_channel(config['adminCommandsChannel'])
        if admin_commands_channel:
            if ctx.guild == self.bot.get_guild(config['portablesServer']):
                if ctx.channel != admin_commands_channel and not ctx.channel.id in portables_channel_ids:
                    raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {portables_channel_mention_string}.')

        if not portable: # if there was no portable type in the input, return
            raise commands.CommandError(message=f'Required argument missing: `portable`.')

        for i, ports in enumerate(portable_aliases):
            if portable in ports:
                portable = ports[0]
                col = i + 1
                break

        input = ''
        for loc in input_locs:
            input += loc + ' '
        input = input.upper().strip()

        name = '' # initialize empty name of user
        is_rank = False # boolean value representing whether or not the user is a rank
        rank_role = discord.utils.get(portables.roles, id=config['rankRole'])
        if rank_role in member.roles: # if the rank role is in the set of roles corresponding to the user
            is_rank = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        timestamp = datetime.utcnow().strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        if input.replace('/', '').replace(' ', '') in ['NA', 'NO', 'NONE', '0', 'ZERO']: # if input was 'N/A' or a variation, remove all locations and return
            await update_sheet(self.bot.agcm, col, 'N/A', timestamp, name, is_rank)
            await ctx.send(f'The **{portable}** locations have been edited to: **N/A**.')
            return

        new_ports = get_ports(input) # calculate new set of portables from the input string
        if not new_ports: # if there were no portables, return
            raise commands.CommandError(message=f'Invalid argument: `location`.')

        ports = await get_port_row(self.bot.agcm) # get the row of portable locations from sheets
        old_val = ports[col-1]
        ports[col-1] = "" # set value for our portable type to empty
        for i, p in enumerate(ports): # for each portable, get the set of portable locations
            ports[i] = get_ports(p)

        error = check_ports(new_ports, ports) # check for errors in the set of portables
        if error: # if there was an error, send the error message and return
            raise commands.CommandError(message=error)

        new_val = format(new_ports) # create a string corresponding
        new_ports_text = new_val.replace('*', '\*') # in the text for the discord message, escape the stars for formatting issues

        # if no change, raise an error
        if new_val == old_val:
            raise commands.CommandError(message=f'The `{portable}` locations were already set to `{new_val}`.')

        await update_sheet(self.bot.agcm, col, new_val, timestamp, name, is_rank) # update the sheet

        await ctx.send(f'The **{portable}** locations have been edited to: **{new_ports_text}**.') # send confirmation message

    @commands.command(pass_context=True, aliases=['watch'], hidden=True)
    @is_rank()
    async def watchlist(self, ctx, name="", *reasons):
        '''
        Adds a player to the watchlist (Rank+) (Portables only).
        Arguments: name, reason, screenshot (optional).
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        Constraints: name must be a valid RSN.
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = re.sub('[^A-z0-9 -]', '', name).replace('`', '').strip()
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match('^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if not reasons:
            raise commands.CommandError(message=f'Required argument missing: `reason`.')
        screenshot = ''
        reasons = list(reasons)
        if validators.url(reasons[len(reasons)-1]):
            screenshot = reasons[len(reasons)-1]
            del reasons[len(reasons)-1]
        reason = " ".join(reasons)

        if not screenshot:
            if ctx.message.attachments:
                screenshot = ctx.message.attachments[0].url

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Watchlist')
        header_rows = 5

        watchlist = await sheet.col_values(1)
        watchlist = watchlist[header_rows:]

        for i, player in enumerate(watchlist):
            if not player:
                watchlist = watchlist[:i]
                break
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        username = ctx.author.display_name
        username = re.sub('[^A-z0-9 -]', '', username).replace('`', '').strip()
        count = 1
        for player in watchlist:
            if name.upper() == player.upper():
                count += 1
        row = header_rows + len(watchlist) + 1
        values = [name, timestamp, reason, username, screenshot]

        await sheet.insert_row(values, row)

        await ctx.send(f'**{name}** has been added to the watchlist ({str(count)}).')

    @commands.command(pass_context=True, aliases=['act', 'active'], hidden=True)
    @portables_admin()
    async def activity(self, ctx, *name_parts):
        '''
        Notes rank activity on admin sheets (Admin+) (Portables only).
        Arguments: name
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        user = ctx.author
        username = user.display_name

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if name.upper() in username.upper():
            raise commands.CommandError(message=f'Invalid argument: `{name}`. You cannot track your own activity.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['adminSheetName'])
        sheet = await ss.worksheet('Rank Reports')
        header_rows = 4

        month = datetime.utcnow().strftime("%B")
        sheet_month_cell = await sheet.cell(3, 1)
        sheet_month = sheet_month_cell.value
        if month.upper().strip() != sheet_month.upper().strip():
            raise commands.CommandError(message=f'Error: `admin_sheet_month`. Please wait for a Leader to perform this month\'s rank changes.')
        ranks = await sheet.col_values(1)
        ranks = ranks[header_rows:]
        for i, rank in enumerate(ranks):
            if rank is None or not rank:
                ranks = ranks[:i]
                break
        timestamp = datetime.utcnow().strftime("%#d")
        row = 0
        for i, rank in enumerate(ranks):
            if rank in rank_titles:
                continue
            if name.upper() == rank.upper():
                row = i + header_rows + 1
                name = rank
                break
        if not row:
            for i, rank in enumerate(ranks):
                if rank in rank_titles:
                    continue
                if name.upper() in rank.upper():
                    row = i + header_rows + 1
                    name = rank
                    break
        if not row:
            raise commands.CommandError(message=f'Could not find rank: `{name}`.')
        activity = await sheet.row_values(row)
        activity = activity[3:34]
        activity = list(filter(bool, activity))
        if timestamp in activity:
            raise commands.CommandError(message=f'`{name}` has already been noted active for today.')
        col = 4 + len(activity)
        await sheet.update_cell(row, col, timestamp)
        await ctx.send(f'**{name}** has been noted as active for **{timestamp}** **{datetime.utcnow().strftime("%b")}**.')

    @commands.command(pass_context=True, hidden=True)
    @portables_admin()
    async def sheetactivity(self, ctx, *name_parts):
        '''
        Notes rank sheet activity on admin sheets (Admin+) (Portables only).
        Arguments: name
        '''
        increment_command_counter()
        await ctx.channel.trigger_typing()

        user = ctx.author
        username = user.display_name

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if name.upper() in username.upper():
            raise commands.CommandError(message=f'Invalid argument: `{name}`. You cannot track your own activity.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['adminSheetName'])
        sheet = await ss.worksheet('Rank Reports')
        header_rows = 4

        month = datetime.utcnow().strftime("%B")
        sheet_month_cell = await sheet.cell(3, 1)
        sheet_month = sheet_month_cell.value
        if month != sheet_month:
            raise commands.CommandError(message=f'Error: `admin_sheet_month`. Please wait for a Leader to perform this month\'s rank changes.')
        ranks = await sheet.col_values(1)
        ranks = ranks[header_rows:]
        for i, rank in enumerate(ranks):
            if rank is None or not rank:
                ranks = ranks[:i]
                break
        timestamp = datetime.utcnow().strftime("%#d")
        row = 0
        for i, rank in enumerate(ranks):
            if rank in rank_titles:
                continue
            if name.upper() == rank.upper():
                row = i + header_rows + 1
                name = rank
                break
        if not row:
            for i, rank in enumerate(ranks):
                if rank in rank_titles:
                    continue
                if name.upper() in rank.upper():
                    row = i + header_rows + 1
                    name = rank
                    break
        if not row:
            raise commands.CommandError(message=f'Could not find rank: `{name}`.')

        activity = await sheet.row_values(row)
        sheet_activity = activity[34:65]
        activity = activity[3:34]

        sheet_activity = list(filter(bool, sheet_activity))
        activity = list(filter(bool, activity))
        if timestamp in sheet_activity:
            raise commands.CommandError(message=f'`{name}` has already been noted active for today.')
        sheet_col = 35 + len(sheet_activity)
        await sheet.update_cell(row, sheet_col, timestamp)
        await ctx.send(f'**{name}** has been noted as active on sheets for **{timestamp}** **{datetime.utcnow().strftime("%b")}**.')


def setup(bot):
    bot.add_cog(Sheets(bot))
