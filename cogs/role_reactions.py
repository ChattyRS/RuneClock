from typing import Iterable, Sequence
import discord
from discord import RawReactionActionEvent, SelectOption, TextStyle, app_commands
from discord.ext.commands import Cog
import traceback
from sqlalchemy import delete, select
from src.bot import Bot
from src.database import Guild, CustomRoleReaction
from src.database_utils import get_db_guild, get_role_reactions
from src.discord_utils import get_guild_text_channel, get_text_channel

class ManagementRoleDropdown(discord.ui.Select):
    def __init__(self, bot: Bot, options: list[SelectOption]) -> None:
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the options
        # The options parameter defines the dropdown options. We defined this above
        self.bot: Bot = bot
        super().__init__(placeholder='Choose a role...', min_values=1, max_values=1, options=options, custom_id='role_react_management_role_select')

    async def callback(self, interaction: discord.Interaction) -> None:
        # Use the interaction object to update the guild role_reaction_management_role_id. 
        # The self object refers to the Select object, 
        # and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        if not interaction.guild:
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        role: discord.Role | None = interaction.guild.get_role(int(self.values[0])) if interaction.guild else None
        if not role:
            await interaction.response.send_message(f'Role not found.', ephemeral=True)
            return
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, interaction.guild)
            guild.role_reaction_management_role_id = role.id
            await session.commit()
        await interaction.response.send_message(f'The custom role-reactions management role has been set to `{role.name}`', ephemeral=True)

class SelectManagementRoleView(discord.ui.View):
    def __init__(self, bot: Bot, guild: discord.Guild) -> None:
        super().__init__()
        self.bot: Bot = bot

        # Get options for role dropdown
        options: list[SelectOption] = [discord.SelectOption(label=role.name, value=str(role.id)) for role in sorted(guild.roles, reverse=True)]
        if len(options) > 25:
            options = options[:25]

        # Adds the dropdown to our view object.
        self.add_item(ManagementRoleDropdown(bot, options))

class AddRoleDropdown(discord.ui.Select):
    def __init__(self, bot: Bot, options: list[SelectOption]) -> None:
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder='Choose a role...', min_values=1, max_values=1, options=options, custom_id='role_react_add_role_select')
        self.bot: Bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        # Use the interaction object to create a custom role-reaction. 
        # The self object refers to the Select object, 
        # and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        if not interaction.message:
            await interaction.response.send_message(f'Message not found', ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != self.bot.config['owner']:
            async with self.bot.get_session() as session:
                guild: Guild = await get_db_guild(session, interaction.guild)
            role_reaction_management_role = None
            if guild.role_reaction_management_role_id:
                role_reaction_management_role: discord.Role | None = interaction.guild.get_role(guild.role_reaction_management_role_id)
            if not role_reaction_management_role or not interaction.user.top_role >= role_reaction_management_role:
                await interaction.response.send_message(f'You do not have permission to use this command.', ephemeral=True)
                return
        role: discord.Role | None = interaction.guild.get_role(int(self.values[0]))
        if not role:
            await interaction.response.send_message(f'Role not found.', ephemeral=True)
            return
        
        await interaction.response.defer()
        
        interaction.message = await interaction.message.fetch() # This is required to fetch the reactions
        if not interaction.message.reactions:
            await interaction.followup.send(f'Please react to the message with an emoji before selecting your role.')
            return
        emoji: discord.PartialEmoji | discord.Emoji | str = interaction.message.reactions[0].emoji
        if isinstance(emoji, str) or not hasattr(emoji, 'guild') or not hasattr(emoji, 'id') or not emoji.guild in self.bot.guilds or not emoji.is_usable(): # type: ignore
            await interaction.followup.send(f'Please choose a **custom** emoji that is available to this bot, or add me to the server that this emoji is from: {emoji}.')
            return
        async with self.bot.get_session() as session:
            session.add(CustomRoleReaction(guild_id=interaction.guild.id, emoji_id=emoji.id, role_id=role.id))
            await session.commit()
        await interaction.followup.send(f'Role-reaction added successfully for emoji {emoji} and role `{role.name}`.')

class SelectAddRoleReactionView(discord.ui.View):
    def __init__(self, bot: Bot, guild: discord.Guild) -> None:
        super().__init__()
        self.bot: Bot = bot

        # Get options for role dropdown
        options: list[SelectOption] = [discord.SelectOption(label=role.name, value=str(role.id)) for role in sorted(guild.roles, reverse=True)]
        if len(options) > 25:
            options = options[:25]

        # Adds the dropdown to our view object.
        self.add_item(AddRoleDropdown(self.bot, options))

class RemoveRoleReactionDropdown(discord.ui.Select):
    def __init__(self, bot: Bot, options: list[SelectOption]) -> None:
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder='Choose a role-reaction...', min_values=1, max_values=1, options=options, custom_id='role_react_remove_role_select')
        self.bot: Bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        # Use the interaction object to remove the role-reaction.
        # The self object refers to the Select object, 
        # and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        async with self.bot.get_session() as session:
            if not interaction.user.guild_permissions.administrator and interaction.user.id != self.bot.config['owner']:
                guild: Guild = await get_db_guild(session, interaction.guild)
                role_reaction_management_role = None
                if guild.role_reaction_management_role_id:
                    role_reaction_management_role: discord.Role | None = interaction.guild.get_role(guild.role_reaction_management_role_id)
                if not role_reaction_management_role or not interaction.user.top_role >= role_reaction_management_role:
                    await interaction.response.send_message(f'You do not have permission to use this command.', ephemeral=True)
                    return
            await session.execute(delete(CustomRoleReaction).where(CustomRoleReaction.id == int(self.values[0])))
            await session.commit()
        await interaction.response.send_message(f'Role-reaction with ID {int(self.values[0])} deleted successfully.')

class SelectRemoveRoleReactionView(discord.ui.View):
    def __init__(self, bot: Bot, guild: discord.Guild, role_reactions: Iterable[CustomRoleReaction]) -> None:
        super().__init__()
        self.bot: Bot = bot

        # Get options for role-reactions dropdown
        options: list[SelectOption] = []
        for reaction in role_reactions:
            emoji: discord.Emoji | int | None = discord.utils.get(guild.emojis, id=reaction.emoji_id)
            if not emoji:
                emoji = reaction.emoji_id
            role: discord.Role | int | None = discord.utils.get(guild.roles, id=reaction.role_id)
            if not role:
                role = reaction.role_id
            options.append(discord.SelectOption(label=f'{emoji}: {role.name if isinstance(role, discord.Role) else role}', value=str(reaction.id)))
        if len(options) > 25:
            options = options[:25]

        # Adds the dropdown to our view object.
        self.add_item(RemoveRoleReactionDropdown(self.bot, options))

class ChannelDropdown(discord.ui.Select):
    def __init__(self, bot: Bot, options: list[SelectOption]) -> None:
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder='Choose a channel...', min_values=1, max_values=1, options=options, custom_id='role_react_channel_select')
        self.bot: Bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        # Use the interaction object to set the custom_role_reaction_channel_id. 
        # The self object refers to the Select object, 
        # and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, interaction.guild)
            if not interaction.user.guild_permissions.administrator and interaction.user.id != self.bot.config['owner']:
                role_reaction_management_role = None
                if guild.role_reaction_management_role_id:
                    role_reaction_management_role: discord.Role | None = interaction.guild.get_role(guild.role_reaction_management_role_id)
                if not role_reaction_management_role or not interaction.user.top_role >= role_reaction_management_role:
                    await interaction.response.send_message(f'You do not have permission to use this command.', ephemeral=True)
                    return
            channel: discord.TextChannel = get_guild_text_channel(interaction.guild, int(self.values[0]))

            guild.custom_role_reaction_channel_id = channel.id
            await session.commit()
        await interaction.response.send_message(f'The role-reaction channel was set to {channel.mention}.')

class SelectChannelView(discord.ui.View):
    def __init__(self, bot: Bot, guild: discord.Guild) -> None:
        super().__init__()
        self.bot: Bot = bot

        # Get options for channel dropdown
        options: list[SelectOption] = [discord.SelectOption(label=channel.name, value=str(channel.id)) for channel in guild.text_channels]
        if len(options) > 25:
            options = options[:25]

        # Adds the dropdown to our view object.
        self.add_item(ChannelDropdown(self.bot, options))

class SetMessageModal(discord.ui.Modal, title='Role-reactions: message'):
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    custom_message = discord.ui.TextInput(label='Custom message', placeholder="Message...", min_length=1, max_length=1000, required=True, style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        
        custom_message: str = self.custom_message.value.strip()

        # Validation
        if not custom_message:
            await interaction.response.send_message(f'Required argument missing: `CUSTOM MESSAGE`.', ephemeral=True)
            return

        # Set message
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, interaction.guild)
            guild.custom_role_reaction_message = custom_message
            await session.commit()
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Role-reactions**', colour=0x00e400)
        embed.add_field(name='Custom message', value=custom_message, inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class RoleReactions(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent) -> None:
        '''
        Adds roles to users when receiving reactions

        Args:
            payload (RawReactionActionEvent): The reaction payload
        '''
        channel: discord.TextChannel = get_text_channel(self.bot, payload.channel_id)

        if not channel or not channel.guild:
            return

        emoji: discord.PartialEmoji = payload.emoji
        if not hasattr(emoji, 'id'):
            return
        
        message: discord.Message = await channel.fetch_message(payload.message_id)
        if message.author != self.bot.user:
            return

        user: discord.Member = await channel.guild.fetch_member(payload.user_id)
        if not user or user.bot:
            return

        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, payload.guild_id)
        if not guild or not guild.custom_role_reaction_channel_id == channel.id:
            return

        async with self.bot.get_session() as session:
            role_reaction: CustomRoleReaction | None = (await session.execute(select(CustomRoleReaction).where(CustomRoleReaction.guild_id == guild.id, CustomRoleReaction.emoji_id == emoji.id))).scalar_one_or_none()
        if role_reaction:
            role: discord.Role | None = discord.utils.get(channel.guild.roles, id=role_reaction.role_id)
            if role:
                try:
                    await user.add_roles(role)
                except discord.Forbidden:
                    pass
    
    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent) -> None:
        '''
        Removes roles from users when receiving reactions

        Args:
            payload (RawReactionActionEvent): The reaction payload
        '''
        channel: discord.TextChannel = get_text_channel(self.bot, payload.channel_id)

        if not channel or not channel.guild:
            return

        emoji: discord.PartialEmoji = payload.emoji
        if not hasattr(emoji, 'id'):
            return

        message: discord.Message = await channel.fetch_message(payload.message_id)
        if message.author != self.bot.user:
            return

        user: discord.Member = await channel.guild.fetch_member(payload.user_id)
        if not user or user.bot:
            return
        
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, payload.guild_id)
        if not guild or not guild.custom_role_reaction_channel_id == channel.id:
            return

        async with self.bot.get_session() as session:
            role_reaction: CustomRoleReaction | None = (await session.execute(select(CustomRoleReaction).where(CustomRoleReaction.guild_id == guild.id, CustomRoleReaction.emoji_id == emoji.id))).scalar_one_or_none()
        if role_reaction:
            role: discord.Role | None = discord.utils.get(channel.guild.roles, id=role_reaction.role_id)
            if role:
                try:
                    await user.remove_roles(role)
                except discord.Forbidden:
                    pass

    @app_commands.command(name='reactions')
    async def reactions(self, interaction: discord.Interaction, action: str) -> None:
        '''
        Manage role reactions
        '''
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != self.bot.config['owner']:
            async with self.bot.get_session() as session:
                guild: Guild = await get_db_guild(session, interaction.guild)
            role_reaction_management_role = None
            if guild.role_reaction_management_role_id:
                role_reaction_management_role: discord.Role | None = interaction.guild.get_role(guild.role_reaction_management_role_id)
            if not role_reaction_management_role or not interaction.user.top_role >= role_reaction_management_role:
                await interaction.response.send_message(f'You do not have permission to use this command.', ephemeral=True)
                return
        # Validation
        if not action in ['view', 'add', 'remove', 'channel', 'message', 'send', 'role']:
            await interaction.response.send_message(f'Invalid action: {action}', ephemeral=True)
            return
        if action == 'add':
            await self.add(interaction)
        elif action == 'remove':
            await self.remove(interaction)
        elif action == 'channel':
            await self.set_channel(interaction)
        elif action == 'message':
            await self.set_message(interaction)
        elif action == 'send':
            await self.send_custom_message(interaction)
        elif action =='role':
            await self.set_role_reaction_management_role(interaction)
        else:
            await self.view(interaction)
    
    @reactions.autocomplete('action')
    async def action_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        actions: list[str] = ['view', 'add', 'remove', 'channel', 'message', 'send']
        admin_actions: list[str] = ['role']
        return [
            app_commands.Choice(name=action, value=action)
            for action in actions if current.lower() in action.lower()
        ] + [
            app_commands.Choice(name=action, value=action)
            for action in admin_actions if current.lower() in action.lower() and 
            ((isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator) or interaction.user.id == self.bot.config['owner'])
        ]

    async def view(self, interaction: discord.Interaction) -> None:
        # Get the role reactions
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        async with self.bot.get_session() as session:
            reactions: Sequence[CustomRoleReaction] = await get_role_reactions(session, interaction.guild.id)
        lines: list[str] = []
        for reaction in reactions:
            emoji: discord.Emoji | int | None = discord.utils.get(interaction.guild.emojis, id=reaction.emoji_id)
            if not emoji:
                emoji = reaction.emoji_id
            role: discord.Role | str | int | None = discord.utils.get(interaction.guild.roles, id=reaction.role_id)
            if not role:
                role = reaction.role_id
            else:
                role = role.mention
            lines.append(f'{reaction.id}: {emoji} {role}')
        txt: str = '\n'.join(lines)
        if not txt:
            txt = 'No custom role-reactions found.'

        embed = discord.Embed(title=f'**Custom role-reactions**', description=txt, colour=0x00b2ff)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    async def add(self, interaction: discord.Interaction) -> None:
        # Add a custom role reaction
        # Validation
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        async with self.bot.get_session() as session:
            reactions: Sequence[CustomRoleReaction] = await get_role_reactions(session, interaction.guild.id)
        if len(reactions) >= 20:
            await interaction.response.send_message('You can only have 20 unique custom role-reactions per guild. You will have to remove one first if you want to add another.', ephemeral=True)
            return
        view = SelectAddRoleReactionView(self.bot, interaction.guild)
        await interaction.response.send_message('React to this message with an emoji, and then select a role to create your role-reaction:', view=view)
    
    async def remove(self, interaction: discord.Interaction):
        # Remove a custom role reaction
        # Validation
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        async with self.bot.get_session() as session:
            reactions: Sequence[CustomRoleReaction] = await get_role_reactions(session, interaction.guild.id)
        if len(reactions) < 1:
            await interaction.response.send_message('There are no role-reactions to remove.', ephemeral=True)
            return
        view = SelectRemoveRoleReactionView(self.bot, interaction.guild, reactions)
        await interaction.response.send_message('Choose a role-reaction to remove:', view=view)
    
    async def set_channel(self, interaction: discord.Interaction) -> None:
        # Choose the role-reaction channel
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        view = SelectChannelView(self.bot, interaction.guild)
        await interaction.response.send_message('Choose a channel for your role-reactions:', view=view)
    
    async def set_message(self, interaction: discord.Interaction) -> None:
        # Set the role-reaction message
        await interaction.response.send_modal(SetMessageModal(self.bot))
    
    async def send_custom_message(self, interaction: discord.Interaction) -> None:
        # Sends the configured role-reaction message to the configured role-reaction channel
        # Validation
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        async with self.bot.get_session() as session:
            reactions: Sequence[CustomRoleReaction] = await get_role_reactions(session, interaction.guild.id)
        if len(reactions) < 1:
            await interaction.response.send_message('There are no role-reactions for this server.', ephemeral=True)
            return
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, interaction.guild)
        if not guild or not guild.custom_role_reaction_channel_id:
            await interaction.response.send_message('There is no custom role-reaction channel configured for this server.', ephemeral=True)
            return
        channel: discord.TextChannel = get_guild_text_channel(interaction.guild, guild.custom_role_reaction_channel_id)
        # Create the message
        msg: str = ''
        if guild.custom_role_reaction_message:
            msg = guild.custom_role_reaction_message + '\n\n'
        lines: list[str] = []
        for reaction in reactions:
            emoji: discord.Emoji | None = discord.utils.get(interaction.guild.emojis, id=reaction.emoji_id)
            if not emoji:
                await interaction.response.send_message(f'Emoji was not found for role-reaction with ID `{reaction.id}`: {reaction.emoji_id}', ephemeral=True)
                return
            role: discord.Role | None = discord.utils.get(interaction.guild.roles, id=reaction.role_id)
            if not role:
                await interaction.response.send_message(f'Role was not found for role-reaction with ID `{reaction.id}`: {reaction.role_id}', ephemeral=True)
                return
            lines.append(f'{emoji} {role.name}')
        msg += '\n'.join(lines)
        await interaction.response.send_message(f'The role-reaction message is being sent to channel {channel.mention}.', ephemeral=True)
        try:
            message: discord.Message = await channel.send(msg)
            for r in reactions:
                emoji = discord.utils.get(interaction.guild.emojis, id=r.emoji_id)
                await message.add_reaction(emoji) # type: ignore
        except discord.Forbidden:
            pass
    
    async def set_role_reaction_management_role(self, interaction: discord.Interaction) -> None:
        # Set the role required to manage custom role reactions.
        # Validation
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This dropdown can only be used in a server.', ephemeral=True)
            return
        if not (interaction.user.guild_permissions.administrator or interaction.user.id == self.bot.config['owner']):
            await interaction.response.send_message('Missing permission: `administrator`', ephemeral=True)
            return
        view = SelectManagementRoleView(self.bot, interaction.guild)
        await interaction.response.send_message('Choose a role to allow management of your role-reactions:', view=view, ephemeral=True)


async def setup(bot: Bot) -> None:
    await bot.add_cog(RoleReactions(bot))
