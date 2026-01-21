import discord
from discord import app_commands
from discord.ext.commands import Cog
from src.bot import Bot
from src.discord_utils import find_guild_text_channel
from src.configuration import config
from cogs.obliterate import AccountInfoModal
from cogs.malignant import ApplicationModal

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
        
        test_channel: discord.TextChannel | None = find_guild_text_channel(interaction.guild, self.bot.config['testChannel'])
        
        if interaction.guild.id == config['obliterate_guild_id']:
            applicant_role: discord.Role | None = interaction.guild.get_role(self.bot.config['obliterate_applicant_role_id'])
            if not applicant_role or not applicant_role in interaction.user.roles:
                await interaction.response.send_message(f'Must be an applicant to submit an application', ephemeral=True)
                return
            obliterate_application_channel: discord.TextChannel | None = find_guild_text_channel(interaction.guild, self.bot.config['obliterate_applications_channel_id'])
            if not obliterate_application_channel or not interaction.channel in [obliterate_application_channel, test_channel]:
                await interaction.response.send_message(f'Applications can only be submitted in the #applications channel', ephemeral=True)
                return
            await interaction.response.send_modal(AccountInfoModal(self.bot))

        if interaction.guild.id in [config['malignant_guild_id'], config['test_guild_id']]:
            malignant_application_channel: discord.TextChannel | None = find_guild_text_channel(interaction.guild, self.bot.config['malignant_applications_channel_id'])
            if (not malignant_application_channel and not interaction.channel == malignant_application_channel 
                and not test_channel and not interaction.channel == test_channel):
                await interaction.response.send_message(f'Applications can only be submitted in the #applications channel', ephemeral=True)
                return
            bronze_role: discord.Role | None = interaction.guild.get_role(self.bot.config['malignant_bronze_role_id'])
            if bronze_role and interaction.user.top_role >= bronze_role and interaction.user.id != self.bot.config['owner']:
                await interaction.response.send_message(f'This command cannot be used by clan members', ephemeral=True)
                return
            await interaction.response.send_modal(ApplicationModal(self.bot))

async def setup(bot: Bot) -> None:
    await bot.add_cog(Shared(bot))
