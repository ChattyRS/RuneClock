import math
import discord
from discord.ext import commands
from discord.ext.commands import Cog
from gspread_asyncio import AsyncioGspreadClient, AsyncioGspreadSpreadsheet, AsyncioGspreadWorksheet
from src.bot import Bot

class Sheets(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot: Bot = bot

    @commands.hybrid_command(pass_context=True, aliases=['sheet'])
    async def display_sheet(self, ctx: commands.Context, key: str | None, sheet_name: str | None = None, value_columns: int | None = None) -> None:
        '''
        Displays info from a Google sheet.

        Args:
            key (str | None): The key to your sheet. This is the part of the URL that comes after "spreadsheets/d/" and before "/edit".
            sheet_name (str | None, optional): The sheet name to display. Defaults to None for the first sheet.
            value_columns (int | None, optional): The number of value columns to display. Defaults to None for auto-detect. Max number of value columns supported is 4, excluding the first column that is used as row title / name.

        Raises:
            commands.CommandError: _description_
            commands.CommandError: _description_
        '''
        self.bot.increment_command_counter()
        await ctx.channel.typing()

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

        embed = discord.Embed(title=f'**{sheet_name}**', colour=0x00b2ff)
        for row in data:
            embed.add_field(name=identity_column_name, value=f'**{row[0]}**', inline=False)
            for i, column in enumerate(row[1:]):
                embed.add_field(name=value_column_names[i], value=column, inline=True)

        await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    await bot.add_cog(Sheets(bot))
