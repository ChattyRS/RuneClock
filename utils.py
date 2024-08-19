import codecs
import json
import re
from numpy import number
from oauth2client.service_account import ServiceAccountCredentials
from discord.ext import commands
import math
from datetime import datetime, timedelta
import discord
import logging

# convert float to string without scientific notation
# https://stackoverflow.com/questions/38847690/convert-float-to-string-without-scientific-notation-and-false-precision
import decimal

# create a new context for this task
decimal_ctx = decimal.Context()

# 20 digits should be enough for everyone :D
decimal_ctx.prec = 20

'''
Load config file with necessary information
'''
def config_load():
    with codecs.open('data/config.json', 'r', encoding='utf-8-sig') as doc:
        #  Please make sure encoding is correct, especially after editing the config file
        return json.load(doc)

config = config_load()

max_cash = 2147483647

'''
Check functions used for commands
'''
def is_owner():
    async def predicate(ctx):
        if ctx.author.id == config['owner']:
            return True
        raise commands.CommandError(message='Insufficient permissions: `Owner`')
    return commands.check(predicate)

def is_admin():
    async def predicate(ctx):
        try:
            portables = ctx.bot.get_guild(config['portablesServer'])
            if portables:
                member = await portables.fetch_member(ctx.author.id)
                if member:
                    admin_role = portables.get_role(config['adminRole'])
                    if admin_role in member.roles:
                        return True
        except:
            pass
        if ctx.author.guild_permissions.administrator or ctx.author.id == ctx.guild.owner.id or ctx.author.id == config['owner']:
            return True
        raise commands.CommandError(message='Insufficient permissions: `Admin`')
    return commands.check(predicate)

def portables_leader():
    async def predicate(ctx):
        portables = ctx.bot.get_guild(config['portablesServer'])
        if portables:
            member = await portables.fetch_member(ctx.author.id)
            if member:
                leader_role = portables.get_role(config['leaderRole'])
                if leader_role in member.roles:
                    return True
        if ctx.author.id == config['owner']:
            return True
        raise commands.CommandError(message='Insufficient permissions: `Portables leader`')
    return commands.check(predicate)

def portables_admin():
    async def predicate(ctx):
        portables = ctx.bot.get_guild(config['portablesServer'])
        if portables:
            member = await portables.fetch_member(ctx.author.id)
            if member:
                admin_role = portables.get_role(config['adminRole'])
                if admin_role in member.roles:
                    return True
        if ctx.author.id == config['owner']:
            return True
        raise commands.CommandError(message='Insufficient permissions: `Portables admin`')
    return commands.check(predicate)

def is_mod():
    async def predicate(ctx):
        portables = ctx.bot.get_guild(config['portablesServer'])
        if portables:
            member = await portables.fetch_member(ctx.author.id)
            if member:
                mod_role = portables.get_role(config['modRole'])
                if mod_role in member.roles:
                    return True
        if ctx.author.id == config['owner']:
            return True
        raise commands.CommandError(message='Insufficient permissions: `Portables moderator`')
    return commands.check(predicate)

def is_rank():
    async def predicate(ctx):
        portables = ctx.bot.get_guild(config['portablesServer'])
        if portables:
            member = await portables.fetch_member(ctx.author.id)
            if member:
                rank_role = portables.get_role(config['rankRole'])
                if rank_role in member.roles:
                    return True
        if ctx.author.id == config['owner']:
            return True
        raise commands.CommandError(message='Insufficient permissions: `Portables rank`')
    return commands.check(predicate)

def is_helper():
    async def predicate(ctx):
        portables = ctx.bot.get_guild(config['portablesServer'])
        if portables:
            member = await portables.fetch_member(ctx.author.id)
            if member:
                helper_role = portables.get_role(config['helperRole'])
                if helper_role in member.roles:
                    return True
        if ctx.author.id == config['owner']:
            return True
        raise commands.CommandError(message='Insufficient permissions: `Portables helper`')
    return commands.check(predicate)

def portables_only():
    async def predicate(ctx):
        if ctx.guild.id == config['portablesServer']:
            return True
        if ctx.author.id == config['owner']:
            return True
        raise commands.CommandError(message='Insufficient permissions: `Portables server only`')
    return commands.check(predicate)

def obliterate_only():
    async def predicate(ctx):
        if ctx.author.id == config['owner']:
            return True
        if ctx.guild.id == config['obliterate_guild_id']:
            return True
        raise commands.CommandError(message='Insufficient permissions: `Obliterate server only`')
    return commands.check(predicate)

def obliterate_mods():
    async def predicate(ctx):
        if ctx.author.id == config['owner']:
            return True
        obliterate = ctx.bot.get_guild(config['obliterate_guild_id'])
        if obliterate:
            member = await obliterate.fetch_member(ctx.author.id)
            if member:
                mod_role = obliterate.get_role(config['obliterate_moderator_role_id'])
                key_role = obliterate.get_role(config['obliterate_key_role_id'])
                if mod_role in member.roles or key_role in member.roles:
                    return True
        raise commands.CommandError(message='Insufficient permissions: `Obliterate moderator`')
    return commands.check(predicate)

def get_coins_image_name(amount: number):
    amount = abs(amount)
    if amount >= 10000:
        return 'Coins_10000_detail'
    elif amount >= 1000:
        return 'Coins_1000_detail'
    elif amount >= 250:
        return 'Coins_250_detail'
    elif amount >= 100:
        return 'Coins_100_detail'
    elif amount >= 25:
        return 'Coins_25_detail'
    elif amount >= 5:
        return 'Coins_5_detail'
    elif amount >= 1 and amount <= 5:
        return f'Coins_{amount}_detail'
    else:
         return 'Coins_1_detail'

def get_gspread_creds():
    return ServiceAccountCredentials.from_json_keyfile_name('data/gspread.json',
      ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive',
      'https://www.googleapis.com/auth/spreadsheets'])

def is_name(member_name, member):
    pattern = re.compile('[\W_]+')
    name = member.display_name.upper()
    if member_name.upper() in pattern.sub('', name):
        return True
    else:
        return False

class RoleConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument) -> discord.Role:
        if not argument or not ctx.guild:
            raise commands.CommandError(message=f'Required argument missing: `role`.')
        if len(ctx.message.role_mentions) == 1:
            return ctx.message.role_mentions[0]
        id_match, mention_match, name_match, case_insensitive_match, substring_match = None, None, None, None, None
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
        raise commands.CommandError(message=f'Could not find role: `{argument}`.')

zero_digit =  [
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 1, 0]
]
one_digit = [
    [0, 1, 0],
    [1, 1, 0],
    [0, 1, 0],
    [0, 1, 0],
    [0, 1, 0],
    [0, 1, 0],
    [0, 1, 0],
    [1, 1, 1]
]
two_digit = [
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [0, 0, 0, 0, 1],
    [0, 0, 0, 1, 0],
    [0, 0, 1, 0, 0],
    [0, 1, 0, 0, 0],
    [1, 0, 0, 0, 0],
    [1, 1, 1, 1, 1]
]
three_digit = [
    [0, 1, 1, 0],
    [1, 0, 0, 1],
    [0, 0, 0, 1],
    [0, 1, 1, 0],
    [0, 0, 0, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1],
    [0, 1, 1, 0]
]
four_digit = [
    [1, 0, 0, 0],
    [1, 0, 0, 0],
    [1, 0, 0, 0],
    [1, 0, 1, 0],
    [1, 0, 1, 0],
    [1, 1, 1, 1],
    [0, 0, 1, 0],
    [0, 0, 1, 0]
]
five_digit = [
    [1, 1, 1, 1],
    [1, 0, 0, 0],
    [1, 0, 0, 0],
    [1, 1, 1, 0],
    [0, 0, 0, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1],
    [0, 1, 1, 0]
]
six_digit = [
    [0, 0, 1, 1, 0],
    [0, 1, 0, 0, 1],
    [1, 0, 0, 0, 0],
    [1, 0, 1, 1, 0],
    [1, 1, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 1, 0]
]
seven_digit = [
    [1, 1, 1, 1],
    [0, 0, 0, 1],
    [0, 0, 1, 0],
    [0, 0, 1, 0],
    [0, 1, 0, 0],
    [0, 1, 0, 0],
    [1, 0, 0, 0],
    [1, 0, 0, 0]
]
eight_digit = [
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 1, 1, 0]
]
nine_digit = [
    [0, 1, 1, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 0, 0, 1],
    [0, 0, 1, 1, 1],
    [0, 0, 0, 0, 1],
    [0, 0, 0, 0, 1],
    [0, 0, 0, 0, 1]
]
k_char = [
    [1, 0, 0, 0, 1],
    [1, 0, 0, 1, 0],
    [1, 0, 1, 0, 0],
    [1, 1, 0, 0, 0],
    [1, 1, 0, 0, 0],
    [1, 0, 1, 0, 0],
    [1, 0, 0, 1, 0],
    [1, 0, 0, 0, 1]
]
m_char = [
    [1, 0, 0, 0, 1],
    [1, 1, 0, 1, 1],
    [1, 0, 1, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1]
]
minus_char = [
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [1, 1, 1, 1, 1],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0]
]

digits = [zero_digit, one_digit, two_digit, three_digit, four_digit, five_digit, six_digit, seven_digit, eight_digit, nine_digit, k_char, m_char, minus_char]

zero_digit_rs3 =  [
    [0, 0, 1, 0, 0],
    [0, 1, 0, 1, 0],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 0, 0, 1],
    [0, 1, 0, 1, 0],
    [0, 0, 1, 0, 0]
]
digits_rs3 = [zero_digit_rs3, one_digit, two_digit, three_digit, four_digit, five_digit, six_digit, seven_digit, eight_digit, nine_digit]

black = [0, 0, 0, 255]

def draw_digit(im, digit, x, y, c, osrs):
    colour = c
    if im.shape[2] == 3 and len(c) > 3:
        colour = colour[:3]
    elif im.shape[2] == 4 and len(c) < 4:
        colour.append(255)
    if osrs:
        pixels = digits[digit]
    else:
        pixels = digits_rs3[digit]
    x_0 = x
    for row in reversed(pixels):
        x = x_0
        for value in reversed(row):
            if value == 1:
                im[y, x] = colour
            x -= 1
        y -= 1
    return (x-1, y)

def draw_num(im, num, x, y, c, osrs):
    if not is_int(num):
        raise ValueError(f'Invalid Integer argument: {num}')
    else:
        num = int(num)
    digit_list = []
    for i in range(len(str(num))):
        digit_list.append(int(str(num)[i]))
    if len(digit_list) == 1:
        x -= 3
    for digit in reversed(digit_list):
        if osrs: 
            draw_digit(im, digit, x, y, black, osrs)
            x, y = x-1, y-1
        x, _ = draw_digit(im, digit, x, y, c, osrs)
        if osrs:
            y += 1

def draw_outline_osrs(im, x0, y0, c):
    colour = c
    if im.shape[2] == 3 and len(c) > 3:
        colour = colour[:3]
    elif im.shape[2] == 4 and len(c) < 4:
        colour.append(255)
    for x in range(x0, x0+62):
        for y in range(y0, y0+32):
            if ((y-y0 == 0 and (x-x0 >= 3 and x-x0 <= 58)) or 
                (y-y0 == 31 and (x-x0 >= 3 and x-x0 <= 58)) or
                (x-x0 == 0 and (y-y0 >= 3 and y-y0 <= 28)) or
                (x-x0 == 61 and (y-y0 >= 3 and y-y0 <= 28))):
                im[y, x] = colour
            elif ((x-x0 == 3 and y-y0 < 3) or
                  (y-y0 == 3 and x-x0 < 3) or
                  (x-x0 == 2 and y-y0 == 2)):
                im[y, x] = colour
            elif ((x-x0 == 58 and y-y0 < 3) or
                  (y-y0 == 3 and x-x0 > 58) or
                  (x-x0 == 59 and y-y0 == 2)):
                im[y, x] = colour
            elif ((x-x0 == 3 and y-y0 > 28) or
                  (y-y0 == 28 and x-x0 < 3) or
                  (x-x0 == 2 and y-y0 == 29)):
                im[y, x] = colour
            elif ((x-x0 == 58 and y-y0 > 28) or
                  (y-y0 == 28 and x-x0 > 58) or
                  (x-x0 == 59 and y-y0 == 29)):
                im[y, x] = colour

def draw_outline_rs3(im, x0, y0, c):
    colour = c
    if im.shape[2] == 3 and len(c) > 3:
        colour = colour[:3]
    elif im.shape[2] == 4 and len(c) < 4:
        colour.append(255)
    for x in range(x0, x0+58):
        for y in range(y0, y0+25):
            if x == x0 or x == x0+57 or y == y0 or y == y0+24:
                im[y, x] = colour

def level_to_xp(level):
    return math.floor(1/4 * sum([math.floor(x + 300 * 2 ** (x/7)) for x in range(1, level)]))

def xp_to_level(xp):
    if is_int(xp):
        xp = int(xp)
    else:
        raise ValueError(f'Invalid Integer argument: {xp}')
    for level in range(120, 0, -1):
        if xp >= level_to_xp(level):
            return level
    return 1

def combat_level(attack, strength, defence, constitution, magic, ranged, prayer, summoning):
    return (13/10 * max(attack + strength, 2 * magic, 2 * ranged) + defence + constitution + math.floor(1/2 * prayer) + math.floor(1/2 * summoning)) / 4

def osrs_combat_level(attack, strength, defence, hitpoints, magic, ranged, prayer):
    base = (defence + hitpoints + math.floor(prayer / 2)) / 4
    melee = 13 / 40 * (attack + strength)
    _range = 13 / 40 * math.floor(ranged * 3 / 2)
    mage = 13 / 40 * math.floor(magic * 3 / 2)
    final = math.floor(base + max(melee, _range, mage))
    return final

unit_aliases = {    
    # distance
    'millimeters': 'mm', 'millimetres': 'mm',
    'centimeters': 'cm', 'centimetres': 'cm',
    'decimeters': 'dm', 'decimetres': 'dm',
    'meters': 'm', 'metres': 'm',
    'decameters': 'dam', 'decametres': 'dam',
    'hectometers': 'hm', 'hectometres': 'hm',
    'kilometers': 'km', 'kilometres': 'km',
    'inches': 'in', '\"': 'in',
    'foot': 'ft', 'feet': 'ft', '\'': 'ft',
    'yards': 'yd',
    'miles': 'mi',
    'au': 'AU', 'ua': 'AU', 'astronomicalunits': 'AU',
    'parsecs': 'pc',
    'lightyears': 'ly', 'light-years': 'ly',
    # time
    'milliseconds': 'ms',
    'seconds': 's', 'sec': 's',
    'minutes': 'min',
    'hours': 'h',
    'days': 'day', 'd': 'day',
    'weeks': 'week',
    'months': 'month',
    'years': 'year', 'yr': 'year',
    'decades': 'decade',
    'centuries': 'century',
    'millenniums': 'millennium', 'millennia': 'millennium',
    # mass
    'milligrams': 'mg',
    'grams': 'g',
    'kilograms': 'kg',
    'ounces': 'oz',
    'troyounces': 'oz t', 'ozt': 'oz t',
    'pounds': 'lb', 'lbs': 'lb',
    'st': 'st.', 'stones': 'st.',
    'earthmasses': 'M⊕', 'me': 'M⊕', 'm⊕': 'M⊕',
    'solarmasses': 'M☉', 'm☉': 'M☉',
    # temperature
    'c': '°C', '°c': '°C', 'celcius': '°C',
    'f': '°F', '°f': '°F', 'fahrenheit': '°F',
    'k': 'K', 'kelvin': 'K',
    # energy
    'millijoules': 'mJ', 'mj': 'mJ',
    'joules': 'J', 'j': 'J',
    'kilojoules': 'kJ', 'kj': 'kJ',
    'wh': 'Wh', 'watthour': 'Wh', 'watt-hour': 'Wh',
    'kwh': 'kWh', 'kilowatthour': 'kWh', 'kilowatt-hour': 'kWh',
    'millicalories': 'mcal',
    'calories': 'cal',
    'kilocalories': 'kcal',
    'millielectronvolts': 'meV', 'mev': 'meV',
    'electronvolts': 'eV', 'ev': 'eV',
    'kiloelectronvolts': 'keV', 'kev': 'keV',
    'btu': 'Btu',
    'therms': 'thm',
    # speed
    'metersperseconds': 'm/s', 'metresperseconds': 'm/s', 'meterperseconds': 'm/s', 'metreperseconds': 'm/s', 'm/sec': 'm/s',
    'kilometersperhours': 'km/h', 'kilometerperhours': 'km/h', 'kilometresperhour': 'km/h', 'kilometreperhours': 'km/h', 'kmh': 'km/h', 'kph': 'km/h',
    'fps': 'ft/s', 'footperseconds': 'ft/s', 'feetperseconds': 'ft/s',
    'mi/h': 'mph', 'milesperhours': 'mph',
    'knots': 'kn', 'kt': 'kn',
    'speedoflight': 'c', 'lightspeed': 'c',
    # area
    'mm2': 'mm²', 'mm^2': 'mm²', 'sqmm': 'mm²', 'mmsq': 'mm²',
    'm2': 'm²', 'm^2': 'm²', 'sqm': 'm²', 'msq': 'm²',
    'km2': 'km²', 'km^2': 'km²', 'sqkm': 'km²', 'kmsq': 'km²',
    'in2': 'in²', 'in^2': 'in²', 'sqin': 'in²', 'insq': 'in²',
    'ft2': 'ft²', 'ft^2': 'ft²', 'sqft': 'ft²', 'ftsq': 'ft²',
    'yd2': 'yd²', 'yd^2': 'yd²', 'sqyd': 'yd²', 'ydsq': 'yd²',
    'mi2': 'mi²', 'mi^2': 'mi²', 'sqmi': 'mi²', 'misq': 'mi²',
    'ares': 'a',
    'hectares': 'ha',
    'acres': 'ac',
    # volume
    'milliliters': 'mL', 'millilitres': 'mL', 'ml': 'mL',
    'centiliters': 'cL', 'centilitres': 'cL', 'cl': 'cL',
    'deciliters': 'dL', 'decilitres': 'dL', 'dl': 'dL',
    'liters': 'L', 'litres': 'L', 'l': 'L',
    'decaliters': 'daL', 'decalitres': 'daL', 'dal': 'daL',
    'hectoliters': 'hL', 'hectolitres': 'hL', 'hl': 'hL',
    'kiloliters': 'kL', 'kilolitres': 'kL', 'kl': 'kL',
    'mm3': 'mm³', 'cubicmillimeters': 'mm³', 'cubicmillimetres': 'mm³',
    'cm3': 'cm³', 'cubiccentimeters': 'cm³', 'cubiccentimetres': 'cm³',
    'dm3': 'dm³', 'cubicdecimeters': 'dm³', 'cubicdecimetres': 'dm³',
    'm3': 'm³', 'cubicmeters': 'm³', 'cubicmetres': 'm³',
    'dam3': 'dam³', 'cubicdecameters': 'dam³', 'cubicdecametres': 'dam³',
    'hm3': 'hm³', 'cubihectometers': 'hm³', 'cubichectometres': 'hm³',
    'km3': 'km³', 'cubickilometers': 'km³', 'cubickilometres': 'km³',
    'in3': 'in³', 'cubicinches': 'in³',
    'ft3': 'ft³', 'cubicfeet': 'ft³', 'cubicfoot': 'ft³',
    'yd3': 'yd³', 'cubicyards': 'yd³',
    'mi3': 'mi³', 'cubicmiles': 'mi³',
    'gallons': 'gal', 
    'quarts': 'qt.', 'qt' : 'qt.',
    'pints': 'pt', 
    'cups': 'cp',
    'floz': 'fl oz', 'fluid ounces': 'fl oz',
    'tablespoons': 'tbsp', 
    'teaspoon': 'tsp'
}

units = { 
    # length
    'mm': {'mm': 1, 'cm': 1/10, 'dm': 1/100, 'm': 1/1000, 'dam': 1/10000, 'hm': 1/100000, 'km': 1/1000000, 'in': 0.0393701, 'ft': 0.00328084, 'yd': 0.00109361, 'mi': 0.00000062137, 'AU': 1/1.495978707e14, 'pc': 1/3.08567782e19, 'ly': 1/9460730472580000000},
    'cm': {'mm': 10, 'cm': 1, 'dm': 1/10, 'm': 1/100, 'dam': 1/1000, 'hm': 1/10000, 'km': 1/100000, 'in': 0.393701, 'ft': 0.0328084, 'yd': 0.0109361, 'mi': 0.0000062137, 'AU': 1/1.495978707e13, 'pc': 1/3.08567782e18, 'ly': 1/946073047258000000},
    'dm': {'mm': 100, 'cm': 10, 'dm': 1, 'm': 1/10, 'dam': 1/100, 'hm': 1/1000, 'km': 1/10000, 'in': 3.93701, 'ft': 0.328084, 'yd': 0.109361, 'mi': 0.000062137, 'AU': 1/1.495978707e12, 'pc': 1/3.08567782e17, 'ly': 1/94607304725800000},
    'm': {'mm': 1000, 'cm': 100, 'dm': 10, 'm': 1, 'dam': 1/10, 'hm': 1/100, 'km': 1/1000, 'in': 39.3701, 'ft': 3.28084, 'yd': 1.09361, 'mi': 0.000621371, 'AU': 1/1.495978707e11, 'pc': 1/3.08567782e16, 'ly': 1/9460730472580000},
    'dam': {'mm': 10000, 'cm': 1000, 'dm': 100, 'm': 10, 'dam': 1, 'hm': 1/10, 'km': 1/100, 'in': 393.701, 'ft': 32.8084, 'yd': 10.9361, 'mi': 0.00621371, 'AU': 1/1.495978707e10, 'pc': 1/3.08567782e15, 'ly': 1/946073047258000},
    'hm': {'mm': 100000, 'cm': 10000, 'dm': 1000, 'm': 100, 'dam': 10, 'hm': 1, 'km': 1/10, 'in': 3937.01, 'ft': 328.084, 'yd': 109.361, 'mi': 0.0621371, 'AU': 1/1.495978707e9, 'pc': 1/3.08567782e14, 'ly': 1/94607304725800},
    'km': {'mm': 1000000, 'cm': 100000, 'dm': 10000, 'm': 1000, 'dam': 100, 'hm': 10, 'km': 1, 'in': 39370.1, 'ft': 3280.84, 'yd': 1093.61, 'mi': 0.621371, 'AU': 1/1.495978707e8, 'pc': 1/3.08567782e13, 'ly': 1/9460730472580},
    'in': {'mm': 25.4, 'cm': 2.54, 'dm': 0.254, 'm': 0.0254, 'dam': 0.00254, 'hm': 0.000254, 'km': 0.0000254, 'in': 1, 'ft': 1/12, 'yd': 1/36, 'mi': 1/63360, 'AU': 2.54*1/1.495978707e13, 'pc': 2.54*1/3.08567782e18, 'ly': 2.54*1/946073047258000000},
    'ft': {'mm': 304.8, 'cm': 30.48, 'dm': 3.048, 'm': 0.3048, 'dam': 0.03048, 'hm': 0.003048, 'km': 0.0003048, 'in': 12, 'ft': 1, 'yd': 1/3, 'mi': 1/5280, 'AU': 0.3048*1/1.495978707e11, 'pc': 0.3048*1/3.08567782e16, 'ly': 0.3048*1/9460730472580000},
    'yd': {'mm': 914.4, 'cm': 91.44, 'dm': 9.144, 'm': 0.9144, 'dam': 0.09144, 'hm': 0.009144, 'km': 0.0009144, 'in': 36, 'ft': 3, 'yd': 1, 'mi': 1/1760, 'AU': 0.9144*1/1.495978707e11, 'pc': 0.9144*1/3.08567782e16, 'ly': 0.9144*1/9460730472580000},
    'mi': {'mm': 1609340, 'cm': 160934, 'dm': 16093.4, 'm': 1609.34, 'dam': 160.934, 'hm': 16.0934, 'km': 1.60934, 'in': 63360, 'ft': 5280, 'yd': 1760, 'mi': 1, 'AU': 1609.34*1/1.495978707e11, 'pc': 1609.34*1/3.08567782e16, 'ly': 1609.34*1/9460730472580000},
    'AU': {'mm': 1.495978707e14, 'cm': 1.495978707e13, 'dm': 1.495978707e12, 'm': 1.495978707e11, 'dam': 1.495978707e10, 'hm': 1.495978707e9, 'km': 1.495978707e8, 'in': 2.54*1.495978707e13, 'ft': 0.3048*1.495978707e11, 'yd': 0.9144*1.495978707e11, 'mi': 1609.34*1.495978707e11, 'AU': 1, 'pc': 4.84814e-6, 'ly': 1.5813e-5},
    'pc': {'mm': 3.08567782e19, 'cm': 3.08567782e18, 'dm': 3.08567782e17, 'm': 3.08567782e16, 'dam': 3.08567782e15, 'hm': 3.08567782e14, 'km': 3.08567782e13, 'in': 2.54*3.08567782e18, 'ft': 0.3048*3.08567782e16, 'yd': 0.9144*3.08567782e16, 'mi': 1609.34*3.08567782e16, 'AU': 2.06265e5, 'pc': 1, 'ly': 3.26156},
    'ly': {'mm': 9460730472580000000, 'cm': 946073047258000000, 'dm': 94607304725800000, 'm': 9460730472580000, 'dam': 946073047258000, 'hm': 94607304725800, 'km': 9460730472580, 'in': 2.54*946073047258000000, 'ft': 0.3048*9460730472580000, 'yd': 0.9144*9460730472580000, 'mi': 1609.34*9460730472580000, 'AU': 63241, 'pc': 0.3066, 'ly': 1},

    # time
    'ms': {'ms': 1, 's': 1/1000, 'min': 1/1000/60, 'h': 1/1000/60/60, 'day': 1/1000/60/60/24, 'week': 1/1000/60/60/24/7, 'month': 1/1000/60/60/24/30.43685, 'year': 1/1000/60/60/24/365.2422, 'decade': 1/1000/60/60/24/365.2422/10, 'century': 1/1000/60/60/24/365.2422/100, 'millennium': 1/1000/60/60/24/365.2422/1000},
    's': {'ms': 1000, 's': 1, 'min': 1/60, 'h': 1/60/60, 'day': 1/60/60/24, 'week': 1/60/60/24/7, 'month': 1/60/60/24/30.43685, 'year': 1/60/60/24/365.2422, 'decade': 1/60/60/24/365.2422/10, 'century': 1/60/60/24/365.2422/100, 'millennium': 1/60/60/24/365.2422/1000},
    'min': {'ms': 60000, 's': 60, 'min': 1, 'h': 1/60, 'day': 1/60/24, 'week': 1/60/24/7, 'month': 1/60/24/30.43685, 'year': 1/60/24/365.2422, 'decade': 1/60/24/365.2422/10, 'century': 1/60/24/365.2422/100, 'millennium': 1/60/24/365.2422/1000},
    'h': {'ms': 3600000, 's': 3600, 'min': 60, 'h': 1, 'day': 1/24, 'week': 1/24/7, 'month': 1/24/30.43685, 'year': 1/24/365.2422, 'decade': 1/24/365.2422/10, 'century': 1/24/365.2422/100, 'millennium': 1/24/365.2422/1000},
    'day': {'ms': 24*3600000, 's': 24*3600, 'min': 24*60, 'h': 24, 'day': 1, 'week': 1/7, 'month': 1/30.43685, 'year': 1/365.2422, 'decade': 1/365.2422/10, 'century': 1/365.2422/100, 'millennium': 1/365.2422/1000},
    'week': {'ms': 7*24*3600000, 's': 7*24*3600, 'min': 7*24*60, 'h': 7*24, 'day': 7, 'week': 1, 'month': 7/30.43685, 'year': 1/52.177457142857142857142857142857, 'decade': 1/52.177457142857142857142857142857/10, 'century': 1/52.177457142857142857142857142857/100, 'millennium': 1/52.177457142857142857142857142857/1000},
    'month': {'ms': 30.43685*24*3600000, 's': 30.43685*24*3600, 'min': 30.43685*24*60, 'h': 30.43685*24, 'day': 30.43685, 'week': 30.43685/7, 'month': 1, 'year': 1/12, 'decade': 1/12/10, 'century': 1/12/100, 'millennium': 1/12/1000},
    'year': {'ms': 365.2422*24*3600000, 's': 365.2422*24*3600, 'min': 365.2422*24*60, 'h': 365.2422*24, 'day': 365.2422, 'week': 52.177457142857142857142857142857, 'month': 12, 'year': 1, 'decade': 1/10, 'century': 1/100, 'millennium': 1/1000},
    'decade': {'ms': 10*365.2422*24*3600000, 's': 10*365.2422*24*3600, 'min': 10*365.2422*24*60, 'h': 10*365.2422*24, 'day': 10*365.2422, 'week': 10*52.177457142857142857142857142857, 'month': 10*12, 'year': 10, 'decade': 1, 'century': 1/10, 'millennium': 1/100},
    'century': {'ms': 100*365.2422*24*3600000, 's': 100*365.2422*24*3600, 'min': 100*365.2422*24*60, 'h': 100*365.2422*24, 'day': 100*365.2422, 'week': 100*52.177457142857142857142857142857, 'month': 100*12, 'year': 100, 'decade': 10, 'century': 1, 'millennium': 1/10},
    'millennium': {'ms': 1000*365.2422*24*3600000, 's': 1000*365.2422*24*3600, 'min': 1000*365.2422*24*60, 'h': 1000*365.2422*24, 'day': 1000*365.2422, 'week': 1000*52.177457142857142857142857142857, 'month': 1000*12, 'year': 1000, 'decade': 100, 'century': 10, 'millennium': 1},

    # mass
    'mg': {'mg': 1, 'g': 1/1000, 'kg': 1/1000000, 'oz': 0.000035274, 'oz t': 1/31.1034768/1000, 'lb': 0.0000022046, 'st.': 1.5747e-7, 'M⊕': 1/5.9722e30, 'M☉': 1/1.98847e36},
    'g': {'mg': 1000, 'g': 1, 'kg': 1/1000, 'oz': 0.035274, 'oz t': 1/31.1034768, 'lb': 0.00220462, 'st.': 1.5747e-4, 'M⊕': 1/5.9722e27, 'M☉': 1/1.98847e33},
    'kg': {'mg': 1000000, 'g': 1000, 'kg': 1, 'oz': 35.274, 'oz t': 1000/31.1034768, 'lb': 2.20462, 'st.': 1.5747e-1, 'M⊕': 1/5.9722e24, 'M☉': 1/1.98847e30},
    'oz': {'mg': 28349.5, 'g': 28.3495, 'kg': 0.0283495, 'oz': 1, 'oz t': 28.3495/31.1034768, 'lb': 0.0625, 'st.': 0.00446429, 'M⊕': 0.0283495*1/5.9722e24, 'M☉': 0.0283495*1/1.98847e30},
    'oz t': {'mg': 31.1034768*1000, 'g': 31.1034768, 'kg': 31.1034768/1000, 'oz': 31.1034768/28.3495, 'oz t': 1, 'lb': 1/(453.592*31.1034768), 'st.': 1/(14*453.592*31.1034768), 'M⊕': 1/(5.9722e27*31.1034768), 'M☉': 1/(1.98847e33*31.1034768)},
    'lb': {'mg': 453592, 'g': 453.592, 'kg': 0.453592, 'oz': 16, 'oz t': 453.592*31.1034768, 'lb': 1, 'st.': 0.0714286, 'M⊕': 0.453592*1/5.9722e24, 'M☉': 0.453592*1/1.98847e30},
    'st.': {'mg': 6.35e+6, 'g': 6.35e+3, 'kg': 6.35, 'oz': 224, 'oz t': 14*453.592*31.1034768, 'lb': 14, 'st.': 1, 'M⊕': 6.35*1/5.9722e24, 'M☉': 6.35*1/1.98847e30},
    'M⊕': {'mg': 5.9722e30, 'g': 5.9722e27, 'kg': 5.9722e24, 'oz': 0.0283495*5.9722e24, 'oz t': 5.9722e27*31.1034768, 'lb': 0.453592*5.9722e24, 'st.': 6.35*5.9722e24, 'M⊕': 1, 'M☉': 5.9722e24/1.98847e30},
    'M☉': {'mg': 1.98847e36, 'g': 1.98847e33, 'kg': 1.98847e30, 'oz': 0.0283495*1.98847e30, 'oz t': 1.98847e33*31.1034768, 'lb': 0.453592*1.98847e30, 'st.': 6.35*1.98847e30, 'M⊕': 1.98847e30/5.9722e24, 'M☉': 1},

    # temperature
    '°C': {'°C': 1, '°F': '*(9/5)+32', 'K': '+273.15'},
    '°F': {'°C': '*(5/9)-(32*5/9)', '°F': 1, 'K': '*(5/9)-(32*5/9)+273.15'},
    'K': {'°C': '-273.15', '°F': '*(9/5)-(273.15*9/5)+32', 'K': 1},

    # area
    'mm²': {'mm²': 1, 'm²': 1e-6, 'km²': 1e-12, 'in²': 0.00155, 'ft²': 1.0764e-5, 'yd²': 1.196e-6, 'mi²': 3.861e-13, 'a': 1e-8, 'ha': 1e-10, 'ac': 2.4711e-10},
    'm²': {'mm²': 1000000, 'm²': 1, 'km²': 1e-6, 'in²': 1550, 'ft²': 10.7639, 'yd²': 1.19599, 'mi²': 3.861e-7, 'a': 1e-2, 'ha': 1e-4, 'ac': 0.000247105},
    'km²': {'mm²': 1e12, 'm²': 1e6, 'km²': 1, 'in²': 1.55e+9, 'ft²': 1.076e+7, 'yd²': 1.196e+6, 'mi²': 0.386102, 'a': 10000, 'ha': 100, 'ac': 247.105},
    'in²': {'mm²': 645.16, 'm²': 0.00064516, 'km²': 6.4516e-10, 'in²': 1, 'ft²': 0.00694444, 'yd²': 0.000771605, 'mi²': 2.491e-10, 'a': 6.4516e-6, 'ha': 6.4516e-8, 'ac': 1.5942e-7},
    'ft²': {'mm²': 92903, 'm²': 0.092903, 'km²': 9.2903e-8, 'in²': 144, 'ft²': 1, 'yd²': 0.111111, 'mi²': 3.587e-8, 'a': 9.2903e-4, 'ha': 9.2903e-6, 'ac': 2.2957e-5},
    'yd²': {'mm²': 836127, 'm²': 0.836127, 'km²': 8.3613e-7, 'in²': 1296, 'ft²': 9, 'yd²': 1, 'mi²': 3.2283e-7, 'a': 8.3613e-3, 'ha': 8.3613e-5, 'ac': 0.000206612},
    'mi²': {'mm²': 2.59e+12, 'm²': 2.59e+6, 'km²': 2.58999, 'in²': 4.014e+9, 'ft²': 2.788e+7, 'yd²': 3.098e+6, 'mi²': 1, 'a': 25899.9, 'ha': 258.999, 'ac': 640},
    'a': {'mm²': 1e8, 'm²': 100, 'km²': 0.0001, 'in²': 1.55e+5, 'ft²': 1076.39, 'yd²': 119.599, 'mi²': 0.0000386102, 'a': 1, 'ha': 1/100, 'ac': 0.0247105},
    'ha': {'mm²': 1e10, 'm²': 10000, 'km²': 0.01, 'in²': 1.55e+7, 'ft²': 107639, 'yd²': 11959.9, 'mi²': 0.00386102, 'a': 100, 'ha': 1, 'ac': 2.47105},
    'ac': {'mm²': 4046860000, 'm²': 4046.86, 'km²': 0.00404686, 'in²': 6.273e+6, 'ft²': 43560, 'yd²': 4840, 'mi²': 0.0015625, 'a': 40.4686, 'ha': 0.404686, 'ac': 1},

    # density

    # energy
    'mJ': {'mJ': 1, 'J': 1/1000, 'kJ': 1/1000000, 'Wh': 0.0000002777778, 'kWh': 2.777778e-10, 'mcal': 0.23900574, 'cal': 0.00023900574, 'kcal': 0.00000023900574, 'meV': 6.24151e+18, 'eV': 6.24151e+15, 'keV': 6.24151e+12, 'Btu': 9.478171e-7, 'thm': 9.480434e-12},
    'J': {'mJ': 1000, 'J': 1, 'kJ': 1/1000, 'Wh': 0.0002777778, 'kWh': 2.777778e-7, 'mcal': 239.00574, 'cal': 0.23900574, 'kcal': 0.00023900574, 'meV': 6.24151e+21, 'eV': 6.24151e+18, 'keV': 6.24151e+15, 'Btu': 9.478171e-4, 'thm': 9.480434e-9},
    'kJ': {'mJ': 1000000, 'J': 1000, 'kJ': 1, 'Wh': 0.2777778, 'kWh': 2.777778e-4, 'mcal': 239005.74, 'cal': 239.00574, 'kcal': 0.23900574, 'meV': 6.24151e+24, 'eV': 6.24151e+21, 'keV': 6.24151e+18, 'Btu': 9.478171e-1, 'thm': 9.480434e-6},
    'Wh': {'mJ': 3600000, 'J': 3600, 'kJ': 3.6, 'Wh': 1, 'kWh': 1/1000, 'mcal': 860421, 'cal': 860.421, 'kcal': 0.860421, 'meV': 2.247e+25, 'eV': 2.247e+22, 'keV': 2.247e+19, 'Btu': 3.41214, 'thm': 3.413e-5},
    'kWh': {'mJ': 3600000000, 'J': 3600000, 'kJ': 3600, 'Wh': 1000, 'kWh': 1, 'mcal': 860421000, 'cal': 860421, 'kcal': 860.421, 'meV': 2.247e+28, 'eV': 2.247e+25, 'keV': 2.247e+22, 'Btu': 3412.14, 'thm': 3.413e-2},
    'mcal': {'mJ': 4.184, 'J': 0.004184, 'kJ': 0.000004184, 'Wh': 0.00000116222, 'kWh': 0.00000000116222, 'mcal': 1, 'cal': 1/1000, 'kcal': 1/1000000, 'meV': 2.611e+19, 'eV': 2.611e+16, 'keV': 2.611e+13, 'Btu': 0.00000396567, 'thm': 3.9666e-11},
    'cal': {'mJ': 4184, 'J': 4.184, 'kJ': 0.004184, 'Wh': 0.00116222, 'kWh': 0.00000116222, 'mcal': 1000, 'cal': 1, 'kcal': 1/1000, 'meV': 2.611e+22, 'eV': 2.611e+19, 'keV': 2.611e+16, 'Btu': 0.00396567, 'thm': 3.9666e-8},
    'kcal': {'mJ': 4184000, 'J': 4184, 'kJ': 4.184, 'Wh': 1.16222, 'kWh': 0.00116222, 'mcal': 1000000, 'cal': 1000, 'kcal': 1, 'meV': 2.611e+25, 'eV': 2.611e+22, 'keV': 2.611e+19, 'Btu': 3.96567, 'thm': 3.9666e-5},
    'meV': {'mJ': 1.6022e-19, 'J': 1.6022e-22, 'kJ': 1.6022e-25, 'Wh': 4.4505e-26, 'kWh': 4.4505e-29, 'mcal': 3.8293e-20, 'cal': 3.8293e-23, 'kcal': 3.8293e-26, 'meV': 1, 'eV': 1/1000, 'keV': 1/1000000, 'Btu': 1.5186e-25, 'thm': 1.5189e-30},
    'eV': {'mJ': 1.6022e-16, 'J': 1.6022e-19, 'kJ': 1.6022e-22, 'Wh': 4.4505e-23, 'kWh': 4.4505e-26, 'mcal': 3.8293e-17, 'cal': 3.8293e-20, 'kcal': 3.8293e-23, 'meV': 1000, 'eV': 1, 'keV': 1/1000, 'Btu': 1.5186e-22, 'thm': 1.5189e-27},
    'keV': {'mJ': 1.6022e-13, 'J': 1.6022e-16, 'kJ': 1.6022e-19, 'Wh': 4.4505e-20, 'kWh': 4.4505e-23, 'mcal': 3.8293e-14, 'cal': 3.8293e-17, 'kcal': 3.8293e-20, 'meV': 1000000, 'eV': 1000, 'keV': 1, 'Btu': 1.5186e-19, 'thm': 1.5189e-24},
    'Btu': {'mJ': 1055060, 'J': 1055.06, 'kJ': 1.05506, 'Wh': 0.293071, 'kWh': 0.000293071, 'mcal': 252164, 'cal': 252.164, 'kcal': 0.252164, 'meV': 6.585e+24, 'eV': 6.585e+21, 'keV': 6.585e+18, 'Btu': 1, 'thm': 1.0002e-5},
    'thm': {'mJ': 1.055e+11, 'J': 1.055e+8, 'kJ': 1.055e+5, 'Wh': 29300.1, 'kWh': 29.3001, 'mcal': 2.521e+10, 'cal': 2.521e+7, 'kcal': 2.521e+4, 'meV': 6.584e+29, 'eV': 6.584e+26, 'keV': 6.584e+23, 'Btu': 99976.1, 'thm': 1},

    # force

    # speed
    'm/s': {'m/s': 1, 'km/h': 3.6, 'ft/s': 3.28084, 'mph': 2.23694, 'kn': 1.94384, 'c': 1/299792458},
    'km/h': {'m/s': 0.277778, 'km/h': 1, 'ft/s': 0.911344, 'mph': 0.621371, 'kn': 0.539957, 'c': 1/1079252848.8},
    'ft/s': {'m/s': 0.3048, 'km/h': 1.09728, 'ft/s': 1, 'mph': 0.681818, 'kn': 0.592484, 'c': 1/983571087.90472},
    'mph': {'m/s': 0.44704, 'km/h': 1.60934, 'ft/s': 1.46667, 'mph': 1, 'kn': 0.868976, 'c': 1/670617740.99852},
    'kn': {'m/s': 0.514444, 'km/h': 1.852, 'ft/s': 1.68781, 'mph': 1.15078, 'kn': 1, 'c': 1/582748571.55872},
    'c': {'m/s': 299792458, 'km/h': 1079252848.8, 'ft/s': 983571087.90472, 'mph': 670617740.99852, 'kn': 582748571.55872, 'c': 1},

    # acceleration

    # storage

    # transfer rates

    # frequency

    # angles

    # pressure

    # volume
    # Other volume units are added by for-loop below
    'mL': {'mL': 1, 'cL': 0.1, 'dL': 0.01, 'L': 0.001, 'daL': 1e-4, 'hL': 1e-5, 'kL': 1e-6, 'mm³': 1000, 'cm³': 1, 'dm³': 0.001, 'm³': 1e-6, 'dam³': 1e-9, 'hm³': 1e-12, 'km³': 1e-15, 'in³': 1/16.387064, 'ft³': 1/28316.846592, 'yd³': 1/764554.857984, 'mi³': 2.39913e-16, 'gal': 0.000264172, 'qt.': 0.00105669, 'pt': 0.00211338, 'cp': 0.00416667, 'fl oz': 0.033814, 'tbsp': 0.067628, 'tsp': 0.202884}
}

vol = units['mL']
for unit, val in vol.items():
    if unit == 'mL':
        continue
    units[unit] = {'mL': 1/val}
    for unit_2, val_2 in vol.items():
        if unit_2 == 'mL':
            continue
        elif unit_2 == unit:
            units[unit][unit_2] = 1
        else:
            units[unit][unit_2] = 1 / val * val_2


item_emojis = [
    ['Uncharted island map', 'uncharted_island_map'],
    ['Livid plant', 'livid_plant'],
    ['Crystal triskelion', 'crystal_triskelion'],
    ['Deathtouched dart', 'deathtouched_dart'],
    ['Gift for the Reaper', 'gift_for_the_reaper'],
    ['Slayer VIP Coupon', 'slayer_vip_coupon'],
    ['Shattered anima', 'shattered_anima'],
    ['Unstable air rune', 'unstable_air_rune'],
    ['Dungeoneering Wildcard', 'dungeoneering_wildcard'],
    ['Taijitu', 'taijitu'],
    ['Harmonic dust', 'harmonic_dust'],
    ['Sacred clay', 'sacred_clay'],
    ['Advanced pulse core', 'advanced_pulse_core'],
    ['Silverhawk down', 'silverhawk_down'],
    ['Barrel of bait', 'fishing_boost'],
    ['Broken fishing rod', 'fishing_boost'],
    ['Tangled fishbowl', 'fishing_boost'],
    ['Message in a bottle', 'message_in_a_bottle'],
    ['Dragonkin lamp', 'dragonkin_lamp'],
    ['Starved ancient effigy', 'starved_ancient_effigy'],
    ['Unfocused damage enhancer', 'unfocused_damage_enhancer'],
    ['Unfocused reward enhancer', 'unfocused_reward_enhancer'],
    ['Daily D&D token', 'dnd_token_daily'],
    ['Weekly D&D token', 'dnd_token_weekly'],
    ['Monthly D&D token', 'dnd_token_monthly'],
    ['Small goebie burial charm', 'mazcab_reputation'],
    ['Goebie burial charm', 'mazcab_reputation'],
    ['Large goebie burial charm', 'mazcab_reputation'],
    ['Small Menaphite gift offering', 'menaphos_reputation'],
    ['Medium Menaphite gift offering', 'menaphos_reputation'],
    ['Large Menaphite gift offering', 'menaphos_reputation'],
    ['Anima crystal', 'anima_crystal']
]

countries = [   
    {"name": "Afghanistan", "code": "AF"},
    {"name": "Åland Islands", "code": "AX"},
    {"name": "Albania", "code": "AL"},
    {"name": "Algeria", "code": "DZ"},
    {"name": "American Samoa", "code": "AS"},
    {"name": "AndorrA", "code": "AD"},
    {"name": "Angola", "code": "AO"},
    {"name": "Anguilla", "code": "AI"},
    {"name": "Antarctica", "code": "AQ"},
    {"name": "Antigua and Barbuda", "code": "AG"},
    {"name": "Argentina", "code": "AR"},
    {"name": "Armenia", "code": "AM"},
    {"name": "Aruba", "code": "AW"},
    {"name": "Australia", "code": "AU"},
    {"name": "Austria", "code": "AT"},
    {"name": "Azerbaijan", "code": "AZ"},
    {"name": "Bahamas", "code": "BS"},
    {"name": "Bahrain", "code": "BH"},
    {"name": "Bangladesh", "code": "BD"},
    {"name": "Barbados", "code": "BB"},
    {"name": "Belarus", "code": "BY"},
    {"name": "Belgium", "code": "BE"},
    {"name": "Belize", "code": "BZ"},
    {"name": "Benin", "code": "BJ"},
    {"name": "Bermuda", "code": "BM"},
    {"name": "Bhutan", "code": "BT"},
    {"name": "Bolivia", "code": "BO"},
    {"name": "Bosnia and Herzegovina", "code": "BA"},
    {"name": "Botswana", "code": "BW"},
    {"name": "Bouvet Island", "code": "BV"},
    {"name": "Brazil", "code": "BR"},
    {"name": "British Indian Ocean Territory", "code": "IO"},
    {"name": "Brunei Darussalam", "code": "BN"},
    {"name": "Bulgaria", "code": "BG"},
    {"name": "Burkina Faso", "code": "BF"},
    {"name": "Burundi", "code": "BI"},
    {"name": "Cambodia", "code": "KH"},
    {"name": "Cameroon", "code": "CM"},
    {"name": "Canada", "code": "CA"},
    {"name": "Cape Verde", "code": "CV"},
    {"name": "Cayman Islands", "code": "KY"},
    {"name": "Central African Republic", "code": "CF"},
    {"name": "Chad", "code": "TD"},
    {"name": "Chile", "code": "CL"},
    {"name": "China", "code": "CN"},
    {"name": "Christmas Island", "code": "CX"},
    {"name": "Cocos (Keeling) Islands", "code": "CC"},
    {"name": "Colombia", "code": "CO"},
    {"name": "Comoros", "code": "KM"},
    {"name": "Congo", "code": "CG"},
    {"name": "Congo, The Democratic Republic of the", "code": "CD"},
    {"name": "Cook Islands", "code": "CK"},
    {"name": "Costa Rica", "code": "CR"},
    {"name": "Cote D\"Ivoire", "code": "CI"},
    {"name": "Croatia", "code": "HR"},
    {"name": "Cuba", "code": "CU"},
    {"name": "Cyprus", "code": "CY"},
    {"name": "Czech Republic", "code": "CZ"},
    {"name": "Denmark", "code": "DK"},
    {"name": "Djibouti", "code": "DJ"},
    {"name": "Dominica", "code": "DM"},
    {"name": "Dominican Republic", "code": "DO"},
    {"name": "Ecuador", "code": "EC"},
    {"name": "Egypt", "code": "EG"},
    {"name": "El Salvador", "code": "SV"},
    {"name": "Equatorial Guinea", "code": "GQ"},
    {"name": "Eritrea", "code": "ER"},
    {"name": "Estonia", "code": "EE"},
    {"name": "Ethiopia", "code": "ET"},
    {"name": "Falkland Islands (Malvinas)", "code": "FK"},
    {"name": "Faroe Islands", "code": "FO"},
    {"name": "Fiji", "code": "FJ"},
    {"name": "Finland", "code": "FI"},
    {"name": "France", "code": "FR"},
    {"name": "French Guiana", "code": "GF"},
    {"name": "French Polynesia", "code": "PF"},
    {"name": "French Southern Territories", "code": "TF"},
    {"name": "Gabon", "code": "GA"},
    {"name": "Gambia", "code": "GM"},
    {"name": "Georgia", "code": "GE"},
    {"name": "Germany", "code": "DE"},
    {"name": "Ghana", "code": "GH"},
    {"name": "Gibraltar", "code": "GI"},
    {"name": "Greece", "code": "GR"},
    {"name": "Greenland", "code": "GL"},
    {"name": "Grenada", "code": "GD"},
    {"name": "Guadeloupe", "code": "GP"},
    {"name": "Guam", "code": "GU"},
    {"name": "Guatemala", "code": "GT"},
    {"name": "Guernsey", "code": "GG"},
    {"name": "Guinea", "code": "GN"},
    {"name": "Guinea-Bissau", "code": "GW"},
    {"name": "Guyana", "code": "GY"},
    {"name": "Haiti", "code": "HT"},
    {"name": "Heard Island and Mcdonald Islands", "code": "HM"},
    {"name": "Holy See (Vatican City State)", "code": "VA"},
    {"name": "Honduras", "code": "HN"},
    {"name": "Hong Kong", "code": "HK"},
    {"name": "Hungary", "code": "HU"},
    {"name": "Iceland", "code": "IS"},
    {"name": "India", "code": "IN"},
    {"name": "Indonesia", "code": "ID"},
    {"name": "Iran, Islamic Republic Of", "code": "IR"},
    {"name": "Iraq", "code": "IQ"},
    {"name": "Ireland", "code": "IE"},
    {"name": "Isle of Man", "code": "IM"},
    {"name": "Israel", "code": "IL"},
    {"name": "Italy", "code": "IT"},
    {"name": "Jamaica", "code": "JM"},
    {"name": "Japan", "code": "JP"},
    {"name": "Jersey", "code": "JE"},
    {"name": "Jordan", "code": "JO"},
    {"name": "Kazakhstan", "code": "KZ"},
    {"name": "Kenya", "code": "KE"},
    {"name": "Kiribati", "code": "KI"},
    {"name": "Korea, Democratic People\"S Republic of", "code": "KP"},
    {"name": "Korea, Republic of", "code": "KR"},
    {"name": "Kuwait", "code": "KW"},
    {"name": "Kyrgyzstan", "code": "KG"},
    {"name": "Lao People\"S Democratic Republic", "code": "LA"},
    {"name": "Latvia", "code": "LV"},
    {"name": "Lebanon", "code": "LB"},
    {"name": "Lesotho", "code": "LS"},
    {"name": "Liberia", "code": "LR"},
    {"name": "Libyan Arab Jamahiriya", "code": "LY"},
    {"name": "Liechtenstein", "code": "LI"},
    {"name": "Lithuania", "code": "LT"},
    {"name": "Luxembourg", "code": "LU"},
    {"name": "Macao", "code": "MO"},
    {"name": "Macedonia, The Former Yugoslav Republic of", "code": "MK"},
    {"name": "Madagascar", "code": "MG"},
    {"name": "Malawi", "code": "MW"},
    {"name": "Malaysia", "code": "MY"},
    {"name": "Maldives", "code": "MV"},
    {"name": "Mali", "code": "ML"},
    {"name": "Malta", "code": "MT"},
    {"name": "Marshall Islands", "code": "MH"},
    {"name": "Martinique", "code": "MQ"},
    {"name": "Mauritania", "code": "MR"},
    {"name": "Mauritius", "code": "MU"},
    {"name": "Mayotte", "code": "YT"},
    {"name": "Mexico", "code": "MX"},
    {"name": "Micronesia, Federated States of", "code": "FM"},
    {"name": "Moldova, Republic of", "code": "MD"},
    {"name": "Monaco", "code": "MC"},
    {"name": "Mongolia", "code": "MN"},
    {"name": "Montserrat", "code": "MS"},
    {"name": "Morocco", "code": "MA"},
    {"name": "Mozambique", "code": "MZ"},
    {"name": "Myanmar", "code": "MM"},
    {"name": "Namibia", "code": "NA"},
    {"name": "Nauru", "code": "NR"},
    {"name": "Nepal", "code": "NP"},
    {"name": "Netherlands", "code": "NL"},
    {"name": "Netherlands Antilles", "code": "AN"},
    {"name": "New Caledonia", "code": "NC"},
    {"name": "New Zealand", "code": "NZ"},
    {"name": "Nicaragua", "code": "NI"},
    {"name": "Niger", "code": "NE"},
    {"name": "Nigeria", "code": "NG"},
    {"name": "Niue", "code": "NU"},
    {"name": "Norfolk Island", "code": "NF"},
    {"name": "Northern Mariana Islands", "code": "MP"},
    {"name": "Norway", "code": "NO"},
    {"name": "Oman", "code": "OM"},
    {"name": "Pakistan", "code": "PK"},
    {"name": "Palau", "code": "PW"},
    {"name": "Palestinian Territory, Occupied", "code": "PS"},
    {"name": "Panama", "code": "PA"},
    {"name": "Papua New Guinea", "code": "PG"},
    {"name": "Paraguay", "code": "PY"},
    {"name": "Peru", "code": "PE"},
    {"name": "Philippines", "code": "PH"},
    {"name": "Pitcairn", "code": "PN"},
    {"name": "Poland", "code": "PL"},
    {"name": "Portugal", "code": "PT"},
    {"name": "Puerto Rico", "code": "PR"},
    {"name": "Qatar", "code": "QA"},
    {"name": "Reunion", "code": "RE"},
    {"name": "Romania", "code": "RO"},
    {"name": "Russian Federation", "code": "RU"},
    {"name": "RWANDA", "code": "RW"},
    {"name": "Saint Helena", "code": "SH"},
    {"name": "Saint Kitts and Nevis", "code": "KN"},
    {"name": "Saint Lucia", "code": "LC"},
    {"name": "Saint Pierre and Miquelon", "code": "PM"},
    {"name": "Saint Vincent and the Grenadines", "code": "VC"},
    {"name": "Samoa", "code": "WS"},
    {"name": "San Marino", "code": "SM"},
    {"name": "Sao Tome and Principe", "code": "ST"},
    {"name": "Saudi Arabia", "code": "SA"},
    {"name": "Senegal", "code": "SN"},
    {"name": "Serbia and Montenegro", "code": "CS"},
    {"name": "Seychelles", "code": "SC"},
    {"name": "Sierra Leone", "code": "SL"},
    {"name": "Singapore", "code": "SG"},
    {"name": "Slovakia", "code": "SK"},
    {"name": "Slovenia", "code": "SI"},
    {"name": "Solomon Islands", "code": "SB"},
    {"name": "Somalia", "code": "SO"},
    {"name": "South Africa", "code": "ZA"},
    {"name": "South Georgia and the South Sandwich Islands", "code": "GS"},
    {"name": "Spain", "code": "ES"},
    {"name": "Sri Lanka", "code": "LK"},
    {"name": "Sudan", "code": "SD"},
    {"name": "Suriname", "code": "SR"},
    {"name": "Svalbard and Jan Mayen", "code": "SJ"},
    {"name": "Swaziland", "code": "SZ"},
    {"name": "Sweden", "code": "SE"},
    {"name": "Switzerland", "code": "CH"},
    {"name": "Syrian Arab Republic", "code": "SY"},
    {"name": "Taiwan, Province of China", "code": "TW"},
    {"name": "Tajikistan", "code": "TJ"},
    {"name": "Tanzania, United Republic of", "code": "TZ"},
    {"name": "Thailand", "code": "TH"},
    {"name": "Timor-Leste", "code": "TL"},
    {"name": "Togo", "code": "TG"},
    {"name": "Tokelau", "code": "TK"},
    {"name": "Tonga", "code": "TO"},
    {"name": "Trinidad and Tobago", "code": "TT"},
    {"name": "Tunisia", "code": "TN"},
    {"name": "Turkey", "code": "TR"},
    {"name": "Turkmenistan", "code": "TM"},
    {"name": "Turks and Caicos Islands", "code": "TC"},
    {"name": "Tuvalu", "code": "TV"},
    {"name": "Uganda", "code": "UG"},
    {"name": "Ukraine", "code": "UA"},
    {"name": "United Arab Emirates", "code": "AE"},
    {"name": "United Kingdom", "code": "GB"},
    {"name": "United States", "code": "US"},
    {"name": "United States Minor Outlying Islands", "code": "UM"},
    {"name": "Uruguay", "code": "UY"},
    {"name": "Uzbekistan", "code": "UZ"},
    {"name": "Vanuatu", "code": "VU"},
    {"name": "Venezuela", "code": "VE"},
    {"name": "Viet Nam", "code": "VN"},
    {"name": "Virgin Islands, British", "code": "VG"},
    {"name": "Virgin Islands, U.S.", "code": "VI"},
    {"name": "Wallis and Futuna", "code": "WF"},
    {"name": "Western Sahara", "code": "EH"},
    {"name": "Yemen", "code": "YE"},
    {"name": "Zambia", "code": "ZM"},
    {"name": "Zimbabwe", "code": "ZW"}
]

def get_user_name(user):
    '''
    Returns RSN-formatted name for member.
    '''
    name = user.display_name
    # format name to alphanumeric only (to get valid RSN)
    name = re.sub('[^A-z0-9 -]', '', name).replace('`', '').strip()
    return name

def is_int(num):
    try:
        int(num)
        return True
    except:
        return False

def is_float(num):
    try:
        float(num)
        return True
    except:
        return False

'''
Function to convert timedelta to a string of the form:
x day(s), x hour(s), x minute(s), x second(s)
'''
def time_diff_to_string(time):
    postfix = ''
    if time < timedelta(seconds=0):
        time = -time
        postfix = ' ago'
    seconds = time.seconds
    days = time.days
    hours = seconds // 3600
    seconds -= hours * 3600
    minutes = seconds // 60
    seconds -= minutes * 60
    time = ""
    if days != 0:
        time += str(days) + " day"
        if days != 1:
            time += "s"
    if hours != 0:
        if days != 0:
            time += ", "
            if minutes == 0 and seconds == 0:
                time += "and "
        time += str(hours) + " hour"
        if hours != 1:
            time += "s"
    if minutes != 0:
        if days != 0 or hours != 0:
            time += ", "
            if seconds == 0:
                time += "and "
        time += str(minutes) + " minute"
        if minutes != 1:
            time += "s"
    if seconds != 0:
        if days != 0 or hours != 0 or minutes != 0:
            time += ", and "
        time += str(seconds) + " second"
        if seconds != 1:
            time += "s"
    return f'{time}{postfix}'

def float_to_str(f):
    """
    Convert the given float to a string,
    without resorting to scientific notation
    """
    d1 = decimal_ctx.create_decimal(repr(f))
    return format(d1, 'f')

def float_to_formatted_string(input):
    output = float_to_str(input) 
    if output.endswith('.0'):
        output = output[:len(output)-2]
    end = ''
    if output.find('.') != -1:
        end = output[output.find('.'):]
        output = output[:output.find('.')]
    index = len(output)-2
    while index >= 0:
        if (len(output.replace(',', '')) - 1 - index) % 3 == 0:
            output = output[:index+1] + ',' + output[index+1:]
        index -= 1
    output += end
    return output

async def safe_send_coroutine(channel: discord.TextChannel, message: str):
    try:
        await channel.send(message)
    except discord.Forbidden:
        pass
    except Exception as e:
        error = f'Encountered error while sending a message:\n{type(e).__name__}: {e}'
        logging.critical(error)
        print(error)