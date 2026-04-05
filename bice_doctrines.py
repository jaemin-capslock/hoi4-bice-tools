#!/usr/bin/env python3
"""
bice_doctrines.py — Doctrine modifier presets for BICE.

Modifier format
---------------
A doctrine preset dict has three sections:

    {
        "name": "Human-readable name",

        # Per-category MULTIPLICATIVE bonuses (percentages) on combat stats.
        # Applied per-battalion: if a battalion has "category_all_infantry"
        # in its categories list, these multiply its computed stat values.
        "category_mult": {
            "category_all_infantry": {"defense": 0.23, "breakthrough": 0.12},
            "category_all_armor":    {"soft_attack": 0.30, ...},
            ...
        },

        # Per-category FLAT (additive) bonuses.
        # Applied per-battalion before division aggregation.
        "category_flat": {
            "category_army": {"max_organisation": 5},
            "category_all_DIV_HQ": {"max_organisation": 8},
            ...
        },

        # Division-level stats (strategic, not per-battalion).
        # Informational / applied to the final division result dict.
        "division": {
            "planning_speed": 0.17,
            "max_planning": 0.03,
            "reinforce_rate": 0.019,
            "max_dig_in": 1,
            "org_loss_when_moving": -0.05,
        },
    }

HOI4 stacking: multiplicative doctrine bonuses stack additively with each
other (as in vanilla HOI4):  final = base * (1 + sum_of_pct_bonuses).

Public API
----------
DOCTRINE_PRESETS : dict[str, dict]   — named presets
get_preset(name) -> dict             — look up by name
list_presets() -> list[str]          — available preset names
combine_presets(*names) -> dict      — merge multiple presets additively
"""

from __future__ import annotations
from copy import deepcopy


# ─────────────────────────────────────────────
#  WW1 DOCTRINE CUMULATIVE BONUSES
#
#  These represent the cumulative stat modifiers from researching all
#  WW1-era land doctrines in BICE.  Where XOR (mutually exclusive)
#  branches exist, the "Defensive" variant is chosen by default.
#
#  Source: common/technologies/ww1_land_doctrine.txt
#  Numbers aggregated from all non-XOR techs + defensive XOR picks.
# ─────────────────────────────────────────────

# ── All WW1 doctrines — DEFENSIVE XOR pick ──────────────────────────
# XOR: MG_support_infantry_doctrine (+10% inf def)
# Source: ww1_land_doctrine.txt — 55 land techs + 6 air techs total
#
# Numbers are PER-CATEGORY cumulative totals.  A unit that belongs to
# MULTIPLE categories (e.g. infantry has both category_all_infantry and
# category_light_infantry) gets bonuses from ALL matching categories
# stacked additively, then applied as a single multiplier.
_WW1_FULL_DEFENSIVE: dict = {
    "name": "WW1 Full (Defensive picks)",

    "category_mult": {
        # ── Infantry (all) ──
        # defense: def_trenches(5) + barbed_wire(2) + pillboxes(10) +
        #   fortress_trenches(10) + basic_MG(2) + multiple_MG(3) +
        #   enfilade_MG(8) + MG_support_infantry_doctrine(10) = 50%
        # breakthrough: charge(2) + offensive_trenches(5) + dispersed(2) +
        #   infiltration(5) + tunnel_mines(5) = 19%
        # hard_attack: anti_tank_traps(5) + infantry_AT_defences(5) = 10%
        "category_all_infantry": {
            "defense":       0.50,
            "breakthrough":  0.19,
            "hard_attack":   0.10,
        },
        # ── Light infantry ── (stacks ON TOP of all_infantry)
        # breakthrough: charge(2) + offensive_trenches(5) + dispersed(2) +
        #   stormtroopers(5) + infiltration(5) = 19%
        "category_light_infantry": {
            "breakthrough":  0.19,
        },
        # ── Artillery ──
        # soft_attack: concentration(5) + continuous_fire(5) + barrage_chain(3×3=9) +
        #   observers(2+3+4=9) ≈ 30%   [block/creeping/rolling each +3%]
        # defense: continuous_fire(5) + barrage(3×3=9) + observers(2+3+4=9) ≈ 35%
        #   Hmm, actual breakdown: cf(5)+harass(2)+rear(3)+dummy(3)+stand(2)+box(3)+
        #   block/creep/roll(3)+obs(2+3+4) = 35%
        # breakthrough: same pattern = 35%
        # combat_width: concentration(-10%)
        "category_artillery": {
            "soft_attack":   0.30,
            "defense":       0.35,
            "breakthrough":  0.35,
            "combat_width":  -0.10,
        },
        # ── Armor (all) ──
        # mobile_doctrines(2%BT) + armor_support(10%SA,10%HA,12%BT,10%def)
        # + inf_tank_coord(10%SA,10%HA,12%BT,10%def)
        # + inf_tank_arty_coord(10%SA,10%HA,12%BT,10%def)
        "category_all_armor": {
            "soft_attack":   0.30,
            "hard_attack":   0.30,
            "breakthrough":  0.38,    # 2+12+12+12
            "defense":       0.30,
        },
        # ── Support armor (half of armor bonuses from inf_tank techs) ──
        "category_all_support_armor": {
            "soft_attack":   0.30,
            "hard_attack":   0.30,
            "breakthrough":  0.30,
            "defense":       0.30,
        },
        # ── Tanks (standalone) ──
        "category_tanks": {
            "soft_attack":   0.15,
            "hard_attack":   0.15,
            "breakthrough":  0.15,
            "defense":       0.15,
        },
        # ── Cavalry ──
        "category_cavalry": {
            "soft_attack":   0.10,
            "defense":       0.05,
            "breakthrough":  0.05,
        },
        # ── Army-wide ──
        "category_army": {
            "air_attack":    0.10,   # AA_positions
        },
    },

    "category_flat": {
        # category_army: infantry_charge(-5) + complex_trench(+2) + logistics_trench(+3) = 0
        "category_army": {
            "max_organisation": 0.0,
        },
        # DIV_HQ: foot_runners(1) + pidgeons(1) + telephone(2) + battlefield_support(1)
        #   + commissions(1) + motorcycle(2) + staff_vehicles(2) = 10
        "category_all_DIV_HQ": {
            "max_organisation": 10.0,
        },
        # infantry_charge gives +5 org to all_infantry
        "category_all_infantry": {
            "max_organisation": 5.0,
        },
        # armor: mobile(1) + armor_support(2) + inf_tank_coord(2) + inf_tank_arty(1) = 6
        "category_all_armor": {
            "max_organisation": 6.0,
        },
        "category_all_support_armor": {
            "max_organisation": 5.0,
        },
        # cavalry: mobile(2) + charges(2) + dismounting(2) + exploitation(4) = 10
        "category_cavalry": {
            "max_organisation": 10.0,
        },
        # artillery: concentration(1) + continuous(-1) + prep_fire(1) + obs(1) = 2
        "category_artillery": {
            "max_organisation": 2.0,
        },
    },

    "division": {
        "max_dig_in":              1,       # -10 + 5 + 6 = +1
        "org_loss_when_moving":   -0.30,    # +5+10-10-5-10-10-10 = -30%
        "attrition":               0.00,    # +8-1-1-2.5-2-1.5 ≈ 0 net
        "reinforce_rate":          0.019,   # foot+pidgeon+telephone+reserve
        "planning_speed":          0.24,    # communication(5)+terrain(10)+motorcycle(2)+staff(5)+comm(2)
        "max_planning":            0.03,    # offensive_prep_fire
        "land_night_attack":       0.15,    # night_patrols
        "dig_in_speed_factor":     0.15,    # offensive_trenches
        "no_supply_grace":         36,      # stormtroopers (+36h)
        "supply_consumption":      0.03,    # net +3%
        "experience_loss_factor": -0.05,    # camouflage
        "cas_damage_reduction":    0.02,    # camouflage
    },
}

# ── All WW1 doctrines — OFFENSIVE XOR pick ──────────────────────────
# XOR: Infantry_support_MG_doctrine (+12% inf BT instead of +10% inf def)
_WW1_FULL_OFFENSIVE: dict = deepcopy(_WW1_FULL_DEFENSIVE)
_WW1_FULL_OFFENSIVE["name"] = "WW1 Full (Offensive picks)"
_WW1_FULL_OFFENSIVE["category_mult"]["category_all_infantry"]["defense"] = 0.40       # 50% - 10%
_WW1_FULL_OFFENSIVE["category_mult"]["category_all_infantry"]["breakthrough"] = 0.31  # 19% + 12%

# No doctrines researched (clean slate)
_NONE: dict = {
    "name": "No Doctrines",
    "category_mult": {},
    "category_flat": {},
    "division": {},
}


# ─────────────────────────────────────────────
#  PRESET REGISTRY
# ─────────────────────────────────────────────

DOCTRINE_PRESETS: dict[str, dict] = {
    "none":              _NONE,
    "ww1_full":          _WW1_FULL_DEFENSIVE,  # default alias
    "ww1_full_def":      _WW1_FULL_DEFENSIVE,
    "ww1_full_off":      _WW1_FULL_OFFENSIVE,
}


def list_presets() -> list[str]:
    """Return available preset names."""
    return sorted(DOCTRINE_PRESETS.keys())


def get_preset(name: str) -> dict:
    """Look up a doctrine preset by name. Raises KeyError if unknown."""
    if name not in DOCTRINE_PRESETS:
        raise KeyError(
            f"Unknown doctrine preset: {name!r}. "
            f"Available: {list_presets()}"
        )
    return deepcopy(DOCTRINE_PRESETS[name])


def combine_presets(*names: str) -> dict:
    """
    Merge multiple presets by summing their bonuses additively.
    Useful for combining WW1 base + a WW2 branch.
    """
    merged: dict = {
        "name": " + ".join(names),
        "category_mult": {},
        "category_flat": {},
        "division": {},
    }

    for name in names:
        preset = get_preset(name)

        for cat, bonuses in preset.get("category_mult", {}).items():
            if cat not in merged["category_mult"]:
                merged["category_mult"][cat] = {}
            for stat, val in bonuses.items():
                merged["category_mult"][cat][stat] = (
                    merged["category_mult"][cat].get(stat, 0.0) + val
                )

        for cat, bonuses in preset.get("category_flat", {}).items():
            if cat not in merged["category_flat"]:
                merged["category_flat"][cat] = {}
            for stat, val in bonuses.items():
                merged["category_flat"][cat][stat] = (
                    merged["category_flat"][cat].get(stat, 0.0) + val
                )

        for stat, val in preset.get("division", {}).items():
            merged["division"][stat] = (
                merged["division"].get(stat, 0.0) + val
            )

    return merged
