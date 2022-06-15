from typing import List
import discord
from discord import app_commands, TextStyle
from discord.ext import commands
from discord.ext.commands import Cog
import sys

sys.path.append('../')
from main import config_load, Guild
from datetime import datetime
import re
import gspread
import traceback
from utils import is_int

config = config_load()

def is_obliterate_mod(interaction: discord.Interaction):
    if interaction.user.id == config['owner']:
        return True
    if interaction.guild.id == config['obliterate_guild_id']:
        mod_role = interaction.guild.get_role(config['obliterate_moderator_role_id'])
        key_role = interaction.guild.get_role(config['obliterate_key_role_id'])
        if mod_role in interaction.user.roles or key_role in interaction.user.roles:
            return True
    return False

class ApplicationView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.value = None
    
    @discord.ui.button(label='Decline', style=discord.ButtonStyle.danger, custom_id='obliterate_app_decline_button')
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Validate permissions
        if not is_obliterate_mod(interaction):
            await interaction.response.send_message('Missing permissions: `Obliterate moderator`', ephemeral=True)
            return
        # Update message
        embed = interaction.message.embeds[0]
        embed.set_footer(text=f'Declined by {interaction.user.display_name}', icon_url='https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/160/twitter/322/cross-mark_274c.png')
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message('Application declined successfully.', ephemeral=True)
        self.value = False
        self.stop()

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.success, custom_id='obliterate_app_accept_button')
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Validate permissions
        if not is_obliterate_mod(interaction):
            await interaction.response.send_message('Missing permissions: `Obliterate moderator`', ephemeral=True)
            return
        # Handle accept
        status = await self.accept_handler(interaction)
        if status != 'success':
            await interaction.response.send_message(status, ephemeral=True)
            return
        # Update message
        embed = interaction.message.embeds[0]
        embed.set_footer(text=f'Accepted by {interaction.user.display_name}', icon_url='https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/160/twitter/322/check-mark-button_2705.png')
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message('Application accepted successfully.', ephemeral=True)
        self.value = True
        self.stop()

    async def accept_handler(self, interaction: discord.Interaction) -> str:
        '''
        Parses data from an accepted application to perform the following actions:
        - Add the new member to the roster
        - Set their discord display name to their RSN
        - Promote them in discord
        - Add them to WOM
        '''
        print('Running accept handler')

        user_id = int(interaction.message.embeds[0].footer.text.replace('User ID: ', ''))
        member = await interaction.guild.fetch_member(user_id)

        if not member:
            return 'Error: applicant not found'

        applicant_role = member.guild.get_role(config['obliterate_applicant_role_id'])
        bronze_role = member.guild.get_role(config['obliterate_bronze_role_id'])

        if (not applicant_role in member.roles) or (bronze_role in member.roles):
            return f'Error: incorrect roles for applicant: `{member.display_name}`. Either they are not an applicant, or they are already bronze.'
        
        # Parse message
        rsn = interaction.message.embeds[0].fields[0].value
        ironman = interaction.message.embeds[0].fields[2].value
        if not ironman.upper() in ['NO', 'YES', 'IRONMAN', 'HCIM', 'UIM', 'GIM']:
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
        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['obliterate_roster_key'])
        roster = await ss.worksheet('Roster')

        members_col = await roster.col_values(1)
        rows = len(members_col)

        date_str = datetime.utcnow().strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row = [rsn, 'Bronze', ironman, 'Yes', f'{member.name}#{member.discriminator}', '', date_str]
        cell_list = [gspread.models.Cell(rows+1, i+1, value=val) for i, val in enumerate(new_row)]
        print(f'writing values:\n{new_row}\nto row {rows+1}')
        await roster.update_cells(cell_list, nowait=True)

        # Update member nickname and roles
        roles = member.roles
        roles.remove(applicant_role)
        roles.append(bronze_role)
        await member.edit(nick=rsn, roles=roles)

        # Add to WOM
        url = f'https://api.wiseoldman.net/groups/{config["obliterate_wom_group_id"]}/add-members'
        payload = {'verificationCode': config['obliterate_wom_verification_code']}
        payload['members'] = [{'username': rsn, 'role': 'member'}]
        async with self.bot.aiohttp.post(url, json=payload) as r:
            if r.status != 200:
                data = await r.json()
                return f'Error adding to WOM: {r.status}\n{data}'
            data = await r.json()

        # Send message in promotions channel
        channel = interaction.guild.get_channel(config['obliterate_promotions_channel_id'])
        await channel.send(f'`{rsn}`\'s application was accepted by {interaction.user.mention}. Please invite them to the CC in-game and react to this message once done.')
        
        return 'success'
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)


class PersonalInfoModal(discord.ui.Modal):
    def __init__(self, bot, data):
        self.bot = bot
        self.data = data
        try:
            super().__init__(title='Personal information')
        except Exception as e:
            print(e)

    motivation = discord.ui.TextInput(label='Why do you want to join our clan?', max_length=200, required=True, style=TextStyle.paragraph)
    play_time = discord.ui.TextInput(label='When are you most active?', placeholder='Morning / Afternoon / Evening / Night', max_length=200, required=True, style=TextStyle.paragraph)
    referral = discord.ui.TextInput(label='Where did you hear about our clan?', max_length=200, required=True, style=TextStyle.paragraph)
    voice_chat = discord.ui.TextInput(label='Would you join voice chat during events?', placeholder='Yes / No', max_length=200, required=True, style=TextStyle.paragraph)
    fav_activity = discord.ui.TextInput(label='Favourite in-game activity', max_length=200, required=True, style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        self.value = self.data
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
        msg = await interaction.response.send_message(embed=embed, view=view)
        await view.wait()

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class OpenPersonalInfoView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.value = None

    @discord.ui.button(label='Part 2', style=discord.ButtonStyle.primary, custom_id='obliterate_app_part2_button')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get data from first modal from message embed
        data = {}
        for field in interaction.message.embeds[0].fields:
            data[field.name] = field.value
        # Open second form modal
        modal = PersonalInfoModal(self.bot, data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.value:
            self.value = True
            self.stop()
        else:
            self.value = False

class AccountInfoModal(discord.ui.Modal, title='Account information'):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    rsn = discord.ui.TextInput(label='RuneScape username', min_length=1, max_length=12, required=True, style=TextStyle.short)
    total = discord.ui.TextInput(label='Total level', min_length=2, max_length=4, required=True, style=TextStyle.short)
    ironman = discord.ui.TextInput(label='Are you an ironman?', placeholder='(No / Ironman / HCIM / UIM / GIM)', min_length=2, max_length=7, required=True, style=TextStyle.short)
    timezone = discord.ui.TextInput(label='What is your timezone?', min_length=1, max_length=20, required=True, style=TextStyle.short)
    experience = discord.ui.TextInput(label='How long have you played OSRS?', max_length=200, required=True, style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        # Validation
        if re.match('^[A-z0-9 -]+$', self.rsn.value) is None:
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
        msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class AppreciationModal(discord.ui.Modal, title="Message of Appreciation"):
    def __init__(self, bot, appreciate_player):
        super().__init__()
        self.bot = bot
        self.appreciate_player = appreciate_player

    message = discord.ui.TextInput(label='Message of appreciation', min_length=1, max_length=1000, required=True, style=TextStyle.long)
    anonymous = discord.ui.TextInput(label='Would you like this post to be anonymous?', min_length=1, max_length=3, required=True, placeholder="Yes/No", style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        member = interaction.user
        message = self.message.value
        anonymous = self.anonymous.value
        appreciate_player = self.appreciate_player

        if not 'Y' in anonymous.upper() and not 'N' in anonymous.upper():
            interaction.response.send_message(f'Error: invalid value for anonymous: `{anonymous}`', ephemeral=True)
        else:
            anonymous = 'Y' in anonymous.upper()

        # Update appreciation sheet on roster
        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['obliterate_roster_key'])
        roster = await ss.worksheet('Appreciation')

        members_col = await roster.col_values(1)
        rows = len(members_col)

        date_str = datetime.utcnow().strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row = [member, appreciate_player, message, date_str]
        cell_list = [gspread.models.Cell(rows+1, i+1, value=val) for i, val in enumerate(new_row)]
        print(f'writing values:\n{new_row}\nto row {rows+1}')
        await roster.update_cells(cell_list, nowait=True)

        # Send appreciation message to Appreciation Station channel
        embed = discord.Embed(title=f'**Message of Appreciation**', colour=0x00b2ff)
        if anonymous:
            embed.set_author(name="Anonymous", icon_url=discord.AppInfo.icon.url)
        else:
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.add_field(name="For:", value=appreciate_player.display_name, inline=True)
        embed.add_field(name="Message:", value=message, inline=False)
        
        await interaction.channel.send(embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class Obliterate(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    def cog_unload(self):
        pass
    
    def cog_load(self):
        # Register persistent views
        self.bot.add_view(ApplicationView(self.bot))
        self.bot.add_view(OpenPersonalInfoView(self.bot))
    

    @Cog.listener()
    async def on_user_update(self, before, after):
        if before.name != after.name or before.discriminator != after.discriminator:
            obliterate = self.bot.get_guild(config['obliterate_guild_id'])
            if obliterate:
                if after.id in [member.id for member in obliterate.members]:
                    guild = await Guild.get(obliterate.id)
                    if guild:
                        if guild.log_channel_id:
                            channel = obliterate.get_channel(guild.log_channel_id)

                            member = None
                            for m in obliterate.members:
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
                                ss = await agc.open_by_key(config['obliterate_roster_key'])
                                roster = await ss.worksheet('Roster')

                                values = await roster.get_all_values()
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
    async def apply(self, interaction: discord.Interaction):
        '''
        Send a modal with the application form.
        '''
        applicant_role = interaction.guild.get_role(config['obliterate_applicant_role_id'])
        if not applicant_role or not applicant_role in interaction.user.roles:
            await interaction.response.send_message(f'Must be an applicant to submit an application', ephemeral=True)
            return
        application_channel = interaction.guild.get_channel(config['obliterate_applications_channel_id'])
        if not application_channel or not interaction.channel == application_channel:
            await interaction.response.send_message(f'Applications can only be submitted in the #applications channel', ephemeral=True)
            return
        await interaction.response.send_modal(AccountInfoModal(self.bot))

    @app_commands.command()
    @app_commands.guilds(discord.Object(id=config['obliterate_guild_id']), discord.Object(id=config['test_guild_id']))
    async def appreciate(self, interaction: discord.Interaction, member: str):
        '''
        Send a modal with the appreciation station form.
        '''
        if not member or not is_int(member):
            await interaction.response.send_message(f'Invalid argument `member: "{member}"`', ephemeral=True)
            return
        member = interaction.guild.get_member(int(member))
        if not member:
            await interaction.response.send_message(f'Could not find member: `{member}`', ephemeral=True)
            return

        appreciation_station_channel = interaction.guild.get_channel(config['obliterate_appreciation_station_channel_id'])
        if not appreciation_station_channel or not interaction.channel == appreciation_station_channel:
            await interaction.response.send_message(f'Appreciations can only be submitted in the #appreciation_station channel', ephemeral=True)
            return
        await interaction.response.send_modal(AppreciationModal(self.bot, member))

    @appreciate.autocomplete('member')
    async def member_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        members = [m for m in interaction.guild.members if current.upper() in m.display_name.upper() or current.upper() in m.name.upper()]
        # filter out names that cannot be displayed, all clan member names should match this pattern (valid RSNs)
        members = [m for m in members if not re.match('^[A-z0-9 -]+$', m.display_name) is None]
        members = members[:25] if len(members) > 25 else members
        return [app_commands.Choice(name=m.display_name, value=str(m.id)) for m in members]

async def setup(bot):
    await bot.add_cog(Obliterate(bot))
