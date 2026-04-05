#!/usr/bin/env python3
"""
bice_tanks.py — TRM Tank Design system for BICE.

The Tank Rework Mod (TRM) in BICE uses a modular tank design system:
chassis + turret + gun + engine + armor + transmission + ... = complete tank.

This module:
 1. Parses the module database (1136 tank modules)
 2. Defines a TankDesign class that computes final equipment stats
 3. Includes German historical tank designs
 4. Injects computed tank designs into the equipment DB

HOI4 stat formula per module:
    final_stat = base_stat * (1 + sum_of_all_multiply_stats) + sum_of_all_add_stats

Public API
----------
build_module_db()                → dict of 1136 tank modules
TankDesign(name, chassis, mods)  → design object with .compute_stats()
GERMAN_TANK_DESIGNS              → pre-built German historical designs
inject_tank_designs(equip_db)    → add computed designs to equipment DB
"""

from __future__ import annotations

from pathlib import Path
from bice_parser import parse_hoi4_file, MOD_ROOT


# Stats tracked for tank equipment
TANK_STATS = [
    "soft_attack", "hard_attack", "air_attack", "defense", "breakthrough",
    "ap_attack", "armor_value", "hardness", "maximum_speed",
    "build_cost_ic", "reliability", "fuel_consumption",
    "additional_collateral_damage", "suppression",
]

MODULES_PATH = MOD_ROOT / "common" / "units" / "equipment" / "modules" / "00_tank_modules.txt"


# ─────────────────────────────────────────────
#  MODULE DATABASE
# ─────────────────────────────────────────────

def build_module_db(modules_path: Path = MODULES_PATH) -> dict:
    """Parse 00_tank_modules.txt into a module database.

    Returns dict[module_id] = {
        'add_stats': {stat: float, ...},
        'multiply_stats': {stat: float, ...},
        'add_average_stats': {stat: float, ...},
        ...
    }
    """
    data = parse_hoi4_file(modules_path)
    return data.get("equipment_modules", {})


def _extract_stat_dict(block: dict) -> dict[str, float]:
    """Extract numeric values from a parsed stats block."""
    return {k: float(v) for k, v in block.items()
            if isinstance(v, (int, float))}


# ─────────────────────────────────────────────
#  TANK DESIGN
# ─────────────────────────────────────────────

class TankDesign:
    """A complete tank design: chassis + assigned modules.

    Parameters
    ----------
    name : str
        Human-readable name (e.g. "PzKpfw III J").
    chassis_id : str
        Equipment ID of the chassis variant (e.g.
        "trm_medium_tank_chassis_ger_panzer3_4").
    modules : dict[str, str]
        Module assignments: {slot_name: module_id}.
        Use "empty" or omit for empty slots.
    year : int, optional
        Override year (defaults to chassis year).
    tank_class : str
        Tank class for battalion matching: "light", "medium",
        "medium_advanced", "heavy", "superheavy".
    """

    def __init__(
        self,
        name: str,
        chassis_id: str,
        modules: dict[str, str],
        year: int | None = None,
        tank_class: str = "light",
    ):
        self.name = name
        self.chassis_id = chassis_id
        self.modules = modules
        self._year_override = year
        self.tank_class = tank_class

    @property
    def equip_id(self) -> str:
        """Unique equipment ID for this design."""
        return "tank_design_" + self.name.lower().replace(" ", "_").replace("/", "_")

    @property
    def family(self) -> str:
        """Archetype family for battalion slot matching."""
        return f"trm_{self.tank_class}_tank_chassis"

    def compute_stats(
        self,
        equip_db: dict,
        module_db: dict,
    ) -> dict[str, float]:
        """Compute final equipment stats from chassis + all modules.

        Formula: final = base * (1 + sum_multiply) + sum_add
        """
        chassis = equip_db.get(self.chassis_id, {})

        # Base stats from chassis (inherits archetype defaults)
        base: dict[str, float] = {}
        for stat in TANK_STATS:
            base[stat] = float(chassis.get(stat, 0))

        # Accumulate module contributions
        sum_add: dict[str, float] = {s: 0.0 for s in TANK_STATS}
        sum_mult: dict[str, float] = {s: 0.0 for s in TANK_STATS}
        sum_avg: dict[str, float] = {}

        for _slot, mod_id in self.modules.items():
            if mod_id == "empty" or mod_id not in module_db:
                continue
            mod = module_db[mod_id]

            for stat, val in _extract_stat_dict(mod.get("add_stats", {})).items():
                if stat in sum_add:
                    sum_add[stat] += val

            for stat, val in _extract_stat_dict(mod.get("multiply_stats", {})).items():
                if stat in sum_mult:
                    sum_mult[stat] += val

            for stat, val in _extract_stat_dict(mod.get("add_average_stats", {})).items():
                sum_avg[stat] = sum_avg.get(stat, 0.0) + val

        # Apply formula: final = base * (1 + mult) + add
        final: dict[str, float] = {}
        for stat in TANK_STATS:
            b = base[stat]
            a = sum_add[stat]
            m = sum_mult[stat]
            final[stat] = b * (1.0 + m) + a

        # add_average_stats (ap_attack from guns) — just add
        for stat, val in sum_avg.items():
            final[stat] = final.get(stat, 0.0) + val

        return final

    def to_equipment_entry(
        self,
        equip_db: dict,
        module_db: dict,
    ) -> dict:
        """Create a full equipment DB entry with computed stats."""
        stats = self.compute_stats(equip_db, module_db)
        chassis = equip_db.get(self.chassis_id, {})

        year = self._year_override or chassis.get("year", 0)
        if isinstance(year, list):
            year = year[-1]

        return {
            "id": self.equip_id,
            "family": self.family,
            "family_label": f"Tank: {self.name}",
            "archetype": self.family,
            "year": int(year),
            "is_archetype": False,
            "source": "tank_design",
            "design_name": self.name,
            "chassis": self.chassis_id,
            "tank_class": self.tank_class,
            **stats,
        }

    def __repr__(self) -> str:
        n_mods = sum(1 for v in self.modules.values() if v != "empty")
        return f"TankDesign({self.name!r}, {self.chassis_id}, {n_mods} modules)"


# ─────────────────────────────────────────────
#  MODULE SHORTHANDS (slot names)
# ─────────────────────────────────────────────
# Slot name constants to reduce typos in design definitions
_S = {
    "turret":       "fixed_trm_tank_turret_slot",
    "gun":          "fixed_trm_tank_main_gun_slot",
    "ammo":         "fixed_trm_tank_ammunition_slot",
    "coax":         "fixed_trm_tank_coax_gun_slot",
    "hull_gun":     "fixed_trm_tank_hull_gun_slot",
    "engine":       "fixed_trm_tank_engine_slot",
    "transmission": "fixed_trm_tank_transmission_slot",
    "gearbox":      "fixed_trm_tank_gearbox_slot",
    "suspension":   "fixed_trm_tank_suspension_slot",
    "armor":        "fixed_trm_tank_armor_thickness_slot",
    "armor_design": "fixed_trm_tank_armor_design_slot",
    "armor_dist":   "fixed_trm_tank_armor_distribution_slot",
    "armor_const":  "fixed_trm_tank_armor_construction_slot",
    "turret_const": "fixed_trm_tank_armor_construction_turret_slot",
    "radio":        "fixed_trm_tank_radio_slot",
    "ergonomics":   "fixed_trm_tank_ergonomics_slot",
    "construction": "fixed_trm_tank_construction_slot",
    "special1":     "special_type_slot_1",
    "special2":     "special_type_slot_2",
    "special3":     "special_type_slot_3",
    "special4":     "special_type_slot_4",
    "special5":     "special_type_slot_5",
    "special6":     "special_type_slot_6",
}


def _design(name, chassis, tank_class, year=None, **short_modules) -> TankDesign:
    """Helper to build a TankDesign using shorthand slot names."""
    full_modules = {}
    for short_key, mod_id in short_modules.items():
        slot = _S.get(short_key, short_key)
        full_modules[slot] = mod_id
    return TankDesign(name, chassis, full_modules, year=year, tank_class=tank_class)


# ─────────────────────────────────────────────
#  GERMAN HISTORICAL TANK DESIGNS
# ─────────────────────────────────────────────
# These match the `create_equipment_variant` blocks in history files
# plus common later-war configurations.

GERMAN_TANK_DESIGNS: list[TankDesign] = [

    # ── LIGHT TANKS ─────────────────────────────

    _design("PzKpfw I A", "trm_light_tank_chassis_ger_panzer1_1", "light",
        turret="trm_light_tank_ger_panzer1_turret_1",
        gun="trm_weapon_mg_ger_mg13_x2",
        ammo="empty", coax="empty", hull_gun="empty",
        engine="trm_engine_G1_0060",
        transmission="trm_transmission_brake_front",
        gearbox="trm_gearbox_simple",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_012",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_rounded",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_1",
        ergonomics="trm_ergonomics_light_standard",
        construction="trm_tank_construction_quality",
    ),

    _design("PzKpfw I B", "trm_light_tank_chassis_ger_panzer1_2", "light",
        turret="trm_light_tank_ger_panzer1_turret_1",
        gun="trm_weapon_mg_ger_mg13_x2",
        ammo="empty", coax="empty", hull_gun="empty",
        engine="trm_engine_G1_0100",
        transmission="trm_transmission_brake_front",
        gearbox="trm_gearbox_simple",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_012",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_rounded",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_1",
        ergonomics="trm_ergonomics_light_standard",
        construction="trm_tank_construction_quality",
    ),

    _design("PzKpfw II A", "trm_light_tank_chassis_ger_panzer2_1", "light",
        turret="trm_light_tank_ger_panzer2_turret_1",
        gun="trm_weapon_ac_ger_20_kwk30",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="empty",
        engine="trm_engine_G1_0140",
        transmission="trm_transmission_differential_front",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_015",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_rounded",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="empty",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── MEDIUM TANKS ────────────────────────────

    _design("PzKpfw III E", "trm_medium_tank_chassis_ger_panzer3_2", "medium",
        year=1938,
        turret="trm_medium_tank_ger_panzer3_turret_1",
        gun="trm_weapon_c_ger_37_kwk36",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_030",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_mixed",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("PzKpfw III J", "trm_medium_tank_chassis_ger_panzer3_4", "medium",
        year=1941,
        turret="trm_medium_tank_ger_panzer3_turret_2",
        gun="trm_weapon_c_ger_50_kwk39",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_050",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_mixed",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("PzKpfw IV D", "trm_medium_tank_chassis_ger_panzer4_2", "medium",
        year=1939,
        turret="trm_medium_tank_ger_panzer4_turret_1",
        gun="trm_weapon_c_ger_75_kwk37",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_030",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_mixed",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("PzKpfw IV F2", "trm_medium_tank_chassis_ger_panzer4_3", "medium",
        year=1942,
        turret="trm_medium_tank_ger_panzer4_turret_2",
        gun="trm_weapon_c_ger_75_kwk40",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_050",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_mixed",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("PzKpfw IV H", "trm_medium_tank_chassis_ger_panzer4_4", "medium",
        year=1943,
        turret="trm_medium_tank_ger_panzer4_turret_4",
        gun="trm_weapon_c_ger_75_kwk40_long",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_080",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── HEAVY TANKS ─────────────────────────────

    _design("Neubaufahrzeug", "trm_heavy_tank_chassis_ger_neubaufahrzeug_1", "heavy",
        turret="trm_heavy_tank_ger_neubaufahrzeug_turret_1",
        gun="trm_weapon_c_ger_75_kwk37",
        ammo="empty",
        coax="trm_weapon_coax_c_ger_37_kwk36",
        hull_gun="trm_weapon_hull_mg_ger_mg13",
        engine="trm_engine_G1_0275",
        transmission="trm_transmission_brake_rear",
        gearbox="trm_gearbox_simple",
        suspension="trm_suspension_spring_coil",
        armor="trm_armour_020",
        armor_design="trm_armour_design_heavy_basic",
        armor_dist="trm_armour_distribution_rounded",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_1",
        ergonomics="trm_ergonomics_heavy_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
        special2="trm_special_turret_mg_ger_mg13",
        special3="trm_special_turret_mg_ger_mg13",
    ),

    _design("Tiger I", "trm_heavy_tank_chassis_ger_tiger_1", "heavy",
        year=1942,
        turret="trm_heavy_tank_ger_tiger_turret_1",
        gun="trm_weapon_c_ger_88_kwk36",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0700",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_100",
        armor_design="trm_armour_design_heavy_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── MEDIUM ADVANCED TANKS (Panther) ────────

    _design("Panther D", "trm_medium_advanced_tank_chassis_ger_panther_1", "medium_advanced",
        year=1943,
        turret="trm_medium_advanced_tank_ger_panther_turret_1",
        gun="trm_weapon_c_ger_75_kwk42",
        ammo="trm_ammo_c_ger_75_kwk42",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0700",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_080",
        armor_design="trm_armour_design_heavy_sloped",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_cast",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("Panther G", "trm_medium_advanced_tank_chassis_ger_panther_2", "medium_advanced",
        year=1944,
        turret="trm_medium_advanced_tank_ger_panther_turret_1",
        gun="trm_weapon_c_ger_75_kwk42",
        ammo="trm_ammo_c_ger_75_kwk42",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0700",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_080",
        armor_design="trm_armour_design_heavy_sloped",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── TIGER II ───────────────────────────────

    _design("Tiger II", "trm_heavy_tank_chassis_ger_tiger2_1", "heavy",
        year=1944,
        turret="trm_heavy_tank_ger_tiger2_turret_1",
        gun="trm_weapon_c_ger_88_kwk43",
        ammo="trm_ammo_c_ger_88_kwk43",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0700",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_150",
        armor_design="trm_armour_design_heavy_sloped",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── MORE LIGHT TANKS ──────────────────────

    _design("PzKpfw II C", "trm_light_tank_chassis_ger_panzer2_2", "light",
        year=1938,
        turret="trm_light_tank_ger_panzer2_turret_1",
        gun="trm_weapon_ac_ger_20_kwk30",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="empty",
        engine="trm_engine_G1_0140",
        transmission="trm_transmission_differential_front",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_015",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_rounded",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_1",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("PzKpfw II F", "trm_light_tank_chassis_ger_panzer2_3", "light",
        year=1941,
        turret="trm_light_tank_ger_panzer2_turret_1",
        gun="trm_weapon_ac_ger_20_kwk38",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="empty",
        engine="trm_engine_G1_0140",
        transmission="trm_transmission_differential_front",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_035",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("PzKpfw II L Luchs", "trm_light_tank_chassis_ger_panzer2_4", "light",
        year=1943,
        turret="trm_light_tank_ger_panzer2_turret_1",
        gun="trm_weapon_ac_ger_20_kwk38",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="empty",
        engine="trm_engine_G1_0180",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_030",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("VK 16.02 Leopard", "trm_light_tank_chassis_ger_vk1602_leopard_1", "light",
        year=1944,
        turret="trm_light_tank_ger_vk1602_leopard_turret_1",
        gun="trm_weapon_c_ger_50_kwk39",
        ammo="trm_ammo_c_ger_50_kwk39",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="empty",
        engine="trm_engine_G1_0550",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_050",
        armor_design="trm_armour_design_light_sloped",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── CAVALRY TANKS ─────────────────────────

    _design("PzKpfw 35(t)", "trm_cavalry_tank_chassis_ger_pz35_1", "cavalry",
        year=1936,
        turret="trm_cavalry_tank_ger_pz35_turret_1",
        gun="trm_weapon_c_ger_37_kwk34t",
        ammo="trm_ammo_c_ger_37_kwk34t",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0120",
        transmission="trm_transmission_brake_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_025",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_rounded",
        armor_const="trm_armour_construction_riveted",
        turret_const="trm_turret_construction_enclosed_riveted",
        radio="trm_radio_1",
        ergonomics="trm_ergonomics_light_standard",
        construction="trm_tank_construction_quality",
    ),

    _design("PzKpfw 38(t) A", "trm_cavalry_tank_chassis_ger_pz38_1", "cavalry",
        year=1938,
        turret="trm_cavalry_tank_ger_pz38_turret_1",
        gun="trm_weapon_c_ger_37_kwk38t",
        ammo="trm_ammo_c_ger_37_kwk38t",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0120",
        transmission="trm_transmission_brake_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_025",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_rounded",
        armor_const="trm_armour_construction_riveted",
        turret_const="trm_turret_construction_enclosed_riveted",
        radio="trm_radio_1",
        ergonomics="trm_ergonomics_light_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("PzKpfw 38(t) G", "trm_cavalry_tank_chassis_ger_pz38_2", "cavalry",
        year=1940,
        turret="trm_cavalry_tank_ger_pz38_turret_2",
        gun="trm_weapon_c_ger_37_kwk38t",
        ammo="trm_ammo_c_ger_37_kwk38t",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0120",
        transmission="trm_transmission_brake_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_050",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_riveted",
        turret_const="trm_turret_construction_enclosed_riveted",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── MORE MEDIUM TANKS ─────────────────────

    _design("PzKpfw III A", "trm_medium_tank_chassis_ger_panzer3_1", "medium",
        year=1937,
        turret="trm_medium_tank_ger_panzer3_turret_1",
        gun="trm_weapon_c_ger_37_kwk36",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0250",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_simple",
        suspension="trm_suspension_spring_coil",
        armor="trm_armour_015",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_rounded",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("PzKpfw III F", "trm_medium_tank_chassis_ger_panzer3_3", "medium",
        year=1939,
        turret="trm_medium_tank_ger_panzer3_turret_1",
        gun="trm_weapon_c_ger_50_kwk38",
        ammo="trm_ammo_c_ger_50_kwk38",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_030",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_mixed",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("PzKpfw III M", "trm_medium_tank_chassis_ger_panzer3_5", "medium",
        year=1942,
        turret="trm_medium_tank_ger_panzer3_turret_2",
        gun="trm_weapon_c_ger_50_kwk39",
        ammo="trm_ammo_c_ger_50_kwk39",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_050",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
        special2="trm_special_schurzen",
    ),

    _design("PzKpfw III N", "trm_medium_tank_chassis_ger_panzer3_5", "medium",
        year=1942,
        turret="trm_medium_tank_ger_panzer3_turret_3",
        gun="trm_weapon_c_ger_75_kwk37",
        ammo="trm_ammo_c_ger_75_kwk37",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_050",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
        special2="trm_special_schurzen",
    ),

    _design("PzKpfw IV A", "trm_medium_tank_chassis_ger_panzer4_1", "medium",
        year=1937,
        turret="trm_medium_tank_ger_panzer4_turret_1",
        gun="trm_weapon_c_ger_75_kwk37",
        ammo="empty",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0250",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_simple",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_015",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_rounded",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── PANTHER F ─────────────────────────────

    _design("Panther F", "trm_medium_advanced_tank_chassis_ger_panther_3", "medium_advanced",
        year=1945,
        turret="trm_medium_advanced_tank_ger_panther_turret_2",
        gun="trm_weapon_c_ger_75_kwk42",
        ammo="trm_ammo_c_ger_75_kwk42",
        coax="trm_weapon_coax_mg_ger_mg34",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0700",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_080",
        armor_design="trm_armour_design_heavy_sloped",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── SUPERHEAVY TANKS ──────────────────────

    _design("Maus", "trm_superheavy_tank_chassis_ger_maus_1", "superheavy",
        year=1945,
        turret="trm_superheavy_tank_ger_maus_turret_1",
        gun="trm_weapon_c_ger_128_kwk44",
        ammo="trm_ammo_c_ger_128_pak44",
        coax="trm_weapon_coax_c_ger_75_kwk37",
        hull_gun="empty",
        engine="trm_engine_D1_1200",
        transmission="trm_transmission_xelectrical",
        gearbox="trm_gearbox_advanced",
        suspension="trm_suspension_torsion_double",
        armor="trm_armour_220",
        armor_design="trm_armour_design_heavy_sloped",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_cast",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    # ── ASSAULT GUNS / TANK DESTROYERS ────────

    _design("StuG III A", "trm_medium_tank_chassis_ger_panzer3_3", "medium",
        year=1940,
        turret="trm_medium_tank_ger_panzer3_casemate_1",
        gun="trm_weapon_c_ger_75_kwk37",
        ammo="trm_ammo_c_ger_75_kwk37",
        coax="empty",
        hull_gun="empty",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_050",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
    ),

    _design("StuG III G", "trm_medium_tank_chassis_ger_panzer3_4", "medium",
        year=1942,
        turret="trm_medium_tank_ger_panzer3_casemate_2",
        gun="trm_weapon_c_ger_75_kwk40",
        ammo="trm_ammo_c_ger_75_kwk40",
        coax="empty",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_080",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
        special2="trm_special_schurzen",
    ),

    _design("StuH 42", "trm_medium_tank_chassis_ger_panzer3_5", "medium",
        year=1942,
        turret="trm_medium_tank_ger_panzer3_casemate_2",
        gun="trm_weapon_c_ger_105_stuh42",
        ammo="trm_ammo_c_ger_105_stuh42",
        coax="empty",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_080",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("Hetzer", "trm_cavalry_tank_chassis_ger_pz38_2", "cavalry",
        year=1944,
        turret="trm_cavalry_tank_ger_pz38_casemate_2",
        gun="trm_weapon_c_ger_75_kwk40",
        ammo="trm_ammo_c_ger_75_kwk40",
        coax="empty",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0160",
        transmission="trm_transmission_brake_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_060",
        armor_design="trm_armour_design_light_sloped",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_poor",
        construction="trm_tank_construction_quality",
    ),

    _design("Jagdpanzer IV", "trm_medium_tank_chassis_ger_panzer4_4", "medium",
        year=1944,
        turret="trm_medium_tank_ger_panzer4_casemate_1",
        gun="trm_weapon_c_ger_75_kwk40_long",
        ammo="trm_ammo_c_ger_75_kwk40_long",
        coax="empty",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_080",
        armor_design="trm_armour_design_light_sloped",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_improved",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("Jagdpanther", "trm_medium_advanced_tank_chassis_ger_panther_1", "medium_advanced",
        year=1944,
        turret="trm_medium_advanced_tank_ger_panther_casemate_1",
        gun="trm_weapon_c_ger_88_kwk43",
        ammo="trm_ammo_c_ger_88_kwk43",
        coax="empty",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0700",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_080",
        armor_design="trm_armour_design_heavy_sloped",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("Ferdinand", "trm_heavy_tank_chassis_ger_tiger_1", "heavy",
        year=1943,
        turret="trm_heavy_tank_ger_tiger_casemate_1",
        gun="trm_weapon_c_ger_88_kwk43",
        ammo="trm_ammo_c_ger_88_kwk43",
        coax="empty",
        hull_gun="empty",
        engine="trm_engine_G1_0600",
        transmission="trm_transmission_xelectrical",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_200",
        armor_design="trm_armour_design_heavy_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_poor",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("Jagdtiger", "trm_heavy_tank_chassis_ger_tiger2_1", "heavy",
        year=1944,
        turret="trm_heavy_tank_ger_tiger2_casemate_1",
        gun="trm_weapon_c_ger_128_pak40",
        ammo="trm_ammo_c_ger_128_pak40",
        coax="empty",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0700",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_260",
        armor_design="trm_armour_design_heavy_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_standard",
        construction="trm_tank_construction_quality",
        special1="trm_special_cupola",
    ),

    _design("Sturmpanzer IV Brummbar", "trm_medium_tank_chassis_ger_panzer4_3", "medium",
        year=1943,
        turret="trm_medium_tank_ger_panzer4_casemate_1",
        gun="trm_weapon_c_ger_150_stuh43",
        ammo="trm_ammo_c_ger_150_stuh43",
        coax="empty",
        hull_gun="trm_weapon_hull_mg_ger_mg34",
        engine="trm_engine_G1_0300",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_spring_leaf",
        armor="trm_armour_100",
        armor_design="trm_armour_design_light_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_2",
        ergonomics="trm_ergonomics_light_poor",
        construction="trm_tank_construction_quality",
    ),

    _design("Sturmtiger", "trm_heavy_tank_chassis_ger_tiger_1", "heavy",
        year=1944,
        turret="trm_heavy_tank_ger_tiger_casemate_1",
        gun="trm_weapon_c_ger_380_rw61",
        ammo="empty",
        coax="empty",
        hull_gun="empty",
        engine="trm_engine_G1_0700",
        transmission="trm_transmission_differential_rear",
        gearbox="trm_gearbox_standard",
        suspension="trm_suspension_torsion",
        armor="trm_armour_150",
        armor_design="trm_armour_design_heavy_basic",
        armor_dist="trm_armour_distribution_front",
        armor_const="trm_armour_construction_welded",
        turret_const="trm_turret_construction_enclosed_welded",
        radio="trm_radio_3",
        ergonomics="trm_ergonomics_heavy_standard",
        construction="trm_tank_construction_quality",
    ),
]


# ─────────────────────────────────────────────
#  INTEGRATION
# ─────��───────────────────────────────────────

def inject_tank_designs(
    equip_db: dict,
    designs: list[TankDesign] | None = None,
    module_db: dict | None = None,
) -> list[str]:
    """Compute and inject tank design equipment entries into *equip_db*.

    Parameters
    ----------
    equip_db : dict
        The equipment database to modify (from ``build_equipment_db()``).
    designs : list[TankDesign], optional
        Designs to inject.  Defaults to ``GERMAN_TANK_DESIGNS``.
    module_db : dict, optional
        Module database.  Built automatically if not supplied.

    Returns
    -------
    list[str]
        Equipment IDs of the injected designs.
    """
    if designs is None:
        designs = GERMAN_TANK_DESIGNS
    if module_db is None:
        module_db = build_module_db()

    injected: list[str] = []
    for design in designs:
        entry = design.to_equipment_entry(equip_db, module_db)
        equip_db[entry["id"]] = entry
        injected.append(entry["id"])

    return injected


def list_german_designs() -> list[str]:
    """Return names of all pre-built German tank designs."""
    return [d.name for d in GERMAN_TANK_DESIGNS]


def get_design(name: str) -> TankDesign:
    """Look up a German tank design by name. Raises KeyError if not found."""
    for d in GERMAN_TANK_DESIGNS:
        if d.name == name:
            return d
    raise KeyError(
        f"Unknown tank design: {name!r}. "
        f"Available: {list_german_designs()}"
    )
