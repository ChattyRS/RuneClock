from discord.ext.commands import Converter, Context, CommandError
from discord import Role

class RoleConverter(Converter):
    async def convert(self, ctx: Context, argument) -> Role:
        if not argument or not ctx.guild:
            raise CommandError(message=f'Required argument missing: `role`.')
        if len(ctx.message.role_mentions) == 1:
            return ctx.message.role_mentions[0]
        id_match: Role | None = None
        mention_match: Role | None = None
        name_match: Role | None = None
        case_insensitive_match: Role | None = None
        substring_match: Role | None = None
        for r in ctx.guild.roles:
            if r.id == argument:
                id_match = r
                break
            if r.mention == argument:
                mention_match = r
                break
            if r.name == argument:
                name_match = r
            if r.name.upper() == argument.upper():
                case_insensitive_match = r
            if argument.upper() in r.name.upper():
                substring_match = r
        for match in [id_match, mention_match, name_match, case_insensitive_match, substring_match]:
            if match:
                return match
        raise CommandError(message=f'Could not find role: `{argument}`.')