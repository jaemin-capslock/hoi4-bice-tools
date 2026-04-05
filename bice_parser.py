#!/usr/bin/env python3
"""
bice_parser.py — HOI4 Clausewitz format parser and equipment/battalion DB builder.

Public API
----------
parse_hoi4_file(filepath)   → dict
build_equipment_db()        → dict[equip_id, {...}]
build_battalion_db()        → dict[bat_id, {...}]
"""

import re
from pathlib import Path


# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────

MOD_ROOT  = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\394360\1851181613")
EQUIP_DIR = MOD_ROOT / "common" / "units" / "equipment"
UNITS_DIR = MOD_ROOT / "common" / "units"


# ─────────────────────────────────────────────
#  STAT / FIELD LISTS
# ─────────────────────────────────────────────

# Equipment combat stats we track
COMBAT_STATS = [
    "soft_attack", "hard_attack", "air_attack", "defense", "breakthrough",
    "ap_attack", "armor_value", "hardness", "reliability",
    "maximum_speed", "build_cost_ic", "lend_lease_cost",
    "additional_collateral_damage", "suppression",
    "fuel_consumption", "fuel_capacity",
]

# Battalion base-stat fields
BATTALION_BASE_STATS = [
    "max_strength", "max_organisation", "default_morale",
    "weight", "supply_consumption", "combat_width", "manpower",
    "training_time", "maximum_speed",
    "soft_attack", "hard_attack", "air_attack",
    "defense", "breakthrough", "suppression",
    "own_equipment_fuel_consumption_mult", "fuel_capacity",
]

# Equipment archetype → human-readable label for land divisions
LAND_EQUIP_FAMILIES: dict[str, str] = {
    "infantry_equipment":           "Infantry Weapons",
    "infantry_uniforms":            "Infantry Uniforms",
    "ss_infantry_uniforms":         "SS Uniforms",
    "SMG_equipment":                "SMG / Assault",
    "HMG_equipment":                "HMG",
    "mortar_equipment":             "Mortar",
    "para_equipment":               "Paratrooper Gear",
    "mount_equipment":              "Mountain Gear",
    "amph_equipment":               "Amphibious Gear",
    "horse_equipment":              "Horse",
    "garrison_equipment":           "Garrison",
    "artillery_equipment":          "Light Artillery",
    "mountain_artillery_equipment": "Mountain Artillery",
    "medartillery_equipment":       "Medium Artillery",
    "Hvartillery_equipment":        "Heavy Artillery",
    "rocket_artillery_equipment":   "Rocket Artillery",
    "motorized_rocket_equipment":   "Motorized Rocket Art.",
    "infantrygun_equipment":        "Infantry Gun",
    "artyhorse_equipment":          "Arty Horse / Limber",
    "artytruck_equipment":          "Arty Truck",
    "artytractor_equipment":        "Arty Tractor",
    "anti_tank_equipment":          "Anti-Tank",
    "anti_air_equipment":           "Anti-Air",
    "motorized_equipment":          "Motorized (Truck)",
    "mechanized_equipment":         "Mechanized (Half-track)",
    "spotter_planes_equipment":     "Arty Spotter Planes",
}

LAND_FAMILY_SET = set(LAND_EQUIP_FAMILIES.keys())


# ─────────────────────────────────────────────
#  HOI4 CLAUSEWITZ PARSER
# ─────────────────────────────────────────────

def _strip_comments(text: str) -> str:
    """Remove # … end-of-line comments."""
    return re.sub(r"#[^\n]*", "", text)


def _tokenize(text: str) -> list[str]:
    """
    Split Clausewitz script into tokens: braces, equals, quoted strings,
    numbers (including negative / scientific), and bare identifiers.
    """
    return re.findall(
        r'[{}=]|"[^"]*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[A-Za-z_]\w*',
        text,
    )


def _parse_block(tokens: list[str], idx: int) -> tuple[dict, int]:
    """
    Recursively parse a Clausewitz block (everything up to the matching `}`).
    Returns (parsed_dict, new_index).

    Duplicate keys are collected into a list.
    Bare values (no `=` following) are silently skipped.
    """
    result: dict = {}
    while idx < len(tokens):
        tok = tokens[idx]

        if tok == "}":
            return result, idx + 1

        if idx + 1 < len(tokens) and tokens[idx + 1] == "=":
            key = tok
            idx += 2  # skip key + '='

            if idx < len(tokens) and tokens[idx] == "{":
                val, idx = _parse_block(tokens, idx + 1)
            else:
                raw = tokens[idx]
                idx += 1
                try:
                    val = int(raw)
                except ValueError:
                    try:
                        val = float(raw)
                    except ValueError:
                        val = raw.strip('"')

            # Collect duplicate keys into a list
            if key in result:
                if not isinstance(result[key], list):
                    result[key] = [result[key]]
                result[key].append(val)
            else:
                result[key] = val
        else:
            # Bare value (no '=' following) — common in HOI4 for category
            # and type lists, e.g. `categories = { category_army infantry }`.
            # Store as key → True so callers can use dict.keys().
            if tok not in ("{", "="):
                result[tok] = True
            idx += 1

    return result, idx


def _scalar(v):
    """
    HOI4 files occasionally repeat a key; the parser collects duplicates into
    a list. For numeric stats, the last value wins (same as HOI4's behaviour).
    Returns the raw value for non-list inputs unchanged.
    """
    if isinstance(v, list):
        return v[-1]
    return v


def parse_hoi4_file(filepath: Path) -> dict:
    """
    Parse a single HOI4 Clausewitz-format `.txt` file.
    Returns a nested dict; returns {} on I/O or parse errors.
    """
    try:
        text = filepath.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}
    tokens = _tokenize(_strip_comments(text))
    result, _ = _parse_block(tokens, 0)
    return result


# ─────────────────────────────────────────────
#  EQUIPMENT DATABASE
# ─────────────────────────────────────────────

def build_equipment_db(equip_dir: Path = EQUIP_DIR) -> dict:
    """
    Parse every `*.txt` under *equip_dir* and build a flat dict of all
    equipment entries with archetype-inheritance resolved.

    Returns
    -------
    equip_db[equip_id] = {
        'id':           str,
        'source':       str (filename stem),
        'family':       str (archetype id),
        'family_label': str (human label),
        'year':         int,
        'is_archetype': bool,
        <stat>:         float | int,
        ...
    }
    """
    raw: dict = {}
    archetypes: dict = {}

    for fp in sorted(equip_dir.glob("*.txt")):
        data = parse_hoi4_file(fp)
        equips = data.get("equipments", {})
        if not isinstance(equips, dict):
            continue

        for eid, edata in equips.items():
            if not isinstance(edata, dict):
                continue

            rec: dict = {"id": eid, "source": fp.stem}

            for key in ("year", "is_archetype", "active", "type",
                        "group_by", "archetype", "parent", "priority",
                        "visual_level", "supply_truck"):
                if key in edata:
                    rec[key] = edata[key]

            for stat in COMBAT_STATS:
                if stat in edata:
                    rec[stat] = _scalar(edata[stat])

            raw[eid] = rec
            if edata.get("is_archetype") in (True, "yes", 1):
                archetypes[eid] = rec

    # Resolve one level of archetype inheritance
    for rec in raw.values():
        arch_id = rec.get("archetype")
        if arch_id and arch_id in archetypes:
            arch = archetypes[arch_id]
            for stat in COMBAT_STATS:
                if stat not in rec and stat in arch:
                    rec[stat] = arch[stat]
            rec["family"] = arch_id
            rec["family_label"] = LAND_EQUIP_FAMILIES.get(arch_id, arch_id)
        elif rec.get("is_archetype") in (True, "yes", 1):
            rec["family"] = rec["id"]
            rec["family_label"] = LAND_EQUIP_FAMILIES.get(rec["id"], rec["id"])
        else:
            fallback = rec.get("archetype", "unknown")
            rec["family"] = fallback
            rec["family_label"] = LAND_EQUIP_FAMILIES.get(fallback, fallback)

    return raw


# ─────────────────────────────────────────────
#  BATTALION DATABASE
# ─────────────────────────────────────────────

_TERRAIN_KEYS = [
    "desert", "plains", "forest", "hills", "mountain", "jungle",
    "marsh", "urban", "densecity", "capital", "river", "fort", "amphibious",
]


def build_battalion_db(units_dir: Path = UNITS_DIR) -> dict:
    """
    Parse every `*.txt` directly under *units_dir* and build a dict of all
    `sub_units` (battalion) definitions.

    Returns
    -------
    bat_db[unit_id] = {
        'id':         str,
        'source':     str (filename stem),
        'types':      list[str],
        'group':      str,
        'categories': list[str],
        'need':       {slot_archetype: qty},
        'transport':  str,
        'terrain':    {terrain: {attack, defence, movement}},
        <base_stat>:  float | int,
        ...
    }
    """
    bat_db: dict = {}

    for fp in sorted(units_dir.glob("*.txt")):
        data = parse_hoi4_file(fp)
        sub_units = data.get("sub_units", {})
        if not isinstance(sub_units, dict):
            continue

        for uid, udata in sub_units.items():
            if not isinstance(udata, dict):
                continue

            rec: dict = {"id": uid, "source": fp.stem}

            # `type` block can be a dict (block) or a string
            utype = udata.get("type", {})
            if isinstance(utype, dict):
                rec["types"] = list(utype.keys())
            elif isinstance(utype, list):
                rec["types"] = [str(t) for t in utype]
            else:
                rec["types"] = [str(utype)]

            rec["group"] = udata.get("group", "")

            cats = udata.get("categories", {})
            rec["categories"] = list(cats.keys()) if isinstance(cats, dict) else []

            for stat in BATTALION_BASE_STATS:
                if stat in udata:
                    rec[stat] = _scalar(udata[stat])

            rec["transport"] = udata.get("transport", "")

            need = udata.get("need", {})
            rec["need"] = (
                {k: v for k, v in need.items()
                 if isinstance(k, str) and isinstance(v, (int, float))}
                if isinstance(need, dict) else {}
            )

            terrain: dict = {}
            for t in _TERRAIN_KEYS:
                if t in udata and isinstance(udata[t], dict):
                    terrain[t] = udata[t]
            rec["terrain"] = terrain

            bat_db[uid] = rec

    return bat_db
