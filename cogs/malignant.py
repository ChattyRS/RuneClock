from typing import Any
import discord
from discord import Attachment, TextStyle
from discord.ext import commands
from discord.ext.commands import Cog
from gspread_asyncio import AsyncioGspreadClient, AsyncioGspreadSpreadsheet, AsyncioGspreadWorksheet
from src.message_queue import QueueMessage
from src.database_utils import find_db_guild
from src.database import Guild
from src.bot import Bot
from datetime import datetime, UTC
import gspread
import traceback
from src.runescape_utils import is_valid_rsn
from src.wise_old_man import get_player_details, add_group_member
from src.localization import get_country_by_code
from src.discord_utils import get_guild_text_channel, get_text_channel

ranks: list[str] = ['Bronze', 'Iron', 'Steel', 'Black', 'Mithril', 'Adamant', 'Rune', 'Dragon']

reqs: dict[str, dict[str, int]] = {
    'Bronze': { 'ehb': 50, 'months': 0 },
    'Iron': { 'ehb': 100, 'months': 1 },
    'Steel': { 'ehb': 200, 'months': 2 },
    'Black': { 'ehb': 350, 'months': 3 },
    'Mithril': { 'ehb': 550, 'months': 4 },
    'Adamant': { 'ehb': 800, 'months': 5 },
    'Rune': { 'ehb': 1200, 'months': 6 },
    'Dragon': { 'ehb': 2000, 'months': 12 },
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
    'total': 'Total level',
    'combat': 'Combat level',
    'ehb': 'EHB',
    'type': 'Account type',
    'build': 'Account build',
    'country': 'Country'
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

class ApplicationView(discord.ui.View):
    '''
    A view on Malignant application embed messages.
    There are two buttons, labeled "Accept" and "Decline", that can be user by Moderators to accept to decline the application.
    '''
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot
    
    def is_malignant_moderator(self, interaction: discord.Interaction) -> bool:
        '''
        Returns true iff the interaction user is a Malignant moderator.
        '''
        if interaction.user.id == self.bot.config['owner']:
            return True
        if interaction.guild and interaction.guild.id == self.bot.config['malignant_guild_id'] and isinstance(interaction.user, discord.Member):
            mod_role: discord.Role | None = interaction.guild.get_role(self.bot.config['malignant_moderator_role_id'])
            if mod_role in interaction.user.roles:
                return True
        return False
    
    @discord.ui.button(label='Decline', style=discord.ButtonStyle.danger, custom_id='malignant_app_decline_button')
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message or not self.is_malignant_moderator(interaction):
            await interaction.response.send_message('Missing permissions: `Malignant Moderator`', ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message('Error: this can only done in a text channel.', ephemeral=True)
            return
        # Update message
        embed: discord.Embed = interaction.message.embeds[0]
        if not embed.footer.text:
            await interaction.response.send_message('Embed footer was unexpectedly empty.', ephemeral=True)
            return

        # Defer interaction response to ensure timeouts cannot occur due to converting of attachments
        await interaction.response.defer()

        files: list[discord.File] = []
        log_channel: discord.TextChannel = get_text_channel(self.bot, self.bot.config['malignant_logging_channel_id'])
        attachment_message_id: int = int(embed.footer.text.split(';')[1].replace(' Attachments reference: ', ''))
        attachment_message: discord.Message = await log_channel.fetch_message(attachment_message_id)
        for attachment in attachment_message.attachments:
            file: discord.File = await attachment.to_file(filename=attachment.filename, description=attachment.description, use_cached=True)
            files.append(file)
        embed.set_image(url=f'attachment://{files[0].filename}')
        embed.set_footer(text=f'❌ Declined by {interaction.user.display_name}')
        await interaction.message.edit(embed=embed, attachments=files, view=None)
        await interaction.followup.send('Application declined successfully.', ephemeral=True)

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.success, custom_id='malignant_app_accept_button')
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.guild or not interaction.message or not interaction.message.embeds or not self.is_malignant_moderator(interaction):
            await interaction.response.send_message('Missing permissions: `Malignant Moderator`', ephemeral=True)
            return
        embed: discord.Embed = interaction.message.embeds[0]
        if not embed.footer.text:
            await interaction.response.send_message('Interaction message embed footer not found.', ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message('Error: this can only done in a text channel.', ephemeral=True)
            return
        bronze_role: discord.Role | None = interaction.guild.get_role(self.bot.config['malignant_bronze_role_id'])
        if not bronze_role:
            await interaction.response.send_message('Bronze role not found.', ephemeral=True)
            return
        
        # Get applicant info from embed
        rsn: str | None = next((f.value for f in embed.fields if f.name == application_fields['rsn']), None)
        ehb: str | None = next((f.value for f in embed.fields if f.name == application_fields['ehb']), None)
        account_type: str | None = next((f.value for f in embed.fields if f.name == application_fields['type']), None)

        if not rsn or not ehb:
            await interaction.response.send_message('Failed to read required data from application embed.', ephemeral=True)
            return
        
        # Defer interaction response because these operations will take some time
        await interaction.response.defer()

        # Get applicant discord user 
        user_id = int(embed.footer.text.split(';')[0].replace('User ID: ', ''))
        applicant: discord.Member = await interaction.guild.fetch_member(user_id)
        
        # Update roster
        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['malignant_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

        members_col: list[str | None] = await roster.col_values(roster_columns['RSN'] + 1)
        rows: int = len(members_col)

        date_str: str = datetime.now(UTC).strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row: list[str | None] = [rsn, 'Bronze', applicant.name, translate_wom_player_type_to_sheet[account_type.lower()] if account_type else 'No', date_str, ehb]
        await update_row(roster, rows+1, new_row)

        results: list[str] = []

        # Update Discord user
        try:
            await applicant.add_roles(bronze_role)
            await applicant.edit(nick=rsn)
        except discord.Forbidden:
            results.append(f'Failed to update roles or nickname for Discord user `{applicant.name}`.')

        # Add to WOM
        success: bool = await add_group_member(self.bot, self.bot.config['malignant_wom_verification_code'], self.bot.config['malignant_wom_group_id'], rsn, 'mentor')
        if not success:
            results.append(f'Failed to add `{rsn}` to WOM.')
        
        # Update message
        files: list[discord.File] = []
        log_channel: discord.TextChannel = get_text_channel(self.bot, self.bot.config['malignant_logging_channel_id'])
        attachment_message_id: int = int(embed.footer.text.split(';')[1].replace(' Attachments reference: ', ''))
        attachment_message: discord.Message = await log_channel.fetch_message(attachment_message_id)
        for attachment in attachment_message.attachments:
            file: discord.File = await attachment.to_file(filename=attachment.filename, description=attachment.description, use_cached=True)
            files.append(file)
        embed.set_image(url=f'attachment://{files[0].filename}')
        embed.set_footer(text=f'✅ Accepted by {interaction.user.display_name}')
        await interaction.message.edit(embed=embed, attachments=files, view=None)
        
        if results:
            await interaction.followup.send('\n'.join(results), ephemeral=True)
        else:
            await interaction.followup.send('Application accepted successfully.', ephemeral=True)

class ApplicationModal(discord.ui.Modal, title='Malignant application'):
    '''
    A trivial application modal, where the applicant only needs to enter their RSN.
    Required info is then pulled from WOM.
    '''
    def __init__(self, bot: Bot, message: discord.Message) -> None:
        super().__init__()
        self.bot: Bot = bot
        self.message: discord.Message = message

    rsn = discord.ui.TextInput(label=application_fields['rsn'], min_length=1, max_length=12, required=True, style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Validation
        if not is_valid_rsn(self.rsn.value):
            await interaction.response.send_message(f'Error: invalid RSN: `{self.rsn.value}`', ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(f'Error, this can only be done in a text channel.', ephemeral=True)
            return
        embed: discord.Embed = self.message.embeds[0]
        if not embed.footer.text:
            await interaction.response.send_message('Embed footer was unexpectedly empty.', ephemeral=True)
            return
        
        # Defer the interaction response, as it will take some time to request data from WOM
        await interaction.response.defer()

        # Update embed with RSN
        embed.title = 'Malignant application'
        embed.colour = 0x00b2ff
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
        if total < 1500:
            await interaction.followup.send(f'You do not meet the requirements to join Malignant because your total level is too low ({total}/1500). If you want to join anyway, please contact a Moderator. Or get good ;)', ephemeral=True)
            return
        if combat < 100:
            await interaction.followup.send(f'You do not meet the requirements to join Malignant because your combat level is too low ({combat}/100). If you want to join anyway, please contact a Moderator. Or get good ;)', ephemeral=True)
            return
        if ehb < 50:
            await interaction.followup.send(f'You do not meet the requirements to join Malignant because your EHB is too low ({ehb}/50). If you want to join anyway, please contact a Moderator. Or get good ;)', ephemeral=True)
            return

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

        # Update the message with the new data and add view with accept / decline buttons for mods
        files: list[discord.File] = []
        log_channel: discord.TextChannel = get_text_channel(self.bot, self.bot.config['malignant_logging_channel_id'])
        attachment_message_id: int = int(embed.footer.text.split(';')[1].replace(' Attachments reference: ', ''))
        attachment_message: discord.Message = await log_channel.fetch_message(attachment_message_id)
        for attachment in attachment_message.attachments:
            file: discord.File = await attachment.to_file(filename=attachment.filename, description=attachment.description, use_cached=True)
            files.append(file)
        embed.set_image(url=f'attachment://{files[0].filename}')
        view = ApplicationView(self.bot)
        await self.message.edit(embed=embed, attachments=files, view=view)

        # Send followup message to the applicant notifying them that their application came through successfully
        await interaction.followup.send('Your application was sent successfully!', ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.followup.send('Unexpected error occurred', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class RequirementsView(discord.ui.View):
    '''
    A view on an embed message showing the submitted requirements screenshot(s) from the applicant.
    There is an "Apply" button below the modal allowing the applicant to proceed with their application.
    '''
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot

    def is_applicant(self, interaction: discord.Interaction) -> bool:
        '''
        Returns true iff the interaction user is the user who originally sent the requirements screenshot(s).
        '''
        # Check requirements
        if not interaction.message or not interaction.message.embeds or not interaction.message.embeds[0].footer.text:
            return False
        # Return true iff the user is the original applicant
        return interaction.user.id == int(interaction.message.embeds[0].footer.text.split(';')[0].replace('User ID: ', ''))

    @discord.ui.button(label='Apply', style=discord.ButtonStyle.blurple, custom_id='malignant_req_apply_button')
    async def apply(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message or not interaction.message.embeds or not self.is_applicant(interaction):
            await interaction.response.send_message('Only the original applicant can use this to apply.', ephemeral=True)
            return
        
        # Send the application modal
        modal = ApplicationModal(self.bot, interaction.message)
        await interaction.response.send_modal(modal)
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, _: discord.ui.Item[Any]) -> None:
        await interaction.response.send_message('Unexpected error occurred.', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class Malignant(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot
    
    async def cog_load(self) -> None:
        # Register persistent views
        self.bot.add_view(RequirementsView(self.bot))
        self.bot.add_view(ApplicationView(self.bot))

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
        if before.global_name == after.name:
            return
        
        # Ignore users who are not a member for the Malignant guild
        malignant: discord.Guild | None = self.bot.get_guild(self.bot.config['malignant_guild_id'])
        if not malignant or not after.id in [m.id for m in malignant.members]:
            return
        
        # Get the logging channel
        async with self.bot.get_session() as session:
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
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(self.bot.config['malignant_roster_key'])
        roster: AsyncioGspreadWorksheet = await ss.worksheet('Roster')

        values: list[list[str]] = await roster.get_all_values()
        values = values[1:]

        discord_col = 2 # zero-indexed

        for i, val in enumerate(values):
            if val[discord_col] == before.name:
                await roster.update_cell(i+2, discord_col+1, after.name)
                self.bot.queue_message(QueueMessage(channel, f'The roster has been updated with the new username: `{after.name}`.'))
                return
        
        # If we did not find a matching row on the sheet, send an error message
        self.bot.queue_message(QueueMessage(channel, f'The roster has not been updated, because the old value `{before.name}` could not be found.'))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        '''
        This event triggers on every message received by the bot. Including ones that it sent itself.
        When a message is sent in the Malignant applications channel which includes one or more images, 
        this event will trigger the application process.

        Args:
            message (discord.Message): The message
        '''
        # Ignore all bots
        if message.author.bot:
            return

        # Ignore messages that were not sent from guilds or text channels.
        if message.guild is None or not isinstance(message.channel, discord.TextChannel) or not isinstance(message.author, discord.Member):
            return
        
        # Ignore messages from outside the Malignant server
        if not message.guild.id in [self.bot.config['malignant_guild_id'], self.bot.config['test_guild_id']]:
            return
        
        # Ignore messages in channels other than the applications channel
        if not message.channel.id in [self.bot.config['malignant_applications_channel_id'], self.bot.config['testChannel']]:
            return
        
        # Ignore messages from ranked players
        bronze_role: discord.Role | None = message.guild.get_role(self.bot.config['malignant_bronze_role_id'])
        if bronze_role and message.author.top_role >= bronze_role and (message.author.id != self.bot.config['owner'] or not 'test' in message.content.lower()):
            return
        
        # Ignore messages without image attachments
        if not message.attachments:
            return
        
        # Get list of attached images
        images: list[Attachment] = [a for a in message.attachments if a.content_type in ['image/jpeg', 'image/png']]
        
        # Ignore messages without any image attachments
        if not images:
            return
        
        await self.send_requirements_view(message, images)
        
    async def send_requirements_view(self, message: discord.Message, images: list[Attachment]) -> None:
        '''
        Sends a requirements view to the applications channel based on the given message and attached images.

        Args:
            message (discord.Message): The original message
            images (list[Attachment]): The attached images from the original message
        '''
        # Create embed
        embed = discord.Embed(title=f'**Malignant requirements**', colour=0x7a7a7a)
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        
        # Convert image attachments to Discord files suitable for sending in a message
        files: list[discord.File] = []
        for attachment in images:
            file: discord.File = await attachment.to_file(filename=attachment.filename, description=attachment.description, use_cached=True)
            files.append(file)

        # Forward the attachments to a separate channel.
        # This is required to avoid Discord deleting the image files as the original message is deleted
        log_channel: discord.TextChannel = get_text_channel(self.bot, self.bot.config['malignant_logging_channel_id'])
        fwd_msg: discord.Message = await log_channel.send((
            'This message contains attachments that were sent as part of an application. '
            'Please do not delete this message, otherwise the images may be removed from Discord and no longer be visible in the application embeds.'
        ), files=files)

        # Reload the attachments from the forwarded message to obtain links that will not expire
        files = []
        for attachment in fwd_msg.attachments:
            file: discord.File = await attachment.to_file(filename=attachment.filename, description=attachment.description, use_cached=True)
            files.append(file)

        # Set the message author ID and a reference to the forwarded message as the embed footer for future reference
        embed.set_footer(text=f'User ID: {message.author.id}; Attachments reference: {fwd_msg.id}')

        # Set the first image on the embed
        # Subsequent images, if any, will be sent separately below the embed
        embed.set_image(url=f'attachment://{files[0].filename}')

        view: RequirementsView = RequirementsView(self.bot)
        await message.channel.send(embed=embed, files=files, view=view)
        await message.delete()

async def setup(bot: Bot) -> None:
    await bot.add_cog(Malignant(bot))
