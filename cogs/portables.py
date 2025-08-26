from typing import Any
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Cog
from gspread_asyncio import AsyncioGspreadClient, AsyncioGspreadSpreadsheet, AsyncioGspreadWorksheet
from src.message_queue import QueueMessage
from src.bot import Bot
from datetime import datetime, timedelta, UTC
import re
import validators
import gspread
from src.checks import portables_leader, portables_admin, is_mod, is_rank, is_helper, portables_only
import logging
from src.discord_utils import find_text_channel, get_guild_text_channel, get_text_channel
from src.runescape_utils import get_rsn
from src.portables_utils import portables_names, portables_names_upper, portable_aliases, rank_titles, get_ports, only_f2p, add_ports, remove_ports, format, check_ports
from discord.abc import GuildChannel

class Portables(Cog):
    last_ports: list[gspread.Cell] | None = None

    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

        self.fletchers_channel_id: int = self.bot.config['fletchers_channel_id']
        self.crafters_channel_id: int = self.bot.config['crafters_channel_id']
        self.braziers_channel_id: int = self.bot.config['braziers_channel_id']
        self.sawmills_channel_id: int = self.bot.config['sawmills_channel_id']
        self.ranges_channel_id: int = self.bot.config['ranges_channel_id']
        self.wells_channel_id: int = self.bot.config['wells_channel_id']
        self.workbenches_channel_id: int = self.bot.config['workbenches_channel_id']

        self.portables_channel_ids: list[int] = [
            self.fletchers_channel_id,
            self.crafters_channel_id,
            self.braziers_channel_id,
            self.sawmills_channel_id,
            self.ranges_channel_id,
            self.wells_channel_id,
            self.workbenches_channel_id
        ]

        self.portables_channel_mentions: list[str] = [f'<#{id}>' for id in self.portables_channel_ids]
        self.portables_channel_mention_string: str = ', '.join(self.portables_channel_mentions[:len(self.portables_channel_mentions) - 1]) + ', or ' + self.portables_channel_mentions[len(self.portables_channel_mentions) - 1]

    async def cog_load(self) -> None:
        self.track_location_updates.start()

    async def cog_unload(self) -> None:
        self.track_location_updates.cancel()

    def get_last_ports(self) -> list[gspread.Cell] | None:
        return self.last_ports

    def set_last_ports(self, ports: list[gspread.Cell]) -> None:
        self.last_ports = ports

    async def get_port_row(self) -> list[str | None]:
        '''
        Returns the current row of portable locations on the sheets.
        '''
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Home')
        ports: list[str | None] = await sheet.row_values(21)
        ports = ports[:7]
        return ports

    async def write_error(self, name: str, date: datetime, msg: str) -> None:
        '''
        Write an error message to the error tab on the admin sheets.
        '''
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['adminSheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Errors')

        values: list[str] = [name, str(date), msg]

        errors: list[str | None] = await sheet.col_values(1)
        for i, e in enumerate(errors):
            if e == "":
                row: int = i+1
                cell_list: list[gspread.Cell] = [gspread.Cell(row, col, value=values[col-1]) for col in range(1,4)]
                await sheet.update_cells(cell_list, nowait=True) # type: ignore : nowait is valid
                return
            elif i == len(errors)-1:
                await sheet.insert_row(values, i+2)

    def get_port_type(self, input: str, channel: GuildChannel | None = None) -> tuple[str, int]:
        '''
        Get the portable type from the input string.

        Args:
            input (_type_): The input string
            channel (_type_, optional): The channel. Defaults to None.

        Returns:
            tuple[str, int]: _description_
        '''
        if 'FL' in input or input.startswith('F'):
            return ('fletcher', 1)
        elif 'CR' in input or (input.startswith('C') and not (input.startswith('CA') or input.startswith('CW'))):
            return ('crafter', 2)
        elif 'BR' in input or (input.startswith('B') and not (input.startswith('BE') or input.startswith('BA') or input.startswith('BU'))):
            return ('brazier', 3)
        elif 'SAW' in input or 'MIL' in input or (input.startswith('M') and not (input.startswith('MG') or input.startswith('MEI'))) or input.startswith('S'):
            return ('sawmill', 4)
        elif 'RAN' in input or input.startswith('R'):
            return ('range', 5)
        elif 'WEL' in input or input.startswith('WE'):
            return ('well', 6)
        elif 'WOR' in input or 'BEN' in input or input.startswith('WO') or input.startswith('WB'):
            return ('workbench', 7)
        elif channel and channel.id in self.portables_channel_ids:
            return (portables_names[self.portables_channel_ids.index(channel.id)].lower(), self.portables_channel_ids.index(channel.id) + 1)
        return ('', -1)
    
    async def update_sheet(self, col: int, new_val: Any, timestamp: str, name: str, is_rank: bool) -> None:
        '''
        Update a given column of the location row (i.e. a cell) on the sheets with:
        new_val, new value for the cell (string)
        timestamp, the time for in the time cell (string)
        name, the name of the editor for in the credit cell (string) (if is_rank)
        is_rank, Boolean value that represents whether the editor is a rank
        '''
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Home')

        if col and new_val:
            await sheet.update_cell(21, col, new_val, nowait=True) # type: ignore update location cell
            await sheet.update_cell(31+col, 2, new_val, nowait=True) # type: ignore update mobile location cell
        await sheet.update_cell(22, 3, timestamp, nowait=True) # type: ignore update time cell
        if is_rank:
            await sheet.update_cell(22, 5, name, nowait=True) # type: ignore update editor name
            await sheet.update_cell(39, 2, name, nowait=True) # type: ignore update mobile editor name

    async def update_sheet_row(self, ports_row: list, timestamp: str, name: str, is_rank: bool) -> None:
        '''
        Update the entire row of locations on the sheets, where:
        ports_row: list of length 6 with strings denoting the value for each cell.
        timestamp: string representing the time for in the time cell.
        name: the name of the editor.
        is_rank: bollean value that denotes whether or not the editor is a rank.
        '''
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Home')

        cell_list: list[gspread.Cell] = [gspread.Cell(21, i+1, value=val) for i, val in enumerate(ports_row)]
        mobile_cell_list: list[gspread.Cell] = [gspread.Cell(32+i, 2, value=val) for i, val in enumerate(ports_row)]
        await sheet.update_cells(cell_list, nowait=True) # type: ignore
        await sheet.update_cells(mobile_cell_list, nowait=True) # type: ignore
        await sheet.update_cell(22, 3, timestamp, nowait=True) # type: ignore update time cell
        if is_rank:
            await sheet.update_cell(22, 5, name, nowait=True) # type: ignore update editor name
            await sheet.update_cell(39, 2, name, nowait=True) # type: ignore update mobile editor name

    async def add_activity(self, name: str, date: datetime, sheet_activity: bool = False) -> None:
        '''
        Note a player as active for a given date
        '''
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['adminSheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Rank Reports')

        sheet_month_cell: gspread.Cell = await sheet.cell(3, 1)
        sheet_month: str | None = sheet_month_cell.value
        if not sheet_month or sheet_month.upper() != date.strftime("%B").upper():
            await self.write_error(name, date, f"Could not track {'fc' if not sheet_activity else 'sheet'} activity: month out of sync")
            return
        
        day = str(date.day)
        ranks: list[str | None] = await sheet.col_values(1)
        for i, r in enumerate(ranks):
            if r and r.upper() == name.upper():
                row: int = i+1
                if not sheet_activity:
                    dates: list = (await sheet.row_values(row) + [""]*100)[3:33]
                else:
                    dates = (await sheet.row_values(row) + [""]*100)[34:64]
                if not dates:
                    if not sheet_activity:
                        col: int = 4
                    else:
                        col = 35
                    await sheet.update_cell(row, col, day, nowait=True) # type: ignore
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
                            await sheet.update_cell(row, col, day, nowait=True) # type: ignore
                            return
            elif i == len(ranks) - 1:
                await self.write_error(name, date, f"Could not track {'fc' if not sheet_activity else 'sheet'} activity: name not found")
                return
    
    @tasks.loop(seconds=10)
    async def track_location_updates(self) -> None:
        '''
        Loop to track location update activity
        '''
        try:
            agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
            ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
            home: AsyncioGspreadWorksheet = await ss.worksheet('Home')

            last_ports: list[gspread.Cell] | None = self.get_last_ports()
            if last_ports is None:
                last_ports = await home.range('A20:I22')
                self.set_last_ports(last_ports)
                return

            ports: list[gspread.Cell] = await home.range('A20:I22')
            
            if not any(ports[i].value != l_p.value for i, l_p in enumerate(last_ports)):
                return
            else:
                self.set_last_ports(ports)

                # top_row_old: list[gspread.Cell] = last_ports[:9]
                mid_row_old: list[gspread.Cell] = last_ports[9:18]
                # bot_row_old: list[gspread.Cell] = last_ports[18:]
                # top_row: list[gspread.Cell] = ports[:9]
                mid_row: list[gspread.Cell] = ports[9:18]
                # bot_row: list[gspread.Cell] = ports[18:]

                role_ids: list[int] = [self.bot.config['fletcher_role'], self.bot.config['crafter_role'], self.bot.config['brazier_role'], self.bot.config['sawmill_role'], self.bot.config['range_role'], self.bot.config['well_role'], self.bot.config['workbench_role']]
                port_server: discord.Guild | None = self.bot.get_guild(self.bot.config['portablesServer'])
                if port_server:
                    roles: list[discord.Role | None] = []
                    for role_id in role_ids:
                        role: discord.Role | None = port_server.get_role(role_id)
                        roles.append(role)

                    for i, cell in enumerate(mid_row[:7]):
                        old_cell: gspread.Cell = mid_row_old[i]
                        val: str | None = cell.value
                        old_val: str | None = old_cell.value
                        current_locs: list[tuple[list[int], str]] = get_ports(val) if val else []
                        old_locs: list[tuple[list[int], str]] = get_ports(old_val) if old_val else []
                        
                        if only_f2p(old_locs):
                            if not only_f2p(current_locs):
                                role = roles[i]
                                if role:
                                    channel_id: int = self.portables_channel_ids[i]
                                    loc_channel: discord.TextChannel = get_guild_text_channel(port_server, channel_id)
                                    if loc_channel:
                                        self.bot.queue_message(QueueMessage(loc_channel, f'{role.mention} active at **{format(current_locs)}**'))
        except Exception as e:
            error: str = f'Error encountered portable locations tracking: {e}'
            print(error)
            logging.critical(error)

            try:
                channel: discord.TextChannel = get_text_channel(self.bot, self.bot.config['testChannel'])
                self.bot.queue_message(QueueMessage(channel, error))
            except:
                pass

    @commands.command(aliases=['box'])
    async def boxes(self, ctx: commands.Context) -> None:
        '''
        Get portable bank deposit box locations.
        Only available during DXP.
        '''
        self.bot.increment_command_counter()
        
        last_ports: list[gspread.Cell] | None = self.get_last_ports()
        boxes: str | None = last_ports[17].value if last_ports else None

        embed = discord.Embed(title='__Deposit boxes__', description=boxes, colour=0xff0000, url=self.bot.config['publicSheets'], timestamp=datetime.now(UTC))
        embed.set_thumbnail(url='https://i.imgur.com/Hccdnts.png')

        await ctx.send(embed=embed)

    @commands.command(aliases=['p', 'portable'] + [item for sublist in portable_aliases for item in sublist])
    async def portables(self, ctx: commands.Context, portable: str = '', *input: str) -> None:
        '''
        Get portable locations.
        '''
        self.bot.increment_command_counter()

        if ctx.invoked_with in [item for sublist in portable_aliases for item in sublist]:
            input = (portable,) + input
            portable = ctx.invoked_with
        
        if any(thing for thing in input):
            edit_command: commands.Command | None = self.bot.get_command('edit')
            try:
                for check in (edit_command.checks if edit_command else []):
                    if not await check(ctx): # type: ignore : MaybeCoro can be awaited
                        raise commands.CommandError(message=f'Insufficient permissions: `Portables helper`.')
                if edit_command:
                    await edit_command.callback(self, ctx, portable, *input) # type: ignore : Portables (self) is valid as first argument for the callback
                return
            except commands.CommandError as e:
                raise e

        admin_commands_channel: discord.TextChannel | None = find_text_channel(self.bot, self.bot.config['adminCommandsChannel'])
        if (admin_commands_channel and ctx.guild == self.bot.get_guild(self.bot.config['portablesServer']) and
            ctx.channel != admin_commands_channel and not ctx.channel.id in self.portables_channel_ids and not ctx.author.id == self.bot.config['owner']):
            raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {self.portables_channel_mention_string}.')

        last_ports: list[gspread.Cell] | None = self.get_last_ports()
        if last_ports is None:
            return
        top_row: list[gspread.Cell] = last_ports[:9]
        mid_row: list[gspread.Cell] = last_ports[9:18]
        bot_row: list[gspread.Cell] = last_ports[18:]

        now: datetime = datetime.now(UTC)
        time_val: str = str(now.year) + (" " + bot_row[2].value if bot_row[2].value else '') + ":" + str(now.second)
        time: datetime = datetime.strptime(time_val, '%Y %d %b, %H:%M:%S').replace(tzinfo=UTC)

        embed = discord.Embed(title='__Portables FC Locations__', colour=0xff0000, url=self.bot.config['publicSheets'], timestamp=time)

        if (not portable or not any(portable.upper() in port_name for port_name in portables_names_upper)) and not portable.upper() == 'WB':
            for i in range(len(top_row)-2):
                mid_row_value: str | None = mid_row[i].value
                mid_row_value = mid_row_value.replace('*', '\\*') if mid_row_value else ''
                embed.add_field(name=top_row[i].value, value=mid_row_value, inline=True)

            notes: str | None = mid_row[7].value
            embed.add_field(name='Notes', value=notes, inline=False)
        else:
            index = 0
            if portable.upper() == 'WB':
                index = 6
            else:
                for i, port_name in enumerate(portables_names_upper):
                    if port_name.startswith(portable.upper()):
                        index: int = i
                        break
                if not index:
                    for i, port_name in enumerate(portables_names_upper):
                        if portable.upper() in port_name:
                            index = i
                            break
            # Check for correct portable channel
            if ctx.guild == self.bot.get_guild(self.bot.config['portablesServer']) and admin_commands_channel:
                if ctx.channel.id in self.portables_channel_ids:
                    port_channel_index = self.portables_channel_ids.index(ctx.channel.id)
                    if index != port_channel_index:
                        correct_channel: discord.TextChannel | None = get_guild_text_channel(ctx.guild, self.portables_channel_ids[index]) if ctx.guild else None
                        if correct_channel:
                            raise commands.CommandError(message=f'Error: `Incorrect channel for {portables_names_upper[index].lower()}`. Please use {correct_channel.mention}.')
            mid_row_value: str | None = mid_row[index].value
            mid_row_value = mid_row_value.replace('*', '\\*') if mid_row_value else ''
            embed.add_field(name=top_row[index].value, value=mid_row_value)

        embed.set_thumbnail(url='https://i.imgur.com/Hccdnts.png')

        names: str = bot_row[4].value if bot_row[4].value else ''
        name: str = names.split(',')[0].split('&')[0].split('/')[0].split('|')[0].strip()
        pattern: re.Pattern[str] = re.compile(r'([^\s\w]|_)+')
        name = pattern.sub('', name).replace(' ', '%20')
        player_image_url: str = f'https://services.runescape.com/m=avatar-rs/{name}/chat.png'
        embed.set_author(name=names, url=self.bot.config['publicSheets'], icon_url=player_image_url)

        await ctx.send(embed=embed)
    
    @commands.command()
    @is_helper()
    async def update_time(self, ctx: commands.Context) -> None:
        '''
        Updates the time on the Portables sheet.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        timestamp: str = datetime.now(UTC).strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        portables: discord.Guild | None = self.bot.get_guild(self.bot.config['portablesServer'])
        if not portables:
            raise commands.CommandError(message=f'Error: could not find Portables server.')
        member: discord.Member = await portables.fetch_member(ctx.author.id)

        admin_commands_channel: discord.TextChannel | None = find_text_channel(self.bot, self.bot.config['adminCommandsChannel'])
        if (admin_commands_channel and ctx.guild == self.bot.get_guild(self.bot.config['portablesServer']) and
            ctx.channel != admin_commands_channel and not ctx.channel.id in self.portables_channel_ids):
            raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {self.portables_channel_mention_string}.')

        name: str = '' # initialize empty name of user
        is_rank = False # boolean value representing whether or not the user is a rank
        rank_role: discord.Role | None = discord.utils.get(portables.roles, id=self.bot.config['rankRole'])
        if rank_role in member.roles: # if the rank role is in the set of roles corresponding to the user
            is_rank = True # then set isRank to true
            name = get_rsn(member) # and get the name of the user

        await self.update_sheet(0, "", timestamp, name, is_rank) # update the sheet

        await ctx.send(f'The time has been updated to `{timestamp}`.')

    @commands.command(aliases=['banlist'], hidden=True)
    @is_mod()
    async def addban(self, ctx: commands.Context, name="", *reasons) -> None:
        '''
        Adds a player to the banlist (Mod+) (Portables only).
        Arguments: name, reason, screenshot (optional).
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        Constraints: name must be a valid RSN.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = re.sub(r'[^A-z0-9 -]', '', name).replace('`', '').strip()
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if not reasons:
            raise commands.CommandError(message=f'Required argument missing: `reason`.')
        screenshot = ''
        reasons = list(reasons)
        if validators.url(reasons[len(reasons)-1]):
            screenshot = reasons[len(reasons)-1]
            del reasons[len(reasons)-1]
        reason: str = ""
        for i, r in enumerate(reasons):
            reason += r
            if i < len(reasons) - 1:
                reason += ' '

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Bans')

        header_rows = 5
        banlist: list[str | None] = await sheet.col_values(1)
        banlist = banlist[header_rows:]
        durations: list[str | None] = await sheet.col_values(2)
        durations = durations[header_rows:]

        perma_ban_index: int = durations.index('Permanent') + 1
        temp_bans: list[str | None] = []
        perma_bans: list[str | None] = []
        ex_bans: list[str | None] = []
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
        for player in [temp_ban for temp_ban in temp_bans if temp_ban]:
            if name.upper() == player.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the banlist.')
        for player in [perm_ban for perm_ban in perma_bans if perm_ban]:
            if name.upper() == player.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the banlist.')
        row: int = header_rows + len(temp_bans) + 1
        count = 1
        for player in [ex_ban for ex_ban in ex_bans if ex_ban]:
            if name.upper() == player.upper():
                count += 1
        timestamp: str = datetime.now(UTC).strftime("%b %#d, %Y")
        end_time: str = (datetime.now(UTC) + timedelta(days=14)).strftime("%b %#d, %Y")
        username: str = ctx.author.display_name
        username = re.sub(r'[^A-z0-9 -]', '', username).replace('`', '').strip()
        values: list[str] = [name, '2 weeks', timestamp, end_time, reason, username, 'Pending', '', screenshot]

        await sheet.insert_row(values, row)

        await ctx.send(f'**{name}** has been added to the banlist ({str(count)}).')
        admin_channel: discord.TextChannel = get_text_channel(self.bot, self.bot.config['adminChannel'])
        self.bot.queue_message(QueueMessage(admin_channel, f'**{name}** has been added to the banlist with status **Pending**.'))

    @commands.command(hidden=True)
    @is_rank()
    async def helper(self, ctx: commands.Context, *name_parts) -> None:
        '''
        Adds a helper, or notes activity for an existing helper (Rank+) (Portables only).
        Arguments: name
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name: str = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Helpers')

        smileys_sheet: AsyncioGspreadWorksheet = await ss.worksheet('Smileys')

        smileys: list[str | None] = await smileys_sheet.col_values(1)
        smileys = smileys[4:]
        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                smileys = smileys[:i]
                break
        
        if any(smiley.lower().strip() == name.lower() for smiley in smileys if smiley):
            raise commands.CommandError(message=f'Error: `{name}` is on the Smileys list. Please note their activity instead using the `smileyactivity` command.')

        header_rows = 3
        helpers: list[str | None] = await sheet.col_values(1)
        helpers = helpers[header_rows:]
        for i, helper in enumerate(helpers):
            if not helper:
                helpers = helpers[:i]
                break

        timestamp: str = datetime.now(UTC).strftime("%b %#d, %Y")
        username: str = ctx.author.display_name
        username = re.sub(r'[^A-z0-9 -]', '', username).replace('`', '').strip()

        on_list = False
        row = 0
        pattern: re.Pattern[str] = re.compile(r'[\W_]+')
        for i, helper in enumerate(helpers):
            if not helper:
                continue
            if pattern.sub('', name.upper()) == pattern.sub('', helper.upper()):
                name = helper
                row: int = i + header_rows + 1
                on_list = True
                break
        if not on_list:
            row = header_rows + len(helpers) + 1
            values: list[str] = [name, 'Helper', timestamp, username]
            await sheet.insert_row(values, row)
            await ctx.send(f'**{name}** has been added to the helper sheet.')
            return
        else:
            activity: list[str | None] = await sheet.row_values(row)
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
            time_col: int = 3 + len(activity) * 2
            credit_col: int = time_col + 1
            await sheet.update_cell(row, time_col, timestamp)
            await sheet.update_cell(row, credit_col, username)
            await ctx.send(f'**{name}** has been noted as active for **{timestamp}**.')

    @commands.command(hidden=True)
    @is_rank()
    async def smileyactivity(self, ctx: commands.Context, *name_parts) -> None:
        '''
        Notes activity for a smiley on sheets (Rank+) (Portables only).
        Arguments: name
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name: str = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Smileys')

        header_rows = 4
        smileys: list[str | None] = await sheet.col_values(1)
        smileys = smileys[header_rows:]
        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                smileys = smileys[:i]
                break
        timestamp: str = datetime.now(UTC).strftime("%b %#d, %Y")
        username: str = ctx.author.display_name
        username = re.sub(r'[^A-z0-9 -]', '', username).replace('`', '').strip()

        row = 0
        for i, smiley in enumerate(smileys):
            if not smiley:
                continue
            if name.upper() == smiley.upper():
                row = i + header_rows + 1
                name = smiley
                break
        if not row:
            for i, smiley in enumerate(smileys):
                if not smiley:
                    continue
                if name.upper() in smiley.upper():
                    row = i + header_rows + 1
                    name = smiley
                    break
        if not row:
            raise commands.CommandError(message=f'Could not find smiley: `{name}`.')

        activity: list[str | None] = await sheet.row_values(row)
        status: str | None = activity[1]
        activity = activity[4:12]
        if status and 'alt' in status:
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
        time_col: int = 5 + len(activity) * 2
        credit_col: int = time_col + 1
        await sheet.update_cell(row, time_col, timestamp)
        await sheet.update_cell(row, credit_col, username)
        await ctx.send(f'**{name}** has been noted as active for **{timestamp}**.')

    @commands.command(hidden=True)
    @portables_admin()
    async def addsmiley(self, ctx: commands.Context, *name_parts) -> None:
        '''
        Adds a smiley to the sheets (Admin+) (Portables only).
        Arguments: name.
        Constraints: name must be a valid RSN.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        leader_role: discord.Role | None = discord.utils.get((ctx.guild.roles if ctx.guild else []), id=self.bot.config['leaderRole'])

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name: str = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Smileys')

        header_rows = 4
        smileys: list[str | None] = await sheet.col_values(1)
        smileys = smileys[header_rows:]

        current_smileys: list[str | None] = []
        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                current_smileys = smileys[:i]
                break
        for smiley in [current_smiley for current_smiley in current_smileys if current_smiley]:
            if name.upper() == smiley.upper():
                raise commands.CommandError(message=f'Error: `{name}` is already on the smiley list.')
        row = 0
        for i, smiley in enumerate(smileys):
            if not smiley:
                continue
            if name.upper() == smiley.upper():
                row: int = i + header_rows + 1
                break
        if row:
            await sheet.delete_rows(row)
        row = header_rows + len(current_smileys) + 1
        timestamp: str = datetime.now(UTC).strftime("%b %#d, %Y")
        end_time: str = (datetime.now(UTC) + timedelta(days=30)).strftime("%b %#d, %Y")
        values: list[str] = [name, 'No', 'Applied', '', '', '', '', '', '', '', '', '', '', 'Pending', timestamp, end_time]
        await sheet.insert_row(values, row)
        await ctx.send(f'**{name}** has been added to the smileys sheet.')
        if isinstance(ctx.author, discord.Member) and ctx.author.top_role <= leader_role:
            admin_channel: discord.TextChannel = get_text_channel(self.bot, self.bot.config['adminChannel'])
            self.bot.queue_message(QueueMessage(admin_channel, f'**{name}** has been added to the smileys sheet with status **Pending**.'))

    @commands.command(hidden=True)
    @portables_leader()
    async def activatesmiley(self, ctx: commands.Context, *name_parts) -> None:
        '''
        Sets smiley status to active (Leader+) (Portables only).
        Arguments: name.
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name: str = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Smileys')

        header_rows = 4
        smileys: list[str | None] = await sheet.col_values(1)
        smileys = smileys[header_rows:]

        for i, smiley in enumerate(smileys):
            if smiley is None or not smiley:
                smileys = smileys[:i]
                break
        row = 0
        for i, smiley in enumerate(smileys):
            if not smiley:
                continue
            if name.upper() == smiley.upper():
                row: int = i + header_rows + 1
                name = smiley
                break
        if not row:
            for i, smiley in enumerate(smileys):
                if not smiley:
                    continue
                if name.upper() in smiley.upper():
                    row = i + header_rows + 1
                    name = smiley
                    break
        if not row:
            raise commands.CommandError(message=f'Could not find smiley: `{name}`.')
        col = 14
        status: str | None = (await sheet.cell(row, col)).value
        if status == 'Active':
            raise commands.CommandError(message=f'Error: `{name}`\'s status was already set to active.')
        await sheet.update_cell(row, col, 'Active')

        await ctx.send(f'**{name}**\'s status has been set to active.')

    @commands.command(aliases=['a'], ignore_extra=True)
    @portables_only()
    async def add(self, ctx: commands.Context) -> None:
        """
        Add portable locations (Portables only).
        Arguments: portable, worlds, location, worlds, location, etc...
        Constraints: This command can only be used in the locations channel. Only approved locations, and worlds are allowed. Additionally, worlds must be a valid world. No more than 3 portables per location.
        """
        self.bot.increment_command_counter()

        if not isinstance(ctx.channel, GuildChannel):
            raise commands.CommandError(message=f'This command can only be used in a server.')

        await ctx.channel.typing() # send 'typing...' status

        portables: discord.Guild | None = self.bot.get_guild(self.bot.config['portablesServer'])
        member: discord.Member | None = await portables.fetch_member(ctx.author.id) if portables else None

        admin_commands_channel: discord.TextChannel | None = find_text_channel(self.bot, self.bot.config['adminCommandsChannel'])
        if (admin_commands_channel and ctx.guild == self.bot.get_guild(self.bot.config['portablesServer']) and
            ctx.channel != admin_commands_channel and not ctx.channel.id in self.portables_channel_ids):
            raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {self.portables_channel_mention_string}.')

        # get the input corresponding to this message
        input: str = ctx.message.content.upper()
        if ctx.prefix:
            input = input.replace(ctx.prefix.upper(), '', 1)
        if ctx.invoked_with:
            input = input.replace(ctx.invoked_with.upper(), '', 1)
        input = input.strip()
        if not input: # if there was no input, return
            raise commands.CommandError(message=f'Required argument missing: `location`.')

        # get the portable type corresponding to the input
        portable, col = self.get_port_type(input, ctx.channel)
        if col == -1: # if no portable type was given, return
            raise commands.CommandError(message=f'Required argument missing: `portable`.')

        # replace some portable types due to incompatibilities with location abbreviations
        input = input.replace('RANGE', '')
        input = input.replace('WORKBENCH', '')
        new_ports: list[tuple[list[int], str]] = get_ports(input) # get the set of portable locations corresponding to the input

        if not new_ports: # if there were no locations, return
            raise commands.CommandError(message=f'Invalid argument: `location`.')

        ports_row: list[str | None] = await self.get_port_row() # get the current portable locations from the sheet

        val: str | None = ports_row[col-1] # get the string corresponding to our portable type
        ports: list[list[tuple[list[int], str]]] = []
        for p in ports_row: # for each portable, get the set of portable locations
            ports.append(get_ports(p) if p else [])

        error: str = check_ports(new_ports, ports) # check for errors in the set of portables
        if error: # if there was an error, send the error message and return
            raise commands.CommandError(message=error)

        new_ports_text: str = format(new_ports).replace('*', '\\*') # string representing portables to be added
        current_ports: list[tuple[list[int], str]] = get_ports(val) if val else [] # current portables on sheets
        sum_ports: list[tuple[list[int], str]] = add_ports(current_ports, new_ports) # set of portables after adding given portables
        new_val: str = format(sum_ports) # string representing the new set of portable locations

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

        timestamp: str = datetime.now(UTC).strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        name: str = '' # initialize empty name of user
        is_helper = False # boolean value representing whether or not the user is a rank
        helper_role: discord.Role | None = discord.utils.get(portables.roles, id=self.bot.config['helperRole']) if portables else None
        if member and helper_role in member.roles: # if the rank role is in the set of roles corresponding to the user
            is_helper = True # then set isRank to true
            name = get_rsn(member) # and get the name of the user

        await self.update_sheet(col, new_val, timestamp, name, is_helper) # update the sheet

        # send confirmation message
        if multiple:
            await ctx.send(f'The **{portable}** locations **{new_ports_text}** have been added.')
        else:
            await ctx.send(f'The **{portable}** location **{new_ports_text}** has been added.')

    @commands.command(aliases=['rem'], ignore_extra=True)
    @portables_only()
    async def remove(self, ctx: commands.Context) -> None:
        """
        Remove portable locations (Portables only).
        Arguments: portable, worlds, location, worlds, location, etc...
        Constraints: This command can only be used in the locations channel. Only approved locations, and worlds are allowed. Additionally, worlds must be a valid world. No more than 3 portables per location.
        """
        self.bot.increment_command_counter() # increment global commands counter

        if not isinstance(ctx.channel, GuildChannel):
            raise commands.CommandError(message=f'This command can only be used in a server.')
        
        await ctx.channel.typing() # send 'typing...' status

        portables: discord.Guild | None = self.bot.get_guild(self.bot.config['portablesServer'])
        member: discord.Member | None = await portables.fetch_member(ctx.author.id) if portables else None

        admin_commands_channel: discord.TextChannel | None = find_text_channel(self.bot, self.bot.config['adminCommandsChannel'])
        if (admin_commands_channel and ctx.guild == self.bot.get_guild(self.bot.config['portablesServer']) and
            ctx.channel != admin_commands_channel and not ctx.channel.id in self.portables_channel_ids):
            raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {self.portables_channel_mention_string}.')

        # get the input corresponding to this message
        input: str = ctx.message.content.upper()
        if ctx.prefix:
            input = input.replace(ctx.prefix.upper(), '', 1)
        if ctx.invoked_with:
            input = input.replace(ctx.invoked_with.upper(), '', 1)
        input = input.strip()
        if not input: # if there was no input, return
            raise commands.CommandError(message=f'Required argument missing: `location`.')

        # get the portable type corresponding to the input
        portable, col = self.get_port_type(input, ctx.channel)
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
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Home')
        val: str | None = (await sheet.cell(21, col)).value

        old_ports_text: str = format(old_ports).replace('*', '\\*') # string representing portables to be removed
        current_ports: list[tuple[list[int], str]] = get_ports(val) if val else [] # current portables on sheets
        dif_ports: list[tuple[list[int], str]] = remove_ports(current_ports, old_ports) # set of portables after removing given portables
        new_val: str = format(dif_ports) # string representing the new set of portable locations

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

        timestamp: str = datetime.now(UTC).strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        name: str = '' # initialize empty name of user
        is_helper = False # boolean value representing whether or not the user is a rank
        helper_role: discord.Role | None = discord.utils.get(portables.roles, id=self.bot.config['helperRole']) if portables else None
        if member and helper_role in member.roles: # if the rank role is in the set of roles corresponding to the user
            is_helper = True # then set isRank to true
            name = get_rsn(member) # and get the name of the user

        await self.update_sheet(col, new_val, timestamp, name, is_helper) # update the sheet

        # send confirmation message
        if multiple:
            await ctx.send(f'The **{portable}** locations **{old_ports_text}** have been removed.')
        else:
            await ctx.send(f'The **{portable}** location **{old_ports_text}** has been removed.')

    @commands.command(aliases=['rall'], ignore_extra=True)
    @is_helper()
    async def removeall(self, ctx: commands.Context, *input) -> None:
        '''
        Removes all instances of a given location, or all locations of a given portable. (Helper+) (Portables only)
        Arguments: [portable] / [worlds][locations]
        Constraints: If calling the command with a portable, you can only do one portable at a time.
        Example: `-removeall range` / `-removeall 84 ca`
        '''
        self.bot.increment_command_counter() # increment global commands counter
        await ctx.channel.typing() # send 'typing...' status

        portables: discord.Guild | None = self.bot.get_guild(self.bot.config['portablesServer'])
        member: discord.Member | None = await portables.fetch_member(ctx.author.id) if portables else None

        admin_commands_channel: discord.TextChannel | None = find_text_channel(self.bot, self.bot.config['adminCommandsChannel'])
        if (admin_commands_channel and ctx.guild == self.bot.get_guild(self.bot.config['portablesServer']) and
            ctx.channel != admin_commands_channel and not ctx.channel.id in self.portables_channel_ids):
            raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {self.portables_channel_mention_string}.')

        input_str: str | None = ' '.join(input).upper().strip() if input else None
        if not input_str:
            raise commands.CommandError(message=f'Required argument missing: `portable/location`.')

        to_remove: list[tuple[list[int], str]] = get_ports(input_str)
        if format(to_remove) == 'N/A':
            to_remove = []
        index: int = 0
        port: str = ''
        if not to_remove:
            index = 0
            for i, aliases in enumerate(portable_aliases):
                if input_str.lower() in aliases:
                    port = aliases[0]
                    index = i
                    break
            if not port:
                if ctx.channel.id in self.portables_channel_ids:
                    port = portables_names[self.portables_channel_ids.index(ctx.channel.id)].lower()
            if not port:
                raise commands.CommandError(message=f'Invalid argument: `{input_str}`.')

        current_values: list[str | None] = await self.get_port_row()
        current: list[list[tuple[list[int], str]]] = [get_ports(i) if i else [] for i in current_values]

        if to_remove:
            new_values: list[str] = [format(remove_ports(cur, to_remove)) for cur in current]
        else:
            new_values = [format(cur) for cur in current]
            new_values[index] = 'N/A'

        # if no change, raise an error
        if new_values == current_values:
            if to_remove:
                raise commands.CommandError(message=f'Location(s) `{format(to_remove)}` were not found on the sheet.')
            else:
                raise commands.CommandError(message=f'Portable `{port}` had no locations listed.')

        timestamp: str = datetime.now(UTC).strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        name: str = '' # initialize empty name of user
        is_rank = False # boolean value representing whether or not the user is a rank
        rank_role: discord.Role | None = discord.utils.get(portables.roles, id=self.bot.config['rankRole']) if portables else None
        if rank_role in (member.roles if member else []): # if the rank role is in the set of roles corresponding to the user
            is_rank = True # then set isRank to true
            name = get_rsn(member) if member else '' # and get the name of the user

        await self.update_sheet_row(new_values, timestamp, name, is_rank)

        if to_remove:
            await ctx.send(f'All instances of the location(s) `{format(to_remove)}` have been removed.')
        else:
            await ctx.send(f'All locations for the portable `{port}` have been removed.')


    @commands.command(ignore_extra=True)
    @is_helper()
    async def edit(self, ctx: commands.Context, portable: str = '', *input_locs) -> None:
        '''
        Edit portable locations (Helper+) (Portables only).
        Arguments: portable, worlds, location, worlds, location, etc...
        Alternatively, you can directly use -portable [arguments], e.g.: -fletch 100 ca
        Constraints: This command can only be used in the locations channel. Only approved locations and worlds are allowed. Additionally, worlds must be a valid world. No more than 3 portables per location.
        '''
        self.bot.increment_command_counter() # increment global commands counter
        await ctx.channel.typing() # send 'typing...' status

        portables: discord.Guild | None = self.bot.get_guild(self.bot.config['portablesServer'])
        member: discord.Member | None = await portables.fetch_member(ctx.author.id) if portables else None

        admin_commands_channel: discord.TextChannel | None = find_text_channel(self.bot, self.bot.config['adminCommandsChannel'])
        if (admin_commands_channel and ctx.guild == self.bot.get_guild(self.bot.config['portablesServer']) and
            ctx.channel != admin_commands_channel and not ctx.channel.id in self.portables_channel_ids):
            raise commands.CommandError(message=f'Error: `Incorrect channel`. Please use {self.portables_channel_mention_string}.')

        if not portable: # if there was no portable type in the input, return
            raise commands.CommandError(message=f'Required argument missing: `portable`.')

        col: int = 0
        for i, port_aliases in enumerate(portable_aliases):
            if portable in port_aliases:
                portable = port_aliases[0]
                col = i + 1
                break

        input: str = ''
        for loc in input_locs:
            input += loc + ' '
        input = input.upper().strip()

        name: str = '' # initialize empty name of user
        is_rank = False # boolean value representing whether or not the user is a rank
        rank_role = discord.utils.get(portables.roles, id=self.bot.config['rankRole']) if portables else None
        if rank_role in (member.roles if member else []): # if the rank role is in the set of roles corresponding to the user
            is_rank = True # then set isRank to true
            name = get_rsn(member) if member else '' # and get the name of the user

        timestamp: str = datetime.now(UTC).strftime("%#d %b, %#H:%M") # get timestamp string in format: day Month, hours:minutes

        if input.replace('/', '').replace(' ', '') in ['NA', 'NO', 'NONE', '0', 'ZERO']: # if input was 'N/A' or a variation, remove all locations and return
            await self.update_sheet(col, 'N/A', timestamp, name, is_rank)
            await ctx.send(f'The **{portable}** locations have been edited to: **N/A**.')
            return

        new_ports: list[tuple[list[int], str]] = get_ports(input) # calculate new set of portables from the input string
        if not new_ports: # if there were no portables, return
            raise commands.CommandError(message=f'Invalid argument: `location`.')

        ports_row: list[str | None] = await self.get_port_row() # get the row of portable locations from sheets
        old_val: str | None = ports_row[col-1]
        ports: list[list[tuple[list[int], str]]] = []
        for p in ports_row: # for each portable, get the set of portable locations
            ports.append(get_ports(p) if p else [])

        error: str = check_ports(new_ports, ports) # check for errors in the set of portables
        if error: # if there was an error, send the error message and return
            raise commands.CommandError(message=error)

        new_val: str = format(new_ports) # create a string corresponding
        new_ports_text: str = new_val.replace('*', '\\*') # in the text for the discord message, escape the stars for formatting issues

        # if no change, raise an error
        if new_val == old_val:
            raise commands.CommandError(message=f'The `{portable}` locations were already set to `{new_val}`.')

        await self.update_sheet(col, new_val, timestamp, name, is_rank) # update the sheet

        await ctx.send(f'The **{portable}** locations have been edited to: **{new_ports_text}**.') # send confirmation message

    @commands.command(aliases=['watch'], hidden=True)
    @is_rank()
    async def watchlist(self, ctx: commands.Context, name: str = "", *reasons) -> None:
        '''
        Adds a player to the watchlist (Rank+) (Portables only).
        Arguments: name, reason, screenshot (optional).
        Surround names containing spaces with quotation marks, e.g.: "name with spaces".
        Constraints: name must be a valid RSN.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name = re.sub(r'[^A-z0-9 -]', '', name).replace('`', '').strip()
        if len(name) > 12:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if re.match(r'^[A-z0-9 -]+$', name) is None:
            raise commands.CommandError(message=f'Invalid argument: `{name}`.')
        if not reasons:
            raise commands.CommandError(message=f'Required argument missing: `reason`.')
        screenshot: str = ''
        reasons = list(reasons)
        if validators.url(reasons[len(reasons)-1]):
            screenshot = reasons[len(reasons)-1]
            del reasons[len(reasons)-1]
        reason: str = " ".join(reasons)

        if not screenshot:
            if ctx.message.attachments:
                screenshot = ctx.message.attachments[0].url

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['sheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Watchlist')
        header_rows = 5

        watchlist: list[str | None] = await sheet.col_values(1)
        watchlist = watchlist[header_rows:]

        for i, player in enumerate(watchlist):
            if not player:
                watchlist = watchlist[:i]
                break
        timestamp: str = datetime.now(UTC).strftime("%b %#d, %Y")
        username: str = ctx.author.display_name
        username = re.sub(r'[^A-z0-9 -]', '', username).replace('`', '').strip()
        count = 1
        for player in [watched for watched in watchlist if watched]:
            if name.upper() == player.upper():
                count += 1
        row: int = header_rows + len(watchlist) + 1
        values: list[str] = [name, timestamp, reason, username, screenshot]

        await sheet.insert_row(values, row)

        await ctx.send(f'**{name}** has been added to the watchlist ({str(count)}).')

    @commands.command(aliases=['act', 'active'], hidden=True)
    @portables_admin()
    async def activity(self, ctx: commands.Context, *name_parts) -> None:
        '''
        Notes rank activity on admin sheets (Admin+) (Portables only).
        Arguments: name
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        user: discord.User | discord.Member = ctx.author
        username: str = user.display_name

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name: str = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if name.upper() in username.upper():
            raise commands.CommandError(message=f'Invalid argument: `{name}`. You cannot track your own activity.')

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['adminSheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Rank Reports')
        header_rows = 4

        month: str = datetime.now(UTC).strftime("%B")
        sheet_month_cell: gspread.Cell = await sheet.cell(3, 1)
        sheet_month: str | None = sheet_month_cell.value
        if sheet_month and month.upper().strip() != sheet_month.upper().strip():
            raise commands.CommandError(message=f'Error: `admin_sheet_month`. Please wait for a Leader to perform this month\'s rank changes.')
        ranks: list[str | None] = await sheet.col_values(1)
        ranks = ranks[header_rows:]
        for i, rank in enumerate(ranks):
            if rank is None or not rank:
                ranks = ranks[:i]
                break
        timestamp: str = datetime.now(UTC).strftime("%#d")
        row = 0
        for i, rank in enumerate(ranks):
            if not rank or rank in rank_titles:
                continue
            if name.upper() == rank.upper():
                row: int = i + header_rows + 1
                name = rank
                break
        if not row:
            for i, rank in enumerate(ranks):
                if not rank or rank in rank_titles:
                    continue
                if name.upper() in rank.upper():
                    row = i + header_rows + 1
                    name = rank
                    break
        if not row:
            raise commands.CommandError(message=f'Could not find rank: `{name}`.')
        activity: list[str | None] = await sheet.row_values(row)
        activity = activity[3:34]
        activity = list(filter(bool, activity))
        if timestamp in activity:
            raise commands.CommandError(message=f'`{name}` has already been noted active for today.')
        col: int = 4 + len(activity)
        await sheet.update_cell(row, col, timestamp)
        await ctx.send(f'**{name}** has been noted as active for **{timestamp}** **{datetime.now(UTC).strftime("%b")}**.')

    @commands.command(hidden=True)
    @portables_admin()
    async def sheetactivity(self, ctx: commands.Context, *name_parts) -> None:
        '''
        Notes rank sheet activity on admin sheets (Admin+) (Portables only).
        Arguments: name
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        user: discord.User | discord.Member = ctx.author
        username: str = user.display_name

        if not name_parts:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        name: str = ''
        for part in name_parts:
            name += part + ' '
        name = name.strip()
        if not name:
            raise commands.CommandError(message=f'Required argument missing: `name`.')
        if name.upper() in username.upper():
            raise commands.CommandError(message=f'Invalid argument: `{name}`. You cannot track your own activity.')

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open(self.bot.config['adminSheetName'])
        sheet: AsyncioGspreadWorksheet = await ss.worksheet('Rank Reports')
        header_rows = 4

        month: str = datetime.now(UTC).strftime("%B")
        sheet_month_cell: gspread.Cell = await sheet.cell(3, 1)
        sheet_month: str | None = sheet_month_cell.value
        if month != sheet_month:
            raise commands.CommandError(message=f'Error: `admin_sheet_month`. Please wait for a Leader to perform this month\'s rank changes.')
        ranks: list[str | None] = await sheet.col_values(1)
        ranks = ranks[header_rows:]
        for i, rank in enumerate(ranks):
            if rank is None or not rank:
                ranks = ranks[:i]
                break
        timestamp: str = datetime.now(UTC).strftime("%#d")
        row = 0
        for i, rank in enumerate(ranks):
            if not rank or rank in rank_titles:
                continue
            if name.upper() == rank.upper():
                row: int = i + header_rows + 1
                name = rank
                break
        if not row:
            for i, rank in enumerate(ranks):
                if not rank or rank in rank_titles:
                    continue
                if name.upper() in rank.upper():
                    row = i + header_rows + 1
                    name = rank
                    break
        if not row:
            raise commands.CommandError(message=f'Could not find rank: `{name}`.')

        activity: list[str | None] = await sheet.row_values(row)
        sheet_activity = activity[34:65]
        activity = activity[3:34]

        sheet_activity = list(filter(bool, sheet_activity))
        activity = list(filter(bool, activity))
        if timestamp in sheet_activity:
            raise commands.CommandError(message=f'`{name}` has already been noted active for today.')
        sheet_col: int = 35 + len(sheet_activity)
        await sheet.update_cell(row, sheet_col, timestamp)
        await ctx.send(f'**{name}** has been noted as active on sheets for **{timestamp}** **{datetime.now(UTC).strftime("%b")}**.')

async def setup(bot: Bot) -> None:
    await bot.add_cog(Portables(bot))