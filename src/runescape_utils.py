import re
import math
from discord import User, Member
from number_utils import is_int

max_cash = 2147483647

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