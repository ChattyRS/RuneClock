from datetime import UTC, datetime, timedelta
import re
import math
from discord import User, Member
from src.date_utils import timedelta_to_string
from src.number_utils import is_int
from discord.ext import commands

max_cash = 2147483647

item_emojis: list[list[str]] = [
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

def level_to_xp(level: int) -> int:
    '''
    Returns the required amount of XP for the given skill level.

    Args:
        level (int): The skill level (normally 1-99).

    Returns:
        int: Amount of XP required for the given skill level.
    '''
    return math.floor(1/4 * sum([math.floor(x + 300 * 2 ** (x/7)) for x in range(1, level)]))

def xp_to_level(xp: int) -> int:
    '''
    Returns the skill level for the given amount of XP.

    Args:
        xp (int): The amount of XP (normally 0-200M).

    Raises:
        ValueError: If the given amount of XP is not a valid integer.

    Returns:
        int: The skill level corresponding to the given amount of XP.
    '''
    if is_int(xp):
        xp = int(xp)
    else:
        raise ValueError(f'Invalid Integer argument: {xp}')
    for level in range(120, 0, -1):
        if xp >= level_to_xp(level):
            return level
    return 1

def combat_level(attack: int, strength: int, defence: int, constitution: int, magic: int, ranged: int, prayer: int, summoning: int) -> float:
    '''
    Calculates the (RS3) combat level for the given skill levels.

    Args:
        attack (int): The attack level
        strength (int): The strength level
        defence (int): The defence level
        constitution (int): The constitution level
        magic (int): The magic level
        ranged (int): The ranged level
        prayer (int): The prayer level
        summoning (int): The summoning level

    Returns:
        float: The player's combat level (normally 3-138).
    '''
    return (13/10 * max(attack + strength, 2 * magic, 2 * ranged) + defence + constitution + math.floor(1/2 * prayer) + math.floor(1/2 * summoning)) / 4

def osrs_combat_level(attack: int, strength: int, defence: int, hitpoints: int, magic: int, ranged: int, prayer: int) -> int:
    '''
    Calculates the (OSRS) combat level for the given skill levels.

    Args:
        attack (int): The attack level
        strength (int): The strength level
        defence (int): The defence level
        hitpoints (int): The hitpoints level
        magic (int): The magic level
        ranged (int): The ranged level
        prayer (int): The prayer level

    Returns:
        int: The player's combat level (normally 3-126).
    '''
    base: float = (defence + hitpoints + math.floor(prayer / 2)) / 4
    melee: float = 13 / 40 * (attack + strength)
    _range: float = 13 / 40 * math.floor(ranged * 3 / 2)
    mage: float = 13 / 40 * math.floor(magic * 3 / 2)
    final: int = math.floor(base + max(melee, _range, mage))
    return final

def get_rsn(user: Member | User) -> str:
    '''
    Returns RSN-formatted name for member.
    '''
    name: str = user.display_name
    # format name to alphanumeric only (to get valid RSN)
    name = re.sub(r'[^A-z0-9 -]', '', name).replace('`', '').strip()
    return name

def get_rotation(t: datetime, rotation_count: int, interval_days: int, offset_days: int) -> tuple[int, timedelta]:
    '''
    Gets the current rotation and the time to the next rotation
    
    Args:
        t (datetime): _description_
        rotation_count (int): number of rotations
        interval_days (int): frequency of rotation changes in days
        offset_days (int): 1 jan 1970 + offset in days = starting day for rot 0

    Returns:
        tuple[int, timedelta]: current rotation and time to the next rotation
    '''
    t = t.replace(second=0, microsecond=0)
    interval = timedelta(days=interval_days)
    offset = timedelta(days=offset_days)

    t_0: datetime = datetime(1970, 1, 1, 0, 0, 0, 0, tzinfo=UTC) + offset
    rotation: int = ((t - t_0) // interval) % rotation_count
    time_to_next: timedelta = interval - ((t - t_0) % interval)

    return (rotation, time_to_next)

def araxxor(t: datetime) -> tuple[str, str]:
    '''
    Gets the current Araxxor rotation and the time to the next rotation in human-readable format.

    Args:
        t (datetime): The current time

    Returns:
        tuple[str, str]: The current Araxxor rotation and the time to the next rotation.
    '''
    rotation, next = get_rotation(t, 3, 4, 9)
    return (['Path 1 (Minions)', 'Path 2 (Acid)', 'Path 3 (Darkness)'][rotation], timedelta_to_string(next))

def vorago(t: datetime) -> tuple[str, str]:
    '''
    Gets the current Vorage rotation and the time to the next rotation in human-readable format.

    Args:
        t (datetime): The current time

    Returns:
        tuple[str, str]: The current Vorago rotation and the time to the next rotation.
    '''
    rotation, next = get_rotation(t, 6, 7, 6)
    return (['Ceiling collapse', 'Scopulus', 'Vitalis', 'Green bomb', 'Team split', 'The end'][rotation], timedelta_to_string(next))

def rots(t: datetime) -> tuple[list[list[str]], str]:
    '''
    Gets the current rotation and time to the next rotation for ROTS (Barrows Rise Of The Six) in human-readable format.

    Args:
        t (datetime): The current time

    Returns:
        tuple[list[list[str]], str]: The current ROTS rotation and the time to the next rotation.
    '''
    rotations: list[list[list[str]]] = [
        [['Dharok','Torag','Verac'],['Karil','Ahrim','Guthan']],
		[['Karil','Torag','Guthan'],['Ahrim','Dharok','Verac']],
		[['Karil','Guthan','Verac'],['Ahrim','Torag','Dharok']],
		[['Guthan','Torag','Verac'],['Karil','Ahrim','Dharok']],
		[['Karil','Torag','Verac'],['Ahrim','Guthan','Dharok']],
		[['Ahrim','Guthan','Dharok'],['Karil','Torag','Verac']],
		[['Karil','Ahrim','Dharok'],['Guthan','Torag','Verac']],
		[['Ahrim','Torag','Dharok'],['Karil','Guthan','Verac']],
		[['Ahrim','Dharok','Verac'],['Karil','Torag','Guthan']],
		[['Karil','Ahrim','Guthan'],['Torag','Dharok','Verac']],
		[['Ahrim','Torag','Guthan'],['Karil','Dharok','Verac']],
		[['Ahrim','Guthan','Verac'],['Karil','Torag','Dharok']],
		[['Karil','Ahrim','Torag'],['Guthan','Dharok','Verac']],
		[['Karil','Ahrim','Verac'],['Dharok','Torag','Guthan']],
		[['Ahrim','Torag','Verac'],['Karil','Dharok','Guthan']],
		[['Karil','Dharok','Guthan'],['Ahrim','Torag','Verac']],
		[['Dharok','Torag','Guthan'],['Karil','Ahrim','Verac']],
		[['Guthan','Dharok','Verac'],['Karil','Ahrim','Torag']],
		[['Karil','Torag','Dharok'],['Ahrim','Guthan','Verac']],
		[['Karil','Dharok','Verac'],['Ahrim','Torag','Guthan']]
    ]

    rotation, next = get_rotation(t, 20, 1, 0)
    return (rotations[rotation], timedelta_to_string(next))

# variable used for VOS notifications
prif_districts: list[str] = ['Cadarn', 'Amlodd', 'Crwys', 'Ithell', 'Hefin', 'Meilyr', 'Trahaearn', 'Iorwerth']

# variable used for role management
dnd_names: list[str] = ['Warbands', 'Cache', 'Sinkhole', 'Yews', 'Goebies', 'Merchant', 'Spotlight', 'WildernessFlashEvents']
for d in prif_districts:
    dnd_names.append(d)

wilderness_flash_events: list[str] = [
    'Spider Swarm',
    'Unnatural Outcrop',
    'Stryke the Wyrm',
    'Demon Stragglers',
    'Butterfly Swarm',
    'King Black Dragon Rampage',
    'Forgotten Soldiers',
    'Surprising Seedlings',
    'Hellhound Pack',
    'Infernal Star',
    'Lost Souls',
    'Ramokee Incursion',
    'Displaced Energy',
    'Evil Bloodwood Tree'
]

skills_07: list[str] = [
    'Overall', 
    'Attack', 
    'Defence', 
    'Strength', 
    'Hitpoints', 
    'Ranged',
    'Prayer', 
    'Magic', 
    'Cooking', 
    'Woodcutting', 
    'Fletching', 
    'Fishing',
    'Firemaking', 
    'Crafting', 
    'Smithing', 
    'Mining', 
    'Herblore', 
    'Agility',
    'Thieving', 
    'Slayer', 
    'Farming', 
    'Runecraft', 
    'Hunter', 
    'Construction'#,
    #'Sailing'
]

osrs_skill_emojis: list[str] = [
    '<:Attack_icon:624387168982269952>', 
    '<:Defence_icon:624387168655114263>', 
    '<:Strength_icon:624387169145847808>', 
    '<:Hitpoints_icon:624387169058029568>', 
    '<:Ranged_icon:624387169028538378>',
    '<:Prayer_icon:624387169129332743>', 
    '<:Magic_icon:624387168726548495>', 
    '<:Cooking_icon:624387169066287104>', 
    '<:Woodcutting_icon:624387168844120065>', 
    '<:Fletching_icon:624387168885800981>', 
    '<:Fishing_icon:624387169024213008>',
    '<:Firemaking_icon:624387169011630120>', 
    '<:Crafting_icon:624387169003503616>', 
    '<:Smithing_icon:624387168898383903>', 
    '<:Mining_icon:624387168785137669>', 
    '<:Herblore_icon:624387169053704195>', 
    '<:Agility_icon:624387168609239048>',
    '<:Thieving_icon:624387169015955475>', 
    '<:Slayer_icon:624387168822886435>', 
    '<:Farming_icon:624387168990658570>', 
    '<:Runecraft_icon:624387169041121290>', 
    '<:Hunter_icon:624387169070350336>', 
    '<:Construction_icon:624387168995115041>', 
    '<:Stats_icon:624389156344430594>',
    '<:Sailing_icon:1437589669272490156>'
]

skills_rs3: list[str] = [
    'Overall', 
    'Attack', 
    'Defence', 
    'Strength', 
    'Constitution', 
    'Ranged',
    'Prayer', 
    'Magic', 
    'Cooking', 
    'Woodcutting', 
    'Fletching', 
    'Fishing',
    'Firemaking', 
    'Crafting', 
    'Smithing', 
    'Mining', 
    'Herblore', 
    'Agility',
    'Thieving', 
    'Slayer', 
    'Farming', 
    'Runecrafting', 
    'Hunter', 
    'Construction',
    'Summoning', 
    'Dungeoneering', 
    'Divination', 
    'Invention', 
    'Archaeology',
    'Necromancy'
]

rs3_skill_emojis: list[str] = [
    '<:Attack:962315037668696084>', 
    '<:Defence:962315037396074517>', 
    '<:Strength:962315037538668555>', 
    '<:Constitution:962315037601562624>', 
    '<:Ranged:962315037177970769>',
    '<:Prayer:962315037509300224>', 
    '<:Magic:962315037207318579>', 
    '<:Cooking:962315037563817994>', 
    '<:Woodcutting:962315037593194516>', 
    '<:Fletching:962315037664493568>', 
    '<:Fishing:962315037630951484>',
    '<:Firemaking:962315037542871070>', 
    '<:Crafting:962315037647732766>', 
    '<:Smithing:962315037530271744>', 
    '<:Mining:962315037526085632>', 
    '<:Herblore:962315037563834398>', 
    '<:Agility:962315037635121162>',
    '<:Thieving:962315037106634753>', 
    '<:Slayer:962315037278609419>', 
    '<:Farming:962315037484130324>', 
    '<:Runecrafting:962315037538676736>', 
    '<:Hunter:962315037261848607>', 
    '<:Construction:962315037626761226>',
    '<:Summoning:962315037559631892>', 
    '<:Dungeoneering:962315037815492648>', 
    '<:Divination:962315037727412245>', 
    '<:Invention:962315037723222026>', 
    '<:Archaeology:962315037509316628>'
]

skill_indices: list[int] = [0, 3, 14, 2, 16, 13, 1, 15, 10, 4, 17, 7, 5, 12, 11, 6, 9, 8, 20, 18, 19, 22, 21]#,23
skill_indices_rs3: list[int] = [0, 3, 14, 2, 16, 13, 1, 15, 10, 4, 17, 7, 5, 12, 11, 6, 9, 8, 20, 18, 19, 22, 21, 23, 24, 25, 26, 27, 28]

cb_indices_rs3: list[int] = [0, 2, 1, 3, 6, 4, 5, 23]
cb_indices_osrs: list[int] = [0, 2, 1, 3, 6, 4, 5]

def runescape_api_cooldown_key(_: commands.Context) -> str:
    '''
    Returns a cooldown key specific to any commands using the runescape api.

    Returns:
        str: The runescape api cooldown key
    '''
    return 'runescape_api'

def is_valid_rsn(input: str) -> bool:
    '''
    Returns true iff the input value could be a valid RSN.

    Args:
        input (str): The input string

    Returns:
        bool: True iff the input could be a valid RSN.
    '''
    return re.match(r'^[A-z0-9 -]+$', input) is not None