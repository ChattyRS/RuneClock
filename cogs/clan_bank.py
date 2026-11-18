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
            self.bot.cache.guild(guild)
            
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

def get_creator_id(embed: discord.Embed) -> int | None:
    '''
    Gets the ID of the user who created a transaction from the embed footer.
    '''
    if not embed.footer.text or not embed.footer.text.startswith('User ID: '):
        return None
    try:
        return int(embed.footer.text.replace('User ID: ', ''))
    except ValueError:
        return None

def get_embed_field(embed: discord.Embed, name: str) -> str | None:
    '''
    Gets the value of the first embed field with the given name.
    '''
    for field in embed.fields:
        if field.name == name:
            return field.value
    return None

class ConfirmView(discord.ui.View):
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger, custom_id='bank_tx_cancel_button')
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message or not interaction.message.embeds or interaction.user.id != get_creator_id(interaction.message.embeds[0]):
            await interaction.response.send_message('Only the creator of a transaction can cancel it', ephemeral=True)
            return
        # Update message
        embed: discord.Embed = interaction.message.embeds[0]
        embed.set_footer(text=f'❌ Cancelled by {interaction.user.display_name}')
        await interaction.response.edit_message(embed=embed, view=None)
        await interaction.followup.send('Transaction cancelled successfully.', ephemeral=True)

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.success, custom_id='bank_tx_confirm_button')
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message or not interaction.message.embeds or interaction.user.id != get_creator_id(interaction.message.embeds[0]):
            await interaction.response.send_message('Only the creator of a transaction can confirm it', ephemeral=True)
            return
        # Acknowledge the interaction right away so it doesn't time out after 3 seconds
        await interaction.response.defer()
        # Handle confirm
        status: str = await self.confirm_handler(interaction)
        if status != 'success':
            await interaction.followup.send(status, ephemeral=True)
            return
        # Update message
        embed: discord.Embed = interaction.message.embeds[0]
        embed.set_footer(text=f'✅ Confirmed by {interaction.user.display_name}')
        await interaction.edit_original_response(attachments=interaction.message.attachments, embed=embed, view=None)
        await interaction.followup.send('Transaction confirmed successfully.', ephemeral=True)

    async def confirm_handler(self, interaction: discord.Interaction) -> str:
        '''
        Parses data from an addition / subtraction embed and processes the transaction.
        '''
        if not interaction.message or not interaction.guild or not interaction.message.embeds:
            return 'Error: interaction message or guild was not found.'
        embed: discord.Embed = interaction.message.embeds[0]
        creator_id: int | None = get_creator_id(embed)
        amount_value: str | None = get_embed_field(embed, 'Amount')
        if creator_id is None or not amount_value or not embed.title:
            return 'Error: interaction message did not have a valid signature.'

        # The member the transaction is for. Defaults to the creator when there is no member field.
        member_value: str | None = get_embed_field(embed, 'Member')
        member_digits: str = ''.join(c for c in member_value if c.isdigit()) if member_value else ''
        member_id: int = int(member_digits) if member_digits else creator_id

        # Parse message
        amount_str: str = amount_value.replace(',', '')
        if not is_int(amount_str):
            return f'Error: invalid amount: `{amount_value}`'
        amount: int = int(amount_str)
        if 'subtraction' in embed.title:
            amount = -amount
        description: str | None = get_embed_field(embed, 'Description')

        async with self.bot.db.get_session() as session:
            session.add(ClanBankTransaction(amount=amount, description=description, guild_id=interaction.guild.id, member_id=member_id, submitter_id=creator_id, time=datetime.now(UTC)))
            await session.commit()

        return 'success'

    async def on_error(self, interaction: discord.Interaction, error: Exception, _: discord.ui.Item[Any]) -> None:
        if interaction.response.is_done():
            await interaction.followup.send('Error', ephemeral=True)
        else:
            await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class TransactionModal(discord.ui.Modal):
    def __init__(self, bot: Bot, subtract: bool, is_admin: bool, user: discord.Member | discord.User) -> None:
        self.kind: str = 'subtraction' if subtract else 'addition'
        verb: str = 'subtract' if subtract else 'add'
        super().__init__(title=f'Clan bank {self.kind}')
        self.bot: Bot = bot
        self.subtract: bool = subtract

        # Administrators and the bot owner can create transactions for other members
        self.member_select: discord.ui.UserSelect | None = None
        if is_admin:
            self.member_select = discord.ui.UserSelect(min_values=1, max_values=1, required=True, default_values=[user])
            self.add_item(discord.ui.Label(text='Member', description=f'The member to {verb} funds for', component=self.member_select))

        self.amount = discord.ui.TextInput(placeholder='0', min_length=1, max_length=13, required=True, style=TextStyle.short)
        self.add_item(discord.ui.Label(text=f'How much do you want to {verb}?', component=self.amount))

        self.description = discord.ui.TextInput(placeholder=f'Describe the reason for your {self.kind} here...', max_length=1000, required=False, style=TextStyle.paragraph)
        self.add_item(discord.ui.Label(text='Description (optional)', component=self.description))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Validation
        amount: str | int = self.amount.value
        amount = amount.upper().replace(',', '').replace('K', '000').replace('M', '000000').replace('B', '000000000')
        if not is_int(amount):
            await interaction.response.send_message(f'Error: invalid amount: `{amount}`', ephemeral=True)
            return
        amount = int(amount)
        if amount == 0:
            await interaction.response.send_message(f'Error: amount cannot be 0', ephemeral=True)
            return
        if amount > max_cash or amount < -max_cash:
            await interaction.response.send_message(f'Error: amount too great: `{amount:,}`', ephemeral=True)
            return

        member: discord.Member | discord.User = interaction.user
        if self.member_select and self.member_select.values:
            member = self.member_select.values[0]
            if member.bot:
                await interaction.response.send_message(f'Error: cannot create a transaction for a bot', ephemeral=True)
                return

        # Get an image for the given amount of coins
        coins_image: discord.File = get_coins_image(-amount if self.subtract else amount)

        # Create embed to show data
        embed = discord.Embed(title=f'**Clan bank {self.kind}**', colour=0xff0000 if self.subtract else 0x00e400)
        embed.add_field(name='Amount', value=f'{amount:,}', inline=False)
        embed.add_field(name='Description', value=self.description.value if self.description.value else 'N/A', inline=False)
        if member.id != interaction.user.id:
            embed.add_field(name='Member', value=member.mention, inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')
        embed.set_thumbnail(url='attachment://coins.png')

        await interaction.response.send_message(files=[coins_image], embed=embed, view=ConfirmView(self.bot))

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if interaction.response.is_done():
            await interaction.followup.send('Error', ephemeral=True)
        else:
            await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class HistoryView(discord.ui.View):
    '''
    Shows the clan bank transaction history, split into pages that each fit in a single embed.
    '''
    # Embed descriptions can hold up to 4096 characters
    max_page_length: int = 4096
    # Blank line between transactions
    separator: str = '\n\n'

    def __init__(self, user_id: int, author_name: str, author_icon_url: str, entries: list[str]) -> None:
        super().__init__(timeout=600)
        self.user_id: int = user_id
        self.author_name: str = author_name
        self.author_icon_url: str = author_icon_url
        self.message: discord.Message | None = None
        self.page: int = 0
        self.total: int = len(entries)

        # Fit as many entries as possible on each page
        self.pages: list[list[str]] = [[]]
        length: int = 0
        for entry in entries:
            if self.pages[-1] and length + len(self.separator) + len(entry) > self.max_page_length:
                self.pages.append([])
                length = 0
            length += len(entry) + (len(self.separator) if self.pages[-1] else 0)
            self.pages[-1].append(entry)
        self.update_buttons()

    def get_embed(self) -> discord.Embed:
        description: str = self.separator.join(self.pages[self.page]) if self.total else 'No transactions have been recorded yet.'
        embed = discord.Embed(title='**Clan bank history**', description=description, colour=0x00b2ff)
        embed.set_author(name=self.author_name, icon_url=self.author_icon_url)
        if self.total:
            embed.set_footer(text=f'Page {self.page + 1}/{len(self.pages)} · {self.total:,} transactions')
        return embed

    def update_buttons(self) -> None:
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('Only the user who requested this history can change pages. Use `/bank history` to view it yourself.', ephemeral=True)
            return False
        return True

    async def change_page(self, interaction: discord.Interaction, page: int) -> None:
        self.page = max(0, min(page, len(self.pages) - 1))
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label='Previous', emoji='◀️', style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.change_page(interaction, self.page - 1)

    @discord.ui.button(label='Next', emoji='▶️', style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.change_page(interaction, self.page + 1)

    async def on_timeout(self) -> None:
        # Remove the buttons once they stop working
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

class ClanBank(Cog):
    # Longer descriptions are shortened in the history, so that a page always fits at least ~10 transactions
    max_history_description_length: int = 250

    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    async def cog_load(self) -> None:
        # Register persistent views
        self.bot.add_view(ConfirmView(self.bot))

    @app_commands.command(name='bank')
    @app_commands.guild_only()
    async def bank(self, interaction: discord.Interaction, action: str) -> None:
        '''
        Manage the clan bank
        '''
        self.bot.increment_command_counter()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(f'This command can only be used in a server', ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != self.bot.config['owner']:
            guild: Guild | None = self.bot.cache.get_guild(interaction.guild)
            if not guild:
                await interaction.response.send_message(f'Guild with id {id} was not found.', ephemeral=True)
                return
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
        non_zero_amounts: list[tuple[int, int]] = [item for item in user_amounts.items() if item[1] != 0]
        for user_id, user_amount in sorted(non_zero_amounts, key=lambda item: item[1], reverse=True)[:25]:
            member: discord.Member | None = interaction.guild.get_member(user_id)
            name: str = member.display_name if member else f'Unknown member: {user_id}'
            embed.add_field(name=name, value=f'Amount: `{user_amount:,}`', inline=False)
        if coins_image:
            await interaction.followup.send(files=[coins_image], embed=embed)
        else:
            await interaction.followup.send(embed=embed)

    def is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.bot.config['owner'] or (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator)

    async def add(self, interaction: discord.Interaction) -> None:
        # Add to the clan bank
        await interaction.response.send_modal(TransactionModal(self.bot, False, self.is_admin(interaction), interaction.user))

    async def subtract(self, interaction: discord.Interaction) -> None:
        # Subtract from the clan bank
        await interaction.response.send_modal(TransactionModal(self.bot, True, self.is_admin(interaction), interaction.user))

    async def history(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(f'This command can only be used in a server', ephemeral=True)
            return
        
        await interaction.response.defer()

        # View the history of clan bank transaction
        async with self.bot.db.get_session() as session:
            tx: Sequence[ClanBankTransaction] = (await session.execute(select(ClanBankTransaction).where(ClanBankTransaction.guild_id == interaction.guild.id).order_by(ClanBankTransaction.time.desc()))).scalars().all()

        guild: discord.Guild = interaction.guild
        def name(user_id: int) -> str:
            member: discord.Member | None = guild.get_member(user_id)
            return discord.utils.escape_markdown(member.display_name) if member else f'Unknown member ({user_id})'

        # One entry per transaction, newest first
        entries: list[str] = []
        for t in tx:
            entry: str = f'**{name(t.member_id)}** · `{"+" if t.amount > 0 else ""}{t.amount:,}` · `{t.time.strftime("%Y-%m-%d")}`'
            if t.description and t.description != 'N/A':
                # Keep the description on a single quoted line and shorten long ones so each page fits enough entries
                description: str = ' '.join(t.description.split())
                if len(description) > self.max_history_description_length:
                    description = description[:self.max_history_description_length - 1].rstrip() + '…'
                entry += f'\n> {discord.utils.escape_markdown(description)}'
            if t.submitter_id != t.member_id:
                entry += f'\n-# Submitted by {name(t.submitter_id)}'
            entries.append(entry)

        view = HistoryView(interaction.user.id, interaction.user.display_name, interaction.user.display_avatar.url, entries)
        if len(view.pages) > 1:
            view.message = await interaction.followup.send(embed=view.get_embed(), view=view, wait=True)
        else:
            await interaction.followup.send(embed=view.get_embed())
    
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
