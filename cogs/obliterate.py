import io
from typing import Any
from aiohttp import ClientResponse
import discord
from discord import Member, TextChannel, app_commands, TextStyle
from discord.ext import commands, tasks
from discord.ext.commands import Cog
from gspread_asyncio import AsyncioGspreadClient, AsyncioGspreadSpreadsheet, AsyncioGspreadWorksheet
from message_queue import QueueMessage
from src.bot import Bot
from src.database import Guild
from datetime import datetime, timedelta, UTC
import re
import gspread
import traceback
from src.database_utils import find_db_guild
from src.discord_utils import find_guild_text_channel, get_guild_text_channel, get_text_channel
from src.number_utils import is_int
from src.checks import obliterate_only, obliterate_mods
from src.configuration import config

ranks: list[str] = ['Bronze', 'Iron', 'Steel', 'Mithril', 'Adamant', 'Rune']

reqs: dict[str, dict[str, int]] = {
    'Bronze': { 'number': 2, 'events': 5, 'top3': 2, 'appointments': 5, 'appreciations': 2, 'discord': 2, 'months': 1 },
    'Iron': { 'number': 2, 'events': 15, 'top3': 3, 'appointments': 15, 'appreciations': 4, 'discord': 3, 'months': 2 },
    'Steel': { 'number': 3, 'events': 20, 'top3': 4, 'appointments': 25, 'appreciations': 6, 'discord': 5, 'months': 3 },
    'Mithril': { 'number': 3, 'events': 30, 'top3': 5, 'appointments': 30, 'appreciations': 8, 'discord': 8, 'months': 6 },
    'Adamant': { 'number': 4, 'events': 40, 'top3': 6, 'appointments': 40, 'appreciations': 10, 'discord': 10, 'months': 9 }
}

async def update_row(sheet: AsyncioGspreadWorksheet, row_num: int, new_row: list[str | None] | list[str]) -> None:
    cell_list: list[gspread.Cell] = [gspread.Cell(row_num, i+1, value=val) for i, val in enumerate(new_row)]
    await sheet.update_cells(cell_list, nowait=True) # type: ignore - extra arg nowait is supported via an odd decorator

class AppreciationModal(discord.ui.Modal, title='Appreciation'):
    def __init__(self, bot: Bot, member_to_appreciate: discord.Member) -> None:
        super().__init__()
        self.bot: Bot = bot
        self.member_to_appreciate: discord.Member = member_to_appreciate

    message = discord.ui.TextInput(label='Message', min_length=1, max_length=1000, required=True, style=TextStyle.long)
    anonymous = discord.ui.TextInput(label='Should this post be anonymous?', min_length=1, max_length=3, required=True, placeholder='Yes / No', style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not 'Y' in self.anonymous.value.upper() and not 'N' in self.anonymous.value.upper():
            await interaction.response.send_message(f'Error: invalid value for anonymous: `{self.anonymous.value}`', ephemeral=True)
            return
        anonymous: bool = 'Y' in self.anonymous.value.upper()

        if anonymous and not interaction.channel:
            await interaction.response.send_message(f'Error: anonymous appreciation messages can only be sent in a server channel.', ephemeral=True)
            return

        # Create an embed to send to the appreciation station channel
        embed = discord.Embed(title=f'Appreciation message', description=self.message.value, colour=0x00e400)
        if anonymous:
            with open('images/default_avatar.png', 'rb') as f:
                default_avatar = io.BytesIO(f.read())
            default_avatar = discord.File(default_avatar, filename='default_avatar.png')
            embed.set_author(name='Anonymous', icon_url='attachment://default_avatar.png')
        else:
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        # Update appreciation sheet on roster
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['obliterate_roster_key'])
        appreciations: AsyncioGspreadWorksheet = await ss.worksheet('Appreciation')

        members_col: list[str | None] = await appreciations.col_values(1)
        rows: int = len(members_col)

        date_str: str = datetime.now(UTC).strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row: list[str | None] = [interaction.user.display_name, self.member_to_appreciate.display_name, date_str, self.message.value]

        # Update appreciation column on roster
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')
        appreciation_col = 9

        raw_members: list[list[str]] = await roster.get_all_values()
        raw_members = raw_members[1:]
        members: list[list[str]] = []
        # Ensure expected row length
        for member in raw_members:
            while len(member) < appreciation_col + 1:
                member.append('')
            if len(member) > appreciation_col + 1:
                member = member[:appreciation_col+1]
            members.append(member)

        # Find member row
        member_row: list[str] = []
        member_index: int = 0
        for i, member in enumerate(members):
            if member[4].strip() == f'{self.member_to_appreciate.name}#{self.member_to_appreciate.discriminator}':
                member_row, member_index = member, i
                break
        if not member_row:
            await interaction.response.send_message(f'Could not find member on roster: `{self.member_to_appreciate.name}#{self.member_to_appreciate.discriminator}`')
            return

        if not is_int(member_row[appreciation_col]):
            member_row[appreciation_col] = '0'
        member_row[appreciation_col] = str(int(member_row[appreciation_col]) + 1)

        # Send an embed to the appreciation station channel
        if anonymous:
            await interaction.channel.send(self.member_to_appreciate.mention, embed=embed, file=default_avatar) # type: ignore - interaction.channel is checked earlier for anonymous appreciations
            await interaction.response.send_message(f'Your appreciation message for {self.member_to_appreciate.mention} has been sent!', ephemeral=True)
        else:
            await interaction.response.send_message(self.member_to_appreciate.mention, embed=embed)

        await update_row(appreciations, rows+1, new_row)
        await update_row(roster, member_index+2, member_row) # +2 for header row and 1-indexing

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class NameChangeModal(discord.ui.Modal, title='Name change'):
    def __init__(self, bot: Bot, member_to_rename: discord.Member) -> None:
        self.new_name.placeholder = member_to_rename.display_name
        super().__init__()
        self.bot: Bot = bot
        self.member_to_rename: discord.Member = member_to_rename

    new_name = discord.ui.TextInput(label='New name', min_length=1, max_length=12, required=True, style=TextStyle.short, placeholder='New name')

    async def on_submit(self, interaction: discord.Interaction) -> None:
        new_name: str = self.new_name.value.strip()

        if not interaction.guild:
            await interaction.response.send_message(f'Error: could not find guild.', ephemeral=True)
            return

        if not new_name or re.match(r'^[A-z0-9 -]+$', new_name) is None or len(new_name) > 12:
            await interaction.response.send_message(f'Error: invalid RSN: `{new_name}`', ephemeral=True)
            return
        if new_name == self.member_to_rename.display_name:
            await interaction.response.send_message(f'Error: new name cannot be the same as the previous name: `{new_name}`', ephemeral=True)
            return

        # Create an embed to send to the name change channel
        embed = discord.Embed(title=f'Name change', colour=0x00e400)
        embed.add_field(name='Previous name', value=self.member_to_rename.display_name, inline=False)
        embed.add_field(name='New name', value=new_name, inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {self.member_to_rename.id}')

        # Update name on roster
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['obliterate_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')
        name_col: int = 0
        notes_col: int = 5

        raw_members: list[list[str]] = await roster.get_all_values()
        raw_members = raw_members[1:]
        members: list[list[str]] = []
        # Ensure expected row length
        for member in raw_members:
            while len(member) < notes_col + 1:
                member.append('')
            if len(member) > notes_col + 1:
                member = member[:notes_col+1]
            members.append(member)

        # Find member row
        member_row: list[str] = []
        member_index: int = 0
        for i, member in enumerate(members):
            if member[4].strip() == f'{self.member_to_rename.name}#{self.member_to_rename.discriminator}':
                member_row, member_index = member, i
                break
        if not member_row:
            await interaction.response.send_message(f'Could not find member on roster: `{self.member_to_rename.name}#{self.member_to_rename.discriminator}`')
            return

        member_row[notes_col] = (member_row[notes_col].strip() + ('.' if member_row[notes_col].strip() and not member_row[notes_col].strip().endswith('.') else '') + f' Formerly known as {member_row[name_col]}.').strip()
        member_row[name_col] = new_name

        await update_row(roster, member_index+2, member_row) # +2 for header row and 1-indexing

        renamed = False
        try:
            await self.member_to_rename.edit(nick=new_name)
            renamed = True
        except discord.Forbidden:
            pass

        # Send an embed to the name change channel
        channel: discord.TextChannel = get_guild_text_channel(interaction.guild, self.bot.config['obliterate_promotions_channel_id'])
        self.bot.queue_message(QueueMessage(channel, None, embed))
        await interaction.response.send_message(f'Member renamed from `{self.member_to_rename.display_name}` to `{new_name}`.'
            + f'\nInsufficient permissions to change nickname for user: {self.member_to_rename.mention}.' if not renamed else '', ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class ApplicationView(discord.ui.View):
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot
        self.value: bool | None = None

    def is_obliterate_recruiter(self, interaction: discord.Interaction) -> bool:
        '''
        Returns true iff the interaction user is an obliterate recruiter, moderator, or key.
        '''
        if interaction.user.id == self.bot.config['owner']:
            return True
        if interaction.guild and interaction.guild.id == self.bot.config['obliterate_guild_id']:
            recruiter_role: discord.Role | None = interaction.guild.get_role(self.bot.config['obliterate_recruiter_role_id'])
            mod_role: discord.Role | None = interaction.guild.get_role(self.bot.config['obliterate_moderator_role_id'])
            key_role: discord.Role | None = interaction.guild.get_role(self.bot.config['obliterate_key_role_id'])
            if isinstance(interaction.user, discord.Member) and (recruiter_role in interaction.user.roles or mod_role in interaction.user.roles or key_role in interaction.user.roles):
                return True
        return False
    
    @discord.ui.button(label='Decline', style=discord.ButtonStyle.danger, custom_id='obliterate_app_decline_button')
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not self.is_obliterate_recruiter(interaction):
            await interaction.response.send_message('Missing permissions: `Obliterate moderator`', ephemeral=True)
            return
        if not interaction.message:
            await interaction.response.send_message('Could not find interaction message.', ephemeral=True)
            return
        # Update message
        embed: discord.Embed = interaction.message.embeds[0]
        embed.set_footer(text=f'Declined by {interaction.user.display_name}', icon_url='https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/160/twitter/322/cross-mark_274c.png')
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message('Application declined successfully.', ephemeral=True)
        self.value = False

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.success, custom_id='obliterate_app_accept_button')
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not self.is_obliterate_recruiter(interaction):
            await interaction.response.send_message('Missing permissions: `Obliterate moderator`', ephemeral=True)
            return
        if not interaction.message:
            await interaction.response.send_message('Could not find interaction message.', ephemeral=True)
            return
        # Handle accept
        status: str = await self.accept_handler(interaction)
        if status != 'success':
            await interaction.response.send_message(status, ephemeral=True)
            return
        # Update message
        embed: discord.Embed = interaction.message.embeds[0]
        embed.set_footer(text=f'Accepted by {interaction.user.display_name}', icon_url='https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/160/twitter/322/check-mark-button_2705.png')
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message('Application accepted successfully.', ephemeral=True)
        self.value = True

    async def accept_handler(self, interaction: discord.Interaction) -> str:
        '''
        Parses data from an accepted application to perform the following actions:
        - Add the new member to the roster
        - Set their discord display name to their RSN
        - Promote them in discord
        - Add them to WOM
        '''
        print('Running accept handler')

        if not interaction.guild or not interaction.message or not interaction.message.embeds[0].footer.text:
            return 'Could not find interaction message.'

        user_id = int(interaction.message.embeds[0].footer.text.replace('User ID: ', ''))
        member: discord.Member = await interaction.guild.fetch_member(user_id)

        applicant_role: discord.Role | None = member.guild.get_role(self.bot.config['obliterate_applicant_role_id'])
        bronze_role: discord.Role | None = member.guild.get_role(self.bot.config['obliterate_bronze_role_id'])

        if (not applicant_role in member.roles) or (bronze_role in member.roles) or not bronze_role:
            return f'Error: incorrect roles for applicant: `{member.display_name}`. Either they are not an applicant, or they are already bronze.'
        
        channel: discord.TextChannel | None = find_guild_text_channel(interaction.guild, self.bot.config['obliterate_promotions_channel_id'])
        if not channel:
            return 'Promotions channel not found.'
        
        # Parse message
        rsn: str | None = interaction.message.embeds[0].fields[0].value
        ironman: str | None = interaction.message.embeds[0].fields[2].value
        if not ironman or not ironman.upper() in ['NO', 'YES', 'IRONMAN', 'HCIM', 'UIM', 'GIM']:
            return f'Error invalid value for ironman: `{ironman}`'
        else:
            for i, opt in enumerate(['NO', 'YES', 'IRONMAN', 'HCIM', 'UIM', 'GIM']):
                if ironman.upper() == opt and i < 3:
                    if opt == 'YES':
                        opt = 'IRONMAN'
                    ironman = opt.capitalize()
                    break
                elif ironman.upper() == opt:
                    ironman = opt
                    break

        # Update roster
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['obliterate_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

        members_col: list[str | None] = await roster.col_values(1)
        rows: int = len(members_col)

        date_str: str = datetime.now(UTC).strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row: list[str | None] = [rsn, 'Bronze', ironman, 'Yes', f'{member.name}#{member.discriminator}', '', date_str]
        cell_list: list[gspread.Cell] = [gspread.Cell(rows+1, i+1, value=val) for i, val in enumerate(new_row)]
        print(f'writing values:\n{new_row}\nto row {rows+1}')
        await roster.update_cells(cell_list, nowait=True) # type: ignore - nowait is enabled through an odd decorator

        # Update member nickname and roles
        roles = member.roles
        roles.remove(applicant_role)
        roles.append(bronze_role)
        await member.edit(nick=rsn, roles=roles)

        # Add to WOM
        url: str = f'https://api.wiseoldman.net/v2/groups/{self.bot.config["obliterate_wom_group_id"]}/members'
        payload: dict[str, Any] = {'verificationCode': self.bot.config['obliterate_wom_verification_code']}
        payload['members'] = [{'username': rsn, 'role': 'member'}]
        async with self.bot.aiohttp.post(url, json=payload, headers={'x-user-agent': self.bot.config['wom_user_agent'], 'x-api-key': self.bot.config['wom_api_key']}) as r:
            if r.status != 200:
                data: Any = await r.json()
                return f'Error adding to WOM: {r.status}\n{data}'
            data = await r.json()

        # Send message in promotions channel
        await channel.send(f'`{rsn}`\'s application was accepted by {interaction.user.mention}. Please invite them to the CC in-game and react to this message once done.')
        
        return 'success'
    
    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class PersonalInfoModal(discord.ui.Modal):
    def __init__(self, bot: Bot, data: dict[str, Any]) -> None:
        self.bot: Bot = bot
        self.data: dict[str, Any] = data
        try:
            super().__init__(title='Personal information')
        except Exception as e:
            print(e)

    motivation = discord.ui.TextInput(label='Why do you want to join our clan?', max_length=200, required=True, style=TextStyle.paragraph)
    play_time = discord.ui.TextInput(label='When are you most active?', placeholder='Morning / Afternoon / Evening / Night', max_length=200, required=True, style=TextStyle.paragraph)
    referral = discord.ui.TextInput(label='Where did you hear about our clan?', max_length=200, required=True, style=TextStyle.paragraph)
    voice_chat = discord.ui.TextInput(label='Would you join voice chat during events?', placeholder='Yes / No', max_length=200, required=True, style=TextStyle.paragraph)
    fav_activity = discord.ui.TextInput(label='Favourite in-game activity', max_length=200, required=True, style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.value: dict[str, Any] = self.data
        self.value['Why do you want to join our clan?'] = self.motivation.value
        self.value['When are you most active?'] = self.play_time.value
        self.value['Where did you hear about our clan?'] = self.referral.value
        self.value['Would you join voice chat during events?'] = self.voice_chat.value
        self.value['Favourite in-game activity'] = self.fav_activity.value
        # Create embed with all data combined
        embed = discord.Embed(title=f'**Obliterate application**', colour=0x00b2ff)
        print(f'Data: {self.data}')
        print(f"rsn: {self.data['RuneScape username']}")
        try:
            embed.add_field(name='RuneScape username', value=self.data['RuneScape username'], inline=False)
        except Exception as e:
            print(e)
        embed.add_field(name='Total level', value=self.data['Total level'], inline=False)
        embed.add_field(name='Are you an ironman?', value=self.data['Are you an ironman?'], inline=False)
        embed.add_field(name='What is your timezone?', value=self.data['What is your timezone?'], inline=False)
        embed.add_field(name='How long have you played OSRS?', value=self.data['How long have you played OSRS?'], inline=False)
        embed.add_field(name='Why do you want to join our clan?', value=self.motivation.value, inline=False)
        embed.add_field(name='When are you most active?', value=self.play_time.value, inline=False)
        embed.add_field(name='Where did you hear about our clan?', value=self.referral.value, inline=False)
        embed.add_field(name='Would you join voice chat during events?', value=self.voice_chat.value, inline=False)
        embed.add_field(name='Favourite in-game activity', value=self.fav_activity.value, inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')
        # Send final result
        view = ApplicationView(self.bot)
        await interaction.response.send_message(embed=embed, view=view)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class OpenPersonalInfoView(discord.ui.View):
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot
        self.value = None

    @discord.ui.button(label='Part 2', style=discord.ButtonStyle.primary, custom_id='obliterate_app_part2_button')
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Get data from first modal from message embed
        data: dict[str, str] = {}
        for field in [f for f in (interaction.message.embeds[0].fields if interaction.message else []) if f.name and f.value]:
            data[field.name] = field.value # type: ignore - try harder mr type checker
        # Open second form modal
        modal = PersonalInfoModal(self.bot, data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.value:
            self.value = True
        else:
            self.value = False

class AccountInfoModal(discord.ui.Modal, title='Account information'):
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    rsn = discord.ui.TextInput(label='RuneScape username', min_length=1, max_length=12, required=True, style=TextStyle.short)
    total = discord.ui.TextInput(label='Total level', min_length=2, max_length=4, required=True, style=TextStyle.short)
    ironman = discord.ui.TextInput(label='Are you an ironman?', placeholder='(No / Ironman / HCIM / UIM / GIM)', min_length=2, max_length=7, required=True, style=TextStyle.short)
    timezone = discord.ui.TextInput(label='What is your timezone?', min_length=1, max_length=20, required=True, style=TextStyle.short)
    experience = discord.ui.TextInput(label='How long have you played OSRS?', max_length=200, required=True, style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Validation
        if re.match(r'^[A-z0-9 -]+$', self.rsn.value) is None:
            await interaction.response.send_message(f'Error: invalid RSN: `{self.rsn.value}`', ephemeral=True)
            return
        if not self.ironman.value.upper() in ['NO', 'YES', 'IRONMAN', 'HCIM', 'UIM', 'GIM']:
            await interaction.response.send_message('Error: ironman value must be one of: `No, Yes, Ironman, HCIM, UIM, GIM`', ephemeral=True)
            return
        # Create embed to show data from first form
        description = 'This is part 1/2 of your application. Please click the button below to move on to the second part when you are ready.'
        embed = discord.Embed(title=f'**Account information**', colour=0x00b2ff, description=description)
        embed.add_field(name='RuneScape username', value=self.rsn.value, inline=False)
        embed.add_field(name='Total level', value=self.total.value, inline=False)
        embed.add_field(name='Are you an ironman?', value=self.ironman.value, inline=False)
        embed.add_field(name='What is your timezone?', value=self.timezone.value, inline=False)
        embed.add_field(name='How long have you played OSRS?', value=self.experience.value, inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        # Create button to open second form
        view = OpenPersonalInfoView(self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class Obliterate(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    def cog_unload(self) -> None:
        self.track_discord_levels.cancel()
    
    def cog_load(self) -> None:
        self.track_discord_levels.start()
        # Register persistent views
        self.bot.add_view(ApplicationView(self.bot))
        self.bot.add_view(OpenPersonalInfoView(self.bot))
    
    @tasks.loop(hours=24)
    async def track_discord_levels(self) -> None:
        '''
        Loop to track discord levels from Mee6 dashboard on clan roster
        '''
        try:
            print('Syncing obliterate discord levels...')
            obliterate_guild_id: int = self.bot.config['obliterate_guild_id']
            r: ClientResponse = await self.bot.aiohttp.get(f'https://mee6.xyz/api/plugins/levels/leaderboard/{obliterate_guild_id}')

            async with r:
                data: dict = await r.json(content_type='application/json')
                player_data: list[dict] = data['players']

                agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
                ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['obliterate_roster_key'])
                roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

                raw_members: list[list[str]] = await roster.get_all_values()
                raw_members = raw_members[1:]

                discord_col = 4 # 0-indexed
                discord_level_col = 11 # 0-indexed

                members: list[list[str]] = []
                # Ensure expected row length
                for member in raw_members:
                    if len(member) and member[0]:
                        while len(member) < discord_level_col + 1:
                            member.append('')
                        if len(member) > discord_level_col + 1:
                            member: list[str] = member[:discord_level_col+1]
                        members.append(member)

                for player in player_data:
                    player_discord: str = f'{player["username"]}#{player["discriminator"]}'
                    player_level: int = player['level']
                    for i, member in enumerate(members):
                        if member[discord_col].strip() == player_discord and str(member[discord_level_col]).strip() != str(player_level):
                            member[discord_level_col] = str(player_level)
                            await update_row(roster, i+2, member) # +2 for 1-indexing and header row
                            break
        except Exception as e:
            error: str = f'Error encountered in obliterate discord level tracking loop:\n{type(e).__name__}: {e}'
            print(error)
            try:
                log_channel: discord.TextChannel = get_text_channel(self.bot, self.bot.config['testChannel'])
                await log_channel.send(error)
            except:
                pass

    @Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        if before.name == after.name and before.discriminator == after.discriminator:
            return
        
        obliterate: discord.Guild | None = self.bot.get_guild(self.bot.config['obliterate_guild_id'])
        if not obliterate:
            return
        
        if not after.id in [member.id for member in obliterate.members]:
            return
        
        guild: Guild | None = await find_db_guild(self.bot.async_session, obliterate)
        if not guild or not guild.log_channel_id:
            return
        
        channel: discord.TextChannel = get_guild_text_channel(obliterate, guild.log_channel_id)

        member: discord.Member | None = None
        for m in obliterate.members:
            if m.id == after.id:
                member = m
                break
        
        if not member:
            return
        
        beforeName: str = f'{before.name}#{before.discriminator}'
        afterName: str = f'{after.name}#{after.discriminator}'
        txt: str = f'{member.mention} {afterName}'
        embed = discord.Embed(title=f'**Name Changed**', colour=0x00b2ff, timestamp=datetime.now(UTC), description=txt)
        embed.add_field(name='Previously', value=beforeName, inline=False)
        embed.set_footer(text=f'User ID: {after.id}')
        embed.set_thumbnail(url=after.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['obliterate_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

        values: list[list[str]] = await roster.get_all_values()
        values = values[1:]

        discord_col = 4 # zero-indexed

        found = False
        for i, val in enumerate(values):
            if val[discord_col] == beforeName:
                await roster.update_cell(i+2, discord_col+1, afterName)
                await channel.send(f'The roster has been updated with the new username: `{afterName}`.')
                found = True
                break
        
        if not found:
            await channel.send(f'The roster has **not** been updated, because the old value `{beforeName}` could not be found.')

    @app_commands.command()
    @app_commands.guilds(discord.Object(id=config['obliterate_guild_id']), discord.Object(id=config['test_guild_id']))
    async def apply(self, interaction: discord.Interaction) -> None:
        '''
        Send a modal with the application form.
        '''
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This command can only be used inside a server.', ephemeral=True)
            return
        applicant_role: discord.Role | None = interaction.guild.get_role(self.bot.config['obliterate_applicant_role_id'])
        if not applicant_role or not applicant_role in interaction.user.roles:
            await interaction.response.send_message(f'Must be an applicant to submit an application', ephemeral=True)
            return
        application_channel: discord.TextChannel | None = find_guild_text_channel(interaction.guild, self.bot.config['obliterate_applications_channel_id'])
        if not application_channel or not interaction.channel == application_channel:
            await interaction.response.send_message(f'Applications can only be submitted in the #applications channel', ephemeral=True)
            return
        await interaction.response.send_modal(AccountInfoModal(self.bot))

    @app_commands.command()
    @app_commands.guilds(discord.Object(id=config['obliterate_guild_id']), discord.Object(id=config['test_guild_id']))
    async def appreciate(self, interaction: discord.Interaction, member_id: str) -> None:
        '''
        Send a modal with the appreciation station form.
        '''
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This command can only be used inside a server.', ephemeral=True)
            return
        appreciation_channel: TextChannel | None = find_guild_text_channel(interaction.guild, self.bot.config['obliterate_appreciation_station_channel_id'])
        if not appreciation_channel or not interaction.channel == appreciation_channel:
            await interaction.response.send_message(f'Appreciation messages can only be sent in the #appreciation-station channel', ephemeral=True)
            return
        if not member_id or not is_int(member_id):
            await interaction.response.send_message(f'Invalid argument `member: "{member_id}"`', ephemeral=True)
            return
        member: discord.Member | None = interaction.guild.get_member(int(member_id))
        if not member:
            await interaction.response.send_message(f'Could not find member: `{member}`', ephemeral=True)
            return
        if member == interaction.user and not member.id == self.bot.config['owner']:
            await interaction.response.send_message(f'You cannot send an appreciation message to yourself, silly.', ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message(f'Bots are nice, but you cannot send them appreciation messages.', ephemeral=True)
            return
        bronze_role: discord.Role | None = member.guild.get_role(self.bot.config['obliterate_bronze_role_id'])
        if not bronze_role or member.top_role < bronze_role or interaction.user.top_role < bronze_role:
            await interaction.response.send_message(f'Only obliterate clan members can send/receive appreciation messages.', ephemeral=True)
            return
        await interaction.response.send_modal(AppreciationModal(self.bot, member))

    @app_commands.command()
    @app_commands.guilds(discord.Object(id=config['obliterate_guild_id']), discord.Object(id=config['test_guild_id']))
    async def namechange(self, interaction: discord.Interaction, member_id: str) -> None:
        '''
        Send a modal with the name change form.
        '''
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This command can only be used inside a server.', ephemeral=True)
            return
        
        obliterate: discord.Guild | None = self.bot.get_guild(self.bot.config['obliterate_guild_id'])
        if not obliterate:
            await interaction.response.send_message(f'Cannot find obliterate server.', ephemeral=True)
            return
        
        mod_role: discord.Role | None = obliterate.get_role(self.bot.config['obliterate_moderator_role_id'])
        key_role: discord.Role | None = obliterate.get_role(self.bot.config['obliterate_key_role_id'])
        if not mod_role in interaction.user.roles and not key_role in interaction.user.roles:
            await interaction.response.send_message(f'Insufficient permissions: `Obliterate moderator`', ephemeral=True)
            return

        if not member_id or not is_int(member_id):
            await interaction.response.send_message(f'Invalid argument `member: "{member_id}"`', ephemeral=True)
            return
        member: discord.Member | None = interaction.guild.get_member(int(member_id))
        if not member:
            await interaction.response.send_message(f'Could not find member: `{member}`', ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message(f'Cannot do a name change for a bot account.', ephemeral=True)
            return
        await interaction.response.send_modal(NameChangeModal(self.bot, member))

    @appreciate.autocomplete('member_id')
    @namechange.autocomplete('member_id')
    async def member_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        members: list[Member] = [m for m in (interaction.guild.members if interaction.guild else []) if current.upper() in m.display_name.upper() or current.upper() in m.name.upper()]
        # filter out names that cannot be displayed, all clan member names should match this pattern (valid RSNs)
        members = [m for m in members if not re.match(r'^[A-z0-9 -]+$', m.display_name) is None]
        members = members[:25] if len(members) > 25 else members
        return [app_commands.Choice(name=m.display_name, value=str(m.id)) for m in members]

    @obliterate_only()
    @obliterate_mods()
    @commands.cooldown(1, 20, commands.BucketType.guild)
    @commands.command(hidden=True)
    async def event(self, ctx: commands.Context) -> None:
        '''
        Marks event attendence (Moderator+ only)
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        message: str = ctx.message.content.replace(ctx.invoked_with, '', 1).replace(ctx.prefix, '', 1) if ctx.invoked_with and ctx.prefix else ctx.message.content

        if not message:
            if ctx.command:
                ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Required argument missing: `Message`.')

        if not 'Present Members' in message:
            if ctx.command:
                ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Required argument missing: `Attendance`.')
        
        if not 'Event name:' in message:
            if ctx.command:
                ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Required argument missing: `Event name`.')
        
        if not 'Hosted by:' in message:
            if ctx.command:
                ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Required argument missing: `Host name`.')

        event_name: str = ''
        host: str = ''
        participants: list[str] = []

        try:
            event_name = message.split('Event name:')[1].split('\n')[0].strip()
            if not event_name:
                if ctx.command:
                    ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Required argument missing: `Event name`.')

            host = message.split('Hosted by:')[1].split('\n')[0].strip()
            if not host:
                if ctx.command:
                    ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Required argument missing: `Host name`.')

            participants = []

            attendance_str: str = message.split('Present Members')[1].strip()

            first_row = True
            for line in attendance_str.split('\n'):
                if line.startswith('-'*5):
                    first_row = True
                    continue
                elif line.startswith('Below Threshold'):
                    break
                elif line.startswith('```'):
                    continue
                elif line.strip() == '':
                    break
                elif first_row:
                    first_row = False
                    continue
                else:
                    name: str = line.split('|')[0].strip()
                    participants.append(name)

            if not participants:
                if ctx.command:
                    ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Error: Could not find any participants while parsing attendance list:\n```\n{attendance_str}\n```')

        except commands.CommandError as e:
            if ctx.command:
                ctx.command.reset_cooldown(ctx)
            raise e
        except:
            if ctx.command:
                ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'An error occurred while attempting to parse your message. Please ensure that you follow the correct format. Contact Chatty for help if you need it.')

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(config['obliterate_roster_key'])

        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')
        attendance_col, host_col = 7, 8

        alts_sheet: AsyncioGspreadWorksheet = await ss.worksheet('Alts')

        attendance: dict[str, Any] = {}

        raw_members: list[list[str]] = await roster.get_all_values()
        raw_members = raw_members[1:]
        members: list[list[str]] = []
        # Ensure expected row length
        for member in raw_members:
            while len(member) < host_col + 1:
                member.append('')
            if len(member) > host_col + 1:
                member: list[str] = member[:host_col+1]
            members.append(member)

        alts: list[list[str]] = await alts_sheet.get_all_values()
        alts = alts[1:]

        # Find host
        host_member: list[str] | None = None
        host_index: int = 0
        for i, member in enumerate(members):
            if member[0].lower().strip() == host.lower():
                host_member, host_index = member, i
                break
        if not host_member:
            for alt in alts:
                    if alt[1].lower().strip() == host.lower():
                        member_name: str = alt[0]
                        for i, member in enumerate(members):
                            if member[0].lower().strip() == member_name.lower():
                                host_member, host_index = member, i
                                break
                        break
        if not host_member:
            raise commands.CommandError(message=f'Could not find host on roster: `{host}`')

        for participant in participants:
            for i, member in enumerate(members):
                if member[0].lower().strip() == participant.lower():
                    attendance[participant] = {'index': i, 'data': member}
                    break
            if not participant in attendance:
                for alt in alts:
                    if alt[1].lower().strip() == participant.lower():
                        member_name = alt[0]
                        for i, member in enumerate(members):
                            if member[0].lower().strip() == member_name.lower():
                                attendance[participant] = {'index': i, 'data': member}
                                break
                        break

        # Increment attendance numbers
        if host in attendance:
            member = attendance[host]['data']
            num_hosted = 0
            if is_int(member[host_col]):
                num_hosted = int(member[host_col])
            num_hosted += 1
            member[host_col] = str(num_hosted)
            attendance[host]['data'] = member
        else:
            # Update host row here if the host is not a participant
            num_hosted = 0
            if is_int(host_member[host_col]):
                num_hosted = int(host_member[host_col])
            num_hosted += 1
            host_member[host_col] = str(num_hosted)
            await update_row(roster, host_index+2, host_member) # +2 for header row and 1-indexing
        
        for participant, value in attendance.items():
            num_attended = 0
            member = value['data']
            if is_int(member[attendance_col]):
                num_attended = int(member[attendance_col])
            num_attended += 1
            member[attendance_col] = str(num_attended)
            attendance[participant]['data'] = member

        # Update participant attendance on roster
        for participant, value in attendance.items():
            await update_row(roster, value['index']+2, value['data']) # +2 for header row and 1-indexing

        # Add event to events sheet
        events: AsyncioGspreadWorksheet = await ss.worksheet('Event attendance')

        event_col: list[str | None] = await events.col_values(1)
        rows: int = len(event_col)

        date_str: str = datetime.now(UTC).strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row: list[str] = [event_name, host, date_str, ', '.join(participants)]
        cell_list: list[gspread.Cell] = [gspread.Cell(rows+1, i+1, value=val) for i, val in enumerate(new_row)]
        await events.update_cells(cell_list, nowait=True) # type: ignore - nowait is enabled through an odd decorator

        # Generate string indicating noted attendance
        data_str: str = f'Host: {host}\n\nParticipants:\n'
        data_str += '\n'.join([f'- {p}' for p in attendance])
        
        if any(p not in attendance for p in participants):
            data_str += '\n\nParticipants not found on roster:'
            for participant in participants:
                if not participant in attendance:
                    data_str += f'\n- {participant}'

        await ctx.send(f'Success! Attendance for event `{event_name}` has been recorded.\n```\n{data_str}\n```')
    
    @obliterate_only()
    @obliterate_mods()
    @commands.cooldown(1, 20, commands.BucketType.guild)
    @commands.command(hidden=True)
    async def appointment(self, ctx: commands.Context) -> None:
        '''
        Adds staff appointments for a list of members.
        Members can be separated by commas or line breaks.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise commands.CommandError(message=f'This command can only be used in a server.')
        if not ctx.command:
            raise commands.CommandError(message=f'Command not found.')

        message: str = ctx.message.content.replace(ctx.invoked_with if ctx.invoked_with else '', '', 1).replace(ctx.prefix if ctx.prefix else '', '', 1).strip()
        msg_members: list[str] = [m.strip() for m in message.replace('\n', ',').split(',') if m.strip() != '']

        guild_members: list[discord.Member] = []
        for m in msg_members:
            found = False
            for member in ctx.guild.members:
                if m == member.mention or m == str(member.id) or m.upper() == member.display_name.upper() or m.upper() == member.name.upper():
                    found = True
                    guild_members.append(member)
                    break
            if not found:
                for member in ctx.guild.members:
                    if m.upper() in member.display_name.upper() or m.upper() in member.name.upper():
                        found = True
                        guild_members.append(member)
                        break
            if not found:
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Could not find Discord member for name: `{m}`.\nNo changes have been made.')
        
        if not guild_members:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Error: no members found in your message.\nNo changes have been made.')

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['obliterate_roster_key'])

        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')
        appointments: AsyncioGspreadWorksheet = await ss.worksheet('Staff appointments')
        appointments_col = 10

        members_col: list[str | None] = await appointments.col_values(1)
        appointment_rows: int = len(members_col)

        raw_members: list[list[str]] = await roster.get_all_values()
        raw_members = raw_members[1:]
        members: list[list[str]] = []
        # Ensure expected row length
        for member in raw_members:
            while len(member) < appointments_col + 1:
                member.append('')
            if len(member) > appointments_col + 1:
                member = member[:appointments_col+1]
            members.append(member)

        rows_to_update: list[list] = [] # Array of arrays of sheet, row number, row data
        
        for m in guild_members:
            # Find member row
            member_row: list[str] | None = None
            member_index: int = 0
            for i, member in enumerate(members):
                if member[4].strip() == f'{m.name}#{m.discriminator}':
                    member_row, member_index = member, i
                    break
            if not member_row:
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Could not find member on roster: `{m.name}#{m.discriminator}`.\nNo changes have been made.')

            if not is_int(member_row[appointments_col]):
                member_row[appointments_col] = '0'
            member_row[appointments_col] = str(int(member_row[appointments_col]) + 1)

            rows_to_update.append([roster, member_index+2, member_row])# +2 for header row and 1-indexing

            date_str: str = datetime.now(UTC).strftime('%d %b %Y')
            date_str = date_str if not date_str.startswith('0') else date_str[1:]
            new_row: list[str] = [m.display_name, ctx.author.display_name, date_str]

            rows_to_update.append([appointments, appointment_rows+1, new_row])
            appointment_rows += 1
        
        for update in rows_to_update:
            await update_row(update[0], update[1], update[2])

        members_str: str = '\n'.join([m.display_name for m in guild_members])

        await ctx.send(f'**Staff appointments by** {ctx.author.mention}:\n```\n{members_str}\n```')

    @obliterate_only()
    @obliterate_mods()
    @commands.cooldown(1, 20, commands.BucketType.guild)
    @commands.command(hidden=True)
    async def top5(self, ctx: commands.Context, competition_url: str) -> None:
        '''
        Logs SOTW / BOTW results (Moderator+ only)
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not ctx.command:
            raise commands.CommandError(message=f'Command not found.')

        # Get and validate competition ID
        if not competition_url.startswith('https://wiseoldman.net/competitions/'):
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Invalid argument **competition_url**: `{competition_url}`. Url must be of the form: `https://wiseoldman.net/competitions/xxxxx`.')
        
        competition_url = competition_url.replace('https://wiseoldman.net/competitions/', '')
        if not competition_url:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Invalid argument **competition_url**: `{competition_url}`. Url must be of the form: `https://wiseoldman.net/competitions/xxxxx`.')

        competition_id: int | str = competition_url.split('/')[0]
        if not is_int(competition_id):
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Invalid competition ID: `{competition_id}`. Must be a positive integer.')
        competition_id = int(competition_id)
        if competition_id <= 0:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Invalid competition ID: `{competition_id}`. Must be a positive integer.')

        # Form request
        url: str = f'https://api.wiseoldman.net/v2/competitions/{competition_id}'
        async with self.bot.aiohttp.get(url, headers={'x-user-agent': self.bot.config['wom_user_agent'], 'x-api-key': self.bot.config['wom_api_key']}) as r:
            if r.status != 200:
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Error retrieving data from: `{url}`.')
            data: dict[str, Any] = await r.json()

            metric: str = data['metric']
            metric = metric[0].upper() + metric[1:]
            participants: list = data['participations']

            if datetime.now(UTC) < datetime.strptime(data['endsAt'], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=UTC):
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'This competition has not ended yet. It will end at `{data["endsAt"]}`.')
            
            agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
            ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['obliterate_roster_key'])

            roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')
            competitions: AsyncioGspreadWorksheet = await ss.worksheet('Competitions')

            top_col = 12

            competition_ids_col: list[str | None] = await competitions.col_values(1)
            competition_rows: int = len(competition_ids_col)

            if str(competition_id) in competition_ids_col:
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Competition with ID `{competition_id}` has already been logged.')

            raw_members: list[list[str]] = await roster.get_all_values()
            raw_members = raw_members[1:]
            members: list[list[str]] = []
            # Ensure expected row length
            for member in raw_members:
                while len(member) < top_col + 1:
                    member.append('')
                if len(member) > top_col + 1:
                    member = member[:top_col+1]
                members.append(member)

            rows_to_update: list[list] = [] # Array of arrays of sheet, row number, row data
            top_num = 0
            top_indices: list[int] = []

            for i, p in enumerate([participant for participant in participants if is_int(participant['progress']['gained']) and int(participant['progress']['gained']) > 0]):
                top_num: int = i + 1
                # Find member row
                member_row: list[str] | None = None
                member_index: int = 0
                for j, member in enumerate(members):
                    if member[0].strip().lower().replace('-', ' ').replace('_', ' ') == p['player']['displayName'].strip().lower().replace('-', ' ').replace('_', ' '):
                        member_row, member_index = member, j
                        break
                if member_row:
                    if not is_int(member_row[top_col]):
                        member_row[top_col] = '0'
                    member_row[top_col] = str(int(member_row[top_col]) + 1)

                    rows_to_update.append([roster, member_index+2, member_row]) # +2 for header row and 1-indexing
                    top_indices.append(i)

                    if len(rows_to_update) >= 5:
                        break

            top: list = participants[:top_num]
            top_names: str = ''

            table = 'No.  Name          Gain'
            for i, p in enumerate(top):
                table += (f'\n{i+1}.' + (4 - len(str(i+1))) * ' ') if i in top_indices else (f'\n--' + (4 - len(str(i+1))) * ' ')
                table += p['player']['displayName'] + (14 - len(p['player']['displayName'])) * ' '
                table += str(p['progress']['gained'])
                if i in top_indices:
                    top_names += ', ' if top_names else ''
                    top_names += p['player']['displayName']

            start: str = datetime.strptime(data['startsAt'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%d %b %Y')
            start = start if not start.startswith('0') else start[1:]
            end: str = datetime.strptime(data['endsAt'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%d %b %Y')
            end = end if not end.startswith('0') else end[1:]

            new_row: list[str] = [str(competition_id), data['title'], metric, start, end, top_names]

            rows_to_update.append([competitions, competition_rows+1, new_row])

            for update in rows_to_update:
                await update_row(update[0], update[1], update[2])

            await ctx.send(f'Results logged for `{metric}` competition **{data["title"]}**\n```\n{table}\n```')
    
    @obliterate_only()
    @obliterate_mods()
    @commands.command(hidden=True)
    async def promotions(self, ctx: commands.Context) -> None:
        '''
        Gets a list of members eligible for a promotion (Moderator+ only)
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['obliterate_roster_key'])

        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')
        events_attended_col: int = 7
        top3_col: int = 12

        raw_members: list[list[str]] = await roster.get_all_values()
        raw_members = raw_members[1:]
        members: list[list[str]] = []
        # Ensure expected row length
        for member in raw_members:
            if len(member) and member[0]:
                while len(member) < top3_col + 1:
                    member.append('')
                if len(member) > top3_col + 1:
                    member = member[:top3_col+1]
                members.append(member)

        eligible: list[list[str]] = []
        
        for m in reversed(members):
            events_attended, events_hosted, appreciations, appointments, discord_level, top3 = [int(val) if is_int(val) else 0 for val in m[events_attended_col:top3_col+1]]
            rank: str = m[1] # Bronze, Iron, Steel, Mithril, Adamant, Rune, Legacy, Moderator, Key
            try:
                join_date: datetime = datetime.strptime(m[6], '%d %b %Y').replace(tzinfo=UTC)
            except:
                join_date = datetime.now(UTC)
            if rank in reqs:
                req: dict[str, int] = reqs[rank]
                reqs_met = 0
                if events_attended + events_hosted >= req['events']:
                    reqs_met += 1
                if appreciations >= req['appreciations']:
                    reqs_met += 1
                if appointments >= req['appointments']:
                    reqs_met += 1
                if discord_level >= req['discord']:
                    reqs_met += 1
                if top3 >= req['top3']:
                    reqs_met += 1
                if join_date <= datetime.now(UTC) - timedelta(days=req['months']*30):
                    reqs_met += 1
                if reqs_met >= req['number']:
                    eligible.append(m)
        
        msg = '```'
        for m in eligible:
            msg += f'\n{m[0]}{" "*(12-len(m[0]))} {m[1]}{" "*(7-len(m[1]))} -> {ranks[ranks.index(m[1])+1]}'
        if not eligible:
            msg += '\nNo eligible members found.'
        msg += '\n```'

        embed = discord.Embed(title=f'**Members eligible for a promotion**', colour=0x00b2ff, description=msg)

        await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    await bot.add_cog(Obliterate(bot))
