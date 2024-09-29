import copy
import re

locations: list[str] = ["LM", "LC", "BA", "SP", "BU", "CW", "PRIF", "MG", "IMP", "GE", "MEI", "ITH", "POF", "BDR", "WG", "BE", "FF"]
portables_names: list[str] = ['Fletcher', 'Crafter', 'Brazier', 'Sawmill', 'Range', 'Well', 'Workbench']
portables_names_upper: list[str] = ['FLETCHERS', 'CRAFTERS', 'BRAZIERS', 'SAWMILLS', 'RANGES', 'WELLS', 'WORKBENCHES']
busy_locs: list[tuple[int, str]] = [(84, "LM"), (99, "LM"), (100, "SP")]
forbidden_locs: list[tuple[int, str]] = [(2, "BU")]
highest_world = 259
forbidden_worlds: list[int] = [13, 47, 55, 75, 90, 93, 94, 95, 101, 102, 107, 109, 110, 111, 112, 113, 118, 121, 122, 125, 126, 127, 128, 129, 130, 131, 132, 133]
f2p_worlds: list[int] = [3, 7, 8, 11, 17, 19, 20, 29, 33, 34, 38, 41, 43, 57, 61, 80, 81, 108, 120, 135, 136, 141, 210, 215, 225, 236, 239, 245, 249, 250, 255, 256]
total_worlds: list[tuple[int, str]] = [(86, " (1500+)"), (114, " (1500+)"), (30, " (2000+)"), (48, " (2600+)"), (52, " (VIP)")]

portable_aliases: list[list[str]] = [
    ['fletcher', 'fletchers', 'fletch', 'fl', 'f'],
    ['crafter', 'crafters', 'craft', 'cr', 'c'],
    ['brazier', 'braziers', 'braz', 'br', 'b'],
    ['sawmill', 'sawmills', 'saw', 'sa', 's', 'mill', 'mi', 'm'],
    ['range', 'ranges', 'ra', 'r'],
    ['well', 'wells', 'we'],
    ['workbench', 'workbenches', 'benches', 'bench', 'wb', 'wo']
]

rank_titles: list[str] = ['Sergeants', 'Corporals', 'Recruits', 'New']

def get_ports(input: str) -> list[tuple[list[int], str]]:
    '''
    Gets portable locations from a string, and returns them in the following format:
    [([world1, world2, ...], location1), ([world3, world4, ...], location2), ...]

    Args:
        input (str): Input string containing portable locations

    Returns:
        list[tuple[list[int], str]]: The parsed list of portable locations.
    '''
    input = input.upper().replace('F2P', '~')
    input = input.replace('~RIF', 'F2PRIF')
    input = input.replace('~OF', 'F2POF')
    input = input.replace('~', '').strip()
    for world in total_worlds:
        total: str = world[1]
        input = input.replace(total, '')

    # Get indices of all occurrences of locations
    indices: list[tuple[str, int]] = []
    for loc in locations:
        substring_indices: list[int] = [m.start() for m in re.finditer(loc, input)] # https://stackoverflow.com/questions/4664850/find-all-occurrences-of-a-substring-in-python
        for index in substring_indices:
            indices.append((loc, index))
    indices.sort(key=lambda x: x[1]) # https://stackoverflow.com/questions/17555218/python-how-to-sort-a-list-of-lists-by-the-fourth-element-in-each-list

    # Fill array ports with (worlds, location) for every location
    ports: list[tuple[list[int], str]] = []
    for i, index in enumerate(indices):
        begin_index: int = 0 if not i else indices[i-1][1]
        end_index: int = index[1]
        substring: str = input[begin_index:end_index]
        worlds: list[int] = [int(s) for s in re.findall(r'\d+', substring)] # https://stackoverflow.com/questions/4289331/python-extract-numbers-from-a-string
        ports.append((worlds, indices[i][0]))

    ports_copy: list[tuple[list[int], str]] = copy.deepcopy(ports)
    duplicates: list[int] = []
    # Add worlds from duplicate locations to the first occurrence of the location
    for i, port1 in enumerate(ports_copy):
        loc1: str = port1[1]
        for j, port2 in enumerate(ports_copy):
            if j <= i:
                continue
            loc2: str = port2[1]
            if loc1 == loc2:
                for world in ports_copy[j][0]:
                    ports_copy[i][0].append(world)
                if not j in duplicates:
                    duplicates.append(j)

    # Delete duplicate locations
    duplicates.sort(reverse=True)
    for i in duplicates:
        del ports_copy[i]

    # Remove duplicates from arrays of worlds and sort worlds
    result: list[tuple[list[int], str]] = []
    for i, port in enumerate(ports_copy):
        result.append((sorted(list(set(port[0]))), port[1]))

    return result

def only_f2p(ports: list[tuple[list[int], str]]) -> bool:
    '''
    Return true iff the input list of portable locations contains exclusively F2P worlds.

    Args:
        ports (list[tuple[list[int], str]]): The list of portable locations.

    Returns:
        bool: True if the input list of portable locations contains exclusively F2P worlds, false otherwise.
    '''
    for worlds in [port[0] for port in ports]:
        if any([world not in f2p_worlds for world in worlds]):
            return False
    return True

def add_port(world: int, loc: str, ports: list[tuple[list[int], str]]) -> list[tuple[list[int], str]]:
    '''
    Adds a specific pair (world, location) to a set of portable locations, and returns the result.

    Args:
        world (int): The world
        loc (str): The location
        ports (list[tuple[list[int], str]]): The current list of portable locations

    Returns:
        list[tuple[list[int], str]]: The updated list of portable locations.
    '''
    new_ports: list[tuple[list[int], str]] = copy.deepcopy(ports)
    for i, port in enumerate(new_ports):
        if port[1] == loc:
            if world in new_ports[i][0]:
                return new_ports
            new_ports[i][0].append(world)
            new_ports[i][0].sort()
            return new_ports
    new_ports.append(([world], loc))
    return new_ports

def add_ports(current: list[tuple[list[int], str]], new: list[tuple[list[int], str]]) -> list[tuple[list[int], str]]:
    '''
    Adds a set of new portable locations to a set of current portable locations, and returns the resulting set.
    Uses add_port() for every location.

    Args:
        current (list[tuple[list[int], str]]): The current list of portable locations
        new (list[tuple[list[int], str]]): The list of new portable locations to be added

    Returns:
        list[tuple[list[int], str]]: The resulting list of portable locations.
    '''
    ports: list[tuple[list[int], str]] = copy.deepcopy(current)
    for port in new:
        loc: str = port[1]
        for world in port[0]:
            ports = add_port(world, loc, ports)
    return ports

def remove_port(world: int, loc: str, ports: list[tuple[list[int], str]]) -> list[tuple[list[int], str]]:
    '''
    Removes a specific pair (world, location) from a set of portable locations, and returns the result.
    Similar to add_port()

    Args:
        world (int): The world
        loc (str): The location
        ports (list[tuple[list[int], str]]): The current list of portable locations

    Returns:
        list[tuple[list[int], str]]: The updated list of portable locations.
    '''
    new_ports: list[tuple[list[int], str]] = copy.deepcopy(ports)
    for i, port in enumerate(new_ports):
        if port[1] == loc:
            if world in new_ports[i][0]:
                new_ports[i][0].remove(world)
                if not new_ports[i][0]:
                    del new_ports[i]
                return new_ports
    return new_ports

def remove_ports(current: list[tuple[list[int], str]], old: list[tuple[list[int], str]]) -> list[tuple[list[int], str]]:
    '''
    Removes a set of new portable locations from a set of current portable locations, and returns the resulting set.
    Uses remove_port() for every location.
    Similar to add_ports()

    Args:
        current (list[tuple[list[int], str]]): The current list of portable locations 
        old (list[tuple[list[int], str]]): The list of old portable locations to be removed

    Returns:
        list[tuple[list[int], str]]: The resulting list of portable locations.
    '''
    ports: list[tuple[list[int], str]] = copy.deepcopy(current)
    for port in old:
        loc: str = port[1]
        for world in port[0]:
            ports = remove_port(world, loc, ports)
    return ports

def format(ports: list[tuple[list[int], str]]) -> str:
    '''
    Returns a string that represents a set of portable locations.

    Args:
        ports (list[tuple[list[int], str]]): The list of portable locations

    Returns:
        str: Formatted string for the given portable locations.
    '''
    txt: str = "" # initialize empty string to be returned
    f2p_ports: list[tuple[list[int], str]] = [] # initialize empty set for f2p locations, these will be added at the end of the string

    # for every location in the set of portables
    for i, port in enumerate(ports):
        worlds: list[int] = port[0] # get the set of worlds corresponding to this location
        loc: str = port[1] # get the location
        count = 0 # initialize count of worlds
        f2p_locs: list[int] = [] # initialize set of f2p worlds
        # for every world corresponding to the current location
        for w in worlds:
            if w in f2p_worlds: # if this is an f2p world, add it to the set of f2p worlds
                f2p_locs.append(w)
            else: # if it is a members world, increment counter, and generate text for the world
                count += 1
                if count > 1: # for all but the first world, add a comma
                    txt += ', '
                elif txt: # if this is the first world, and there is already text in the string, add a separating character
                    txt += ' | '
                txt += str(w) # add the world number
                # if this (world, location) pair corresponds to a busy location, add a star
                for busyLoc in busy_locs:
                    if w == busyLoc[0] and loc == busyLoc[1]:
                        txt += '*'
                        break
                # if this world is a total level world, add the total level required to join
                if loc != "MG": # total level is irrelevant if location is max guild
                    for totalWorld in total_worlds:
                        if w == totalWorld[0]:
                            txt += totalWorld[1]
                            break
        if count: # if there were worlds for this location, add the location
            txt += ' ' + loc
        if f2p_locs: # if there were f2p worlds for this location, add them to the set of f2p locations
            f2p_ports.append((f2p_locs, loc))

    if f2p_ports: # if there are f2p locations, add them to the string, similar to above
        if txt:
            txt += ' | '
        txt += 'F2P '
        for i, port in enumerate(f2p_ports):
            worlds = port[0]
            loc = port[1]
            count = 0
            for w in worlds:
                count += 1
                if count > 1:
                    txt += ', '
                elif i > 0:
                    txt += ' | '
                txt += str(w)
                for busyLoc in busy_locs:
                    if w == busyLoc[0] and loc == busyLoc[1]:
                        txt += '*'
                        break
                for totalWorld in total_worlds:
                    if w == totalWorld[0]:
                        txt += totalWorld[1]
                        break
            if count:
                txt += ' ' + loc

    if not txt: # if there were no locations at all, return 'N/A'
        return 'N/A'

    # replace some locations for nicer formatting
    txt = txt.replace('PRIF', 'Prif').replace('MEI', 'Meilyr').replace('ITH', 'Ithell')

    return txt # return the final result

def check_ports(new_ports: list[tuple[list[int], str]], ports: list[list[tuple[list[int], str]]]) -> str:
    '''
    Checks the validity of a given set of new portable locations, given a set of current locations.
    Returns a string with an error message, empty string if no error.

    Args:
        new_ports (_type_): The new portable locations for a specific portable
        ports (_type_): The current portable locations for all portables

    Returns:
        _type_: A string with an error message, empty string if no error.
    '''
    for port in new_ports:
        loc: str = port[1]
        for world in port[0]:
            if world < 1 or world > highest_world:
                return f'Sorry, **{str(world)}** is not a valid world. Please enter a number between 1 and 141.'
            if world in forbidden_worlds:
                return f'Sorry, world **{str(world)}** is not called because it is either a pking world or a bounty hunter world, or it is not on the world list.'
            for forbiddenLoc in forbidden_locs:
                if world == forbiddenLoc[0] and loc == forbiddenLoc[1]:
                    return f'Sorry, **{str(world)} {loc}** is a forbidden location.'
            if loc == 'GE' and world not in f2p_worlds:
                return 'Sorry, we only call the location **GE** in F2P worlds.'
            port_names: list[str] = []
            count = 0
            i = 0
            for p in ports:
                i += 1
                for entry in p:
                    if loc != entry[1]:
                        continue
                    if world in entry[0]:
                        port_names.append(portables_names[i-1])
                        count += 1
                        break
    return ''

def split(txt: str, seps: list[str]) -> list[str]:
    '''
    Splits the input string into a list of substrings by a list of multiple separators.
    https://stackoverflow.com/questions/4697006/python-split-string-by-list-of-separators/4697047

    Args:
        txt (_type_): The input string
        seps (_type_): The list of separators

    Returns:
        _type_: _description_
    '''
    default_sep: str = seps[0]
    # we skip seps[0] because that's the default seperator
    for sep in seps[1:]:
        txt = txt.replace(sep, default_sep)
    return [i.strip() for i in txt.split(default_sep)]

def get_editors(credit: str) -> list[str]:
    '''
    Get list of editor names from credit cell string

    Args:
        credit (_type_): The credit cell string

    Returns:
        _type_: _description_
    '''
    separators: list[str] = [',', '/', '&', '|', '+', ' - ']
    names: list[str] = split(credit, separators)
    return names