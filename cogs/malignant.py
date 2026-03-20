from typing import Any
import discord
from discord import TextStyle, app_commands
from discord.ext import commands
from discord.ext.commands import Cog
from gspread_asyncio import AsyncioGspreadClient, AsyncioGspreadSpreadsheet, AsyncioGspreadWorksheet
from src.number_utils import is_float
from src.checks import malignant_mods, malignant_only
from src.message_queue import QueueMessage
from src.database_utils import find_db_guild
from src.database import Guild
from src.bot import Bot
from datetime import datetime, UTC, timedelta
import gspread
import traceback
from src.runescape_utils import is_valid_rsn, max_total
from src.wise_old_man import get_group_details, get_player_details, add_group_member
from src.localization import get_country_by_code
from src.discord_utils import get_guild_text_channel, find_guild_text_channel
from src.configuration import config

standard_ranks: list[str] = ['Bronze', 'Iron', 'Steel', 'Black', 'Mithril', 'Adamant', 'Rune', 'Dragon']
achievement_ranks: list[str] = [
    'SOTW Winner',
    'BOTW Champion',
    'Bingo Winner',
    'Bingo MVP',
    'Maxed',
    '800 EHB',
    '1200 EHB',
    '850 Collection Logs',
    '1200 Collection Logs',
    'PB Leaderboard',
    'Pet Hunter of the month',
    'CA Grandmaster'
]
staff_ranks: list[str] = ['Event Coordinator', 'Moderator', 'Head Moderator', 'Deputy Owner', 'Owner']

rank_roles: dict[str, int] = {
    'Bronze': config['malignant_bronze_role_id'],
    'Iron': config['malignant_iron_role_id'],
    'Steel': config['malignant_steel_role_id'],
    'Black': config['malignant_black_role_id'],
    'Mithril': config['malignant_mithril_role_id'],
    'Adamant': config['malignant_adamant_role_id'],
    'Rune': config['malignant_rune_role_id'],
    'Dragon': config['malignant_dragon_role_id'],
    'SOTW Winner': config['malignant_sotw_role_id'],
    'BOTW Champion': config['malignant_botw_role_id'],
    'Bingo Winner': config['malignant_bingo_winner_role_id'],
    'Bingo MVP': config['malignant_bingo_mvp_role_id'],
    'Maxed': config['malignant_maxed_role_id'],
    '800 EHB': config['malignant_ehb_800_role_id'],
    '1200 EHB': config['malignant_ehb_1200_role_id'],
    '850 Collection Logs': config['malignant_clogs_850_role_id'],
    '1200 Collection Logs': config['malignant_clogs_1200_role_id'],
    'PB Leaderboard': config['malignant_pb_leaderboard_role_id'],
    'Pet Hunter of the month': config['malignant_pet_hunter_role_id'],
    'CA Grandmaster': config['malignant_gm_role_id']
}

# Requirements for a promotion from the given rank, i.e. NOT requirements for the rank itself
reqs: dict[str, dict[str, int]] = {
    'Bronze': { 'ehb': 0, 'months': 1 },
    'Iron': { 'ehb': 0, 'months': 2 },
    'Steel': { 'ehb': 0, 'months': 3 },
    'Black': { 'ehb': 0, 'months': 4 },
    'Mithril': { 'ehb': 0, 'months': 5 },
    'Adamant': { 'ehb': 250, 'months': 6 },
    'Rune': { 'ehb': 650, 'months': 12 },
}

roster_columns: dict[str, int] = {
    'RSN': 0,
    'Rank': 1,
    'Discord': 2,
    'Ironman': 3,
    'Date joined': 4,
    'EHB': 5,
    'Notes': 6,
}

application_fields: dict[str, str] = {
    'rsn': 'RuneScape username',
    'requirements': 'Requirements screenshot',
    'total': 'Total level',
    'combat': 'Combat level',
    'ehb': 'EHB',
    'type': 'Account type',
    'build': 'Account build',
    'country': 'Country'
}

achievement_application_fields: dict[str, str] = {
    'achievement': 'Achievement rank',
    'requirements': 'Requirements screenshot',
    'rsn': 'RuneScape username',
    'total': 'Total level',
    'ehb': 'EHB'
}

translate_wom_player_type_to_sheet: dict[str, str] = {
    'unknown': 'No',
    'regular': 'No',
    'ironman': 'Ironman',
    'hardcore': 'HCIM',
    'ultimate': 'UIM'
}

async def update_row(sheet: AsyncioGspreadWorksheet, row_num: int, new_row: list[str | None] | list[str]) -> None:
    cell_list: list[gspread.Cell] = [gspread.Cell(row_num, i+1, value=val) for i, val in enumerate(new_row)]
    await sheet.update_cells(cell_list, nowait=True) # type: ignore - extra arg nowait is supported via an odd decorator

async def get_roster_data(sheet: AsyncioGspreadWorksheet) -> list[list[str]]:
    '''
    Get roster data.

    Args:
        sheet (AsyncioGspreadWorksheet): The sheet to fetch the data from

    Returns:
        list[list[str]]: The roster data
    '''

    rsn_col: int = roster_columns['RSN']
    ehb_col: int = roster_columns['EHB']

    # Get clan members from sheet
    raw_members: list[list[str]] = await sheet.get_all_values()
    raw_members = raw_members[1:]
    members: list[list[str]] = []
    # Ensure at least expected row length
    for member in raw_members:
        if not len(member) or not member[rsn_col]:
            break
        while len(member) < ehb_col + 1:
            member.append('')
        if len(member) > ehb_col + 1:
            member: list[str] = member[:ehb_col+1]
        members.append(member)

    return members

def is_malignant_moderator(member: discord.Member) -> bool:
    '''
    Returns true iff the interaction user is a Malignant moderator.
    '''
    if member.id == config['owner']:
        return True
    if member.guild and member.guild.id == config['malignant_guild_id'] and isinstance(member, discord.Member):
        mod_role: discord.Role | None = member.guild.get_role(config['malignant_moderator_role_id'])
        if mod_role in member.roles:
            return True
    return False

class ApplicationView(discord.ui.View):
    '''
    A view on Malignant application embed messages.
    There are two buttons, labeled "Accept" and "Decline", that can be used by Moderators to accept or decline the application.
    '''
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot
    
    @discord.ui.button(label='Decline', style=discord.ButtonStyle.danger, custom_id='malignant_app_decline_button')
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message or not isinstance(interaction.user, discord.Member) or not is_malignant_moderator(interaction.user):
            await interaction.response.send_message('Missing permissions: `Malignant Moderator`', ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message('Error: this can only done in a text channel.', ephemeral=True)
            return

        # Defer interaction response to ensure timeouts cannot occur
        await interaction.response.defer()

        # Update message
        embed: discord.Embed = interaction.message.embeds[0]

        embed.set_footer(text=f'❌ Declined by {interaction.user.display_name}')
        # Without re-setting the embed image, the image is duplicated for some reason
        embed.set_image(url=f'attachment://image.png')
        await interaction.message.edit(embed=embed, view=None)
        await interaction.followup.send('Application declined successfully.', ephemeral=True)

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.success, custom_id='malignant_app_accept_button')
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.guild or not interaction.message or not interaction.message.embeds or not isinstance(interaction.user, discord.Member) or not is_malignant_moderator(interaction.user):
            await interaction.response.send_message('Missing permissions: `Malignant Moderator`', ephemeral=True)
            return
        embed: discord.Embed = interaction.message.embeds[0]
        if not embed.footer.text:
            await interaction.response.send_message('Interaction message embed footer not found.', ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message('Error: this can only done in a text channel.', ephemeral=True)
            return
        bronze_role: discord.Role | None = interaction.guild.get_role(config['malignant_bronze_role_id'])
        if not bronze_role:
            await interaction.response.send_message('Bronze role not found.', ephemeral=True)
            return
        guest_role: discord.Role | None = interaction.guild.get_role(config['malignant_guest_role_id'])
        
        # Get applicant info from embed
        rsn: str | None = next((f.value for f in embed.fields if f.name == application_fields['rsn']), None)
        ehb: str | None = next((f.value for f in embed.fields if f.name == application_fields['ehb']), None)
        total: str | None = next((f.value for f in embed.fields if f.name == application_fields['total']), None)
        account_type: str | None = next((f.value for f in embed.fields if f.name == application_fields['type']), None)

        if not rsn or not ehb:
            await interaction.response.send_message('Failed to read required data from application embed.', ephemeral=True)
            return
        
        # Defer interaction response because these operations will take some time
        await interaction.response.defer()

        # Get applicant discord user 
        user_id = int(embed.footer.text.replace('User ID: ', ''))
        applicant: discord.Member = await interaction.guild.fetch_member(user_id)
        
        # Update roster
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(config['malignant_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

        members_col: list[str | None] = await roster.col_values(roster_columns['RSN'] + 1)
        rows: int = len(members_col)

        date_str: str = datetime.now(UTC).strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row: list[str | None] = [rsn, 'Bronze', applicant.name, translate_wom_player_type_to_sheet[account_type.lower()] if account_type else 'No', date_str, ehb, total]
        await update_row(roster, rows+1, new_row)

        results: list[str] = []

        # Update Discord user
        try:
            await applicant.add_roles(bronze_role)
            if guest_role and guest_role in applicant.roles:
                await applicant.remove_roles(guest_role)
            await applicant.edit(nick=rsn)
        except discord.Forbidden:
            results.append(f'Failed to update roles or nickname for Discord user `{applicant.name}`.')

        # Add to WOM
        success: bool = await add_group_member(self.bot, config['malignant_wom_verification_code'], config['malignant_wom_group_id'], rsn, 'mentor')
        if not success:
            results.append(f'Failed to add `{rsn}` to WOM.')
        
        # Update message
        embed.set_footer(text=f'✅ Accepted by {interaction.user.display_name}')
        # Without re-setting the embed image, the image is duplicated for some reason
        embed.set_image(url=f'attachment://image.png')
        await interaction.message.edit(embed=embed, view=None)
        
        if results:
            await interaction.followup.send('\n'.join(results), ephemeral=True)
        else:
            await interaction.followup.send(f'Application accepted successfully. Don\'t forget to invite {rsn} in-game!', ephemeral=True)

class ApplicationModal(discord.ui.Modal, title='Malignant application'):
    '''
    A trivial application modal, where the applicant only needs to enter their RSN.
    Required info is then pulled from WOM.
    '''
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    rsn: discord.ui.TextInput = discord.ui.TextInput(label=application_fields['rsn'], min_length=1, max_length=12, required=True, style=TextStyle.short)
    requirements: discord.ui.Label = discord.ui.Label(
        text=application_fields['requirements'], 
        description='Please upload a screenshot showing your username and that you meet the requirements',
        component=discord.ui.FileUpload(min_values=1, max_values=1, required=True)
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Validation
        if not is_valid_rsn(self.rsn.value):
            await interaction.response.send_message(f'Error: invalid RSN: `{self.rsn.value}`', ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(f'Error, this can only be done in a text channel.', ephemeral=True)
            return
        
        upload: discord.ui.FileUpload = self.requirements.component # type: ignore we know that the component for this label is a file upload
        attachment: discord.Attachment = upload.values[0]
        if attachment.content_type is None or not attachment.content_type in ['image/png', 'image/jpeg']:
            await interaction.response.send_message(f'Attachment type was invalid. Please upload an image file (JPG, PNG)', ephemeral=True)
            return
        
        embed: discord.Embed = discord.Embed(title=f'Malignant application', colour=0x00b2ff)
        embed.set_footer(text=f'User ID: {interaction.user.id}')
        
        # Defer the interaction response, as it will take some time to request data from WOM
        await interaction.response.defer()

        # Add RSN to embed
        embed.add_field(name=application_fields['rsn'], value=self.rsn.value, inline=False)

        # Request user data from WOM
        player_details: Any = await get_player_details(self.bot, self.rsn.value)
        if not player_details:
            await interaction.followup.send('Failed to get player details from WOM. Please ensure that you are tracked through WOM before you apply.', ephemeral=True)
            return
        snapshot: Any = player_details['latestSnapshot'] if 'latestSnapshot' in player_details else None
        if not snapshot:
            await interaction.followup.send('Failed to get player data snapshot from WOM. Please update your profile in WOM and try again.', ephemeral=True)
            return
        total: int = snapshot['data']['skills']['overall']['level']
        combat: int = player_details['combatLevel']
        ehb: float = player_details['ehb']
        player_type: str | None = player_details['type'] if 'type' in player_details else None
        player_build: str | None = player_details['build'] if 'build' in player_details else None
        country: str | None = player_details['country'] if 'country' in player_details else None

        # Validate requirements
        # if total < 1500:
        #     await interaction.followup.send(f'You do not meet the requirements to join Malignant because your total level is too low ({total}/1500). If you want to join anyway, please contact a Moderator. Or get good ;)', ephemeral=True)
        #     return
        # if combat < 100:
        #     await interaction.followup.send(f'You do not meet the requirements to join Malignant because your combat level is too low ({combat}/100). If you want to join anyway, please contact a Moderator. Or get good ;)', ephemeral=True)
        #     return
        # if ehb < 50:
        #     await interaction.followup.send(f'You do not meet the requirements to join Malignant because your EHB is too low ({ehb}/50). If you want to join anyway, please contact a Moderator. Or get good ;)', ephemeral=True)
        #     return

        # Add data from WOM to the embed
        embed.add_field(name=application_fields['total'], value=total, inline=False)
        embed.add_field(name=application_fields['combat'], value=combat, inline=False)
        embed.add_field(name=application_fields['ehb'], value=ehb, inline=False)
        if player_type and player_type != 'unknown':
            embed.add_field(name=application_fields['type'], value=player_type.capitalize(), inline=False)
        if player_build:
            embed.add_field(name=application_fields['build'], value=player_build.capitalize(), inline=False)
        if country:
            country_name: str | None = get_country_by_code(country)
            if country_name:
                embed.add_field(name=application_fields['country'], value=country_name, inline=False)

        # Send the message with the application data and add view with accept / decline buttons for mods
        # Note the attachment name is always set to image.png here regardless of the actual extension / content type
        # This is because when editing the embed later, we have to re-use this image url to avoid an odd bug where the image is duplicated.
        file: discord.File = await attachment.to_file(filename='image.png', description=attachment.description, use_cached=True)
        embed.set_image(url=f'attachment://image.png')
        view = ApplicationView(self.bot)
        await interaction.followup.send(embed=embed, file=file, view=view)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.followup.send('Unexpected error occurred', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class AchievementApplicationView(discord.ui.View):
    '''
    A view on achievement application embed messages.
    There are two buttons, labeled "Accept" and "Decline", that can be used by Moderators to accept or decline the application.
    '''
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot
    
    @discord.ui.button(label='Decline', style=discord.ButtonStyle.danger, custom_id='achievement_rank_app_decline_button')
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message or not isinstance(interaction.user, discord.Member) or not is_malignant_moderator(interaction.user):
            await interaction.response.send_message('Missing permissions: `Malignant Moderator`', ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message('Error: this can only done in a text channel.', ephemeral=True)
            return

        # Defer interaction response to ensure timeouts cannot occur
        await interaction.response.defer()

        # Update message
        embed: discord.Embed = interaction.message.embeds[0]

        embed.set_footer(text=f'❌ Declined by {interaction.user.display_name}')
        # Without re-setting the embed image, the image is duplicated for some reason
        embed.set_image(url=f'attachment://image.png')
        await interaction.message.edit(embed=embed, view=None)
        await interaction.followup.send('Application declined successfully.', ephemeral=True)

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.success, custom_id='achievement_rank_app_accept_button')
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.guild or not interaction.message or not interaction.message.embeds or not isinstance(interaction.user, discord.Member) or not is_malignant_moderator(interaction.user):
            await interaction.response.send_message('Missing permissions: `Malignant Moderator`', ephemeral=True)
            return
        embed: discord.Embed = interaction.message.embeds[0]
        if not embed.footer.text:
            await interaction.response.send_message('Interaction message embed footer not found.', ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message('Error: this can only done in a text channel.', ephemeral=True)
            return
        
        # Get applicant info from embed
        achievement_rank: str | None = next((f.value for f in embed.fields if f.name == achievement_application_fields['achievement']), None)
        rsn: str | None = next((f.value for f in embed.fields if f.name == achievement_application_fields['rsn']), None)

        if not achievement_rank or not rsn:
            await interaction.response.send_message('Failed to read required data from application embed.', ephemeral=True)
            return
        if not achievement_rank in rank_roles:
            await interaction.response.send_message(f'Error: role for achievement rank `{achievement_rank}` was not found.', ephemeral=True)
            return
        achievement_role: discord.Role | None = interaction.guild.get_role(rank_roles[achievement_rank])
        if not achievement_role:
            await interaction.response.send_message(f'Error: role for achievement rank `{achievement_rank}` was not found.', ephemeral=True)
            return
        current_rank_role: discord.Role | None = next((r for r in interaction.user.roles if r.id in rank_roles.values()), None)
        if not current_rank_role:
            await interaction.response.send_message('Error: rank role not found.', ephemeral=True)
            return
        
        # Defer interaction response because these operations will take some time
        await interaction.response.defer()

        # Get applicant discord user 
        user_id = int(embed.footer.text.replace('User ID: ', ''))
        applicant: discord.Member = await interaction.guild.fetch_member(user_id)
        
        # Update roster
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(config['malignant_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

        members: list[list[str]] = await get_roster_data(roster)
        rsn_col: int = roster_columns['RSN']
        rank_col: int = roster_columns['Rank']
        member_index: int | None = None

        for i, m in enumerate(members):
            if m[rsn_col] == rsn:
                member_index = i+2
                break

        if not member_index:
            await interaction.followup.send(f'Error: member not found on roster: {rsn}.', ephemeral=True)
            return

        await roster.update_cell(member_index, rank_col+1, achievement_rank)

        results: list[str] = []

        # Update Discord user
        try:
            await applicant.add_roles(achievement_role)
            await applicant.remove_roles(current_rank_role)
        except discord.Forbidden:
            results.append(f'Failed to update roles or nickname for Discord user `{applicant.name}`.')
        
        # Update message
        embed.set_footer(text=f'✅ Accepted by {interaction.user.display_name}')
        # Without re-setting the embed image, the image is duplicated for some reason
        embed.set_image(url=f'attachment://image.png')
        await interaction.message.edit(embed=embed, view=None)
        
        if results:
            await interaction.followup.send('\n'.join(results), ephemeral=True)
        else:
            await interaction.followup.send(f'Application accepted successfully. Don\'t forget to promote `{rsn}` in-game!', ephemeral=True)

class AchievementApplicationModal(discord.ui.Modal, title='Achievement application'):
    '''
    Applicant selects a rank to apply for and provides a screenshot showing that they meet the requirements
    '''
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    achievement: discord.ui.Label = discord.ui.Label(
        text=achievement_application_fields['achievement'],
        component=discord.ui.Select(placeholder='Select...', required=True, options=[discord.SelectOption(label=rank, value=rank) for rank in achievement_ranks])
    )
    requirements: discord.ui.Label = discord.ui.Label(
        text=achievement_application_fields['requirements'],
        description='Please upload a screenshot showing your username and that you meet the requirements',
        component=discord.ui.FileUpload(min_values=1, max_values=1, required=True)
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        achievement_select: discord.ui.Select = self.achievement.component # type: ignore we know that the component for this label is a select
        achievement_rank: str = achievement_select.values[0]
        if not achievement_rank in achievement_ranks:
            await interaction.response.send_message(f'Error: invalid achievement rank: `{achievement_rank}`', ephemeral=True)
            return

        # Validation
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(f'Error, this can only be done in a text channel.', ephemeral=True)
            return
        
        upload: discord.ui.FileUpload = self.requirements.component # type: ignore we know that the component for this label is a file upload
        attachment: discord.Attachment = upload.values[0]
        if attachment.content_type is None or not attachment.content_type in ['image/png', 'image/jpeg']:
            await interaction.response.send_message(f'Attachment type was invalid. Please upload an image file (JPG, PNG)', ephemeral=True)
            return
        
        # Defer the interaction response, as it will take some time to request data from sheets and WOM
        await interaction.response.defer()

        # Get roster sheet
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(config['malignant_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

        # 0-indexed columns
        rsn_col: int = roster_columns['RSN']
        rank_col: int = roster_columns['Rank']
        discord_col: int = roster_columns['Discord']

        members: list[list[str]] = await get_roster_data(roster)

        member: list[str] | None = next((m for m in members if m[discord_col] == interaction.user.name), None)
        if not member:
            await interaction.followup.send(f'Error: member not found: `{interaction.user.name}`', ephemeral=True)
            return
        
        rsn: str = member[rsn_col]
        rank: str = member[rank_col]

        if not is_valid_rsn(rsn):
            await interaction.followup.send(f'Error: invalid RSN: `{rsn}`', ephemeral=True)
            return
        
        if rank in standard_ranks and standard_ranks.index(rank) < standard_ranks.index('Mithril'):
            await interaction.followup.send(f'Error: at least Mithril rank is required to be eligible for an achievement rank, found rank: `{rank}`', ephemeral=True)
            return
        if rank in staff_ranks:
            await interaction.followup.send(f'Error: staff are not eligible for achievement ranks, found staff rank: `{rank}`', ephemeral=True)
            return
        if rank == achievement_rank:
            await interaction.followup.send(f'Error: you already have the rank you are applying for: `{rank}`', ephemeral=True)
            return
        
        embed: discord.Embed = discord.Embed(title=f'Achievement application', colour=0x00b2ff)
        embed.set_footer(text=f'User ID: {interaction.user.id}')

        # Add RSN to embed
        embed.add_field(name=achievement_application_fields['achievement'], value=achievement_rank, inline=False)
        embed.add_field(name=achievement_application_fields['rsn'], value=rsn, inline=False)

        # Request user data from WOM
        player_details: Any = await get_player_details(self.bot, rsn)
        if not player_details:
            await interaction.followup.send('Failed to get player details from WOM. Please ensure that you are tracked through WOM before you apply.', ephemeral=True)
            return
        snapshot: Any = player_details['latestSnapshot'] if 'latestSnapshot' in player_details else None
        if not snapshot:
            await interaction.followup.send('Failed to get player data snapshot from WOM. Please update your profile in WOM and try again.', ephemeral=True)
            return
        total: int = snapshot['data']['skills']['overall']['level']
        ehb: float = player_details['ehb']

        # Validate requirements
        if achievement_rank == 'Maxed' and total < max_total:
            await interaction.followup.send(f'Error: total level of `{max_total}` is required for achievement rank `{achievement_rank}`, found total level `{total}`.', ephemeral=True)
            return
        if achievement_rank == '800 EHB' and ehb < 800:
            await interaction.followup.send(f'Error: `800` EHB is required for achievement rank `{achievement_rank}`, found EHB `{ehb}`.', ephemeral=True)
            return
        if achievement_rank == '1200 EHB' and ehb < 1200:
            await interaction.followup.send(f'Error: `1200` EHB is required for achievement rank `{achievement_rank}`, found EHB `{ehb}`.', ephemeral=True)
            return

        # Add data from WOM to the embed
        embed.add_field(name=achievement_application_fields['total'], value=total, inline=False)
        embed.add_field(name=achievement_application_fields['ehb'], value=ehb, inline=False)

        # Send the message with the application data and add view with accept / decline buttons for mods
        # Note the attachment name is always set to image.png here regardless of the actual extension / content type
        # This is because when editing the embed later, we have to re-use this image url to avoid an odd bug where the image is duplicated.
        file: discord.File = await attachment.to_file(filename='image.png', description=attachment.description, use_cached=True)
        embed.set_image(url=f'attachment://image.png')
        view = AchievementApplicationView(self.bot)
        await interaction.followup.send(embed=embed, file=file, view=view)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.followup.send('Unexpected error occurred', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class Malignant(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
    
    async def cog_load(self) -> None:
        # Register persistent views
        self.bot.add_view(ApplicationView(self.bot))
        self.bot.add_view(AchievementApplicationView(self.bot))

    @Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        '''
        This method is called when a user updates their profile (avatar, username, discriminator).
        When a member of the Malignant guild changes their username, we want to update their username on the sheet.

        Args:
            before (discord.User): Old user data
            after (discord.User): Updated user data
        '''
        # Ignore anything other than username changes
        if before.name == after.name:
            return
        
        # Ignore users who are not a member for the Malignant guild
        malignant: discord.Guild | None = self.bot.get_guild(config['malignant_guild_id'])
        if not malignant or not after.id in [m.id for m in malignant.members]:
            return
        
        # Get the logging channel
        async with self.bot.db.get_session() as session:
            guild: Guild | None = await find_db_guild(session, malignant)
        if not guild or not guild.log_channel_id:
            return
        channel: discord.TextChannel = get_guild_text_channel(malignant, guild.log_channel_id)

        # Get the guild member
        member: discord.Member | None = malignant.get_member(after.id)
        if not member:
            return
        
        # Send embed in the logging channel notifying of the username change
        embed = discord.Embed(title=f'**Name Changed**', colour=0x00b2ff, timestamp=datetime.now(UTC), description=f'{member.mention} `{after.name}`')
        embed.add_field(name='Previously', value=f'`{before.name}`', inline=False)
        embed.set_footer(text=f'User ID: {after.id}')
        embed.set_thumbnail(url=after.display_avatar.url)
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

        # Update the Discord username on the roster sheet
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(config['malignant_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

        values: list[list[str]] = await roster.get_all_values()
        values = values[1:]

        discord_col: int = roster_columns['Discord']

        for i, val in enumerate(values):
            if val[discord_col] == before.name:
                await roster.update_cell(i+2, discord_col+1, after.name)
                self.bot.queue_message(QueueMessage(channel, f'The roster has been updated with the new username: `{after.name}`.'))
                return
        
        # If we did not find a matching row on the sheet, send an error message
        self.bot.queue_message(QueueMessage(channel, f'The roster has not been updated, because the old value `{before.name}` could not be found.'))

    @malignant_only()
    @malignant_mods()
    @commands.command(hidden=True)
    async def promos(self, ctx: commands.Context) -> None:
        '''
        Gets a list of members eligible for a promotion (Moderator+ only).
        Fetches EHB stats from WOM and updates them on the sheet.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        # Get roster sheet
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(config['malignant_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

        # 0-indexed columns
        rsn_col: int = roster_columns['RSN']
        rank_col: int = roster_columns['Rank']
        join_date_col: int = roster_columns['Date joined']
        ehb_col: int = roster_columns['EHB']

        members: list[list[str]] = await get_roster_data(roster)

        # Get updated EHB stats from WOM
        group_details: dict[str, Any] | None = await get_group_details(self.bot, config['malignant_wom_group_id'])
        if not group_details:
            raise commands.CommandError('Failed to retrieve group details from WOM.')
        player_details: list[Any] = [membership['player'] for membership in group_details['memberships']]

        errors: list[str] = []
        
        # Update EHB stats
        cell_list: list[gspread.Cell] = []
        for i, m in enumerate(members):
            player: Any | None = next((p for p in player_details if p['username'].lower() == m[rsn_col].lower()), None)
            if not player:
                errors.append(f'WOM player not found: `{m[rsn_col]}`.')
                continue
            m[ehb_col] = player['ehb']
            cell_list.append(gspread.Cell(i+2, ehb_col+1, value=m[ehb_col]))
        await roster.update_cells(cell_list, nowait=True) # type: ignore - extra arg nowait is supported via an odd decorator

        # Construct list of members eligible for a promotion
        eligible: list[list[str]] = []
        for m in members:
            rank: str = m[rank_col] # Bronze, Iron, Steel, Black, Mithril, Adamant, Rune, Dragon, Moderator, Owner
            join_date: datetime
            try:
                join_date = datetime.strptime(m[join_date_col], '%d %b %Y').replace(tzinfo=UTC)
            except:
                join_date = datetime.now(UTC)
            ehb: float = float(m[ehb_col]) if is_float(m[ehb_col]) else 0
            if rank in reqs:
                req: dict[str, int] = reqs[rank]
                if ehb >= req['ehb'] and join_date <= datetime.now(UTC) - timedelta(days=req['months']*30):
                    eligible.append(m)

        # Send a message listing the eligible members, if any
        msg = '```'
        for m in eligible:
            msg += f'\n{m[rsn_col]}{" "*(12-len(m[rsn_col]))} {m[rank_col]}{" "*(7-len(m[rank_col]))} -> {standard_ranks[standard_ranks.index(m[rank_col])+1]}'
        if not eligible:
            msg += '\nNo eligible members found.'
        msg += '\n```'

        embed = discord.Embed(title=f'**Members eligible for a promotion**', colour=0x00b2ff, description=msg)
        if errors:
            embed.add_field(name='Errors', value='\n'.join(errors), inline=False)

        await ctx.send(embed=embed)

    @app_commands.command(name='achievement_rank')
    @app_commands.guilds(discord.Object(id=config['malignant_guild_id']), discord.Object(id=config['test_guild_id']))
    async def achievement_apply(self, interaction: discord.Interaction) -> None:
        '''
        Send a modal with the application form.
        '''
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This command can only be used inside a server.', ephemeral=True)
            return
        
        test_channel: discord.TextChannel | None = find_guild_text_channel(interaction.guild, config['testChannel'])

        if interaction.guild.id in [config['malignant_guild_id'], config['test_guild_id']]:
            malignant_application_channel: discord.TextChannel | None = find_guild_text_channel(interaction.guild, config['malignant_applications_channel_id'])
            if (not malignant_application_channel and not interaction.channel == malignant_application_channel 
                and not test_channel and not interaction.channel == test_channel):
                await interaction.response.send_message(f'Applications can only be submitted in the #applications channel', ephemeral=True)
                return
            mithril_role: discord.Role | None = interaction.guild.get_role(config['malignant_mithril_role_id'])
            if mithril_role and interaction.user.top_role < mithril_role and interaction.user.id != config['owner']:
                await interaction.response.send_message(f'At least the mithril role is required to be able to apply for achievement ranks', ephemeral=True)
                return
            moderator_role: discord.Role | None = interaction.guild.get_role(config['malignant_moderator_role_id'])
            if moderator_role and interaction.user.top_role >= moderator_role and interaction.user.id != config['owner']:
                await interaction.response.send_message(f'Moderators cannot apply for achievement ranks', ephemeral=True)
                return
            await interaction.response.send_modal(AchievementApplicationModal(self.bot))

async def setup(bot: Bot) -> None:
    await bot.add_cog(Malignant(bot))
