import math
import traceback
from typing import Any
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from gspread_asyncio import AsyncioGspreadClient, AsyncioGspreadSpreadsheet, AsyncioGspreadWorksheet
from src.bot import Bot
from src.number_utils import emoji_from_number

class SheetPageView(discord.ui.View):
    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot: Bot = bot
    
    @discord.ui.button(label='Previous', style=discord.ButtonStyle.blurple, custom_id='display_sheet_previous_page_button')
    async def previous(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message:
            await interaction.response.send_message('Could not find interaction message.', ephemeral=True)
            return
        # Get message and validate action
        embed: discord.Embed = interaction.message.embeds[0]
        if not embed.footer or not embed.footer.text:
            await interaction.response.send_message('Embed footer was empty.', ephemeral=True)
            return
        footer_parts: list[str] = embed.footer.text.split('/')[0:6]
        value_columns, num_rows, total_rows, current_page, num_pages, key = footer_parts
        sheet_name: str = embed.footer.text.split(f'{key}/')[1]
        value_columns = int(value_columns)
        num_rows = int(num_rows)
        total_rows = int(total_rows)
        current_page = int(current_page)
        num_pages = int(num_pages)
        if current_page <= 1:
            await interaction.response.send_message('There is no previous page to go back to. You are already on the first page.', ephemeral=True)
            return
        target_page: int = current_page - 1
        page_rows: int = num_rows if target_page < num_pages else (total_rows % num_rows)

        await interaction.response.defer()

        embed.remove_footer()
        embed.set_footer(text=f'{value_columns}/{num_rows}/{total_rows}/{target_page}/{num_pages}/{key}/{sheet_name}')

        embed.description = f'Page {target_page} / {num_pages}'

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(key)

        sheet: AsyncioGspreadWorksheet = await ss.worksheet(sheet_name)
        values: list[list[str]] = await sheet.get_all_values()

        row_start: int = (target_page - 1) * num_rows
        row_end: int = row_start + page_rows
        if not values or len(values) <= 1 or len(values) - 1 < row_end:
            await interaction.followup.send(f'Could not fetch requested data from sheet (rows {row_start + 2}-{row_end + 2}). Please verify that it is still there.', ephemeral=True)
            return
        
        header: list[str] = values[0]
        if len(header) <= 1:
            raise commands.CommandError(message=f'Sheet `{sheet_name}` must contain at least 2 columns to be able to display any data.')
        header = header[:value_columns+1] if len(header) > value_columns + 1 else header

        identity_column_name: str = header[0]
        value_column_names: list[str] = header[1:]
        value_columns = len(value_column_names)

        data: list[list[str]] = [row[:1+value_columns+1] for row in values[row_start+1:row_end+1]]

        embed.clear_fields()
        for row_num, row in enumerate(data):
            embed.add_field(name=f'{identity_column_name} {emoji_from_number(row_start+row_num+1)}', value=f'**{row[0]}**', inline=False)
            for i, column in enumerate(row[1:]):
                embed.add_field(name=value_column_names[i], value=column, inline=True)

        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.blurple, custom_id='display_sheet_next_page_button')
    async def next(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        # Validate permissions
        if not interaction.message:
            await interaction.response.send_message('Could not find interaction message.', ephemeral=True)
            return
        # Get message and validate action
        embed: discord.Embed = interaction.message.embeds[0]
        if not embed.footer or not embed.footer.text:
            await interaction.response.send_message('Embed footer was empty.', ephemeral=True)
            return
        footer_parts: list[str] = embed.footer.text.split('/')[0:6]
        value_columns, num_rows, total_rows, current_page, num_pages, key = footer_parts
        sheet_name: str = embed.footer.text.split(f'{key}/')[1]
        value_columns = int(value_columns)
        num_rows = int(num_rows)
        total_rows = int(total_rows)
        current_page = int(current_page)
        num_pages = int(num_pages)
        if current_page >= num_pages:
            await interaction.response.send_message('There is no next page to go to. You are already on the last page.', ephemeral=True)
            return
        target_page: int = current_page + 1
        page_rows: int = num_rows if target_page < num_pages else (total_rows % num_rows)

        await interaction.response.defer()

        embed.remove_footer()
        embed.set_footer(text=f'{value_columns}/{num_rows}/{total_rows}/{target_page}/{num_pages}/{key}/{sheet_name}')

        embed.description = f'Page {target_page} / {num_pages}'

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(key)

        sheet: AsyncioGspreadWorksheet = await ss.worksheet(sheet_name)
        values: list[list[str]] = await sheet.get_all_values()

        row_start: int = (target_page - 1) * num_rows
        row_end: int = row_start + page_rows
        if not values or len(values) <= 1 or len(values) - 1 < row_end:
            await interaction.followup.send(f'Could not fetch requested data from sheet (rows {row_start + 2}-{row_end + 2}). Please verify that it is still there.', ephemeral=True)
            return
        
        header: list[str] = values[0]
        if len(header) <= 1:
            raise commands.CommandError(message=f'Sheet `{sheet_name}` must contain at least 2 columns to be able to display any data.')
        header = header[:value_columns+1] if len(header) > value_columns + 1 else header

        identity_column_name: str = header[0]
        value_column_names: list[str] = header[1:]
        value_columns = len(value_column_names)

        data: list[list[str]] = [row[:1+value_columns+1] for row in values[row_start+1:row_end+1]]

        embed.clear_fields()
        for row_num, row in enumerate(data):
            embed.add_field(name=f'{identity_column_name} {emoji_from_number(row_start+row_num+1)}', value=f'**{row[0]}**', inline=False)
            for i, column in enumerate(row[1:]):
                embed.add_field(name=value_column_names[i], value=column, inline=True)

        await interaction.message.edit(embed=embed, view=self)
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, _: discord.ui.Item[Any]) -> None:
        await interaction.followup.send(str(error), ephemeral=True)
        print(error)
        traceback.print_tb(error.__traceback__)

class Sheets(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    async def cog_load(self) -> None:
        # Register persistent views
        self.bot.add_view(SheetPageView(self.bot))

    @commands.hybrid_command(pass_context=True, aliases=['sheet'])
    async def display_sheet(self, ctx: commands.Context, key: str | None, sheet_name: str | None = None, number_of_value_columns: int | None = None) -> None:
        '''
        Displays info from a Google sheet.

        Args:
            key (str | None): The key to your sheet. This is the part of the URL that comes after "spreadsheets/d/" and before "/edit".
            sheet_name (str | None, optional): The sheet name to display. Defaults to None for the first sheet.
            value_columns (int | None, optional): The number of value columns to display. Defaults to None for auto-detect. Max number of value columns supported is 4, excluding the first column that is used as row title / name.
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

        value_columns: int | None = int(number_of_value_columns) if number_of_value_columns else None

        if not key:
            raise commands.CommandError(message=f'The key to your sheet is required to display any data.')
        if value_columns and (value_columns < 0 or value_columns > 4):
            raise commands.CommandError(message=f'Number of value columns is invalid: {value_columns}. Please choose a number between 1 and 4, or leave it at default to auto-detect.')
        value_columns = value_columns if value_columns else 4
        
        await ctx.defer()

        agc: AsyncioGspreadClient = await self.bot.agcm.authorize()
        ss: AsyncioGspreadSpreadsheet = await agc.open_by_key(key)

        sheet: AsyncioGspreadWorksheet = await ss.worksheet(sheet_name) if sheet_name else await ss.get_sheet1()
        sheet_name = sheet.title
        values: list[list[str]] = await sheet.get_all_values()

        if not values or len(values) <= 1:
            raise commands.CommandError(message=f'Sheet `{sheet_name}` contains no data.')
        
        rows: int = len(values) - 1

        header: list[str] = values[0]
        if len(header) <= 1:
            raise commands.CommandError(message=f'Sheet `{sheet_name}` must contain at least 2 columns to be able to display any data.')
        header = header[:value_columns+1] if len(header) > value_columns + 1 else header

        identity_column_name: str = header[0]
        value_column_names: list[str] = header[1:]
        value_columns = len(value_column_names)

        # Embed supports up to 25 fields
        # If each column takes one field, then we can display a certain number of rows depending on the number of columns that are used
        rows = min(math.floor(25 / (1 + value_columns)), rows)

        data: list[list[str]] = [row[:1+value_columns+1] for row in values[1:rows+1]]

        embed = discord.Embed(title=f'**{sheet_name}**', description=f'Page 1 / {math.ceil((len(values)-1)/rows)}', colour=0x00b2ff)
        for row_num, row in enumerate([r[:value_columns+1] for r in data]):
            embed.add_field(name=f'{identity_column_name} {emoji_from_number(row_num+1)}', value=f'**{row[0]}**', inline=False)
            for i, column in enumerate(row[1:]):
                embed.add_field(name=value_column_names[i], value=column, inline=True)

        # Footer encodes: number of value columns, number of rows per page, total number of rows, current page, number of pages, key, sheet name
        embed.set_footer(text=f'{value_columns}/{rows}/{len(values)-1}/1/{math.ceil((len(values)-1)/rows)}/{key}/{sheet_name}')

        view = SheetPageView(self.bot)
        await ctx.send(embed=embed, view=view)


async def setup(bot: Bot) -> None:
    await bot.add_cog(Sheets(bot))
