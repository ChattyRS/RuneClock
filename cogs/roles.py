from typing import Callable, Sequence
import discord
from discord import Emoji, app_commands
from discord.ext import commands
from discord.ext.commands import Cog, CommandError
from sqlalchemy import select
from src.bot import Bot
from src.database import Guild, Role
import random
from src.checks import is_admin
from src.database_utils import get_db_guild
from src.discord_utils import send_lines_over_multiple_embeds
from src.number_utils import is_int
import re
from src.runescape_utils import dnd_names

class Roles(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @commands.command(pass_context=True)
    @is_admin()
    async def manageroles(self, ctx: commands.Context, *, channel: discord.TextChannel | None) -> None:
        '''
        Changes server's role management channel. (Admin+)
        Arguments: channel.
        If no channel is given, roles will no longer be managed.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise CommandError('This command can only be used in a server.')

        if not channel:
            async with self.bot.get_session() as session:
                guild: Guild = await get_db_guild(session, ctx.guild)
                if not guild.role_channel_id:
                    raise commands.CommandError(message=f'Required argument missing: `channel`.')
                guild.role_channel_id = None
                await session.commit()
            await ctx.send(f'I will no longer manage roles on server **{ctx.guild.name}**.')
            return

        permissions: discord.Permissions = discord.Permissions.none()
        colour: discord.Colour = discord.Colour.default()
        role_names: list[str] = []
        for role in ctx.guild.roles:
            role_names.append(role.name.upper())
        for rank in dnd_names:
            if not rank.upper() in role_names:
                try:
                    await ctx.guild.create_role(name=rank, permissions=permissions, colour=colour, hoist=False, mentionable=True)
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `create_roles`.')

        msg = "React to this message with any of the following emoji to be added to the corresponding role for notifications:\n\n"
        notif_emojis: list[Emoji] = []
        for r in dnd_names:
            emojiID = self.bot.config[f'{r.lower()}EmojiID']
            e: Emoji | None = self.bot.get_emoji(emojiID)
            if e:
                notif_emojis.append(e)
                msg += str(e) + ' ' + r + '\n'
        msg += "\nIf you wish to stop receiving notifications, simply remove your reaction. If your reaction isn't there anymore, then you can add a new one and remove it."
        try:
            message: discord.Message = await channel.send(msg)
            for e in notif_emojis:
                await message.add_reaction(e)
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `send_message / add_reaction`.')
        
        async with self.bot.get_session() as session:
            guild: Guild = await get_db_guild(session, ctx.guild)
            guild.role_channel_id = channel.id
            await session.commit()

        await ctx.send(f'The role management channel for server **{ctx.guild.name}** has been changed to {channel.mention}.')

    @commands.command(pass_context=True)
    async def rank(self, ctx: commands.Context, *, rank: str) -> None:
        '''
        Toggles the given rank.
        Arguments: rank
        Constraints: You can only assign yourself the ranks as shown by the `ranks` command.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise CommandError('This command can only be used in a server.')

        if not rank:
            raise commands.CommandError(message=f'Required argument missing: `rank`.')
        valid_rank = False
        rank = rank[0].upper() + rank[1:].lower()
        for r in dnd_names:
            if rank in r:
                valid_rank = True
                break
        if not valid_rank:
            async with self.bot.get_session() as session:
                db_role: Role | None = (await session.execute(select(Role).where(Role.guild_id == ctx.guild.id, Role.name == rank.lower()))).scalar_one_or_none()
            if not db_role:
                raise commands.CommandError(message=f'Could not find rank: `{rank}`.')
            role: discord.Role | None = ctx.guild.get_role(db_role.role_id)
        else:
            role = discord.utils.find(lambda x: x.name.lower() in rank.lower(), ctx.guild.roles)
        if not role:
            raise commands.CommandError(message=f'Could not find role: `{rank}`.')
        if not role in ctx.author.roles:
            try:
                await ctx.author.add_roles(role)
                await ctx.send(f'{ctx.author.mention}, you joined **{role.name}**.')
            except discord.Forbidden:
                raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')
        else:
            try:
                await ctx.author.remove_roles(role)
                await ctx.send(f'{ctx.author.mention}, you left **{role.name}**.')
            except discord.Forbidden:
                raise commands.CommandError(message=f'Missing permissions: `manage_roles`.')

    @commands.command(pass_context=True)
    @is_admin()
    async def addrank(self, ctx: commands.Context, *, rank: str) -> None:
        '''
        Creates a joinable rank. (Admin+)
        Arguments: rank
        If an existing role is given, the role will be made joinable.
        Otherwise, a joinable role with the given name will be created.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise CommandError('This command can only be used in a server.')

        if not rank:
            raise commands.CommandError(message=f'Required argument missing: `rank`.')
        if len(rank) <= 1:
            raise commands.CommandError(message=f'Invalid argument: `{rank}`.')
        rank = rank[0].upper() + rank[1:].lower()
        
        role: discord.Role | None = discord.utils.find(lambda r: r.name.lower() == rank.lower(), ctx.guild.roles)
        if not role:
            try:
                role = await ctx.guild.create_role(name=rank, mentionable=True)
            except discord.Forbidden:
                raise commands.CommandError(message=f'Missing permissions: `create_roles`.')
        
        async with self.bot.get_session() as session:
            db_role: Role | None = (await session.execute(select(Role).where(Role.guild_id == ctx.guild.id, Role.name == rank.lower()))).scalar_one_or_none()
            if db_role:
                raise commands.CommandError(message=f'Rank {rank.lower()} already exists.')
            session.add(Role(guild_id=ctx.guild.id, name=rank.lower(), role_id=role.id))
            await session.commit()
        
        await ctx.send(f'Added rank **{rank}**.')

    @commands.command(pass_context=True, aliases=['removerank'])
    @is_admin()
    async def delrank(self, ctx: commands.Context, *, rank: str) -> None:
        '''
        Removes a joinable rank. (Admin+)
        Arguments: rank
        Note: the role will not be removed, it just won't be joinable anymore.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise CommandError('This command can only be used in a server.')

        if not rank:
            raise commands.CommandError(message=f'Required argument missing: `rank`.')
        
        async with self.bot.get_session() as session:
            db_role: Role | None = (await session.execute(select(Role).where(Role.guild_id == ctx.guild.id, Role.name == rank.lower()))).scalar_one_or_none()
            if not db_role:
                raise commands.CommandError(message=f'Could not find rank: `{rank}`.')
            
            await session.delete(db_role)
            await session.commit()
        
        await ctx.send(f'Removed rank **{rank}**.')

    @commands.command(pass_context=True)
    async def ranks(self, ctx: commands.Context) -> None:
        '''
        Get the list of joinable ranks.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            raise CommandError('This command can only be used in a server.')

        async with self.bot.get_session() as session:
            db_roles: Sequence[Role] = (await session.execute(select(Role).where(Role.guild_id == ctx.guild.id))).scalars().all()
        if not db_roles:
            raise commands.CommandError(message=f'Error: This server does not have any ranks.')

        guild_ranks: list[discord.Role] = []
        for db_role in db_roles:
            role: discord.Role | None = ctx.guild.get_role(db_role.role_id)
            if role:
                guild_ranks.append(role)
        for rank in dnd_names:
            role = discord.utils.find(lambda r: r.name.lower() == rank.lower(), ctx.guild.roles)
            if role:
                guild_ranks.append(role)
        
        if not guild_ranks:
            raise commands.CommandError(message=f'Error: This server does not have any ranks.')

        msg: str = ''

        chars: int = max([len(role.name) for role in guild_ranks])+1
        counts: list[int] = [len(role.members) for role in guild_ranks]
        
        count_chars: int = max([len(str(i)) for i in counts])+1
        for i, role in enumerate(guild_ranks):
            count: int = counts[i]
            msg += role.name + (chars - len(role.name))*' ' + str(count) + (count_chars - len(str(count)))*' ' + 'members\n'
        msg = msg.strip()

        await ctx.send(f'```{msg}```')

    @commands.command(pass_context=True, aliases=['randomcolor'])
    async def randomcolour(self, ctx: commands.Context) -> None:
        '''
        Generates a random hex colour.
        '''
        self.bot.increment_command_counter()

        r: Callable[[], int] = lambda: random.randint(0,255)
        r1: int = r()
        r2: int = r()
        r3: int = r()
        colour: str = '%02X%02X%02X' % (r1, r2, r3)
        embed = discord.Embed(colour=discord.Colour(int(colour, 16)))
        embed.add_field(name='Hex', value=f'#{colour}', inline=False)
        embed.add_field(name='RGB', value=f'{r1}, {r2}, {r3}', inline=False)
        await ctx.send(embed=embed)

    @commands.command(pass_context=True)
    @is_admin()
    async def addrole(self, ctx: commands.Context, *, role_name: str) -> None:
        '''
        Add a role to the server. (Admin+)
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        if not ctx.guild:
            raise CommandError('This command can only be used in a server.')

        if not role_name:
            raise commands.CommandError(message=f'Required argument missing: `role_name`.')
        role_name = ' '.join(role_name)
        
        for r in ctx.guild.roles:
            if r.name.upper() == role_name.upper():
                raise commands.CommandError(message=f'Role already exists: `{role_name}`.')
        
        try:
            await ctx.guild.create_role(name=role_name)
            await ctx.send(f'Created role **{role_name}**.')
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `create_roles`.')

    @commands.command(pass_context=True, aliases=['removerole'])
    @is_admin()
    async def delrole(self, ctx: commands.Context, *, role: discord.Role) -> None:
        '''
        Delete a role from the server. (Admin+)
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        try:
            await role.delete()
            await ctx.send(f'Deleted role **{role.name}**.')
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `delete_roles`.')

    @commands.command(pass_context=True)
    async def members(self, ctx: commands.Context, *, role: discord.Role) -> None:
        '''
        List members in a role.
        '''
        self.bot.increment_command_counter()

        embed = discord.Embed(title=f'Members in {role.name} ({len(role.members)})', colour=0x00b2ff)
        await send_lines_over_multiple_embeds(ctx, [m.mention for m in role.members], embed)

    @commands.command(pass_context=True)
    async def roles(self, ctx: commands.Context) -> None:
        '''
        Get a list of roles and member counts.
        '''
        self.bot.increment_command_counter()

        if not ctx.guild:
            raise CommandError('This command can only be used in a server.')
        
        embed = discord.Embed(title=f'Roles in {ctx.guild.name} ({len(ctx.guild.roles)})', colour=0x00b2ff)
        await send_lines_over_multiple_embeds(ctx, [f'{role.mention} ({len(role.members)})' for role in ctx.guild.roles], embed)

    @app_commands.command()
    async def mention(self, interaction: discord.Interaction, role: str) -> None:
        '''
        Mention all online or idle users with the given role.
        '''
        if not role or not is_int(role):
            await interaction.response.send_message(f'Invalid argument `role: "{role}"`', ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message(f'This command can only be used in a server', ephemeral=True)
            return
        disc_role: discord.Role | None = interaction.guild.get_role(int(role))
        if not disc_role:
            await interaction.response.send_message(f'Role not found: {role}', ephemeral=True)
            return

        members: list[discord.Member] = [m for m in interaction.guild.members if disc_role in m.roles and str(m.status) in ['online', 'idle']]
        mentions: str = ' '.join([m.mention for m in members])
        if not mentions:
            mentions = f'`No online members found.`'

        await interaction.response.send_message(f'**Online members of role {disc_role.name}:**\n{mentions}')

    @mention.autocomplete('role')
    async def role_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        roles: list[discord.Role] = [r for r in (interaction.guild.roles if interaction.guild else []) if current.upper() in r.name.upper()]
        # filter out role names that cannot be displayed
        roles = [r for r in roles if not re.match(r'^[A-z0-9 -]+$', r.name) is None]
        roles = roles[:25] if len(roles) > 25 else roles
        return [app_commands.Choice(name=r.name, value=str(r.id)) for r in roles]


async def setup(bot: Bot):
    await bot.add_cog(Roles(bot))
