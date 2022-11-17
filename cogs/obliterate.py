import io
from typing import List
import discord
from discord import app_commands, TextStyle
from discord.ext import commands, tasks
from discord.ext.commands import Cog
import sys

sys.path.append('../')
from main import config_load, Guild, increment_command_counter
from datetime import datetime
import re
import gspread
import traceback
from utils import is_int, obliterate_only, obliterate_mods

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

async def update_row(sheet, row_num, new_row):
    cell_list = [gspread.models.Cell(row_num, i+1, value=val) for i, val in enumerate(new_row)]
    await sheet.update_cells(cell_list, nowait=True)

class AppreciationModal(discord.ui.Modal, title='Appreciation'):
    def __init__(self, bot, member_to_appreciate):
        super().__init__()
        self.bot = bot
        self.member_to_appreciate = member_to_appreciate

    message = discord.ui.TextInput(label='Message', min_length=1, max_length=1000, required=True, style=TextStyle.long)
    anonymous = discord.ui.TextInput(label='Should this post be anonymous?', min_length=1, max_length=3, required=True, placeholder='Yes / No', style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        message = self.message.value
        anonymous = self.anonymous.value
        member_to_appreciate = self.member_to_appreciate

        if not 'Y' in anonymous.upper() and not 'N' in anonymous.upper():
            interaction.response.send_message(f'Error: invalid value for anonymous: `{anonymous}`', ephemeral=True)
            return
        anonymous = 'Y' in anonymous.upper()

        # Create an embed to send to the appreciation station channel
        embed = discord.Embed(title=f'Appreciation message', description=message, colour=0x00e400)
        if anonymous:
            with open('images/default_avatar.png', 'rb') as f:
                default_avatar = io.BytesIO(f.read())
            default_avatar = discord.File(default_avatar, filename='default_avatar.png')
            embed.set_author(name='Anonymous', icon_url='attachment://default_avatar.png')
        else:
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        # Update appreciation sheet on roster
        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['obliterate_roster_key'])
        appreciations = await ss.worksheet('Appreciation')

        members_col = await appreciations.col_values(1)
        rows = len(members_col)

        date_str = datetime.utcnow().strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row = [interaction.user.display_name, member_to_appreciate.display_name, date_str, message]

        # Update appreciation column on roster
        roster = await ss.worksheet('Roster')
        appreciation_col = 9

        raw_members = await roster.get_all_values()
        raw_members = raw_members[1:]
        members = []
        # Ensure expected row length
        for member in raw_members:
            while len(member) < appreciation_col + 1:
                member.append('')
            if len(member) > appreciation_col + 1:
                member = member[:appreciation_col+1]
            members.append(member)

        # Find member row
        member_row, member_index = None, 0
        for i, member in enumerate(members):
            if member[4].strip() == f'{member_to_appreciate.name}#{member_to_appreciate.discriminator}':
                member_row, member_index = member, i
                break
        if not member_row:
            interaction.response.send_message(f'Could not find member on roster: `{member_to_appreciate.name}#{member_to_appreciate.discriminator}`')
            return

        if not is_int(member_row[appreciation_col]):
            member_row[appreciation_col] = '0'
        member_row[appreciation_col] = str(int(member_row[appreciation_col]) + 1)

        # Send an embed to the appreciation station channel
        if anonymous:
            await interaction.channel.send(member_to_appreciate.mention, embed=embed, file=default_avatar)
            await interaction.response.send_message(f'Your appreciation message for {member_to_appreciate.mention} has been sent!', ephemeral=True)
        else:
            await interaction.response.send_message(member_to_appreciate.mention, embed=embed)

        await update_row(appreciations, rows+1, new_row)
        await update_row(roster, member_index+2, member_row) # +2 for header row and 1-indexing

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

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

class Obliterate(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.track_discord_levels.start()

    def cog_unload(self):
        self.track_discord_levels.cancel()
    
    def cog_load(self):
        # Register persistent views
        self.bot.add_view(ApplicationView(self.bot))
        self.bot.add_view(OpenPersonalInfoView(self.bot))

    
    @tasks.loop(hours=24)
    async def track_discord_levels(self):
        '''
        Loop to track discord levels from Mee6 dashboard on clan roster
        '''
        try:
            print('Syncing obliterate discord levels...')
            obliterate_guild_id = config['obliterate_guild_id']
            r = await self.bot.aiohttp.get(f'https://mee6.xyz/api/plugins/levels/leaderboard/{obliterate_guild_id}')

            async with r:
                data = await r.json(content_type='application/json')
                player_data = data['players']

                agc = await self.bot.agcm.authorize()
                ss = await agc.open_by_key(config['obliterate_roster_key'])
                roster = await ss.worksheet('Roster')

                raw_members = await roster.get_all_values()
                raw_members = raw_members[1:]

                discord_col = 4 # 0-indexed
                discord_level_col = 11 # 0-indexed

                members = []
                # Ensure expected row length
                for member in raw_members:
                    while len(member) < discord_level_col + 1:
                        member.append('')
                    if len(member) > discord_level_col + 1:
                        member = member[:discord_level_col+1]
                    members.append(member)

                for player in player_data:
                    player_discord = f'{player["username"]}#{player["discriminator"]}'
                    player_level = player['level']
                    for i, member in enumerate(members):
                        if member[discord_col].strip() == player_discord:
                            member[discord_level_col] = str(player_level)
                            await update_row(roster, i+2, member) # +2 for 1-indexing and header row
                            break
        except Exception as e:
            error = f'Error encountered in obliterate discord level tracking loop:\n{type(e).__name__}: {e}'
            print(error)
            try:
                log_channel = self.get_channel(config['testChannel'])
                await log_channel.send(error)
            except:
                pass

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
        appreciation_channel = interaction.guild.get_channel(config['obliterate_appreciation_station_channel_id'])
        if not appreciation_channel or not interaction.channel == appreciation_channel:
            await interaction.response.send_message(f'Appreciation messages can only be sent in the #appreciation-station channel', ephemeral=True)
            return
        if not member or not is_int(member):
            await interaction.response.send_message(f'Invalid argument `member: "{member}"`', ephemeral=True)
            return
        member = interaction.guild.get_member(int(member))
        if not member:
            await interaction.response.send_message(f'Could not find member: `{member}`', ephemeral=True)
            return
        if member == interaction.user and not member.id == config['owner']:
            await interaction.response.send_message(f'You cannot send an appreciation message to yourself, silly.', ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message(f'Bots are nice, but you cannot send them appreciation messages.', ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message(f'Bots are nice, but you cannot send them appreciation messages.', ephemeral=True)
            return
        bronze_role = member.guild.get_role(config['obliterate_bronze_role_id'])
        if member.top_role < bronze_role or interaction.user.top_role < bronze_role:
            await interaction.response.send_message(f'Only obliterate clan members can send/receive appreciation messages.', ephemeral=True)
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


    @obliterate_only()
    @obliterate_mods()
    @commands.cooldown(1, 20, commands.BucketType.guild)
    @commands.command(hidden=True)
    async def event(self, ctx):
        '''
        Marks event attendence (Moderator+ only)
        '''
        increment_command_counter()
        await ctx.channel.typing()

        message = ctx.message.content.replace(ctx.invoked_with, '', 1).replace(ctx.prefix, '', 1)

        if not message:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Required argument missing: `Attendance`.')

        if not 'Present Members' in message:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Required argument missing: `Attendance`.')
        
        if not 'Event name:' in message:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Required argument missing: `Event name`.')
        
        if not 'Hosted by:' in message:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Required argument missing: `Host name`.')

        event_name, host, participants = '', '', []

        try:
            event_name = message.split('Event name:')[1].split('\n')[0].strip()
            if not event_name:
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Required argument missing: `Event name`.')

            host = message.split('Hosted by:')[1].split('\n')[0].strip()
            if not host:
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Required argument missing: `Host name`.')

            participants = []

            attendance = message.split('Present Members')[1].strip()

            first_row = True
            for line in attendance.split('\n'):
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
                    name = line.split('|')[0].strip()
                    participants.append(name)

            if not participants:
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Error: Could not find any participants while parsing attendance list:\n```\n{attendance}\n```')

        except commands.CommandError as e:
            ctx.command.reset_cooldown(ctx)
            raise e
        except:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'An error occurred while attempting to parse your message. Please ensure that you follow the correct format. Contact Chatty for help if you need it.')

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['obliterate_roster_key'])

        roster = await ss.worksheet('Roster')
        attendance_col, host_col = 7, 8

        alts_sheet = await ss.worksheet('Alts')

        attendance = {}

        raw_members = await roster.get_all_values()
        raw_members = raw_members[1:]
        members = []
        # Ensure expected row length
        for member in raw_members:
            while len(member) < host_col + 1:
                member.append('')
            if len(member) > host_col + 1:
                member = member[:host_col+1]
            members.append(member)

        alts = await alts_sheet.get_all_values()
        alts = alts[1:]

        # Find host
        host_member, host_index = None, 0
        for i, member in enumerate(members):
            if member[0].lower().strip() == host.lower():
                host_member, host_index = member, i
                break
        if not host_member:
            for alt in alts:
                    if alt[1].lower().strip() == host.lower():
                        member_name = alt[0]
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
            member[host_col] = num_hosted
            attendance[host]['data'] = member
        else:
            # Update host row here if the host is not a participant
            num_hosted = 0
            if is_int(host_member[host_col]):
                num_hosted = int(host_member[host_col])
            num_hosted += 1
            host_member[host_col] = num_hosted
            await update_row(roster, host_index+2, host_member) # +2 for header row and 1-indexing
        
        for participant, value in attendance.items():
            num_attended = 0
            member = value['data']
            if is_int(member[attendance_col]):
                num_attended = int(member[attendance_col])
            num_attended += 1
            member[attendance_col] = num_attended
            attendance[participant]['data'] = member

        # Update participant attendance on roster
        for participant, value in attendance.items():
            await update_row(roster, value['index']+2, value['data']) # +2 for header row and 1-indexing

        # Add event to events sheet
        events = await ss.worksheet('Event attendance')

        event_col = await events.col_values(1)
        rows = len(event_col)

        date_str = datetime.utcnow().strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row = [event_name, host, date_str, ', '.join(participants)]
        cell_list = [gspread.models.Cell(rows+1, i+1, value=val) for i, val in enumerate(new_row)]
        await events.update_cells(cell_list, nowait=True)

        # Generate string indicating noted attendance
        data_str = f'Host: {host}\n\nParticipants:\n'
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
    async def appointment(self, ctx):
        '''
        Adds staff appointments for a list of members.
        Members can be separated by commas or line breaks.
        '''
        increment_command_counter()
        await ctx.channel.typing()

        message = ctx.message.content.replace(ctx.invoked_with, '', 1).replace(ctx.prefix, '', 1).strip()
        members = [m.strip() for m in message.replace('\n', ',').split(',') if m.strip() != '']

        guild_members = []
        for m in members:
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

        agc = await self.bot.agcm.authorize()
        ss = await agc.open_by_key(config['obliterate_roster_key'])

        roster = await ss.worksheet('Roster')
        appointments = await ss.worksheet('Staff appointments')
        appointments_col = 10

        members_col = await appointments.col_values(1)
        appointment_rows = len(members_col)

        raw_members = await roster.get_all_values()
        raw_members = raw_members[1:]
        members = []
        # Ensure expected row length
        for member in raw_members:
            while len(member) < appointments_col + 1:
                member.append('')
            if len(member) > appointments_col + 1:
                member = member[:appointments_col+1]
            members.append(member)

        rows_to_update = [] # Array of arrays of sheet, row number, row data
        
        for m in guild_members:
            # Find member row
            member_row, member_index = None, 0
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

            date_str = datetime.utcnow().strftime('%d %b %Y')
            date_str = date_str if not date_str.startswith('0') else date_str[1:]
            new_row = [m.display_name, ctx.author.display_name, date_str]

            rows_to_update.append([appointments, appointment_rows+1, new_row])
            appointment_rows += 1
        
        for update in rows_to_update:
            await update_row(update[0], update[1], update[2])

        members_str = '\n'.join([m.display_name for m in guild_members])

        await ctx.send(f'**Staff appointments by** {ctx.author.mention}:\n```\n{members_str}\n```')

    @obliterate_only()
    @obliterate_mods()
    @commands.cooldown(1, 20, commands.BucketType.guild)
    @commands.command(hidden=True)
    async def top3(self, ctx, competition_url):
        '''
        Logs SOTW / BOTW results (Moderator+ only)
        '''
        increment_command_counter()
        await ctx.channel.typing()

        # Get and validate competition ID
        if not competition_url.startswith('https://wiseoldman.net/competitions/'):
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Invalid argument **competition_url**: `{competition_url}`. Url must be of the form: `https://wiseoldman.net/competitions/xxxxx`.')
        
        competition_url = competition_url.replace('https://wiseoldman.net/competitions/', '')
        if not competition_url:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Invalid argument **competition_url**: `{competition_url}`. Url must be of the form: `https://wiseoldman.net/competitions/xxxxx`.')

        competition_id = competition_url.split('/')[0]
        if not is_int(competition_id):
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Invalid competition ID: `{competition_id}`. Must be a positive integer.')
        competition_id = int(competition_id)
        if competition_id <= 0:
            ctx.command.reset_cooldown(ctx)
            raise commands.CommandError(message=f'Invalid competition ID: `{competition_id}`. Must be a positive integer.')

        # Form request
        url = f'https://api.wiseoldman.net/competitions/{competition_id}'
        async with self.bot.aiohttp.get(url) as r:
            if r.status != 200:
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Error retrieving data from: `{url}`.')
            data = await r.json()

            metric = data['metric']
            metric = metric[0].upper() + metric[1:]
            participants = data['participants']

            if datetime.utcnow() < datetime.strptime(data['endsAt'], '%Y-%m-%dT%H:%M:%S.%fZ'):
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'This competition has not ended yet. It will end at `{data["endsAt"]}`.')
            
            agc = await self.bot.agcm.authorize()
            ss = await agc.open_by_key(config['obliterate_roster_key'])

            roster = await ss.worksheet('Roster')
            competitions = await ss.worksheet('Competitions')

            top3_col = 12

            competition_ids_col = await competitions.col_values(1)
            competition_rows = len(competition_ids_col)

            if str(competition_id) in competition_ids_col:
                ctx.command.reset_cooldown(ctx)
                raise commands.CommandError(message=f'Competition with ID `{competition_id}` has already been logged.')

            raw_members = await roster.get_all_values()
            raw_members = raw_members[1:]
            members = []
            # Ensure expected row length
            for member in raw_members:
                while len(member) < top3_col + 1:
                    member.append('')
                if len(member) > top3_col + 1:
                    member = member[:top3_col+1]
                members.append(member)

            rows_to_update = [] # Array of arrays of sheet, row number, row data
            top_num = 0
            top_indices = []

            for i, p in enumerate(participants):
                # Find member row
                member_row, member_index = None, 0
                for j, member in enumerate(members):
                    if member[0].strip().lower() == p['displayName'].strip().lower():
                        member_row, member_index = member, j
                        break
                if member_row:
                    if not is_int(member_row[top3_col]):
                        member_row[top3_col] = '0'
                    member_row[top3_col] = str(int(member_row[top3_col]) + 1)

                    rows_to_update.append([roster, member_index+2, member_row]) # +2 for header row and 1-indexing
                    top_indices.append(i)

                    if len(rows_to_update) >= 3:
                        top_num = i + 1
                        break

            top = participants[:top_num]
            top_names = ''

            table = 'No.  Name          Gain'
            for i, p in enumerate(top):
                table += (f'\n{i+1}.' + (4 - len(str(i+1))) * ' ') if i in top_indices else (f'\n--' + (4 - len(str(i+1))) * ' ')
                table += p['displayName'] + (14 - len(p['displayName'])) * ' '
                table += str(p['progress']['gained'])
                if i in top_indices:
                    top_names += ', ' if top_names else ''
                    top_names += p['displayName']

            start = datetime.strptime(data['startsAt'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%d %b %Y')
            start = start if not start.startswith('0') else start[1:]
            end = datetime.strptime(data['endsAt'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime('%d %b %Y')
            end = end if not end.startswith('0') else end[1:]

            new_row = [str(competition_id), data['title'], metric, start, end, top_names]

            rows_to_update.append([competitions, competition_rows+1, new_row])

            for update in rows_to_update:
                await update_row(update[0], update[1], update[2])

            await ctx.send(f'Results logged for `{metric}` competition **{data["title"]}**\n```\n{table}\n```')

async def setup(bot):
    await bot.add_cog(Obliterate(bot))
