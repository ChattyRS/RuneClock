from discord.ext.commands import Context, check, CommandError
from discord.ext.commands._types import Check
from discord import Member, Guild, Role
from src.bot import Bot

def is_owner() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        raise CommandError(message='Insufficient permissions: `Owner`')
    return check(predicate)

def is_admin() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        try:
            portables: Guild | None = ctx.bot.get_guild(ctx.bot.config['portablesServer'])
            if portables:
                member: Member | None = await portables.fetch_member(ctx.author.id)
                if member:
                    admin_role: Role | None = portables.get_role(ctx.bot.config['adminRole'])
                    if admin_role in member.roles:
                        return True
        except:
            pass
        if (isinstance(ctx.author, Member) and ctx.author.guild_permissions.administrator) or (ctx.guild and ctx.guild.owner and ctx.author.id == ctx.guild.owner.id) or ctx.author.id == ctx.bot.config['owner']:
            return True
        raise CommandError(message='Insufficient permissions: `Admin`')
    return check(predicate)

def portables_leader() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        portables: Guild | None = ctx.bot.get_guild(ctx.bot.config['portablesServer'])
        if portables:
            member: Member | None = await portables.fetch_member(ctx.author.id)
            if member:
                leader_role: Role | None = portables.get_role(ctx.bot.config['leaderRole'])
                if leader_role in member.roles:
                    return True
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        raise CommandError(message='Insufficient permissions: `Portables leader`')
    return check(predicate)

def portables_admin() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        portables: Guild | None = ctx.bot.get_guild(ctx.bot.config['portablesServer'])
        if portables:
            member: Member | None = await portables.fetch_member(ctx.author.id)
            if member:
                admin_role: Role | None = portables.get_role(ctx.bot.config['adminRole'])
                if admin_role in member.roles:
                    return True
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        raise CommandError(message='Insufficient permissions: `Portables admin`')
    return check(predicate)

def is_mod() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        portables: Guild | None = ctx.bot.get_guild(ctx.bot.config['portablesServer'])
        if portables:
            member: Member | None = await portables.fetch_member(ctx.author.id)
            if member:
                mod_role: Role | None = portables.get_role(ctx.bot.config['modRole'])
                if mod_role in member.roles:
                    return True
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        raise CommandError(message='Insufficient permissions: `Portables moderator`')
    return check(predicate)

def is_rank() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        portables: Guild | None = ctx.bot.get_guild(ctx.bot.config['portablesServer'])
        if portables:
            member: Member | None = await portables.fetch_member(ctx.author.id)
            if member:
                rank_role: Role | None = portables.get_role(ctx.bot.config['rankRole'])
                if rank_role in member.roles:
                    return True
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        raise CommandError(message='Insufficient permissions: `Portables rank`')
    return check(predicate)

def is_helper() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        portables: Guild | None = ctx.bot.get_guild(ctx.bot.config['portablesServer'])
        if portables:
            member: Member | None = await portables.fetch_member(ctx.author.id)
            if member:
                helper_role: Role | None = portables.get_role(ctx.bot.config['helperRole'])
                if helper_role in member.roles:
                    return True
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        raise CommandError(message='Insufficient permissions: `Portables helper`')
    return check(predicate)

def portables_only() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        if ctx.guild and ctx.guild.id == ctx.bot.config['portablesServer']:
            return True
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        raise CommandError(message='Insufficient permissions: `Portables server only`')
    return check(predicate)

def obliterate_only() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        if ctx.guild and ctx.guild.id == ctx.bot.config['obliterate_guild_id']:
            return True
        raise CommandError(message='Insufficient permissions: `Obliterate server only`')
    return check(predicate)

def obliterate_mods() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        obliterate: Guild | None = ctx.bot.get_guild(ctx.bot.config['obliterate_guild_id'])
        if obliterate:
            member: Member | None = await obliterate.fetch_member(ctx.author.id)
            if member:
                mod_role: Role | None = obliterate.get_role(ctx.bot.config['obliterate_moderator_role_id'])
                key_role: Role | None = obliterate.get_role(ctx.bot.config['obliterate_key_role_id'])
                if mod_role in member.roles or key_role in member.roles:
                    return True
        raise CommandError(message='Insufficient permissions: `Obliterate moderator`')
    return check(predicate)

def malignant_only() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        if ctx.guild and ctx.guild.id == ctx.bot.config['malignant_guild_id']:
            return True
        raise CommandError(message='Insufficient permissions: `Malignant server only`')
    return check(predicate)

def malignant_mods() -> Check[Context[Bot]]:
    async def predicate(ctx: Context[Bot]) -> bool:
        if ctx.author.id == ctx.bot.config['owner']:
            return True
        malignant: Guild | None = ctx.bot.get_guild(ctx.bot.config['malignant_guild_id'])
        if malignant:
            member: Member | None = await malignant.fetch_member(ctx.author.id)
            if member:
                mod_role: Role | None = malignant.get_role(ctx.bot.config['malignant_moderator_role_id'])
                if mod_role in member.roles:
                    return True
        raise CommandError(message='Insufficient permissions: `Malignant moderator`')
    return check(predicate)