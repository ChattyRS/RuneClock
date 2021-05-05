import discord
import asyncio
from discord.ext import commands, tasks
import sys
sys.path.append('../')
from main import config_load, addCommand
from datetime import datetime, timedelta, timezone
import re
from dateutil.relativedelta import relativedelta
import validators
import utils
import copy
import gspread_asyncio
import gspread
from utils import is_owner, is_admin, portables_leader, portables_admin, is_mod, is_rank, is_smiley, portables_only
from utils import cozy_council

config = config_load()

dxp_active = True
locations = ["LM", "LC", "BA", "SP", "BU", "CW", "PRIF", "MG", "IMP", "GE", "MEI", "ITH", "POF", "BDR", "WG", "BE"]
portablesNames = ['Fletcher', 'Crafter', 'Brazier', 'Sawmill', 'Range', 'Well', 'Workbench']
portablesNamesUpper = ['FLETCHERS', 'CRAFTERS', 'BRAZIERS', 'SAWMILLS', 'RANGES', 'WELLS', 'WORKBENCHES']
busyLocs = [[84, "LM"], [99, "LM"], [100, "SP"]]
forbiddenLocs = [[2, "BU"]]
highestWorld = 245
forbiddenWorlds = [13, 47, 55, 75, 90, 93, 94, 95, 101, 102, 107, 109, 110, 111, 112, 113, 118, 121, 122, 125, 126, 127, 128, 129, 130, 131, 132, 133]
f2pWorlds = [3, 7, 8, 11, 17, 19, 20, 29, 33, 34, 38, 41, 43, 57, 61, 80, 81, 108, 120, 135, 136, 141, 210, 215, 225, 236, 245]
totalWorlds = [[86, " (1500+)"], [114, " (1500+)"], [30, " (2000+)"], [48, " (2600+)"], [52, " (VIP)"]]

portableAliases = [['fletcher', 'fletchers', 'fletch', 'fl', 'f'],
                   ['crafter', 'crafters', 'craft', 'cr', 'c'],
                   ['brazier', 'braziers', 'braz', 'br', 'b'],
                   ['sawmill', 'sawmills', 'saw', 'sa', 's', 'mill', 'mi', 'm'],
                   ['range', 'ranges', 'ra', 'r'],
                   ['well', 'wells', 'we'],
                   ['workbench', 'workbenches', 'benches', 'bench', 'wb', 'wo']]

rankTitles = ['Sergeants', 'Corporals', 'Recruits', 'New']

def getPorts(input):
    '''
    Gets portable locations from a string, and returns them in the following format:
    [[[world1, world2, ...], location1], [[world3, world4, ...], location2], ...]
    '''
    input = input.upper().replace('F2P', '~')
    input = input.replace('~RIF', 'F2PRIF')
    input = input.replace('~OF', 'F2POF')
    input = input.replace('~', '').strip()
    for world in totalWorlds:
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

    portsCopy = copy.deepcopy(ports)
    duplicates = []
    # Add worlds from duplicate locations to the first occurrence of the location
    for i, port1 in enumerate(portsCopy):
        loc1 = port1[1]
        for j, port2 in enumerate(portsCopy):
            if j <= i:
                continue
            loc2 = port2[1]
            if loc1 == loc2:
                for world in portsCopy[j][0]:
                    portsCopy[i][0].append(world)
                if not j in duplicates:
                    duplicates.append(j)

    # Delete duplicate locations
    duplicates.sort(reverse=True)
    for i in duplicates:
        del portsCopy[i]

    # Remove duplicates from arrays of worlds and sort worlds
    for i, port in enumerate(portsCopy):
        portsCopy[i][0] = sorted(list(set(port[0])))

    return portsCopy


def only_f2p(ports):
    for item in ports:
        worlds, loc = item[0], item[1]
        for world in worlds:
            if not world in f2pWorlds:
                return False
    return True


def addPort(world, loc, ports):
    '''
    Adds a specific pair (world, location) to a set of portable locations, and returns the result.
    '''
    newPorts = copy.deepcopy(ports)
    for i, port in enumerate(newPorts):
        if port[1] == loc:
            if world in newPorts[i][0]:
                return newPorts
            newPorts[i][0].append(world)
            newPorts[i][0].sort()
            return newPorts
    newPorts.append([[world], loc])
    return newPorts

def addPorts(current, new):
    '''
    Adds a set of new portable locations to a set of current portable locations, and returns the resulting set.
    Uses addPort() for every location.
    '''
    ports = copy.deepcopy(current)
    for port in new:
        loc = port[1]
        for world in port[0]:
            ports = addPort(world, loc, ports)
    return ports

def removePort(world, loc, ports):
    '''
    Removes a specific pair (world, location) from a set of portable locations, and returns the result.
    Similar to addPort()
    '''
    newPorts = copy.deepcopy(ports)
    for i, port in enumerate(newPorts):
        if port[1] == loc:
            if world in newPorts[i][0]:
                newPorts[i][0].remove(world)
                if not newPorts[i][0]:
                    del newPorts[i]
                return newPorts
    return newPorts

def removePorts(current, old):
    '''
    Removes a set of new portable locations from a set of current portable locations, and returns the resulting set.
    Uses removePort() for every location.
    Similar to addPorts()
    '''
    ports = copy.deepcopy(current)
    for port in old:
        loc = port[1]
        for world in port[0]:
            ports = removePort(world, loc, ports)
    return ports

def format(ports):
    '''
    Returns a string that represents a set of portable locations.
    '''
    txt = "" # initialize empty string to be returned
    f2pPorts = [] # initialize empty set for f2p locations, these will be added at the end of the string

    # for every location in the set of portables
    for i, port in enumerate(ports):
        worlds = port[0] # get the set of worlds corresponding to this location
        loc = port[1] # get the location
        count = 0 # initialize count of worlds
        f2pLocs = [] # initialize set of f2p worlds
        # for every world corresponding to the current location
        for w in worlds:
            if w in f2pWorlds: # if this is an f2p world, add it to the set of f2p worlds
                f2pLocs.append(w)
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
                    for totalWorld in totalWorlds:
                        if w == totalWorld[0]:
                            txt += totalWorld[1]
                            break
        if count: # if there were worlds for this location, add the location
            txt += ' ' + loc
        if f2pLocs: # if there were f2p worlds for this location, add them to the set of f2p locations
            f2pPorts.append([f2pLocs, loc])

    if f2pPorts: # if there are f2p locations, add them to the string, similar to above
        if txt:
            txt += ' | '
        txt += 'F2P '
        for i, port in enumerate(f2pPorts):
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
                for totalWorld in totalWorlds:
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

async def updateSheet(agcm, col, newVal, timestamp, name, isRank):
    '''
    Update a given column of the location row (i.e. a cell) on the sheets with:
    newVal, new value for the cell (string)
    timestamp, the time for in the time cell (string)
    name, the name of the editor for in the credit cell (string) (if isRank)
    isRank, Boolean value that represents whether the editor is a rank
    '''
    agc = await agcm.authorize()
    ss = await agc.open(config['sheetName'])
    sheet = await ss.worksheet('Home')

    if col and newVal:
        await sheet.update_cell(21, col, newVal, nowait=True) # update location cell
        await sheet.update_cell(31+col, 2, newVal, nowait=True) # update mobile location cell
    await sheet.update_cell(22, 3, timestamp, nowait=True) # update time cell
    if isRank:
        await sheet.update_cell(22, 5, name, nowait=True) # update editor name
        await sheet.update_cell(39, 2, name, nowait=True) # update mobile editor name

async def update_sheet_row(agcm, ports_row, timestamp, name, isRank):
    '''
    Update the entire row of locations on the sheets, where:
    ports_row: list of length 6 with strings denoting the value for each cell.
    timestamp: string representing the time for in the time cell.
    name: the name of the editor.
    isRank: bollean value that denotes whether or not the editor is a rank.
    '''
    agc = await agcm.authorize()
    ss = await agc.open(config['sheetName'])
    sheet = await ss.worksheet('Home')

    cell_list = [gspread.models.Cell(21, i+1, value=val) for i, val in enumerate(ports_row)]
    mobile_cell_list = [gspread.models.Cell(32+i, 2, value=val) for i, val in enumerate(ports_row)]
    await sheet.update_cells(cell_list, nowait=True)
    await sheet.update_cells(mobile_cell_list, nowait=True)
    await sheet.update_cell(22, 3, timestamp, nowait=True) # update time cell
    if isRank:
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


async def getPortRow(agcm):
    '''
    Returns the current row of portable locations on the sheets.
    '''
    agc = await agcm.authorize()
    ss = await agc.open(config['sheetName'])
    sheet = await ss.worksheet('Home')
    ports = await sheet.row_values(21)
    ports = ports[:7]
    return ports

def checkPorts(newPorts, ports):
    '''
    Checks the validity of a given set of new portable locations, given a set of current locations.
    Returns a string with an error message, empty string if no error.
    '''
    for port in newPorts:
        loc = port[1]
        for world in port[0]:
            if world < 1 or world > highestWorld:
                return f'Sorry, **{str(world)}** is not a valid world. Please enter a number between 1 and 141.'
            if world in forbiddenWorlds:
                return f'Sorry, world **{str(world)}** is not called because it is either a pking world or a bounty hunter world, or it is not on the world list.'
            for forbiddenLoc in forbiddenLocs:
                if world == forbiddenLoc[0] and loc == forbiddenLoc[1]:
                    return f'Sorry, **{str(world)} {loc}** is a forbidden location.'
            if loc == 'GE' and world not in f2pWorlds:
                return 'Sorry, we only call the location **GE** in F2P worlds.'
            portNames = []
            count = 0
            i = 0
            for p in ports:
                i += 1
                for entry in p:
                    if loc != entry[1]:
                        continue
                    if world in entry[0]:
                        portNames.append(portablesNames[i-1])
                        count += 1
                        break
            '''
            if count >= 3 and not dxp_active:
                msgPorts = ""
                i = 0
                for p in portNames:
                    i += 1
                    msgPorts += '**' + p + '**'
                    if i < len(portNames):
                        msgPorts += ", "
                        if i == len(portNames) - 1:
                            msgPorts += "and "
                return f'Sorry, there cannot be more than 3 portables at the same location.\nThe location **{str(world)} {loc}** already has a {msgPorts}.'
            '''
    return ''

def get_port_type(input):
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
        return ['', -1]
    
last_ports = None

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
        global last_ports
        if last_ports is None:
            agc = await self.bot.agcm.authorize()
            ss = await agc.open(config['sheetName'])
            home = await ss.worksheet('Home')

            last_ports = await home.range('A20:I22')
            return
        
        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        home = await ss.worksheet('Home')

        ports = await home.range('A20:I22')
        
        if not any(ports[i].value != l_p.value for i, l_p in enumerate(last_ports)):
            return
        else:
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
                    current_locs = getPorts(val)
                    old_locs = getPorts(old_val)
                    
                    if only_f2p(old_locs):
                        if not only_f2p(current_locs):
                            role = roles[i]
                            if role:
                                loc_channel = port_server.get_channel(config['locationChannel'])
                                if loc_channel:
                                    await loc_channel.send(f'{role.mention} active at **{format(current_locs)}**')
                        
        if ports[22].value == last_ports[22].value:
            last_ports = ports
            return
        last_ports = ports

        credit = ports[22].value

        editors = get_editors(credit)
        for rank in editors:
            await add_activity(self.bot.agcm, rank.strip(), datetime.utcnow(), sheet_activity=True)

    @commands.command()
    async def boxes(self, ctx):
        '''
        Get portable bank deposit box locations.
        Only available during DXP.
        '''
        addCommand()
        if not dxp_active:
            raise commands.CommandError(message='This command is only enabled during DXP.')

        locChannel = self.bot.get_channel(config['locChannel'])
        adminCommandsChannel = self.bot.get_channel(config['adminCommandsChannel'])

        if ctx.guild == self.bot.get_guild(config['portablesServer']):
            if ctx.channel != locChannel and ctx.channel != adminCommandsChannel:
                raise commands.CommandError(message=f'Error: Incorrect channel. Use {locChannel.mention}.')
        
        global last_ports
        boxes = last_ports[17].value

        embed = discord.Embed(title='__Deposit boxes__', description=boxes, colour=0xff0000, url=config['publicSheets'], timestamp=datetime.utcnow())
        embed.set_thumbnail(url='https://i.imgur.com/Hccdnts.png')

        await ctx.send(embed=embed)

    @commands.command(aliases=['p', 'portable'] + [item for sublist in portableAliases for item in sublist])
    async def portables(self, ctx, portable='', *stuff):
        '''
        Get portable locations.
        '''
        addCommand()

        if ctx.invoked_with in [item for sublist in portableAliases for item in sublist]:
            stuff = (portable,) + stuff
            portable = ctx.invoked_with
        
        if any(thing for thing in stuff):
            edit_command = commands.Bot.get_command(self.bot, 'edit')
            try:
                for check in edit_command.checks:
                    if not await check(ctx):
                        raise commands.CommandError(message=f'Insufficient permissions: `Portables smiley`.')
                await edit_command.callback(self, ctx, portable, *stuff)
                return
            except commands.CommandError as e:
                raise e

        locChannel = self.bot.get_channel(config['locChannel'])
        adminCommandsChannel = self.bot.get_channel(config['adminCommandsChannel'])

        if locChannel:
            if ctx.guild == self.bot.get_guild(config['portablesServer']):
                if ctx.channel != locChannel and ctx.channel != adminCommandsChannel:
                    raise commands.CommandError(message=f'Error: Incorrect channel. Use {locChannel.mention}.')

        global last_ports
        if last_ports is None:
            return
        top_row, mid_row, bot_row = last_ports[:9], last_ports[9:18], last_ports[18:]

        now = datetime.utcnow()
        time_val = str(now.year) + " " + bot_row[2].value + ":" + str(now.second)
        time = datetime.strptime(time_val, '%Y %d %b, %H:%M:%S')

        embed = discord.Embed(title='__Portables FC Locations__', colour=0xff0000, url=config['publicSheets'], timestamp=time)

        if (not portable or not any(portable.upper() in port_name for port_name in portablesNamesUpper)) and not portable.upper() == 'WB':
            for i in range(len(top_row)-2):
                embed.add_field(name=top_row[i].value, value=mid_row[i].value.replace('*', '\*'), inline=True)

            notes = mid_row[7].value
            embed.add_field(name='Notes', value=notes, inline=False)
        else:
            index = 0
            if portable.upper() == 'WB':
                index = 6
            else:
                for i, port_name in enumerate(portablesNamesUpper):
                    if port_name.startswith(portable.upper()):
                        index = i
                        break
                if not index:
                    for i, port_name in enumerate(portablesNamesUpper):
                        if portable.upper() in port_name:
                            index = i
                            break
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
    @is_smiley()
    async def update_time(self, ctx):
        '''
        Updates the time on the Portables sheet.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        timestamp = datetime.utcnow().strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        portables = self.bot.get_guild(config['portablesServer'])
        if not portables:
            raise commands.CommandError(message=f'Error: could not find Portables server.')
        locChannel = portables.get_channel(config['locationChannel'])
        adminCommandsChannel = portables.get_channel(config['adminCommandsChannel'])
        member = await portables.fetch_member(ctx.author.id)

        if ctx.guild == portables:
            if ctx.channel != locChannel and ctx.channel != adminCommandsChannel: # if this is not the locations channel, return
                if locChannel:
                    raise commands.CommandError(message=f'Incorrect channel. Please use {locChannel.mention}.')
                else:
                    raise commands.CommandError(message=f'Incorrect channel. Please use the `locations` channel.')

        name = '' # initialize empty name of user
        isRank = False # boolean value representing whether or not the user is a rank
        rankRole = discord.utils.get(portables.roles, id=config['rankRole'])
        if rankRole in member.roles: # if the rank role is in the set of roles corresponding to the user
            isRank = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        await updateSheet(self.bot.agcm, 0, "", timestamp, name, isRank) # update the sheet

        await ctx.send(f'The time has been updated to `{timestamp}`.')

    @commands.command(aliases=['banlist'])
    @is_mod()
    async def addban(self, ctx, name="", *reasons):
        '''
        Adds a player to the banlist (Mod+) (Portables only).
        Arguments: name, reason, screenshot (optional).
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        Constraints: name must be a valid RSN.
        '''
        addCommand()
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

        headerRows = 5
        banlist = await sheet.col_values(1)
        banlist = banlist[headerRows:]
        durations = await sheet.col_values(2)
        durations = durations[headerRows:]

        permaBanIndex = durations.index('Permanent') + 1
        tempBans = []
        permaBans = []
        exBans = []
        for i, player in enumerate(banlist):
            if not player:
                tempBans = banlist[:i]
                break
        for i, player in enumerate(banlist):
            if i < permaBanIndex:
                continue
            if not player:
                permaBans = banlist[permaBanIndex:i]
                exBans = banlist[i+1:]
                break
        for player in tempBans:
            if name.upper() == player.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the banlist.')
        for player in permaBans:
            if name.upper() == player.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the banlist.')
        row = headerRows + len(tempBans) + 1
        count = 1
        for player in exBans:
            if name.upper() == player.upper():
                count += 1
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        endTime = (datetime.utcnow() + relativedelta(days=+14)).strftime("%b %#d, %Y")
        userName = ctx.author.display_name
        userName = re.sub('[^A-z0-9 -]', '', userName).replace('`', '').strip()
        values = [name, '2 weeks', timestamp, endTime, reason, userName, 'Pending', '', screenshot]

        await sheet.insert_row(values, row)

        await ctx.send(f'**{name}** has been added to the banlist ({str(count)}).')
        adminChannel = self.bot.get_channel(config['adminChannel'])
        await adminChannel.send(f'**{name}** has been added to the banlist with status **Pending**.')

    @commands.command()
    @is_rank()
    async def helper(self, ctx, *nameParts):
        '''
        Adds a helper, or notes activity for an existing helper (Rank+) (Portables only).
        Arguments: name
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not nameParts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in nameParts:
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

        headerRows = 3
        helpers = await sheet.col_values(1)
        helpers = helpers[headerRows:]
        for i, helper in enumerate(helpers):
            if not helper:
                helpers = helpers[:i]
                break

        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        userName = ctx.author.display_name
        userName = re.sub('[^A-z0-9 -]', '', userName).replace('`', '').strip()

        onList = False
        row = 0
        pattern = re.compile('[\W_]+')
        for i, helper in enumerate(helpers):
            if pattern.sub('', name.upper()) == pattern.sub('', helper.upper()):
                name = helper
                row = i + headerRows + 1
                onList = True
                break
        if not onList:
            row = headerRows + len(helpers) + 1
            values = [name, 'Helper', timestamp, userName]
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
            timeCol = 3 + len(activity) * 2
            creditCol = timeCol + 1
            await sheet.update_cell(row, timeCol, timestamp)
            await sheet.update_cell(row, creditCol, userName)
            await ctx.send(f'**{name}** has been noted as active for **{timestamp}**.')

    @commands.command()
    @is_rank()
    async def smileyactivity(self, ctx, *nameParts):
        '''
        Notes activity for a smiley on sheets (Rank+) (Portables only).
        Arguments: name
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not nameParts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in nameParts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Smileys')

        headerRows = 4
        smileys = await sheet.col_values(1)
        smileys = smileys[headerRows:]
        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                smileys = smileys[:i]
                break
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        userName = ctx.author.display_name
        userName = re.sub('[^A-z0-9 -]', '', userName).replace('`', '').strip()

        row = 0
        for i, smiley in enumerate(smileys):
            if name.upper() == smiley.upper():
                row = i + headerRows + 1
                name = smiley
                break
        if not row:
            for i, smiley in enumerate(smileys):
                if name.upper() in smiley.upper():
                    row = i + headerRows + 1
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
        timeCol = 5 + len(activity) * 2
        creditCol = timeCol + 1
        await sheet.update_cell(row, timeCol, timestamp)
        await sheet.update_cell(row, creditCol, userName)
        await ctx.send(f'**{name}** has been noted as active for **{timestamp}**.')

    @commands.command(pass_context=True)
    @portables_admin()
    async def addsmiley(self, ctx, *nameParts):
        '''
        Adds a smiley to the sheets (Admin+) (Portables only).
        Arguments: name.
        Constraints: name must be a valid RSN.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        leaderRole = discord.utils.get(ctx.guild.roles, id=config['leaderRole'])

        if not nameParts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in nameParts:
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

        headerRows = 4
        smileys = await sheet.col_values(1)
        smileys = smileys[headerRows:]

        currentSmileys = []
        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                currentSmileys = smileys[:i]
                break
        for smiley in currentSmileys:
            if name.upper() == smiley.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the smiley list.')
        row = 0
        for i, smiley in enumerate(smileys):
            if name.upper() == smiley.upper():
                row = i + headerRows + 1
                break
        if row:
            await sheet.delete_row(row)
        row = headerRows + len(currentSmileys) + 1
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        endTime = (datetime.utcnow() + relativedelta(months=+1)).strftime("%b %#d, %Y")
        values = [name, 'No', 'Applied', '', '', '', '', '', '', '', '', '', '', 'Pending', timestamp, endTime]
        await sheet.insert_row(values, row)
        await ctx.send(f'**{name}** has been added to the smileys sheet.')
        if ctx.author.top_role <= leaderRole:
            adminChannel = self.bot.get_channel(config['adminChannel'])
            await adminChannel.send(f'**{name}** has been added to the smileys sheet with status **Pending**.')

    @commands.command(pass_context=True)
    @portables_leader()
    async def activatesmiley(self, ctx, *nameParts):
        '''
        Sets smiley status to active (Leader+) (Portables only).
        Arguments: name.
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not nameParts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in nameParts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Smileys')

        headerRows = 4
        smileys = await sheet.col_values(1)
        smileys = smileys[headerRows:]

        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                smileys = smileys[:i]
                break
        row = 0
        for i, smiley in enumerate(smileys):
            if name.upper() == smiley.upper():
                row = i + headerRows + 1
                name = smiley
                break
        if not row:
            for i, smiley in enumerate(smileys):
                if name.upper() in smiley.upper():
                    row = i + headerRows + 1
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

    @commands.command(pass_context=True)
    @portables_admin()
    async def addalt(self, ctx, name="", member=""):
        '''
        Adds a rank alt to the sheets (Admin+) (Portables only).
        Arguments: name, member.
        Member can be either a name or a mention.
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        Constraints: name must be a valid RSN, member must be a rank.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if not member:
            raise commands.CommandError(message=f'Required argument missing: `member`.')
        rankRole = discord.utils.get(ctx.guild.roles, id=config['rankRole'])
        if ctx.message.mentions:
            member = ctx.message.mentions[0]
        else:
            pattern = re.compile('[\W_]+')
            memberName = pattern.sub('', member).upper()
            member = discord.utils.find(lambda m: utils.is_name(memberName, m) and m.top_role >= rankRole, ctx.guild.members)
            if not member:
                raise commands.CommandError(message=f'Could not find rank: `{memberName}`.')
        memberName = member.display_name
        memberName = re.sub('[^A-z0-9 -]', '', memberName).replace('`', '').strip()
        type = ''
        modRole = discord.utils.get(ctx.guild.roles, id=config['modRole'])
        adminRole = discord.utils.get(ctx.guild.roles, id=config['adminRole'])
        leaderRole = discord.utils.get(ctx.guild.roles, id=config['leaderRole'])
        if member.top_role >= adminRole:
            type = 'Admin+ alt'
        elif member.top_role >= modRole:
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

        headerRows = 4
        smileys = await sheet.col_values(1)
        smileys = smileys[headerRows:]
        types = await sheet.col_values(2)
        types = types[headerRows:]

        currentSmileys = []
        for i, smiley in enumerate(smileys):
            if not smiley:
                currentSmileys = smileys[:i]
                types = types[:i]
                break
        for smiley in currentSmileys:
            if name.upper() == smiley.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the smiley list.')
        row = 0
        if 'Rank' in type:
            for i, t in enumerate(types):
                if not 'ALT' in t.upper():
                    row = i + headerRows + 1
                    break
        elif 'Mod' in type:
            for i, t in enumerate(types):
                if not 'ADMIN' in t.upper() and not 'MODERATOR' in t.upper():
                    row = i + headerRows + 1
                    break
        elif 'Admin' in type:
            for i, t in enumerate(types):
                if not 'ADMIN' in t.upper():
                    row = i + headerRows + 1
                    break
        if not row:
            raise commands.CommandError(message=f'Unexpected error: Could not find row in spreadsheet.')
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        endTime = ''
        values = [name, type, f'{memberName} alt', '', '', '', '', '', '', '', '', '', '', 'Pending', timestamp, endTime]

        await sheet.insert_row(values, row)

        await ctx.send(f'**{memberName}**\'s alt, **{name}**, has been added to the smileys sheet.')
        if ctx.author.top_role < leaderRole:
            adminChannel = self.bot.get_channel(config['adminChannel'])
            await adminChannel.send(f'**{memberName}**\'s alt, **{name}**, has been added to the smileys sheet with status **Pending**.')

    @commands.command(pass_context=True, aliases=['a'], ignore_extra=True)
    @is_smiley()
    async def add(self, ctx):
        """
        Add portable locations (Smiley+) (Portables only).
        Arguments: portable, worlds, location, worlds, location, etc...
        Constraints: This command can only be used in the locations channel. Only approved locations, and worlds are allowed. Additionally, worlds must be a valid world. No more than 3 portables per location.
        """
        addCommand()
        await ctx.channel.trigger_typing() # send 'typing...' status

        portables = self.bot.get_guild(config['portablesServer'])
        if not portables:
            raise commands.CommandError(message=f'Error: could not find Portables server.')
        locChannel = portables.get_channel(config['locationChannel'])
        adminCommandsChannel = portables.get_channel(config['adminCommandsChannel'])
        member = await portables.fetch_member(ctx.author.id)

        if ctx.guild == portables:
            if ctx.channel != locChannel and ctx.channel != adminCommandsChannel: # if this is not the locations channel, return
                if locChannel:
                    raise commands.CommandError(message=f'Incorrect channel. Please use {locChannel.mention}.')
                else:
                    raise commands.CommandError(message=f'Incorrect channel. Please use the `locations` channel.')

        input = ctx.message.content.upper().replace(ctx.prefix.upper(), '', 1).replace(ctx.invoked_with.upper(), '', 1).strip() # get the input corresponding to this message
        if not input: # if there was no input, return
            raise commands.CommandError(message=f'Required argument missing: `location`.')

        # get the portable type corresponding to the input
        portable, col = get_port_type(input)
        if col == -1: # if no portable type was given, return
            raise commands.CommandError(message=f'Required argument missing: `portable`.')

        # replace some portable types due to incompatibilities with location abbreviations
        input = input.replace('RANGE', '')
        input = input.replace('WORKBENCH', '')
        newPorts = getPorts(input) # get the set of portable locations corresponding to the input

        if not newPorts: # if there were no locations, return
            raise commands.CommandError(message=f'Invalid argument: `location`.')

        ports = await getPortRow(self.bot.agcm) # get the current portable locations from the sheet

        val = ports[col-1] # get the string corresponding to our portable type
        ports[col-1] = "" # set value for our portable type to empty
        for i, p in enumerate(ports): # for each portable, get the set of portable locations
            ports[i] = getPorts(p)

        error = checkPorts(newPorts, ports) # check for errors in the set of portables
        if error: # if there was an error, send the error message and return
            raise commands.CommandError(message=error)

        newPortsText = format(newPorts).replace('*', '\*') # string representing portables to be added
        currentPorts = getPorts(val) # current portables on sheets
        sumPorts = addPorts(currentPorts, newPorts) # set of portables after adding given portables
        newVal = format(sumPorts) # string representing the new set of portable locations

        # check whether multiple portables were added
        multiple = False
        if len(newPorts) > 1:
            multiple = True
        elif len(newPorts[0][0]) > 1:
            multiple = True

        # if no change, raise an error
        if newVal == val:
            if multiple:
                raise commands.CommandError(message=f'The `{portable}` locations `{format(newPorts)}` were already on the sheet.')
            else:
                raise commands.CommandError(message=f'The `{portable}` location `{format(newPorts)}` was already on the sheet.')

        timestamp = datetime.utcnow().strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        name = '' # initialize empty name of user
        isRank = False # boolean value representing whether or not the user is a rank
        rankRole = discord.utils.get(portables.roles, id=config['rankRole'])
        if rankRole in member.roles: # if the rank role is in the set of roles corresponding to the user
            isRank = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        await updateSheet(self.bot.agcm, col, newVal, timestamp, name, isRank) # update the sheet

        # send confirmation message
        if multiple:
            await ctx.send(f'The **{portable}** locations **{newPortsText}** have been added to the Portables sheet.')
        else:
            await ctx.send(f'The **{portable}** location **{newPortsText}** has been added to the Portables sheet.')

    @commands.command(pass_context=True, aliases=['rem'], ignore_extra=True)
    @is_smiley()
    async def remove(self, ctx):
        """
        Remove portable locations (Smiley+) (Portables only).
        Arguments: portable, worlds, location, worlds, location, etc...
        Constraints: This command can only be used in the locations channel. Only approved locations, and worlds are allowed. Additionally, worlds must be a valid world. No more than 3 portables per location.
        """
        addCommand() # increment global commands counter
        await ctx.channel.trigger_typing() # send 'typing...' status

        portables = self.bot.get_guild(config['portablesServer'])
        if not portables:
            raise commands.CommandError(message=f'Error: could not find Portables server.')
        locChannel = portables.get_channel(config['locationChannel'])
        adminCommandsChannel = portables.get_channel(config['adminCommandsChannel'])
        member = await portables.fetch_member(ctx.author.id)

        if ctx.guild == portables:
            if ctx.channel != locChannel and ctx.channel != adminCommandsChannel: # if this is not the locations channel, return
                if locChannel:
                    raise commands.CommandError(message=f'Incorrect channel. Please use {locChannel.mention}.')
                else:
                    raise commands.CommandError(message=f'Incorrect channel. Please use the `locations` channel.')

        # get the input corresponding to this message
        input = ctx.message.content.upper().replace(ctx.prefix.upper(), '', 1).replace(ctx.invoked_with.upper(), '', 1).strip() # get the input corresponding to this message

        if not input: # if there was no input, return
            raise commands.CommandError(message=f'Required argument missing: `location`.')

        # get the portable type corresponding to the input
        portable, col = get_port_type(input)
        if col == -1: # if no portable type was given, return
            raise commands.CommandError(message=f'Required argument missing: `portable`.')

        # replace some portable types due to incompatibilities with location abbreviations
        input = input.replace('RANGE', '')
        input = input.replace('WORKBENCH', '')
        oldPorts = getPorts(input) # get the set of portable locations corresponding to the input

        if not oldPorts: # if there were no locations, return=
            raise commands.CommandError(message=f'Invalid argument: `location`.')

        for port in oldPorts: # if the input contains an invalid world, return
            for world in port[0]:
                if world < 1:
                    raise commands.CommandError(message=f'Invalid argument: world `{str(world)}`.')

        # get the current locations for this portable from the sheet
        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['sheetName'])
        sheet = await ss.worksheet('Home')
        val = await sheet.cell(21, col)
        val = val.value

        oldPortsText = format(oldPorts).replace('*', '\*') # string representing portables to be removed
        currentPorts = getPorts(val) # current portables on sheets
        difPorts = removePorts(currentPorts, oldPorts) # set of portables after removing given portables
        newVal = format(difPorts) # string representing the new set of portable locations

        # check whether multiple portables were removed
        multiple = False
        if len(oldPorts) > 1:
            multiple = True
        elif len(oldPorts[0][0]) > 1:
            multiple = True
        
        # if no change, raise an error
        if newVal == val:
            if multiple:
                raise commands.CommandError(message=f'The `{portable}` locations `{format(oldPorts)}` weren\'t found on the sheet.')
            else:
                raise commands.CommandError(message=f'The `{portable}` location `{format(oldPorts)}` was not found on the sheet.')

        timestamp = datetime.utcnow().strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        name = '' # initialize empty name of user
        isRank = False # boolean value representing whether or not the user is a rank
        rankRole = discord.utils.get(portables.roles, id=config['rankRole'])
        if rankRole in member.roles: # if the rank role is in the set of roles corresponding to the user
            isRank = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        await updateSheet(self.bot.agcm, col, newVal, timestamp, name, isRank) # update the sheet

        # send confirmation message
        if multiple:
            await ctx.send(f'The **{portable}** locations **{oldPortsText}** have been removed from the Portables sheet.')
        else:
            await ctx.send(f'The **{portable}** location **{oldPortsText}** has been removed from the Portables sheet.')

    @commands.command(aliases=['rall'], ignore_extra=True)
    @is_smiley()
    async def removeall(self, ctx, *input):
        '''
        Removes all instances of a given location, or all locations of a given portable. (Smiley+) (Portables only)
        Arguments: [portable] / [worlds][locations]
        Constraints: If calling the command with a portable, you can only do one portable at a time.
        Example: `-removeall range` / `-removeall 84 ca`
        '''
        addCommand() # increment global commands counter
        await ctx.channel.trigger_typing() # send 'typing...' status

        portables = self.bot.get_guild(config['portablesServer'])
        locChannel = self.bot.get_channel(config['locationChannel'])
        adminCommandsChannel = self.bot.get_channel(config['adminCommandsChannel'])
        member = await portables.fetch_member(ctx.author.id)

        if ctx.guild == portables:
            if ctx.channel != locChannel and ctx.channel != adminCommandsChannel: # if this is not the locations channel, return
                raise commands.CommandError(message=f'Incorrect channel. Please use {locChannel.mention}.')

        if input:
            input = ' '.join(input).upper().strip()
        if not input:
            raise commands.CommandError(message=f'Required argument missing: `portable/location`.')

        to_remove = getPorts(input)
        if format(to_remove) == 'N/A':
            to_remove = []
        if not to_remove:
            port = ''
            index = 0
            for i, aliases in enumerate(portableAliases):
                if input.lower() in aliases:
                    port = aliases[0]
                    index = i
                    break
            if not port:
                raise commands.CommandError(message=f'Invalid argument: `{input}`.')


        current_values = await getPortRow(self.bot.agcm)
        current = [getPorts(i) for i in current_values]

        if to_remove:
            new_values = [format(removePorts(cur, to_remove)) for cur in current]
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
        isRank = False # boolean value representing whether or not the user is a rank
        rankRole = discord.utils.get(portables.roles, id=config['rankRole'])
        if rankRole in member.roles: # if the rank role is in the set of roles corresponding to the user
            isRank = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        await update_sheet_row(self.bot.agcm, new_values, timestamp, name, isRank)

        if to_remove:
            await ctx.send(f'All instances of the location(s) `{format(to_remove)}` have been removed.')
        else:
            await ctx.send(f'All locations for the portable `{port}` have been removed.')



    @commands.command(pass_context=True, ignore_extra=True)
    @is_smiley()
    async def edit(self, ctx, portable='', *inputLocs):
        '''
        Edit portable locations (Smiley+) (Portables only).
        Arguments: portable, worlds, location, worlds, location, etc...
        Alternatively, you can directly use -portable [arguments], e.g.: -fletch 100 ca
        Constraints: This command can only be used in the locations channel. Only approved locations and worlds are allowed. Additionally, worlds must be a valid world. No more than 3 portables per location.
        '''
        addCommand() # increment global commands counter
        await ctx.channel.trigger_typing() # send 'typing...' status

        portables = self.bot.get_guild(config['portablesServer'])
        locChannel = self.bot.get_channel(config['locationChannel'])
        adminCommandsChannel = self.bot.get_channel(config['adminCommandsChannel'])
        member = await portables.fetch_member(ctx.author.id)

        if ctx.guild == portables:
            if ctx.channel != locChannel and ctx.channel != adminCommandsChannel: # if this is not the locations channel, return
                raise commands.CommandError(message=f'Incorrect channel. Please use {locChannel.mention}.')

        if not portable: # if there was no portable type in the input, return
            raise commands.CommandError(message=f'Required argument missing: `portable`.')

        for i, ports in enumerate(portableAliases):
            if portable in ports:
                portable = ports[0]
                col = i + 1
                break

        input = ''
        for loc in inputLocs:
            input += loc + ' '
        input = input.upper().strip()

        name = '' # initialize empty name of user
        isRank = False # boolean value representing whether or not the user is a rank
        rankRole = discord.utils.get(portables.roles, id=config['rankRole'])
        if rankRole in member.roles: # if the rank role is in the set of roles corresponding to the user
            isRank = True # then set isRank to true
            name = utils.get_user_name(member) # and get the name of the user

        timestamp = datetime.utcnow().strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        if input.replace('/', '').replace(' ', '') in ['NA', 'NO', 'NONE', '0', 'ZERO']: # if input was 'N/A' or a variation, remove all locations and return
            await updateSheet(self.bot.agcm, col, 'N/A', timestamp, name, isRank)
            await ctx.send(f'The **{portable}** locations have been edited to: **N/A**.')
            return

        newPorts = getPorts(input) # calculate new set of portables from the input string
        if not newPorts: # if there were no portables, return
            raise commands.CommandError(message=f'Invalid argument: `location`.')

        ports = await getPortRow(self.bot.agcm) # get the row of portable locations from sheets
        oldVal = ports[col-1]
        ports[col-1] = "" # set value for our portable type to empty
        for i, p in enumerate(ports): # for each portable, get the set of portable locations
            ports[i] = getPorts(p)

        error = checkPorts(newPorts, ports) # check for errors in the set of portables
        if error: # if there was an error, send the error message and return
            raise commands.CommandError(message=error)

        newVal = format(newPorts) # create a string corresponding
        newPortsText = newVal.replace('*', '\*') # in the text for the discord message, escape the stars for formatting issues

        # if no change, raise an error
        if newVal == oldVal:
            raise commands.CommandError(message=f'The `{portable}` locations were already set to `{newVal}`.')

        await updateSheet(self.bot.agcm, col, newVal, timestamp, name, isRank) # update the sheet

        await ctx.send(f'The **{portable}** locations have been edited to: **{newPortsText}**.') # send confirmation message

    @commands.command(pass_context=True, aliases=['watch'])
    @is_rank()
    async def watchlist(self, ctx, name="", *reasons):
        '''
        Adds a player to the watchlist (Rank+) (Portables only).
        Arguments: name, reason, screenshot (optional).
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        Constraints: name must be a valid RSN.
        '''
        addCommand()
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
        headerRows = 5

        watchlist = await sheet.col_values(1)
        watchlist = watchlist[headerRows:]

        for i, player in enumerate(watchlist):
            if not player:
                watchlist = watchlist[:i]
                break
        timestamp = datetime.utcnow().strftime("%b %#d, %Y")
        userName = ctx.author.display_name
        userName = re.sub('[^A-z0-9 -]', '', userName).replace('`', '').strip()
        count = 1
        for player in watchlist:
            if name.upper() == player.upper():
                count += 1
        row = headerRows + len(watchlist) + 1
        values = [name, timestamp, reason, userName, screenshot]

        await sheet.insert_row(values, row)

        await ctx.send(f'**{name}** has been added to the watchlist ({str(count)}).')

    @commands.command(pass_context=True, aliases=['act', 'active'])
    @portables_admin()
    async def activity(self, ctx, *nameParts):
        '''
        Notes rank activity on admin sheets (Admin+) (Portables only).
        Arguments: name
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        user = ctx.author
        userName = user.display_name

        if not nameParts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in nameParts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if name.upper() in userName.upper():
            raise commands.CommandError(message=f'Invalid argument: `{name}`. You cannot track your own activity.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['adminSheetName'])
        sheet = await ss.worksheet('Rank Reports')
        headerRows = 4

        month = datetime.utcnow().strftime("%B")
        sheetMonthCell = await sheet.cell(3, 1)
        sheetMonth = sheetMonthCell.value
        if month.upper().strip() != sheetMonth.upper().strip():
            raise commands.CommandError(message=f'Error: `admin_sheet_month`. Please wait for a Leader to perform this month\'s rank changes.')
        ranks = await sheet.col_values(1)
        ranks = ranks[headerRows:]
        for i, rank in enumerate(ranks):
            if rank is None or not rank:
                ranks = ranks[:i]
                break
        timestamp = datetime.utcnow().strftime("%#d")
        row = 0
        for i, rank in enumerate(ranks):
            if rank in rankTitles:
                continue
            if name.upper() == rank.upper():
                row = i + headerRows + 1
                name = rank
                break
        if not row:
            for i, rank in enumerate(ranks):
                if rank in rankTitles:
                    continue
                if name.upper() in rank.upper():
                    row = i + headerRows + 1
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

    @commands.command(pass_context=True)
    @portables_admin()
    async def sheetactivity(self, ctx, *nameParts):
        '''
        Notes rank sheet activity on admin sheets (Admin+) (Portables only).
        Arguments: name
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        user = ctx.author
        userName = user.display_name

        if not nameParts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = ''
        for part in nameParts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if name.upper() in userName.upper():
            raise commands.CommandError(message=f'Invalid argument: `{name}`. You cannot track your own activity.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open(config['adminSheetName'])
        sheet = await ss.worksheet('Rank Reports')
        headerRows = 4

        month = datetime.utcnow().strftime("%B")
        sheetMonthCell = await sheet.cell(3, 1)
        sheetMonth = sheetMonthCell.value
        if month != sheetMonth:
            raise commands.CommandError(message=f'Error: `admin_sheet_month`. Please wait for a Leader to perform this month\'s rank changes.')
        ranks = await sheet.col_values(1)
        ranks = ranks[headerRows:]
        for i, rank in enumerate(ranks):
            if rank is None or not rank:
                ranks = ranks[:i]
                break
        timestamp = datetime.utcnow().strftime("%#d")
        row = 0
        for i, rank in enumerate(ranks):
            if rank in rankTitles:
                continue
            if name.upper() == rank.upper():
                row = i + headerRows + 1
                name = rank
                break
        if not row:
            for i, rank in enumerate(ranks):
                if rank in rankTitles:
                    continue
                if name.upper() in rank.upper():
                    row = i + headerRows + 1
                    name = rank
                    break
        if not row:
            raise commands.CommandError(message=f'Could not find rank: `{name}`.')

        activity = await sheet.row_values(row)
        sheetActivity = activity[34:65]
        activity = activity[3:34]

        sheetActivity = list(filter(bool, sheetActivity))
        activity = list(filter(bool, activity))
        if timestamp in sheetActivity:
            raise commands.CommandError(message=f'`{name}` has already been noted active for today.')
        sheetCol = 35 + len(sheetActivity)
        await sheet.update_cell(row, sheetCol, timestamp)
        await ctx.send(f'**{name}** has been noted as active on sheets for **{timestamp}** **{datetime.utcnow().strftime("%b")}**.')


def setup(bot):
    bot.add_cog(Sheets(bot))
