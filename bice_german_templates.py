#!/usr/bin/env python3
"""
bice_german_templates.py — German division templates from AI and historical files.

Templates are defined using the OOP interface (BICEDatabase, Division) and
can be computed with any doctrine preset.

Public API
----------
build_german_templates(db, year=1939) → list[Division]
    All German divisions for a given year.

TEMPLATE_DEFS
    Raw template definitions (dicts) before database resolution.
"""

from __future__ import annotations
from bice_models import BICEDatabase, Division


# ─────────────────────────────────────────────
#  RAW TEMPLATE DEFINITIONS
# ─────────────────────────────────────────────
# Each entry: name, notes, year, list of (bat_type, count, is_support)
# Equipment is auto-assigned via equip_auto(year).

TEMPLATE_DEFS: list[dict] = [
    # ── INFANTRY ──────────────────────────────
    {
        "name": "Infanterie-Division",
        "notes": "Standard German infantry division, 9 inf + 3 art + 1 med art + 1 AT",
        "category": "infantry",
        "year": 1939,
        "battalions": [
            ("infantry", 9),
            ("artillery_brigade", 3),
            ("artillery_brigade_med", 1),
            ("anti_tank_brigade", 1),
        ],
        "support": [
            ("DIV_HQ", 1),
            ("engineer", 1),
            ("recon_cav", 1),
            ("artillery_heavy", 1),
            ("anti_air", 1),
            ("maintenance_company", 1),
            ("logistics_company", 1),
            ("field_hospital", 1),
        ],
    },
    {
        "name": "Infanterie-Division (verstärkt)",
        "notes": "Reinforced infantry, AI role 2: +combat engineer, +signal company",
        "category": "infantry",
        "year": 1940,
        "battalions": [
            ("infantry", 9),
            ("anti_tank_brigade", 1),
            ("artillery_brigade", 4),
        ],
        "support": [
            ("DIV_HQ", 1),
            ("engineer", 1),
            ("combat_engineer", 1),
            ("logistics_company", 1),
            ("field_hospital_cav", 1),
            ("recon", 1),
            ("signal_company", 1),
            ("anti_air", 1),
        ],
    },
    {
        "name": "Schwere Infanterie-Division",
        "notes": "Heavy infantry: assault infantry + medium artillery, AI role",
        "category": "infantry",
        "year": 1941,
        "battalions": [
            ("infantry", 3),
            ("infantry_assault", 6),
            ("anti_tank_brigade", 1),
            ("artillery_brigade_med", 4),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer", 1),
            ("logistics_company_car", 1),
            ("field_hospital", 1),
            ("recon_cav", 1),
            ("artillery_heavy", 1),
            ("maintenance_company", 1),
            ("anti_air_heavy", 1),
        ],
    },
    {
        "name": "Schwere Infanterie-Division (spät)",
        "notes": "Late-war heavy infantry with StuG support, AI role 4",
        "category": "infantry",
        "year": 1943,
        "battalions": [
            ("infantry", 3),
            ("infantry_assault", 6),
            ("anti_tank_brigade_med", 1),
            ("artillery_brigade_med", 3),
            ("trm_medium_assault_gun", 1),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer", 1),
            ("combat_engineer", 1),
            ("logistics_company_mot", 1),
            ("field_hospital", 1),
            ("recon_cav", 1),
            ("signal_company_mot", 1),
            ("artillery_heavy", 1),
            ("maintenance_company", 1),
            ("anti_air_heavy", 1),
        ],
    },

    # ── MOTORIZED ─────────────────────────────
    {
        "name": "Infanterie-Division (halbmot.)",
        "notes": "Semi-motorized infantry, transitional formation",
        "category": "motorized",
        "year": 1939,
        "battalions": [
            ("semi_motorized", 6),
            ("motorized", 2),
            ("armored_car", 1),
            ("artillery_brigade_mot", 3),
            ("anti_tank_brigade_mot", 1),
        ],
        "support": [
            ("DIV_HQ", 1),
            ("recon_mot", 1),
            ("engineer_mot", 1),
            ("artillery_heavy", 1),
            ("maintenance_company", 1),
            ("logistics_company_car", 1),
            ("field_hospital", 1),
        ],
    },
    {
        "name": "Infanterie-Division (mot.)",
        "notes": "AI motorized role 1: semi-mot + assault + armored car",
        "category": "motorized",
        "year": 1940,
        "battalions": [
            ("semi_motorized", 6),
            ("semi_motorized_assault", 3),
            ("armored_car", 1),
            ("anti_tank_brigade_mot", 1),
            ("artillery_brigade_mot", 3),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("combat_engineer_mot", 1),
            ("logistics_company_car", 1),
            ("field_hospital", 1),
            ("recon_ac", 1),
            ("signal_company_mot", 1),
            ("maintenance_company", 1),
            ("anti_air_car", 1),
        ],
    },
    {
        "name": "Infanterie-Division (mot.) Afrika",
        "notes": "Motorized infantry for Africa, 9 mot + 3 art + 1 med art + 1 AT",
        "category": "motorized",
        "year": 1941,
        "battalions": [
            ("motorized", 9),
            ("artillery_brigade_mot", 3),
            ("artillery_brigade_mot_med", 1),
            ("anti_tank_brigade_mot", 1),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("recon_mot", 1),
            ("engineer_mot", 1),
            ("maintenance_company", 1),
            ("logistics_company_car", 1),
            ("field_hospital", 1),
        ],
    },

    # ── PANZER ────────────────────────────────
    {
        "name": "Panzer-Division 1936",
        "notes": "Early panzer division, 5 light tanks + 3 mot + 1 motorcycle",
        "category": "armor",
        "year": 1936,
        "battalions": [
            ("trm_light_armor", 5),
            ("motorized", 3),
            ("motorcycle_infantry", 1),
            ("artillery_brigade_mot", 3),
            ("anti_tank_brigade_mot", 1),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("recon_mot", 1),
            ("engineer_mot", 1),
            ("maintenance_company", 1),
            ("logistics_company_car", 1),
            ("field_hospital", 1),
        ],
    },
    {
        "name": "Panzer-Division 1939",
        "notes": "1939 panzer div: 4 light + 2 medium + 3 mot + motorcycle + AC",
        "category": "armor",
        "year": 1939,
        "battalions": [
            ("trm_light_armor", 4),
            ("trm_medium_armor", 2),
            ("motorized", 3),
            ("armored_car", 1),
            ("motorcycle_infantry", 1),
            ("artillery_brigade_mot", 3),
            ("anti_tank_brigade_mot", 1),
        ],
        "support": [
            ("DIV_HQ", 1),
            ("recon_mot", 1),
            ("combat_engineer", 1),
            ("maintenance_company", 1),
            ("logistics_company", 1),
            ("field_hospital", 1),
            ("anti_air", 1),
        ],
    },
    {
        "name": "Panzer-Division 1940",
        "notes": "1940 panzer div: mixed light/medium tanks + CS armor, +heavy arty",
        "category": "armor",
        "year": 1940,
        "battalions": [
            ("motorcycle_infantry", 1),
            ("motorized", 4),
            ("trm_light_armor", 2),
            ("trm_medium_armor", 4),
            ("trm_medium_cs_armor", 2),
            ("artillery_brigade_mot", 3),
            ("anti_tank_brigade_mot", 1),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("artillery_heavy_mot", 1),
            ("recon_ac", 1),
            ("maintenance_company", 1),
            ("logistics_company_mot", 1),
        ],
    },
    {
        "name": "Panzer-Division (AI Medium Armor)",
        "notes": "AI medium armor role 1: 3 med + 1 CS + 4 mot + 3 med arty",
        "category": "armor",
        "year": 1941,
        "battalions": [
            ("motorized", 4),
            ("motorized_assault", 2),
            ("artillery_brigade_mot_med", 3),
            ("trm_medium_armor", 3),
            ("trm_medium_cs_armor", 1),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("combat_engineer_mot", 1),
            ("logistics_company_mot", 1),
            ("field_hospital", 1),
            ("recon_ac", 1),
            ("signal_company_mot", 1),
            ("maintenance_company", 1),
            ("anti_air_heavy_mot", 1),
        ],
    },
    {
        "name": "Panzer-Division (AI Heavy Armor)",
        "notes": "AI heavy armor role: 1 heavy + 4 medium + 3 mech + 3 SP arty",
        "category": "armor",
        "year": 1943,
        "battalions": [
            ("mechanized", 2),
            ("mechanized_assault", 3),
            ("trm_heavy_armor", 1),
            ("trm_medium_armor", 4),
            ("trm_light_sp_artillery", 3),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("combat_engineer_mot", 1),
            ("logistics_company_mot", 1),
            ("field_hospital", 1),
            ("recon_ac", 1),
            ("signal_company_mot", 1),
            ("maintenance_company", 1),
        ],
    },

    {
        "name": "Panzer-Division (AI Medium Armor spät)",
        "notes": "AI medium armor role 4: 5 med + 3 mech + 3 SP arty, no CS",
        "category": "armor",
        "year": 1943,
        "battalions": [
            ("mechanized", 2),
            ("mechanized_assault", 3),
            ("trm_medium_armor", 5),
            ("trm_light_sp_artillery", 3),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("combat_engineer_mot", 1),
            ("logistics_company_mot", 1),
            ("field_hospital", 1),
            ("recon_ac", 1),
            ("signal_company_mot", 1),
            ("maintenance_company", 1),
        ],
    },
    {
        "name": "Panzer-Division (AI Medium Advanced)",
        "notes": "AI medium advanced armor: Panthers/T-44 class + mech + med SP arty",
        "category": "armor",
        "year": 1944,
        "battalions": [
            ("mechanized", 2),
            ("mechanized_assault", 3),
            ("trm_medium_advanced_armor", 5),
            ("trm_medium_sp_artillery", 3),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("combat_engineer_arm", 1),
            ("logistics_company_mot", 1),
            ("field_hospital", 1),
            ("signal_company_mot", 1),
            ("maintenance_company", 1),
        ],
    },

    # ── MOTORIZED (LATE-WAR UPGRADES) ────────
    {
        "name": "Panzergrenadier-Division (mot.)",
        "notes": "AI motorized role 3: full mot + med AT, late-war upgrade",
        "category": "motorized",
        "year": 1941,
        "battalions": [
            ("motorized", 6),
            ("motorized_assault", 3),
            ("armored_car", 1),
            ("anti_tank_brigade_mot_med", 1),
            ("artillery_brigade_mot", 3),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("combat_engineer_mot", 1),
            ("logistics_company_car", 1),
            ("field_hospital", 1),
            ("recon_ac", 1),
            ("signal_company_mot", 1),
            ("maintenance_company", 1),
            ("anti_air_car", 1),
        ],
    },
    {
        "name": "Panzergrenadier-Division (mixed mech)",
        "notes": "AI motorized role 5: mixed mot/mech + med arty, transitional",
        "category": "motorized",
        "year": 1942,
        "battalions": [
            ("motorized", 4),
            ("motorized_assault", 1),
            ("mechanized", 2),
            ("mechanized_assault", 2),
            ("armored_car", 1),
            ("anti_tank_brigade_mot_med", 1),
            ("artillery_brigade_mot_med", 3),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("combat_engineer_mot", 1),
            ("logistics_company_car", 1),
            ("field_hospital", 1),
            ("recon_ac", 1),
            ("signal_company_mot", 1),
            ("maintenance_company", 1),
            ("anti_air_car", 1),
        ],
    },
    {
        "name": "Panzergrenadier-Division (mech)",
        "notes": "AI motorized role 6: mostly mechanized, late-war upgrade",
        "category": "motorized",
        "year": 1943,
        "battalions": [
            ("motorized", 2),
            ("motorized_assault", 1),
            ("mechanized", 4),
            ("mechanized_assault", 2),
            ("armored_car", 1),
            ("anti_tank_brigade_mot_med", 1),
            ("artillery_brigade_mot_med", 3),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("combat_engineer_mot", 1),
            ("logistics_company_car", 1),
            ("field_hospital", 1),
            ("recon_ac", 1),
            ("signal_company_mot", 1),
            ("maintenance_company", 1),
            ("anti_air_car", 1),
        ],
    },

    # ── MARINES ───────────────────────────────
    {
        "name": "Marine-Division",
        "notes": "AI marine role: 6 amph mech + 2 mtn arty mot + amph tanks",
        "category": "marine",
        "year": 1942,
        "battalions": [
            ("amphibious_mechanized", 6),
            ("mountain_artillery_brigade_mot", 2),
            ("trm_light_amphibious_armor", 1),
            ("trm_medium_amphibious_armor", 1),
        ],
        "support": [
            ("DIV_HQ_mech", 1),
            ("engineer_mech", 1),
            ("logistics_company_car", 1),
            ("recon_mot", 1),
            ("signal_company_mot", 1),
            ("maintenance_company", 1),
            ("anti_air_heavy_mot", 1),
            ("amph_support", 1),
        ],
    },

    # ── LIGHT ARMOR ───────────────────────────
    {
        "name": "Leichte-Division",
        "notes": "Light armored division, 4 light tanks + 5 mot",
        "category": "armor",
        "year": 1936,
        "battalions": [
            ("trm_light_armor", 4),
            ("motorized", 5),
            ("artillery_brigade_mot", 2),
            ("anti_tank_brigade_mot", 1),
        ],
        "support": [
            ("DIV_HQ_car", 1),
            ("engineer_mot", 1),
            ("recon_mot", 1),
            ("maintenance_company", 1),
            ("logistics_company_car", 1),
        ],
    },

    # ── MOUNTAIN ──────────────────────────────
    {
        "name": "Gebirgs-Division",
        "notes": "Mountain division, 9 mountaineers + 4 mountain arty, AI role",
        "category": "mountain",
        "year": 1939,
        "battalions": [
            ("mountaineers", 9),
            ("anti_tank_brigade", 1),
            ("mountain_artillery_brigade", 4),
        ],
        "support": [
            ("DIV_HQ", 1),
            ("engineer", 1),
            ("combat_engineer", 1),
            ("logistics_company", 1),
            ("field_hospital_cav", 1),
            ("recon_cav", 1),
            ("signal_company", 1),
            ("mount_support", 1),
        ],
    },

    # ── GARRISON ──────────────────────────────
    {
        "name": "Sicherungs-Division",
        "notes": "Garrison division, 5 light infantry + 1 arty, AI role",
        "category": "garrison",
        "year": 1939,
        "battalions": [
            ("light_infantry", 5),
            ("artillery_brigade", 1),
        ],
        "support": [
            ("DIV_HQ", 1),
            ("engineer", 1),
            ("anti_tank", 1),
            ("anti_air", 1),
        ],
    },

    # ── PARATROOPERS ──────────────────────────
    {
        "name": "Fallschirmjäger-Brigade",
        "notes": "Paratrooper brigade, 4 paratroopers",
        "category": "paratroop",
        "year": 1940,
        "battalions": [
            ("paratrooper", 4),
        ],
        "support": [
            ("recon_mot", 1),
            ("para_support", 1),
        ],
    },
]


# ─────────────────────────────────────────────
#  BUILDER
# ─────────────────────────────────────────────

def build_german_templates(
    db: BICEDatabase,
    year: int | None = None,
) -> list[Division]:
    """Build Division objects for all German templates.

    Parameters
    ----------
    db : BICEDatabase
    year : int, optional
        Override equipment year for all templates.
        If None, each template uses its own default year.

    Returns list of Division objects ready for .compute().
    """
    divisions: list[Division] = []

    for tdef in TEMPLATE_DEFS:
        eq_year = year if year is not None else tdef.get("year", 1939)
        name = tdef["name"]
        notes = tdef.get("notes", "")

        div = Division(name, db, notes=notes)

        # Line battalions
        for bat_id, count in tdef.get("battalions", []):
            try:
                bt = db.battalion(bat_id)
                equipped = bt.equip_auto(eq_year)
                div.add_battalion(equipped, count)
            except KeyError:
                # Battalion type doesn't exist in DB — skip silently
                pass

        # Support companies
        for bat_id, count in tdef.get("support", []):
            try:
                bt = db.battalion(bat_id)
                equipped = bt.equip_auto(eq_year)
                div.add_support(equipped, count)
            except KeyError:
                pass

        divisions.append(div)

    return divisions


def get_template_def(name: str) -> dict | None:
    """Look up a template definition by name (case-insensitive partial match)."""
    name_lower = name.lower()
    for tdef in TEMPLATE_DEFS:
        if name_lower in tdef["name"].lower():
            return tdef
    return None


def list_template_names() -> list[str]:
    """Return all template names."""
    return [t["name"] for t in TEMPLATE_DEFS]
