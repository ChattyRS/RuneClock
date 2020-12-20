import discord
from discord.ext import commands
from main import config_load, addCommand, Guild, Role
import sys
sys.path.append('../')
import random
from datetime import datetime, timedelta, timezone
from utils import is_owner, is_admin, portables_admin, is_mod, is_rank, is_smiley, portables_only

config = config_load()

ranks = ['Warbands', 'Amlodd', 'Hefin', 'Ithell', 'Trahaearn', 'Meilyr', 'Crwys',
         'Cadarn', 'Iorwerth', 'Cache', 'Sinkhole', 'Yews', 'Goebies', 'Merchant',
         'Spotlight', 'PinkSkirts']

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True)
    @is_admin()
    async def manageroles(self, ctx, channel=''):
        '''
        Changes server's role management channel. (Admin+)
        Arguments: channel.
        If no channel is given, roles will no longer be managed.
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if ctx.message.channel_mentions:
            channel = ctx.message.channel_mentions[0]
        elif channel:
            found = False
            for c in ctx.guild.text_channels:
                if channel.upper() in c.name.upper():
                    channel = c
                    found = True
                    break
            if not found:
                raise commands.CommandError(message=f'Could not find channel: `{channel}`.')
        else:
            guild = await Guild.get(ctx.guild.id)
            if guild.role_channel_id:
                await guild.update(role_channel_id=None).apply()
                await ctx.send(f'I will no longer manage roles on server **{ctx.guild.name}**.')
                return
            else:
                raise commands.CommandError(message=f'Required argument missing: `channel`.')

        permissions = discord.Permissions.none()
        colour = discord.Colour.default()
        roleNames = []
        for role in ctx.guild.roles:
            roleNames.append(role.name.upper())
        for rank in ranks:
            if not rank.upper() in roleNames:
                try:
                    await ctx.guild.create_role(name=rank, permissions=permissions, colour=colour, hoist=False, mentionable=True)
                except discord.Forbidden:
                    raise commands.CommandError(message=f'Missing permissions: `create_roles`.')

        msg = "React to this message with any of the following emoji to be added to the corresponding role for notifications:\n\n"
        notifEmojis = []
        for r in ranks:
            emojiID = config[f'{r.lower()}EmojiID']
            e = self.bot.get_emoji(emojiID)
            notifEmojis.append(e)
            msg += str(e) + ' ' + r + '\n'
        '''
        if ctx.guild.id == config['portablesServer']:
            emoji_ids = [config['fletcher_emoji'], config['crafter_emoji'], config['brazier_emoji'], config['sawmill_emoji'], config['range_emoji'], config['well_emoji']]
            for emoji_id in emoji_ids:
                e = self.bot.get_emoji(emoji_id)
                msg += str(e) + ' ' + e.name + '\n'
                notifEmojis.append(e)
        '''
        msg += "\nIf you wish to stop receiving notifications, simply remove your reaction. If your reaction isn't there anymore, then you can add a new one and remove it."
        try:
            message = await channel.send(msg)
            for e in notifEmojis:
                await message.add_reaction(e)
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `send_message / add_reaction`.')

        guild = await Guild.get(ctx.guild.id)
        await guild.update(role_channel_id=channel.id).apply()

        await ctx.send(f'The role management channel for server **{ctx.guild.name}** has been changed to {channel.mention}.')

    @commands.command(pass_context=True)
    async def rank(self, ctx, *rank):
        '''
        Toggles the given rank.
        Arguments: rank
        Constraints: You can only assign yourself the ranks as shown by the `ranks` command.
        '''
        addCommand()

        guild = ctx.guild
        if not rank:
            raise commands.CommandError(message=f'Required argument missing: `rank`.')
        rank = ' '.join(rank)
        validRank = False
        rank = rank[0].upper() + rank[1:].lower()
        for r in ranks:
            if rank in r:
                validRank = True
                break
        if not validRank:
            db_role = await Role.query.where(Role.guild_id==ctx.guild.id).where(Role.name==rank.lower()).gino.first()
            if not db_role:
                raise commands.CommandError(message=f'Could not find rank: `{rank}`.')
            role = ctx.guild.get_role(db_role.role_id)
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
    async def addrank(self, ctx, *rank):
        '''
        Creates a joinable rank. (Admin+)
        Arguments: rank
        If an existing role is given, the role will be made joinable.
        Otherwise, a joinable role with the given name will be created.
        '''
        addCommand()

        if not rank:
            raise commands.CommandError(message=f'Required argument missing: `rank`.')
        rank = ' '.join(rank)
        if len(rank) <= 1:
            raise commands.CommandError(message=f'Invalid argument: `{rank}`.')
        rank = rank[0].upper() + rank[1:].lower()
        
        role = discord.utils.find(lambda r: r.name.lower() == rank.lower(), ctx.guild.roles)
        if not role:
            try:
                role = await ctx.guild.create_role(name=rank, mentionable=True)
            except discord.Forbidden:
                raise commands.CommandError(message=f'Missing permissions: `create_roles`.')
        
        db_role = await Role.query.where(Role.guild_id==ctx.guild.id).where(Role.name==rank.lower()).gino.first()
        if db_role:
            raise commands.CommandError(message=f'Rank {rank.lower()} already exists.')
        await Role.create(guild_id=ctx.guild.id, name=rank.lower(), role_id=role.id)
        
        await ctx.send(f'Added rank **{rank}**.')

    @commands.command(pass_context=True, aliases=['removerank'])
    @is_admin()
    async def delrank(self, ctx, *rank):
        '''
        Removes a joinable rank. (Admin+)
        Arguments: rank
        Note: the role will not be removed, it just won't be joinable anymore.
        '''
        addCommand()

        if not rank:
            raise commands.CommandError(message=f'Required argument missing: `rank`.')
        rank = ' '.join(rank)
        
        db_role = await Role.query.where(Role.guild_id==ctx.guild.id).where(Role.name==rank.lower()).gino.first()
        if not db_role:
            raise commands.CommandError(message=f'Could not find rank: `{rank}`.')
        
        await db_role.delete()
        
        await ctx.send(f'Removed rank **{rank}**.')

    @commands.command(pass_context=True)
    async def ranks(self, ctx):
        '''
        Get the list of joinable ranks.
        '''
        addCommand()

        db_roles = await Role.query.where(Role.guild_id==ctx.guild.id).gino.all()
        if not db_roles:
            raise commands.CommandError(message=f'Error: This server does not have any ranks.')

        guild_ranks = []
        for db_role in db_roles:
            role = ctx.guild.get_role(db_role.role_id)
            if role:
                guild_ranks.append(role)
        for rank in ranks:
            role = discord.utils.find(lambda r: r.name.lower() == rank.lower(), ctx.guild.roles)
            if role:
                guild_ranks.append(role)
        
        if not guild_ranks:
            raise commands.CommandError(message=f'Error: This server does not have any ranks.')

        msg = ''

        chars = max([len(role.name) for role in guild_ranks])+1
        counts = [len(role.members) for role in guild_ranks]
        
        count_chars = max([len(str(i)) for i in counts])+1
        for i, role in enumerate(guild_ranks):
            count = counts[i]
            msg += role.name + (chars - len(role.name))*' ' + str(count) + (count_chars - len(str(count)))*' ' + 'members\n'
        msg = msg.strip()

        await ctx.send(f'```{msg}```')

    @commands.command(pass_context=True, aliases=['randomcolor'])
    async def randomcolour(self, ctx):
        '''
        Generates a random hex colour.
        '''
        addCommand()

        r = lambda: random.randint(0,255)
        r1 = r()
        r2 = r()
        r3 = r()
        colour = '%02X%02X%02X' % (r1, r2, r3)
        embed = discord.Embed(colour=discord.Colour(int(colour, 16)))
        embed.add_field(name='Hex', value=f'#{colour}', inline=False)
        embed.add_field(name='RGB', value=f'{r1}, {r2}, {r3}', inline=False)
        await ctx.send(embed=embed)

    @commands.command(pass_context=True)
    @is_admin()
    async def addrole(self, ctx, *roleName):
        '''
        Add a role to the server. (Admin+)
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not roleName:
            raise commands.CommandError(message=f'Required argument missing: `role_name`.')
        roleName = ' '.join(roleName)
        
        for r in ctx.guild.roles:
            if r.name.upper() == roleName.upper():
                raise commands.CommandError(message=f'Role already exists: `{roleName}`.')
        
        try:
            await ctx.guild.create_role(name=roleName)
            await ctx.send(f'Created role **{roleName}**.')
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `create_roles`.')

    @commands.command(pass_context=True, aliases=['removerole'])
    @is_admin()
    async def delrole(self, ctx, *roleName):
        '''
        Delete a role from the server. (Admin+)
        '''
        addCommand()
        await ctx.channel.trigger_typing()

        if not roleName:
            raise commands.CommandError(message=f'Required argument missing: `role`.')
        roleName = ' '.join(roleName)
        
        role = discord.utils.find(lambda r: r.name.upper() == roleName.upper(), ctx.guild.roles)
        if not role:
            raise commands.CommandError(message=f'Could not find role: `{roleName}`.')
        try:
            await role.delete()
            await ctx.send(f'Deleted role **{roleName}**.')
        except discord.Forbidden:
            raise commands.CommandError(message=f'Missing permissions: `delete_roles`.')

    @commands.command(pass_context=True)
    async def members(self, ctx, *roleName):
        '''
        List members in a role.
        '''
        addCommand()

        if not roleName:
            raise commands.CommandError(message=f'Required argument missing: `role`.')
        roleName = ' '.join(roleName)
        
        role = discord.utils.find(lambda r: r.name.upper() == roleName.upper(), ctx.guild.roles)
        if not role:
            role = discord.utils.find(lambda r: roleName.upper() in r.name.upper(), ctx.guild.roles)
        if not role:
            raise commands.CommandError(message=f'Could not find role: `{roleName}`.')

        txt = ''
        for m in role.members:
            if len(txt + m.mention) + 5 > 2048:
                txt += '\n...'
                break
            else:
                txt += m.mention + '\n'
        txt = txt.strip()

        embed = discord.Embed(title=f'Members in {roleName} ({len(role.members)})', colour=0x00b2ff, description=txt)

        await ctx.send(embed=embed)

    @commands.command(pass_context=True)
    async def roles(self, ctx):
        '''
        Get a list of roles and member counts.
        '''
        addCommand()

        msg = ''
        chars = max([len(role.name) for role in ctx.guild.roles])+1
        counts = [len(role.members) for role in ctx.guild.roles]
        countChars = max([len(str(i)) for i in counts])+1

        for i, role in enumerate(ctx.guild.roles):
            count = counts[i]
            msg += role.name + (chars - len(role.name))*' ' + str(count) + (countChars - len(str(count)))*' ' + 'members\n'
        msg = msg.strip()

        if len(msg) <= 1994:
            await ctx.send(f'```{msg}```')
        else:
            chunks, chunk_size = len(msg), 1994 # msg at most 2000 chars, and we have 6 ` chars
            msgs = [msg[i:i+chunk_size] for i in range(0, chunks, chunk_size)]
            for msg in msgs:
                await ctx.send(f'```{msg}```')


def setup(bot):
    bot.add_cog(Roles(bot))
