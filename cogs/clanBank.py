import discord
from discord import app_commands, TextStyle
from discord.ext.commands import Cog
import sys
sys.path.append('../')
from main import Bot, get_config, ClanBankTransaction, Guild
from datetime import datetime, UTC
from utils import is_int, max_cash, get_coins_image_name, digits
import traceback
import io
import imageio
from typing import Any

config: dict[str, Any] = get_config()

yellow: list[int] = [255, 255, 0, 255]
white: list[int] = [255, 255, 255, 255]
green: list[int] = [0, 255, 131, 255]
red: list[int] = [255, 50, 50, 255]

char_index: dict[str, int] = {'K': 10, 'M': 11, '-': 12}

def enlarge_digit(digit, factor):
    '''
    Doubles the size of an image factor times
    '''
    for f in range(factor-1):
        ldigit = []
        for row in digit:
            lrow = [row[int(i/2)] for i in range(len(row)*2)]
            ldigit.append(lrow)
            ldigit.append(lrow)
        digit = ldigit
    return digit

def draw_char(img, char, x, y, c, size):
    '''
    Draws a character on an image at (x, y)
    '''
    colour = c
    if img.shape[2] == 3 and len(c) > 3:
        colour = colour[:3]
    elif img.shape[2] == 4 and len(c) < 4:
        colour.append(255)
    digit = digits[int(char) if is_int(char) else char_index[char]]
    pixels = enlarge_digit(digit, size)
    x_0 = x
    for row in reversed(pixels):
        x = x_0
        for value in reversed(row):
            if value == 1:
                img[y, x] = colour
            x -= 1
        y -= 1
    return (x-1, y)

def draw_gp(img, amount):
    '''
    Draw an amount over an image of RuneScape coins.
    '''
    colour = green if amount >= 10000000 else white if amount >= 100000 else yellow if amount >= 0 else red
    amount = round(amount, -6) if abs(amount) >= 10000000 else round(amount, -3) if abs(amount) >= 100000 else amount
    amount_str = str(amount)
    if amount >= 10000000 or amount <= -10000000:
        amount_str = amount_str[::-1].replace('000000', 'M', 1)[::-1]
    elif amount >= 100000 or amount <= -100000:
        amount_str = amount_str[::-1].replace('000', 'K', 1)[::-1]
    size = 5
    for i, char in enumerate(amount_str):
        draw_char(img, char, (int(5*(2**size)/2)-1)*(i+1)+i*(2**size), int(8*(2**size)/2)-1, colour, size)

def get_coins_image(amount):
    '''
    Get an image for the given amount of coins.
    '''
    # Get base coins image
    coins = imageio.imread(f'images/{get_coins_image_name(amount)}.png')

    # Draw amount
    draw_gp(coins, amount)

    imageio.imwrite('images/coins.png', coins)
    with open('images/coins.png', 'rb') as f:
        coins_image = io.BytesIO(f.read())
    coins_image = discord.File(coins_image, filename='coins.png')
    return coins_image

async def get_transactions(guild_id: int):
    '''
    Gets all ClanBankTransaction for a given guild.
    '''
    return await ClanBankTransaction.query.where(ClanBankTransaction.guild_id == guild_id).gino.all()

async def create_transaction(amount: int, description: str, guild_id: int, member_id: int):
    '''
    Creates a ClanBankTransaction.
    '''
    await ClanBankTransaction.create(amount=amount, description=description, guild_id=guild_id, member_id=member_id, time=datetime.now(UTC))

class Dropdown(discord.ui.Select):
    def __init__(self, options):
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder='Choose a role...', min_values=1, max_values=1, options=options, custom_id='bank_role_select')

    async def callback(self, interaction: discord.Interaction):
        # Use the interaction object to update the guild bank_role_id. 
        # The self object refers to the Select object, 
        # and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        role = interaction.guild.get_role(int(self.values[0]))
        guild = await Guild.get(interaction.guild.id)
        await guild.update(bank_role_id=role.id).apply()
        await interaction.response.send_message(f'The bank management role has been set to `{role.name}`', ephemeral=True)

class SelectRoleView(discord.ui.View):
    def __init__(self, bot, guild):
        super().__init__()
        self.bot = bot

        # Get options for role dropdown
        options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in sorted(guild.roles, reverse=True)]
        if len(options) > 25:
            options = options[:25]

        # Adds the dropdown to our view object.
        self.add_item(Dropdown(options))

class ConfirmView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.value = None
    
    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger, custom_id='bank_tx_cancel_button')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Validate permissions
        if not interaction.user.id == int(interaction.message.embeds[0].footer.text.replace('User ID: ', '')):
            await interaction.response.send_message('Only the creator of a transaction can cancel it', ephemeral=True)
            return
        # Update message
        embed = interaction.message.embeds[0]
        embed.set_footer(text=f'Cancelled by {interaction.user.display_name}', icon_url='https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/160/twitter/322/cross-mark_274c.png')
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message('Transaction cancelled successfully.', ephemeral=True)
        self.value = False
        self.stop()

    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.success, custom_id='bank_tx_confirm_button')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Validate permissions
        if not interaction.user.id == int(interaction.message.embeds[0].footer.text.replace('User ID: ', '')):
            await interaction.response.send_message('Only the creator of a transaction can confirm it', ephemeral=True)
            return
        # Handle confirm
        status = await self.confirm_handler(interaction)
        if status != 'success':
            await interaction.response.send_message(status, ephemeral=True)
            return
        # Update message
        embed = interaction.message.embeds[0]
        embed.set_footer(text=f'Confirmed by {interaction.user.display_name}', icon_url='https://emojipedia-us.s3.dualstack.us-west-1.amazonaws.com/thumbs/160/twitter/322/check-mark-button_2705.png')
        await interaction.message.edit(attachments=interaction.message.attachments, embed=embed, view=None)
        await interaction.response.send_message('Transaction confirmed successfully.', ephemeral=True)
        self.value = True
        self.stop()

    async def confirm_handler(self, interaction: discord.Interaction) -> str:
        '''
        Parses data from an addition / subtraction embed and processes the transaction.
        '''
        user_id = int(interaction.message.embeds[0].footer.text.replace('User ID: ', ''))
        member = interaction.guild.get_member(user_id)
        if not member:
            member = await interaction.guild.fetch_member(user_id)

        if not member:
            return 'Error: member not found'
            
        # Parse message
        amount = int(interaction.message.embeds[0].fields[0].value)
        if 'subtraction' in interaction.message.embeds[0].title:
            amount = -amount
        description = interaction.message.embeds[0].fields[1].value

        await create_transaction(amount, description, interaction.guild.id, user_id)

        return 'success'
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class AddTransactionModal(discord.ui.Modal, title='Clan bank addition'):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    amount = discord.ui.TextInput(label='How much do you want to add?', placeholder="0", min_length=1, max_length=10, required=True, style=TextStyle.short)
    description = discord.ui.TextInput(label='Description (optional)', placeholder='Describe the reason for your addition here...', max_length=1000, required=False, style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        # Validation
        amount = self.amount.value
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
        coins_image = get_coins_image(amount)
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Clan bank addition**', colour=0x00e400)
        embed.add_field(name='Amount', value=str(amount), inline=False)
        embed.add_field(name='Description', value=self.description.value if self.description.value else 'N/A', inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')
        embed.set_thumbnail(url='attachment://coins.png')
        
        # Create a view to confirm / cancel
        view = ConfirmView(self.bot)

        msg = await interaction.response.send_message(files=[coins_image], embed=embed, view=view)
        await view.wait()

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class SubtractTransactionModal(discord.ui.Modal, title='Clan bank subtraction'):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    amount = discord.ui.TextInput(label='How much do you want to subtract?', placeholder="0", min_length=1, max_length=10, required=True, style=TextStyle.short)
    description = discord.ui.TextInput(label='Description (optional)', placeholder='Describe the reason for your subtraction here...', max_length=1000, required=False, style=TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        # Validation
        amount = self.amount.value
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
        coins_image = get_coins_image(-amount)
            
        # Create embed to show data
        embed = discord.Embed(title=f'**Clan bank subtraction**', colour=0xff0000)
        embed.add_field(name='Amount', value=str(amount), inline=False)
        embed.add_field(name='Description', value=self.description.value if self.description.value else 'N/A', inline=False)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text=f'User ID: {interaction.user.id}')
        embed.set_thumbnail(url='attachment://coins.png')
        
         # Create a view to confirm / cancel
        view = ConfirmView(self.bot)

        msg = await interaction.response.send_message(files=[coins_image], embed=embed, view=view)
        await view.wait()

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message('Error', ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class ClanBank(Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    def cog_unload(self):
        pass

    @app_commands.command(name='bank')
    async def bank(self, interaction: discord.Interaction, action: str):
        '''
        Manage the clan bank
        '''
        if not interaction.user.guild_permissions.administrator and interaction.user.id != config['owner']:
            guild = await Guild.get(interaction.guild.id)
            bank_role = None
            if guild.bank_role_id:
                bank_role = interaction.guild.get_role(guild.bank_role_id)
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
    ) -> List[app_commands.Choice[str]]:
        actions = ['view', 'add', 'subtract', 'history']
        admin_actions = ['role']
        return [
            app_commands.Choice(name=action, value=action)
            for action in actions if current.lower() in action.lower()
        ] + [
            app_commands.Choice(name=action, value=action)
            for action in admin_actions if current.lower() in action.lower() and 
            (interaction.user.guild_permissions.administrator or interaction.user.id == config['owner'])
        ]

    async def view(self, interaction: discord.Interaction):
        # Get the clan bank transactions
        tx = await get_transactions(interaction.guild.id)
        amount = sum([t.amount for t in tx])

        embed = discord.Embed(title=f'**Clan bank**', description=f'Total amount: `{amount:,}`', colour=0x00b2ff)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        # Get an image for the given amount of coins
        if amount >= -max_cash and amount <= max_cash:
            coins_image = get_coins_image(amount)
            embed.set_thumbnail(url='attachment://coins.png')

        # Add fields for each member holding money for the clan bank
        # Sorted by descending amount, up to 25 members
        user_amounts = {}
        for user_id in set([t.member_id for t in tx]):
            user_amounts[user_id] = sum([t.amount for t in tx if t.member_id == user_id])
        for user_id, user_amount in sorted(user_amounts.items(), key=lambda item: item[1]):
            member = interaction.guild.get_member(user_id)
            if not member:
                member = await interaction.guild.fetch_member(user_id)
            name = member.display_name if member else f'Unknown member: {user_id}'
            embed.add_field(name=name, value=f'Amount: `{user_amount:,}`', inline=False)

        await interaction.response.send_message(files=[coins_image], embed=embed)

    async def add(self, interaction: discord.Interaction):
        # Add to the clan bank
        await interaction.response.send_modal(AddTransactionModal(self.bot))

    async def subtract(self, interaction: discord.Interaction):
        # Subtract from the clan bank
        await interaction.response.send_modal(SubtractTransactionModal(self.bot))

    async def history(self, interaction: discord.Interaction):
        # View the history of clan bank transaction
        tx = await get_transactions(interaction.guild.id)
        
        # Create embed
        description = 'No transactions have been recorded yet.' if len(tx) == 0 else f'Latest {min(5, len(tx))} transactions:'
        embed = discord.Embed(title=f'**Clan bank history**', description=description, colour=0x00b2ff)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        # Add fields for latest 5 transactions
        for i, t in enumerate(sorted(tx, key=lambda x: x.time, reverse=True)):
            member = interaction.guild.get_member(t.member_id)
            if not member:
                member = await interaction.guild.fetch_member(t.member_id)
            name = member.display_name if member else f'Unknown member: {t.member_id}'
            embed.add_field(name=name, value=f'`{"+" if t.amount > 0 else ""}{t.amount:,}` on {t.time.strftime("%Y-%m-%d")}', inline=False)
            if i >= 4:
                break
        
        await interaction.response.send_message(embed=embed)
    
    async def set_bank_role(self, interaction: discord.Interaction):
        # Set the role required to manage the clan bank.
        # Validation
        if not (interaction.user.guild_permissions.administrator or interaction.user.id == config['owner']):
            await interaction.response.send_message('Missing permission: `administrator`', ephemeral=True)
            return
        view = SelectRoleView(self.bot, interaction.guild)
        await interaction.response.send_message('Choose a role to allow management of your clan bank:', view=view, ephemeral=True)


async def setup(bot: Bot):
    await bot.add_cog(ClanBank(bot))
