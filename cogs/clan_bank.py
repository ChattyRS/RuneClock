from typing import Any, Sequence
import discord
from discord import SelectOption, app_commands, TextStyle
from discord.ext.commands import Cog
from sqlalchemy import select
from src.bot import Bot
from src.database import ClanBankTransaction, Guild
from datetime import datetime, UTC
from src.runescape_utils import max_cash
from src.graphics import get_coins_image
import traceback
from src.database_utils import get_db_guild
from src.number_utils import is_int

class Dropdown(discord.ui.Select):
    def __init__(self, bot: Bot, options: list[SelectOption]) -> None:
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder='Choose a role...', min_values=1, max_values=1, options=options, custom_id='bank_role_select')
        self.bot: Bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        # Use the interaction object to update the guild bank_role_id. 
        # The self object refers to the Select object, 
        # and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        if not interaction.guild:
            await interaction.response.send_message(f'This command can only be used inside a server.', ephemeral=True)
            return
        role: discord.Role | None = interaction.guild.get_role(int(self.values[0]))
        if not role:
            await interaction.response.send_message(f'Could not find role.', ephemeral=True)
            return
        
        async with self.bot.db.get_session() as session:
            guild: Guild = await get_db_guild(session, interaction.guild.id)
            guild.bank_role_id = role.id
            await session.commit()
            
        await interaction.response.send_message(f'The bank management role has been set to `{role.name}`', ephemeral=True)

class SelectRoleView(discord.ui.View):
    def __init__(self, bot: Bot, guild: discord.Guild) -> None:
        super().__init__()
        self.bot: Bot = bot

        # Get options for role dropdown
        options: list[SelectOption] = [discord.SelectOption(label=role.name, value=str(role.id)) for role in sorted(guild.roles, reverse=True)]
        if len(options) > 25:
            options = options[:25]

        # Adds the dropdown to our view object.
        self.add_item(Dropdown(bot, options))

class ConfirmView(discord.ui.View):
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot
        self.value = None
    
    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger, custom_id='bank_tx_cancel_button')
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message or not interaction.message.embeds[0].footer.text or not interaction.user.id == int(interaction.message.embeds[0].footer.text.replace('User ID: ', '')):
            await interaction.response.send_message('Only the creator of a transaction can cancel it', ephemeral=True)
            return
        # Update message
        embed: discord.Embed = interaction.message.embeds[0]
        embed.set_footer(text=f'Cancelled by {interaction.user.display_name}', icon_url='https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/160/twitter/322/cross-mark_274c.png')
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message('Transaction cancelled successfully.', ephemeral=True)
        self.value = False
        self.stop()

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.success, custom_id='bank_tx_confirm_button')
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message or not interaction.message.embeds[0].footer.text or not interaction.user.id == int(interaction.message.embeds[0].footer.text.replace('User ID: ', '')):
            await interaction.response.send_message('Only the creator of a transaction can confirm it', ephemeral=True)
            return
        # Handle confirm
        status: str = await self.confirm_handler(interaction)
        if status != 'success':
            await interaction.response.send_message(status, ephemeral=True)
            return
        # Update message
        embed: discord.Embed = interaction.message.embeds[0]
        embed.set_footer(text=f'Confirmed by {interaction.user.display_name}', icon_url='https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/160/twitter/322/check-mark-button_2705.png')
        await interaction.message.edit(attachments=interaction.message.attachments, embed=embed, view=None)
        await interaction.response.send_message('Transaction confirmed successfully.', ephemeral=True)
        self.value = True
        self.stop()

    async def confirm_handler(self, interaction: discord.Interaction) -> str:
        '''
        Parses data from an addition / subtraction embed and processes the transaction.
        '''
        if not interaction.message or not interaction.message.embeds[0].footer.text or not interaction.guild or not interaction.message.embeds or not interaction.message.embeds[0].fields[0].value or not interaction.message.embeds[0].title:
            return 'Error: interaction message or guild was not found or did not have a valid signature.'
        user_id = int(interaction.message.embeds[0].footer.text.replace('User ID: ', ''))
        member: discord.Member | None = interaction.guild.get_member(user_id)
        if not member:
            member = await interaction.guild.fetch_member(user_id)

        if not member:
            return 'Error: member not found'
            
        # Parse message
        amount: int = int(interaction.message.embeds[0].fields[0].value)
        if 'subtraction' in interaction.message.embeds[0].title:
            amount = -amount
        description: str | None = interaction.message.embeds[0].fields[1].value

        async with self.bot.db.get_session() as session:
             session.add(ClanBankTransaction(amount=amount, description=description, guild_id=interaction.guild.id, member_id=user_id, time=datetime.now(UTC)))
             await session.commit()

        return 'success'
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, _: discord.ui.Item[Any]) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class AddTransactionModal(discord.ui.Modal, title='Clan bank addition'):
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    amount = discord.ui.TextInput(label='How much do you want to add?', placeholder="0", min_length=1, max_length=10, required=True, style=TextStyle.short)
    description = discord.ui.TextInput(label='Description (optional)', placeholder='Describe the reason for your addition here...', max_length=1000, required=False, style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Validation
        amount: str | int = self.amount.value
        amount = amount.upper().replace('K', '000').replace('M', '000000').replace('B', '000000000')
        if not is_int(amount):
            await interaction.response.send_message(f'Error: invalid amount: `{amount}`', ephemeral=True)
            return
        amount = int(amount)
        if amount == 0:
            await interaction.response.send_message(f'Error: amount cannot be 0', ephemeral=True)
            return
        if amount > max_cash or amount < -max_cash:
            await interaction.response.send_message(f'Error: amount too great: `{amount}`', ephemeral=True)
            return

        # Get an image for the given amount of coins
        coins_image: discord.File = get_coins_image(amount)
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Clan bank addition**', colour=0x00e400)
        embed.add_field(name='Amount', value=str(amount), inline=False)
        embed.add_field(name='Description', value=self.description.value if self.description.value else 'N/A', inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')
        embed.set_thumbnail(url='attachment://coins.png')
        
        # Create a view to confirm / cancel
        view = ConfirmView(self.bot)

        await interaction.response.send_message(files=[coins_image], embed=embed, view=view)
        await view.wait()

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class SubtractTransactionModal(discord.ui.Modal, title='Clan bank subtraction'):
    def __init__(self, bot: Bot) -> None:
        super().__init__()
        self.bot: Bot = bot

    amount = discord.ui.TextInput(label='How much do you want to subtract?', placeholder="0", min_length=1, max_length=10, required=True, style=TextStyle.short)
    description = discord.ui.TextInput(label='Description (optional)', placeholder='Describe the reason for your subtraction here...', max_length=1000, required=False, style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Validation
        amount: str | int = self.amount.value
        amount = amount.upper().replace('K', '000').replace('M', '000000').replace('B', '000000000')
        if not is_int(amount):
            await interaction.response.send_message(f'Error: invalid amount: `{amount}`', ephemeral=True)
            return
        amount = int(amount)
        if amount == 0:
            await interaction.response.send_message(f'Error: amount cannot be 0', ephemeral=True)
            return
        if amount > max_cash or amount < -max_cash:
            await interaction.response.send_message(f'Error: amount too great: `{amount}`', ephemeral=True)
            return

        # Get an image for the given amount of coins
        coins_image: discord.File = get_coins_image(-amount)
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Clan bank subtraction**', colour=0xff0000)
        embed.add_field(name='Amount', value=str(amount), inline=False)
        embed.add_field(name='Description', value=self.description.value if self.description.value else 'N/A', inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')
        embed.set_thumbnail(url='attachment://coins.png')
        
         # Create a view to confirm / cancel
        view = ConfirmView(self.bot)

        await interaction.response.send_message(files=[coins_image], embed=embed, view=view)
        await view.wait()

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class ClanBank(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    async def cog_load(self) -> None:
        # Register persistent views
        self.bot.add_view(ConfirmView(self.bot))

    @app_commands.command(name='bank')
    async def bank(self, interaction: discord.Interaction, action: str) -> None:
        '''
        Manage the clan bank
        '''
        self.bot.increment_command_counter()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This command can only be used in a server', ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != self.bot.config['owner']:
            async with self.bot.db.get_session() as session:
                guild: Guild = await get_db_guild(session, interaction.guild)
            bank_role = None
            if guild.bank_role_id:
                bank_role: discord.Role | None = interaction.guild.get_role(guild.bank_role_id)
            if bank_role is None or not interaction.user.top_role >= bank_role:
                await interaction.response.send_message(f'You do not have permission to use this command.', ephemeral=True)
                return
        # Validation
        if not action in ['view', 'add', 'subtract', 'history', 'role']:
            await interaction.response.send_message(f'Invalid action: {action}', ephemeral=True)
            return
        if action == 'add':
            await self.add(interaction)
        elif action == 'subtract':
            await self.subtract(interaction)
        elif action == 'history':
            await self.history(interaction)
        elif action =='role':
            await self.set_bank_role(interaction)
        else:
            await self.view(interaction)
    
    @bank.autocomplete('action')
    async def action_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        actions: list[str] = ['view', 'add', 'subtract', 'history']
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
        if not interaction.guild:
            await interaction.response.send_message(f'This command can only be used in a server', ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Get the clan bank transactions
        async with self.bot.db.get_session() as session:
            tx: Sequence[ClanBankTransaction] = (await session.execute(select(ClanBankTransaction).where(ClanBankTransaction.guild_id == interaction.guild.id))).scalars().all()

        amount: int = sum([t.amount for t in tx])

        embed = discord.Embed(title=f'**Clan bank**', description=f'Total amount: `{amount:,}`', colour=0x00b2ff)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        # Get an image for the given amount of coins
        coins_image: discord.File | None = None
        if amount >= -max_cash and amount <= max_cash:
            coins_image = get_coins_image(amount)
            embed.set_thumbnail(url='attachment://coins.png')

        # Add fields for each member holding money for the clan bank
        # Sorted by descending amount, up to 25 members
        user_amounts: dict[int, int] = {}
        for user_id in set([t.member_id for t in tx]):
            user_amounts[user_id] = sum([t.amount for t in tx if t.member_id == user_id])
        for user_id, user_amount in sorted(user_amounts.items(), key=lambda item: item[1]):
            member: discord.Member | None = interaction.guild.get_member(user_id)
            name: str = member.display_name if member else f'Unknown member: {user_id}'
            embed.add_field(name=name, value=f'Amount: `{user_amount:,}`', inline=False)
        if coins_image:
            await interaction.followup.send(files=[coins_image], embed=embed)
        else:
            await interaction.followup.send(embed=embed)

    async def add(self, interaction: discord.Interaction) -> None:
        # Add to the clan bank
        await interaction.response.send_modal(AddTransactionModal(self.bot))

    async def subtract(self, interaction: discord.Interaction) -> None:
        # Subtract from the clan bank
        await interaction.response.send_modal(SubtractTransactionModal(self.bot))

    async def history(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(f'This command can only be used in a server', ephemeral=True)
            return
        
        # View the history of clan bank transaction
        async with self.bot.db.get_session() as session:
            tx: Sequence[ClanBankTransaction] = (await session.execute(select(ClanBankTransaction).where(ClanBankTransaction.guild_id == interaction.guild.id))).scalars().all()
        
        # Create embed
        description: str = 'No transactions have been recorded yet.' if len(tx) == 0 else f'Latest {min(5, len(tx))} transactions:'
        embed = discord.Embed(title=f'**Clan bank history**', description=description, colour=0x00b2ff)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        # Add fields for latest 5 transactions
        for i, t in enumerate(sorted(tx, key=lambda x: x.time, reverse=True)):
            member: discord.Member | None = interaction.guild.get_member(t.member_id)
            if not member:
                member = await interaction.guild.fetch_member(t.member_id)
            name: str = member.display_name if member else f'Unknown member: {t.member_id}'
            embed.add_field(name=name, value=f'`{"+" if t.amount > 0 else ""}{t.amount:,}` on {t.time.strftime("%Y-%m-%d")}', inline=False)
            if i >= 4:
                break
        
        await interaction.response.send_message(embed=embed)
    
    async def set_bank_role(self, interaction: discord.Interaction) -> None:
        # Set the role required to manage the clan bank.
        # Validation
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This command can only be used in a server', ephemeral=True)
            return
        if not (interaction.user.guild_permissions.administrator or interaction.user.id == self.bot.config['owner']):
            await interaction.response.send_message('Missing permission: `administrator`', ephemeral=True)
            return
        view = SelectRoleView(self.bot, interaction.guild)
        await interaction.response.send_message('Choose a role to allow management of your clan bank:', view=view, ephemeral=True)

async def setup(bot: Bot) -> None:
    await bot.add_cog(ClanBank(bot))
