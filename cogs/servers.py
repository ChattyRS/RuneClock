import discord
from discord.ext import commands
from discord.ext.commands import Cog
import sys
sys.path.append('../')
from main import config_load, addCommand, Guild, purge_guild

config = config_load()

class Servers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @Cog.listener()
    async def on_guild_join(self, guild):
        await Guild.create(id=guild.id, prefix='-')

    @Cog.listener()
    async def on_guild_remove(self, guild):
        guild = await Guild.get(guild.id)
        if guild:
            await purge_guild(guild)

def setup(bot):
    bot.add_cog(Servers(bot))
