from datetime import datetime, timedelta, UTC
import traceback
from typing import Any
import discord
from discord import SelectOption, TextStyle, app_commands
from discord.ext.commands import Cog, CommandError
import sys
import random
import copy
sys.path.append('../')
from main import Bot, get_config, Guild
import re
from utils import is_int, wom_skills, wom_bosses, wom_clues, wom_minigames, wom_efficiency, wom_metrics

config: dict[str, Any] = get_config()

def choose_metric(exclude: list[str] = [], type: str = '') -> str:
    type = type.lower().strip()

    options: list[str] = copy.deepcopy(wom_metrics)
    if 'skill' in type:
        options = copy.deepcopy(wom_skills)
    elif 'boss' in type:
        options = copy.deepcopy(wom_bosses)
    elif 'clue' in type:
        options = copy.deepcopy(wom_clues)
    elif 'minigame' in type:
        options = copy.deepcopy(wom_minigames)
    elif 'efficiency' in type:
        options = copy.deepcopy(wom_efficiency)

    for opt in exclude:
        if opt in options:
            options.remove(opt)

    if not options:
        raise Exception('No options to choose from')

    return random.choice(options)
    

class WOMSetupModal(discord.ui.Modal, title='Wise Old Man: setup'):
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    group_id = discord.ui.TextInput(label='Group ID', placeholder="Group ID...", min_length=1, max_length=10, required=True, style=TextStyle.short)
    verification_code = discord.ui.TextInput(label='Verification code', placeholder="Verification code...", min_length=11, max_length=11, required=True, style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        group_id: str | int = self.group_id.value.strip()
        verification_code: str = self.verification_code.value.strip()

        # Validation
        if not group_id:
            await interaction.response.send_message(f'Required argument missing: `GROUP ID`.', ephemeral=True)
            return
        if not is_int(group_id):
            await interaction.response.send_message(f'Invalid argument: `GROUP ID: {group_id}`.', ephemeral=True)
            return
        group_id = int(group_id)

        if not verification_code:
            await interaction.response.send_message(f'Required argument missing: `VERIFICATION CODE`.', ephemeral=True)
            return
        if len(verification_code.split('-')) != 3 or any([len(part) != 3 for part in verification_code.split('-')]) or any([not is_int(part) for part in verification_code.split('-')]):
            await interaction.response.send_message(f'Invalid argument: `VERIFICATION CODE: {verification_code}`.', ephemeral=True)
            return

        # Get WOM group
        group = None
        url: str = f'https://api.wiseoldman.net/v2/groups/{group_id}'
        async with self.bot.aiohttp.get(url, headers={'x-user-agent': config['wom_user_agent'], 'x-api-key': config['wom_api_key']}) as r:
            if r.status != 200:
                await interaction.response.send_message(f'An error occurred while trying to retrieve WOM group with ID `{group_id}`. Please try again later and ensure that you have set your group ID correctly.', ephemeral=True)
                return
            group: Any = await r.json()

        # Store group id and verification code
        async with self.bot.async_session() as session:
            guild: Guild = await self.bot.get_db_guild(interaction.guild, session)
            guild.wom_group_id = group_id
            guild.wom_verification_code = verification_code
            await session.commit()
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Wise Old Man**', colour=0x00e400)
        embed.add_field(name='Group', value=group['name'], inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')

        await interaction.response.send_message(embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)
    
class Dropdown(discord.ui.Select):
    def __init__(self, bot: Bot, options: list[SelectOption]) -> None:
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder='Choose a role...', min_values=1, max_values=1, options=options, custom_id='wom_role_select')
        self.bot: Bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        # Use the interaction object to update the guild wom_role_id. 
        # The self object refers to the Select object, 
        # and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        role: discord.Role = self.bot.get_role(interaction.guild, int(self.values[0]))
        async with self.bot.async_session() as session:
            guild: Guild = await self.bot.get_db_guild(interaction.guild, session)
            guild.wom_role_id = role.id
            await session.commit()
        await interaction.response.send_message(f'The WOM management role has been set to `{role.name}`', ephemeral=True)

class SelectRoleView(discord.ui.View):
    def __init__(self, bot: Bot, guild: discord.Guild) -> None:
        super().__init__()
        self.bot: Bot = bot

        # Get options for role dropdown
        options: list[SelectOption] = [discord.SelectOption(label=role.name, value=str(role.id)) for role in sorted(guild.roles, reverse=True)]
        if len(options) > 25:
            options = options[:25]

        # Adds the dropdown to our view object.
        self.add_item(Dropdown(self.bot, options))

class AddToWOMModal(discord.ui.Modal, title='Wise Old Man: add'):
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    rsn = discord.ui.TextInput(label='Who do you want to add?', placeholder="Player name...", min_length=1, max_length=12, required=True, style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        rsn: str = self.rsn.value

        # Validation
        if not rsn:
            await interaction.response.send_message(f'Required argument missing: `RSN`.', ephemeral=True)
            return

        # Get WOM group
        group = None
        guild: Guild = await self.bot.get_db_guild(interaction.guild)
        url: str = f'https://api.wiseoldman.net/v2/groups/{guild.wom_group_id}'
        async with self.bot.aiohttp.get(url, headers={'x-user-agent': config['wom_user_agent'], 'x-api-key': config['wom_api_key']}) as r:
            if r.status != 200:
                await interaction.response.send_message(f'An error occurred while trying to retrieve WOM group with ID `{guild.wom_group_id}`. Please try again later and ensure that you have set your group ID correctly.', ephemeral=True)
                return
            group = await r.json()
        
        # Add player to group
        url = f'https://api.wiseoldman.net/v2/groups/{guild.wom_group_id}/members'
        payload: dict[str, Any] = {'verificationCode': guild.wom_verification_code}
        payload['members'] = [{'username': rsn, 'role': 'member'}]
        async with self.bot.aiohttp.post(url, json=payload, headers={'x-user-agent': config['wom_user_agent'], 'x-api-key': config['wom_api_key']}) as r:
            if r.status != 200:
                data: Any = await r.json()
                await interaction.response.send_message(f'An error occurred while trying to add `{rsn}` to WOM group with ID `{guild.wom_group_id}`. Please try again later.\n```{r.status}\n\n{data}```', ephemeral=True)
                return
            data = await r.json()
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Wise Old Man**', colour=0x00e400)
        embed.add_field(name='Group', value=group['name'], inline=False)
        embed.add_field(name='Added player', value=rsn, inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')

        pattern: re.Pattern[str] = re.compile(r'([^\s\w]|_)+')
        formatted_name: str = pattern.sub('', rsn).replace(' ', '%20')
        player_image_url: str = f'https://services.runescape.com/m=avatar-rs/{formatted_name}/chat.png'
        embed.set_thumbnail(url=player_image_url)

        await interaction.response.send_message(embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class RemoveFromWOMModal(discord.ui.Modal, title='Wise Old Man: remove'):
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    rsn = discord.ui.TextInput(label='Who do you want to remove?', placeholder="Player name...", min_length=1, max_length=12, required=True, style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        rsn: str = self.rsn.value

        # Validation
        if not rsn:
            await interaction.response.send_message(f'Required argument missing: `RSN`.', ephemeral=True)
            return

        # Get WOM group
        group = None
        guild: Guild = await self.bot.get_db_guild(interaction.guild)
        url: str = f'https://api.wiseoldman.net/v2/groups/{guild.wom_group_id}'
        async with self.bot.aiohttp.get(url, headers={'x-user-agent': config['wom_user_agent'], 'x-api-key': config['wom_api_key']}) as r:
            if r.status != 200:
                await interaction.response.send_message(f'An error occurred while trying to retrieve WOM group with ID `{guild.wom_group_id}`. Please try again later and ensure that you have set your group ID correctly.', ephemeral=True)
                return
            group = await r.json()
        
        # Remove player from group
        url = f'https://api.wiseoldman.net/v2/groups/{guild.wom_group_id}/members'
        payload: dict[str, Any] = {'verificationCode': guild.wom_verification_code}
        payload['members'] = [rsn]
        async with self.bot.aiohttp.delete(url, json=payload, headers={'x-user-agent': config['wom_user_agent'], 'x-api-key': config['wom_api_key']}) as r:
            if r.status != 200:
                data: Any = await r.json()
                await interaction.response.send_message(f'An error occurred while trying to remove `{rsn}` from WOM group with ID `{guild.wom_group_id}`. Please try again later.\n```{r.status}\n\n{data}```', ephemeral=True)
                return
            data = await r.json()
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Wise Old Man**', colour=0xff0000)
        embed.add_field(name='Group', value=group['name'], inline=False)
        embed.add_field(name='Removed player', value=rsn, inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')

        pattern: re.Pattern[str] = re.compile(r'([^\s\w]|_)+')
        formatted_name: str = pattern.sub('', rsn).replace(' ', '%20')
        player_image_url: str = f'https://services.runescape.com/m=avatar-rs/{formatted_name}/chat.png'
        embed.set_thumbnail(url=player_image_url)

        await interaction.response.send_message(embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class WOMCompetitionModal(discord.ui.Modal, title='Wise Old Man: competition'):
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    competition_title = discord.ui.TextInput(label='Competition title', placeholder=f'Title...', min_length=1, max_length=50, required=True, style=TextStyle.short)
    metric = discord.ui.TextInput(label='Competition metric', placeholder=f'Skill / boss', min_length=min([len(m) for m in wom_metrics]), max_length=max([len(m) for m in wom_metrics]), required=True, style=TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        competition_title: str = self.competition_title.value
        metric: str = self.metric.value.strip().replace(' ', '_').lower()

        # Validation
        if not competition_title:
            await interaction.response.send_message(f'Required argument missing: `TITLE`.', ephemeral=True)
            return
        if not metric:
            await interaction.response.send_message(f'Required argument missing: `METRIC`.', ephemeral=True)
            return
        if not metric in wom_metrics:
            await interaction.response.send_message(f'Invalid argument: `METRIC: {metric}`.', ephemeral=True)
            return

        # Get guild info from database
        guild: Guild = await self.bot.get_db_guild(interaction.guild)

        # Calculate start and end datetimes
        now: datetime = datetime.now(UTC)
        start: datetime | str = now + timedelta(days=-now.weekday(), weeks=1)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end: datetime | str = start + timedelta(weeks=1)

        start = start.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        start = start[:len(start)-4] + "Z"

        end = end.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end = end[:len(end)-4] + "Z"
        
        # Create competition
        payload: dict[str, Any] = {"title": competition_title, "metric": metric, "startsAt": start, "endsAt": end, "groupId": guild.wom_group_id, "groupVerificationCode": guild.wom_verification_code}
        url = 'https://api.wiseoldman.net/v2/competitions'
        data = None
        async with self.bot.aiohttp.post(url, json=payload, headers={'x-user-agent': config['wom_user_agent'], 'x-api-key': config['wom_api_key']}) as r:
            if r.status != 201:
                raise CommandError(message=f'Error status: {r.status}.')
            data: Any = await r.json()
            
        competition: Any = data['competition']
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Wise Old Man**', colour=0xff0000)
        embed.add_field(name='Competition', value=competition['title'], inline=False)
        embed.add_field(name='Metric', value=competition['metric'], inline=False)
        embed.add_field(name='Start', value=competition['startsAt'], inline=False)
        embed.add_field(name='End', value=competition['endsAt'], inline=False)
        embed.add_field(name='Link', value=f'https://wiseoldman.net/competitions/{competition["id"]}/participants', inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')

        await interaction.response.send_message(embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(f'{type(error).__name__}: {error}')
        traceback.print_tb(error.__traceback__)

class RandomMetricView(discord.ui.View):
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot

    @discord.ui.button(label='Reroll', style=discord.ButtonStyle.blurple, custom_id='wom_metric_reroll_button')
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Validate permission
        if not interaction.message:
            await interaction.response.send_message('Message not found.', ephemeral=True)
            return
        embed: discord.Embed = interaction.message.embeds[0]
        if not embed.footer.text or not embed.title or not embed.description:
            await interaction.response.send_message('Malformed embed.', ephemeral=True)
            return
        if interaction.user.id != int(embed.footer.text.lower().replace('user id:', '').strip()):
            await interaction.response.send_message('Only the original user of this command can reroll the result.', ephemeral=True)
            return
        # Reroll result
        type: str = interaction.message.embeds[0].title.replace('*', '').lower().strip() if interaction.message and interaction.message.embeds[0].title else ''
        guild: Guild = await self.bot.get_db_guild(interaction.guild)
        exclude: list[str] = await get_excluded_metrics(guild) + ([interaction.message.embeds[0].description] if interaction.message and interaction.message.embeds[0].description else [])
        try:
            metric: str = choose_metric(exclude, type)
        except:
            await interaction.response.send_message('Your result could not be rerolled, because there is no other outcome possible.', ephemeral=True)
            return
        # Update message
        embed: discord.Embed = interaction.message.embeds[0]
        embed.description = metric
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(f'Rerolled metric: `{metric}`', ephemeral=True)

class WOMExcludeModal(discord.ui.Modal, title='Wise Old Man: exclude metrics'):
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    metrics_to_exclude = discord.ui.TextInput(label='Metrics to exclude', placeholder=f'runecrafting, theatre_of_blood_hard_mode', min_length=None, max_length=4000, required=False, style=TextStyle.long)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        metrics_to_exclude: list[str] = [metric.strip().replace(' ', '_') for metric in self.metrics_to_exclude.value.strip().lower().split(',') if metric.strip()]

        # Validation
        for metric in metrics_to_exclude:
            if not metric in wom_metrics:
                await interaction.response.send_message(f'Invalid metric: `{metric}`.', ephemeral=True)
                return

        async with self.bot.async_session() as session:
            guild: Guild = await self.bot.get_db_guild(interaction.guild, session)
            guild.wom_excluded_metrics = ','.join(metrics_to_exclude)
            await session.commit()
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Wise Old Man**', colour=0xff0000)
        embed.add_field(name='Excluded metrics', value=', '.join(metrics_to_exclude) if metrics_to_exclude else 'N/A', inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')

        await interaction.response.send_message(embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

async def get_excluded_metrics(guild: Guild) -> list[str]:
    excluded: str | None = guild.wom_excluded_metrics
    return excluded.split(',') if excluded else []

class Clan(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    def cog_unload(self) -> None:
        pass

    @app_commands.command(name='wom')
    async def wom(self, interaction: discord.Interaction, action: str) -> None:
        '''
        Manage the clan WOM group
        '''
        # Check permissions
        
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'You do not have permission to use this command.', ephemeral=True)
            return
        if interaction.guild and isinstance(interaction.user, discord.Member) and not interaction.user.guild_permissions.administrator and interaction.user.id != config['owner']:
            guild: Guild = await self.bot.get_db_guild(interaction.guild)
            wom_role: discord.Role | None = None
            if guild.wom_role_id:
                wom_role = interaction.guild.get_role(guild.wom_role_id)
            if wom_role is None or not interaction.user.top_role >= wom_role or action in ['setup', 'role', 'exclude']:
                await interaction.response.send_message(f'You do not have permission to use this command.', ephemeral=True)
                return
        # Validation
        if action in ['add', 'remove', 'competition'] and (not guild.wom_group_id or not guild.wom_verification_code):
            await interaction.response.send_message(f'You must setup your WOM group before you can use the `add` and `remove` actions.', ephemeral=True)
            return
        if not action in ['add', 'remove', 'competition', 'setup', 'role', 'skill', 'boss', 'exclude']:
            await interaction.response.send_message(f'Invalid action: `{action}`', ephemeral=True)
            return
        # Perform action
        if action == 'add':
            await self.wom_add(interaction)
        elif action == 'remove':
            await self.wom_remove(interaction)
        elif action == 'competition':
            await self.wom_competition(interaction)
        elif action == 'setup':
            await self.wom_setup(interaction)
        elif action == 'role':
            await self.set_wom_role(interaction)
        elif action == 'skill':
            await self.random_skill(interaction)
        elif action == 'boss':
            await self.random_boss(interaction)
        elif action == 'exclude':
            await self.set_exclude(interaction)
        else:
            await self.wom_setup(interaction)

    @wom.autocomplete('action')
    async def action_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        actions: list[str] = ['add', 'remove', 'competition', 'skill', 'boss']
        admin_actions: list[str] = ['setup', 'role', 'exclude']
        return [
            app_commands.Choice(name=action, value=action)
            for action in actions if current.lower() in action.lower()
        ] + [
            app_commands.Choice(name=action, value=action)
            for action in admin_actions if current.lower() in action.lower() and 
            ((isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator) or interaction.user.id == config['owner'])
        ]

    async def wom_add(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddToWOMModal(self.bot))

    async def wom_remove(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RemoveFromWOMModal(self.bot))

    async def wom_competition(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(WOMCompetitionModal(self.bot))
    
    async def wom_setup(self, interaction: discord.Interaction) -> None:
        # Validation
        if not ((isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator) or interaction.user.id == config['owner']):
            await interaction.response.send_message('Missing permission: `administrator`', ephemeral=True)
            return
        await interaction.response.send_modal(WOMSetupModal(self.bot))

    async def set_wom_role(self, interaction: discord.Interaction) -> None:
        # Set the role required to manage the clan WOM group.
        # Validation
        if not interaction.guild or not ((isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator) or interaction.user.id == config['owner']):
            await interaction.response.send_message('Missing permission: `administrator`', ephemeral=True)
            return
        view = SelectRoleView(self.bot, interaction.guild)
        await interaction.response.send_message('Choose a role to allow management of your clan WOM group:', view=view, ephemeral=True)

    async def random_skill(self, interaction: discord.Interaction):
        # Choose a random skill
        try:
            guild: Guild = await self.bot.get_db_guild(interaction.guild)
            metric: str = choose_metric(await get_excluded_metrics(guild), 'skill')
        except:
            await interaction.response.send_message('Error choosing random skill.', ephemeral=True)
            return
        # Send embed with reroll button
        embed = discord.Embed(title=f'**Skill**', colour=0x00b2ff, description=metric)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')
        view = RandomMetricView(self.bot)
        await interaction.response.send_message(embed=embed, view=view)

    async def random_boss(self, interaction: discord.Interaction) -> None:
        # Choose a random boss
        try:
            guild: Guild = await self.bot.get_db_guild(interaction.guild)
            metric: str = choose_metric(await get_excluded_metrics(guild), 'boss')
        except:
            await interaction.response.send_message('Error choosing random boss.', ephemeral=True)
            return
        # Send embed with reroll button
        embed = discord.Embed(title=f'**Boss**', colour=0x00b2ff, description=metric)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')
        view = RandomMetricView(self.bot)
        await interaction.response.send_message(embed=embed, view=view)

    async def set_exclude(self, interaction: discord.Interaction) -> None:
         await interaction.response.send_modal(WOMExcludeModal(self.bot))

async def setup(bot: Bot) -> None:
    await bot.add_cog(Clan(bot))
