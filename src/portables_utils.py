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