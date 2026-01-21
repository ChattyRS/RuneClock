import discord
from discord import app_commands
from discord.ext.commands import Cog
from src.bot import Bot
from src.discord_utils import find_guild_text_channel
from src.configuration import config
from obliterate import AccountInfoModal

'''
This is a cog for shared features between Malignant and Obliterate.
'''
class Shared(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @app_commands.command()
    @app_commands.guilds(discord.Object(id=config['obliterate_guild_id']), discord.Object(id=config['malignant_guild_id']), discord.Object(id=config['test_guild_id']))
    async def apply(self, interaction: discord.Interaction) -> None:
        '''
        Send a modal with the application form.
        '''
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This command can only be used inside a server.', ephemeral=True)
            return
        
        if interaction.guild.id == config['obliterate_guild_id']:
            applicant_role: discord.Role | None = interaction.guild.get_role(self.bot.config['obliterate_applicant_role_id'])
            if not applicant_role or not applicant_role in interaction.user.roles:
                await interaction.response.send_message(f'Must be an applicant to submit an application', ephemeral=True)
                return
            application_channel: discord.TextChannel | None = find_guild_text_channel(interaction.guild, self.bot.config['obliterate_applications_channel_id'])
            if not application_channel or not interaction.channel == application_channel:
                await interaction.response.send_message(f'Applications can only be submitted in the #applications channel', ephemeral=True)
                return
            await interaction.response.send_modal(AccountInfoModal(self.bot))

        if interaction.guild.id in [config['malignant_guild_id'], config['test_guild_id']]:
            # TODO: rework malignant application
            pass

async def setup(bot: Bot) -> None:
    await bot.add_cog(Shared(bot))
