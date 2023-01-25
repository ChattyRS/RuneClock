import discord
from discord.ext import commands
from discord.ext.commands import Cog
import sys
sys.path.append('../')
from main import config_load, increment_command_counter, Guild, purge_guild, BannedGuild

config = config_load()

class Servers(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    @Cog.listener()
    async def on_guild_join(self, guild):
        banned_guild = await BannedGuild.get(guild.id)
        if banned_guild:
            await guild.leave()
        await Guild.create(id=guild.id, prefix='-')

    @Cog.listener()
    async def on_guild_remove(self, guild):
        guild = await Guild.get(guild.id)
        if guild:
            await purge_guild(guild)

async def setup(bot):
    await bot.add_cog(Servers(bot))
