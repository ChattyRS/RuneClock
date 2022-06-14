import discord
from discord import app_commands, TextStyle
from discord.ext import commands
from discord.ext.commands import Cog
import sys

sys.path.append('../')
from main import config_load, increment_command_counter, Poll, Guild
from datetime import datetime, timedelta
import re
import gspread
from utils import cozy_council, cozy_champions, cozy_only
import math
from utils import is_int
import traceback

config = config_load()

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

def is_champion_or_companion(interaction: discord.Interaction):
    if interaction.user.id == config['owner']:
        return True
    if interaction.guild.id == config['cozy_guild_id']:
        companion_role = interaction.guild.get_role(config['cozy_companion_role_id'])
        champion_role = interaction.guild.get_role(config['cozy_champion_role_id'])
        council_role = interaction.guild.get_role(config['cozy_council_role_id'])
        if council_role in interaction.user.roles or champion_role in interaction.user.roles or companion_role in interaction.user.roles:
            return True
    return False

class ApplicationView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.value = None
    
    @discord.ui.button(label='Decline', style=discord.ButtonStyle.danger, custom_id='cozy_app_decline_button')
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Validate permissions
        if not is_champion_or_companion(interaction):
            await interaction.response.send_message('Missing permissions: `Cozy champion or companion`', ephemeral=True)
            return
        # Update message
        embed = interaction.message.embeds[0]
        embed.set_footer(text=f'Declined by {interaction.user.display_name}', icon_url='https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/160/twitter/322/cross-mark_274c.png')
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message('Application declined successfully.', ephemeral=True)
        self.value = False
        self.stop()

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.success, custom_id='cozy_app_accept_button')
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Validate permissions
        if not is_champion_or_companion(interaction):
            await interaction.response.send_message('Missing permissions: `Cozy champion or companion`', ephemeral=True)
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

        applicant_role = member.guild.get_role(config['cozy_applicant_role_id'])
        friends_role = member.guild.get_role(config['cozy_friend_role_id'])

        if (not applicant_role in member.roles) or (friends_role in member.roles):
            return f'Error: incorrect roles for applicant: `{member.display_name}`. Either they are not an applicant, or they are already a friend.'
        
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
        ss = await agc.open_by_key(config['cozy_roster_key'])
        roster = await ss.worksheet('Roster')

        members_col = await roster.col_values(1)
        rows = len(members_col)

        date_str = datetime.utcnow().strftime('%d %b %Y')
        date_str = date_str if not date_str.startswith('0') else date_str[1:]
        new_row = [rsn, 'Friend', ironman, 'Yes', 'Yes', f'{member.name}#{member.discriminator}', '', date_str]
        cell_list = [gspread.models.Cell(rows+1, i+1, value=val) for i, val in enumerate(new_row)]
        print(f'writing values:\n{new_row}\nto row {rows+1}')
        await roster.update_cells(cell_list, nowait=True)

        # Update member nickname and roles
        roles = member.roles
        roles.remove(applicant_role)
        roles.append(friends_role)
        await member.edit(nick=rsn, roles=roles)

        # Add to WOM
        url = 'https://api.wiseoldman.net/groups/423/add-members'
        payload = {'verificationCode': config['cozy_wiseoldman_verification_code']}
        payload['members'] = [{'username': rsn, 'role': 'member'}]
        async with self.bot.aiohttp.post(url, json=payload) as r:
            if r.status != 200:
                data = await r.json()
                return f'Error adding to WOM: {r.status}\n{data}'
            data = await r.json()

        # Send message in promotions channel
        channel = interaction.guild.get_channel(config['cozy_promotions_channel_id'])
        await channel.send(f'`{rsn}`\'s application was accepted by {interaction.user.mention}. Please invite them to the CC in-game and react to this message once done.')
        
        return 'success'
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)


class CozyPersonalInfoModal(discord.ui.Modal):
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
        embed = discord.Embed(title=f'**Cozy application**', colour=0x00b2ff)
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

    @discord.ui.button(label='Part 2', style=discord.ButtonStyle.primary, custom_id='cozy_app_part2_button')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get data from first modal from message embed
        data = {}
        for field in interaction.message.embeds[0].fields:
            data[field.name] = field.value
        # Open second form modal
        modal = CozyPersonalInfoModal(self.bot, data)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.value:
            self.value = True
            self.stop()
        else:
            self.value = False

class CozyAccountInfoModal(discord.ui.Modal, title='Account information'):
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
        if view.value == True:
            # message deletion does not work here because the message is ephemeral
            # await msg.delete()
            pass

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class Cozy(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    def cog_unload(self):
        pass
    
    def cog_load(self):
        # Register persistent views
        print('Cozy cog load: registering persistent views...')
        self.bot.add_view(ApplicationView(self.bot))
        self.bot.add_view(OpenPersonalInfoView(self.bot))
    

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

    
    @commands.command()
    @cozy_champions()
    @cozy_only()
    async def sotw_poll(self, ctx):
        '''
        Posts a poll for the next SOTW competition.
        '''
        increment_command_counter()
        await ctx.channel.typing()

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
    @cozy_champions()
    @cozy_only()
    async def botw_poll(self, ctx):
        '''
        Posts a poll for the next BOTW competition.
        '''
        increment_command_counter()
        await ctx.channel.typing()

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
    @cozy_champions()
    @cozy_only()
    async def sotw_votes(self, ctx, msg_id):
        '''
        Records votes on a SOTW poll and logs them to the SOTW sheet.
        '''
        increment_command_counter()
        await ctx.channel.typing()

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
    @cozy_champions()
    @cozy_only()
    async def botw_votes(self, ctx, msg_id):
        '''
        Records votes on a BOTW poll and logs them to the BOTW sheet.
        '''
        increment_command_counter()
        await ctx.channel.typing()

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
        await ctx.channel.typing()

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

    
    @app_commands.command()
    @app_commands.guilds(discord.Object(id=config['cozy_guild_id']))
    async def apply(self, interaction: discord.Interaction):
        '''
        Send a modal with the cozy application form.
        '''
        applicant_role = interaction.guild.get_role(config['cozy_applicant_role_id'])
        if not applicant_role or not applicant_role in interaction.user.roles:
            await interaction.response.send_message(f'Must be an applicant to submit an application', ephemeral=True)
            return
        application_channel = interaction.guild.get_channel(config['cozy_applications_channel_id'])
        if not application_channel or not interaction.channel == application_channel:
            await interaction.response.send_message(f'Applications can only be submitted in the #cozy-applications channel', ephemeral=True)
            return
        await interaction.response.send_modal(CozyAccountInfoModal(self.bot))


async def setup(bot):
    await bot.add_cog(Cozy(bot))
