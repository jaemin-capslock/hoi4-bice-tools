#!/usr/bin/env python3
"""
bice_calc.py — Battalion and division stat calculator for HOI4 BICE.

Public API
----------
# Per-battalion (high-level)
calc_battalion(bat_name, equip_list, bat_db, equip_db, modifiers=None)
    → dict[stat, value]

# Batch per-battalion
calc_battalions(specs, bat_db, equip_db, modifiers=None)
    → dict[bat_name, dict[stat, value]]

# Full division
calc_division(template, bat_db, equip_db, modifiers=None)
    → dict[stat, value]

Modifiers  (two formats supported)
-----------------------------------
**Legacy format** (flat division-level only):

    modifiers = {
        "additive":       {"soft_attack": 5.0},
        "multiplicative": {"soft_attack": 0.10},
    }

**Doctrine format** (category-aware, from bice_doctrines):

    modifiers = {
        "category_mult": {
            "category_all_infantry": {"defense": 0.23, "breakthrough": 0.12},
            "category_all_armor":    {"soft_attack": 0.30},
        },
        "category_flat": {
            "category_army": {"max_organisation": 5},
        },
        "division": {
            "planning_speed": 0.17,
            "reinforce_rate": 0.019,
        },
    }

The format is auto-detected by the presence of "category_mult" or
"category_flat" keys.
"""

from __future__ import annotations

from bice_parser import COMBAT_STATS


# Stats that are SUMMED across battalions in a division
_SUM_STATS = {
    "soft_attack", "hard_attack", "air_attack",
    "additional_collateral_damage", "suppression",
    "build_cost_ic",
}

# Stats that are WEIGHTED-AVERAGED by battalion manpower
_AVG_STATS = {"defense", "breakthrough", "hardness"}

# Stats that appear in the per-battalion result dict
_BAT_RESULT_STATS = (
    "soft_attack", "hard_attack", "air_attack", "defense", "breakthrough",
    "ap_attack", "armor_value", "hardness", "reliability", "maximum_speed",
    "additional_collateral_damage", "suppression", "build_cost_ic",
    "fuel_consumption",
)


# ─────────────────────────────────────────────
#  INTERNAL HELPERS
# ─────────────────────────────────────────────

def _auto_assign(bat: dict, equip_list: list[str], equip_db: dict) -> dict[str, str]:
    """
    Map a flat list of specific equipment IDs to the slots defined in
    `bat["need"]`.  Matching is done by equipment family == slot archetype.

    Example
    -------
    bat["need"] = {"infantry_equipment": 125, "infantry_uniforms": 125}
    equip_list  = ["infantry_equipment_2", "infantry_uniforms_2"]
    → {"infantry_equipment": "infantry_equipment_2",
       "infantry_uniforms":  "infantry_uniforms_2"}

    Unmatched equipment IDs are silently ignored; unmatched slots are left
    without an assignment (battalion base stats will be used for those slots).
    """
    slots = set(bat.get("need", {}).keys())
    assignment: dict[str, str] = {}

    for eid in equip_list:
        if eid not in equip_db:
            continue
        eq = equip_db[eid]
        family = eq.get("family", "")
        if family in slots and family not in assignment:
            assignment[family] = eid
        elif eid in slots and eid not in assignment:
            # Direct slot-name match (e.g. for archetypes themselves)
            assignment[eid] = eid

    return assignment


def _calc_raw_stats(
    bat: dict,
    assignment: dict[str, str],
    equip_db: dict,
) -> dict[str, float]:
    """
    Given a battalion definition and a {slot → equip_id} assignment,
    return the battalion's full combat-stat contribution.

    HOI4 rule: combat stats contribute their face value once per slot,
    but production cost (build_cost_ic) is multiplied by the quantity needed.
    """
    stats: dict[str, float] = {s: float(bat.get(s, 0)) for s in _BAT_RESULT_STATS}
    need = bat.get("need", {})

    for slot, eid in assignment.items():
        if eid not in equip_db:
            continue
        eq = equip_db[eid]
        qty = float(need.get(slot, 1))
        for s in _BAT_RESULT_STATS:
            val = float(eq.get(s, 0))
            if s == "build_cost_ic":
                stats[s] = stats.get(s, 0.0) + val * qty
            else:
                stats[s] = stats.get(s, 0.0) + val

    return stats


def apply_modifiers(
    stats: dict[str, float],
    modifiers: dict | None,
) -> dict[str, float]:
    """
    Apply additive and multiplicative modifiers to a stats dict.
    Returns a new dict (does not mutate the input).

    Modifier format::

        {
            "additive":       {"soft_attack": 5.0, ...},
            "multiplicative": {"soft_attack": 0.10, ...},
        }
    """
    if not modifiers:
        return stats

    out = dict(stats)
    additive = modifiers.get("additive", {})
    multiplicative = modifiers.get("multiplicative", {})

    for stat, bonus in additive.items():
        if stat in out:
            out[stat] = out[stat] + bonus

    for stat, bonus in multiplicative.items():
        if stat in out:
            out[stat] = out[stat] * (1.0 + bonus)

    return out


def _is_doctrine_format(modifiers: dict | None) -> bool:
    """Return True if modifiers use the doctrine format (category-aware)."""
    if not modifiers:
        return False
    return "category_mult" in modifiers or "category_flat" in modifiers


def _apply_doctrine_modifiers(
    stats: dict[str, float],
    bat_categories: list[str],
    modifiers: dict,
) -> dict[str, float]:
    """
    Apply category-aware doctrine modifiers to a battalion's computed stats.

    For each category the battalion belongs to, looks up matching modifiers
    in ``category_mult`` (percentage) and ``category_flat`` (additive).

    Multiplicative bonuses from all matching categories stack additively
    (like HOI4): final = base * (1 + sum_of_all_matching_pct_bonuses).
    Flat bonuses are simply summed.

    Returns a new dict.
    """
    out = dict(stats)
    cat_set = set(bat_categories)

    # Accumulate multiplicative bonuses across all matching categories
    pct_accum: dict[str, float] = {}
    for cat, bonuses in modifiers.get("category_mult", {}).items():
        if cat in cat_set:
            for stat, pct in bonuses.items():
                pct_accum[stat] = pct_accum.get(stat, 0.0) + pct

    # Apply accumulated multiplicative bonuses
    for stat, total_pct in pct_accum.items():
        if stat in out:
            out[stat] = out[stat] * (1.0 + total_pct)

    # Apply flat bonuses from all matching categories
    for cat, bonuses in modifiers.get("category_flat", {}).items():
        if cat in cat_set:
            for stat, val in bonuses.items():
                if stat in out:
                    out[stat] = out[stat] + val

    return out


# ─────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────

def calc_battalion(
    bat_name: str,
    equip_list: list[str],
    bat_db: dict,
    equip_db: dict,
    modifiers: dict | None = None,
) -> dict[str, float]:
    """
    Compute combat stats for a named battalion with a given equipment list.

    Parameters
    ----------
    bat_name   : battalion ID, e.g. "infantry" or "artillery_brigade"
    equip_list : specific equipment IDs to assign, e.g.
                 ["infantry_equipment_2", "infantry_uniforms_2"]
    bat_db     : from bice_parser.build_battalion_db()
    equip_db   : from bice_parser.build_equipment_db()
    modifiers  : optional doctrine/experience modifier dict (see module doc)

    Returns
    -------
    {
        "soft_attack": ..., "hard_attack": ..., "defense": ...,
        "breakthrough": ..., "air_attack": ..., "ap_attack": ...,
        "armor_value": ..., "hardness": ..., "reliability": ...,
        "maximum_speed": ..., "additional_collateral_damage": ...,
        "suppression": ..., "build_cost_ic": ..., "fuel_consumption": ...,
        # plus battalion base fields:
        "max_strength": ..., "max_organisation": ...,
        "combat_width": ..., "manpower": ...,
    }
    """
    if bat_name not in bat_db:
        raise ValueError(f"Unknown battalion: {bat_name!r}")

    bat = bat_db[bat_name]
    assignment = _auto_assign(bat, equip_list, equip_db)
    stats = _calc_raw_stats(bat, assignment, equip_db)

    # Attach battalion structural stats before modifier application
    stats["max_strength"]      = float(bat.get("max_strength", 0))
    stats["max_organisation"]  = float(bat.get("max_organisation", 0))
    stats["combat_width"]      = float(bat.get("combat_width", 0))
    stats["manpower"]          = float(bat.get("manpower", 0))
    stats["weight"]            = float(bat.get("weight", 0))
    stats["supply_consumption"] = float(bat.get("supply_consumption", 0))
    stats["training_time"]     = float(bat.get("training_time", 0))

    # Apply modifiers (auto-detect format)
    if _is_doctrine_format(modifiers):
        stats = _apply_doctrine_modifiers(
            stats, bat.get("categories", []), modifiers)
    else:
        stats = apply_modifiers(stats, modifiers)

    return stats


def calc_battalions(
    specs: dict[str, list[str]],
    bat_db: dict,
    equip_db: dict,
    modifiers: dict | None = None,
) -> dict[str, dict[str, float]]:
    """
    Batch version of calc_battalion.

    Parameters
    ----------
    specs : {bat_name: [equip_id, ...], ...}

    Returns
    -------
    {bat_name: {stat: value, ...}, ...}
    """
    return {
        name: calc_battalion(name, equips, bat_db, equip_db, modifiers)
        for name, equips in specs.items()
    }


def calc_division(
    template: dict,
    bat_db: dict,
    equip_db: dict,
    modifiers: dict | None = None,
) -> dict:
    """
    Calculate full division stats from a template dict.

    Template format
    ---------------
    {
        "name": "GER Infantry 1940",
        "notes": "optional description",
        "battalions": [
            {
                "type":  "infantry",
                "count": 9,
                "equip": ["infantry_equipment_2", "infantry_uniforms_2"],
                # OR the legacy dict form:
                # "equip": {"infantry_equipment": "infantry_equipment_2", ...}
            },
            ...
        ],
        "support": [
            {"type": "engineer", "count": 1, "equip": []},
            ...
        ],
    }

    The `equip` field accepts either a **list** of equipment IDs (new API,
    auto-assigned to slots) or the legacy **dict** form {slot: equip_id}.

    Division-level aggregation rules (matching HOI4)
    -------------------------------------------------
    * HP, SA, HA, AA, Collateral, Suppression, IC Cost  →  sum × count
    * Org, Defense, Breakthrough, Hardness              →  weighted avg by manpower
    * Speed                                             →  min across non-support transport equip
    * Width                                             →  sum × count (support adds 0)
    * Modifiers applied to final division totals.

    Returns
    -------
    {
        "name": ..., "Width": ..., "HP": ..., "Org": ...,
        "Soft Attack": ..., "Hard Attack": ..., "Air Attack": ...,
        "Defense": ..., "Breakthrough": ..., "Hardness": ...,
        "Collateral": ..., "Suppression": ..., "Speed (km/h)": ...,
        "Manpower": ..., "Weight": ..., "Supply/day": ...,
        "IC Cost": ..., "Training (days)": ..., "notes": ...,
    }
    """
    totals = dict(
        hp=0.0, width=0.0, manpower=0.0, weight=0.0,
        supply=0.0, training=0,
        sa=0.0, ha=0.0, aa=0.0, collateral=0.0, suppression=0.0, ic=0.0,
        defense=0.0, bt=0.0,
    )
    # Weighted accumulators (numerator; denominator = total_manpower)
    w_org = 0.0
    w_hard = 0.0

    speeds: list[float] = []

    all_units = (
        [(u, False) for u in template.get("battalions", [])] +
        [(u, True)  for u in template.get("support",    [])]
    )

    for unit, is_support in all_units:
        bat_id  = unit["type"]
        count   = float(unit.get("count", 1))
        equip   = unit.get("equip", [])

        if bat_id not in bat_db:
            print(f"  Warning: battalion '{bat_id}' not found in db")
            continue

        bat = bat_db[bat_id]

        # Support both new list-form and legacy dict-form equip
        if isinstance(equip, list):
            assignment = _auto_assign(bat, equip, equip_db)
        else:
            assignment = equip  # legacy {slot: equip_id} dict

        bstats = _calc_raw_stats(bat, assignment, equip_db)

        hp       = float(bat.get("max_strength", 0))
        width    = float(bat.get("combat_width", 0))
        manpower = float(bat.get("manpower", 0))
        weight   = float(bat.get("weight", 0))
        supply   = float(bat.get("supply_consumption", 0))
        org      = float(bat.get("max_organisation", 0))
        training = int(bat.get("training_time", 0))

        # Apply doctrine/category modifiers per-battalion BEFORE aggregation
        use_doctrine = _is_doctrine_format(modifiers)
        if use_doctrine:
            # Add org to bstats so doctrine flat bonuses can modify it
            bstats["max_organisation"] = org
            bstats = _apply_doctrine_modifiers(
                bstats, bat.get("categories", []), modifiers)
            org = bstats.pop("max_organisation", org)

        totals["hp"]          += count * hp
        totals["width"]       += count * width
        totals["manpower"]    += count * manpower
        totals["weight"]      += count * weight
        totals["supply"]      += count * supply
        totals["training"]     = max(totals["training"], training)
        totals["sa"]          += count * bstats["soft_attack"]
        totals["ha"]          += count * bstats["hard_attack"]
        totals["aa"]          += count * bstats["air_attack"]
        totals["defense"]     += count * bstats["defense"]
        totals["bt"]          += count * bstats["breakthrough"]
        totals["collateral"]  += count * bstats["additional_collateral_damage"]
        totals["suppression"] += count * bstats["suppression"]
        totals["ic"]          += count * bstats["build_cost_ic"]

        # Weighted by manpower (count × manpower = manpower contribution)
        mp_w = count * manpower
        w_org  += mp_w * org
        w_hard += mp_w * bstats["hardness"]

        # Speed: minimum transport speed across non-support line battalions
        if not is_support:
            transport_id = bat.get("transport", "")
            if transport_id:
                t_eid = assignment.get(transport_id, transport_id)
                if t_eid in equip_db:
                    sp = float(equip_db[t_eid].get("maximum_speed", 0))
                    if sp > 0:
                        speeds.append(sp)
                else:
                    for eq in equip_db.values():
                        if eq.get("family") == transport_id or eq.get("id") == transport_id:
                            sp = float(eq.get("maximum_speed", 0))
                            if sp > 0:
                                speeds.append(sp)
                                break

    total_mp = totals["manpower"]
    if total_mp > 0:
        org_avg  = w_org  / total_mp
        hard_avg = w_hard / total_mp
    else:
        org_avg = hard_avg = 0.0

    result = {
        "name":            template["name"],
        "HP":              round(totals["hp"],         2),
        "Org":             round(org_avg,              2),
        "Width":           round(totals["width"],      1),
        "Manpower":        int(totals["manpower"]),
        "Weight":          round(totals["weight"],     2),
        "Supply/day":      round(totals["supply"],     3),
        "Soft Attack":     round(totals["sa"],         2),
        "Hard Attack":     round(totals["ha"],         3),
        "Air Attack":      round(totals["aa"],         2),
        "Defense":         round(totals["defense"],     2),
        "Breakthrough":    round(totals["bt"],          2),
        "Hardness":        round(hard_avg,             3),
        "Collateral":      round(totals["collateral"], 0),
        "Suppression":     round(totals["suppression"],2),
        "IC Cost":         round(totals["ic"],         1),
        "Speed (km/h)":    round(min(speeds),          2) if speeds else 0.0,
        "Training (days)": totals["training"],
        "notes":           template.get("notes", ""),
    }

    # Doctrine: attach division-level stats as informational fields
    if use_doctrine:
        for stat, val in (modifiers or {}).get("division", {}).items():
            result[f"div_{stat}"] = val

    # Legacy modifiers: apply flat additive/multiplicative to final results
    if modifiers and not use_doctrine:
        mod_map = {
            "Soft Attack":  "soft_attack",
            "Hard Attack":  "hard_attack",
            "Air Attack":   "air_attack",
            "Defense":      "defense",
            "Breakthrough": "breakthrough",
            "Org":          "max_organisation",
        }
        add = modifiers.get("additive", {})
        mul = modifiers.get("multiplicative", {})
        for result_key, mod_key in mod_map.items():
            if mod_key in add:
                result[result_key] = round(result[result_key] + add[mod_key], 2)
            if mod_key in mul:
                result[result_key] = round(result[result_key] * (1 + mul[mod_key]), 2)

    return result
