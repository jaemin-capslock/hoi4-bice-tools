#!/usr/bin/env python3
"""
bice_stats_gen.py — BICE Division Stats: main entry point.

Imports from:
  bice_parser  — HOI4 file parser + equipment/battalion DB builders
  bice_calc    — stat calculator (battalion & division)
  bice_viz     — Excel workbook writer

Usage:   python bice_stats_gen.py
Output:  ~/Desktop/BICE_Stats.xlsx

Quick API examples
------------------
    from bice_parser import build_equipment_db, build_battalion_db
    from bice_calc   import calc_battalion, calc_battalions, calc_division

    equip_db = build_equipment_db()
    bat_db   = build_battalion_db()

    # Per-battalion
    stats = calc_battalion("infantry",
                           ["infantry_equipment_2", "infantry_uniforms_2"],
                           bat_db, equip_db)
    print(stats["soft_attack"])   # → 2.1

    # Batch
    results = calc_battalions(
        {"inf36": ["infantry_equipment_1", "infantry_uniforms_1"],
         "inf39": ["infantry_equipment_2", "infantry_uniforms_2"]},
        bat_db, equip_db,
    )

    # Division — list-form equip (auto-assigned to slots)
    stats = calc_division(
        {"name": "My Division",
         "battalions": [
             {"type": "infantry", "count": 9,
              "equip": ["infantry_equipment_2", "infantry_uniforms_2"]},
             {"type": "artillery_brigade", "count": 4,
              "equip": ["artillery_equipment_2", "infantry_uniforms_2",
                        "artyhorse_equipment_0"]},
         ],
         "support": [{"type": "engineer", "count": 1, "equip": []}]},
        bat_db, equip_db,
        # Optional doctrine/experience modifiers:
        # modifiers={"multiplicative": {"soft_attack": 0.10, "defense": 0.05}}
    )
"""

from bice_parser    import build_equipment_db, build_battalion_db
from bice_calc      import calc_division
from bice_viz       import generate_excel
from bice_doctrines import get_preset


# ─────────────────────────────────────────────
#  DIVISION TEMPLATES
#  Edit freely — use either equip list form or legacy dict form.
# ─────────────────────────────────────────────

# ── Common support company equipment shorthand ──────────────────────
# (1936/early-war tier)
_SUP_RECON_36      = ["infantry_equipment_1", "infantry_uniforms_1",
                      "recon_equipment_0"]
_SUP_ENGINEER_36   = ["infantry_equipment_1", "infantry_uniforms_1",
                      "support_equipment_1"]
_SUP_HOSPITAL_36   = ["infantry_uniforms_1", "support_equipment_1"]
_SUP_SIGNAL_36     = ["infantry_uniforms_1", "support_equipment_1",
                      "radio_equipment_0"]
_SUP_LOGISTICS_36  = ["infantry_uniforms_1", "support_equipment_1",
                      "artyhorse_equipment_0"]
_SUP_MAINT_36      = ["infantry_uniforms_1", "support_equipment_1",
                      "motorized_equipment_0"]
_SUP_AA_36         = ["infantry_uniforms_1", "anti_air_equipment_0",
                      "artyhorse_equipment_0"]
_SUP_AT_36         = ["infantry_uniforms_1", "anti_tank_equipment_0",
                      "artyhorse_equipment_0"]
_SUP_DIV_HQ_36     = ["infantry_uniforms_1"]

# (1939-40 tier)
_SUP_RECON_39      = ["infantry_equipment_2", "infantry_uniforms_2",
                      "recon_equipment_1"]
_SUP_ENGINEER_39   = ["infantry_equipment_2", "infantry_uniforms_2",
                      "support_equipment_1"]
_SUP_HOSPITAL_39   = ["infantry_uniforms_2", "support_equipment_1"]
_SUP_SIGNAL_39     = ["infantry_uniforms_2", "support_equipment_1",
                      "radio_equipment_0"]
_SUP_LOGISTICS_39  = ["infantry_uniforms_2", "support_equipment_1",
                      "artyhorse_equipment_0"]
_SUP_MAINT_39      = ["infantry_uniforms_2", "support_equipment_1",
                      "motorized_equipment_0"]
_SUP_AA_39         = ["infantry_uniforms_2", "anti_air_equipment_1",
                      "artyhorse_equipment_0"]
_SUP_AT_39         = ["infantry_uniforms_2", "anti_tank_equipment_1",
                      "artyhorse_equipment_0"]
_SUP_DIV_HQ_39     = ["infantry_uniforms_2"]


DIVISION_TEMPLATES = [
    # ── GERMAN INFANTRY ──────────────────────────────────────────────
    {
        "name": "GER Infanterie-Division 1936",
        "notes": "Historical German inf div, early-war equipment",
        "battalions": [
            {"type": "infantry", "count": 9,
             "equip": ["infantry_equipment_1", "infantry_uniforms_1"]},
            {"type": "artillery_brigade", "count": 4,
             "equip": ["artillery_equipment_0", "infantry_uniforms_1",
                       "artyhorse_equipment_0"]},
            {"type": "artillery_brigade_med", "count": 1,
             "equip": ["medartillery_equipment_0", "infantry_uniforms_1",
                       "artyhorse_equipment_0"]},
        ],
        "support": [
            {"type": "DIV_HQ",          "count": 1, "equip": _SUP_DIV_HQ_36},
            {"type": "recon",            "count": 1, "equip": _SUP_RECON_36},
            {"type": "engineer",         "count": 1, "equip": _SUP_ENGINEER_36},
            {"type": "field_hospital",   "count": 1, "equip": _SUP_HOSPITAL_36},
            {"type": "signal_company",   "count": 1, "equip": _SUP_SIGNAL_36},
            {"type": "logistics_company","count": 1, "equip": _SUP_LOGISTICS_36},
        ],
    },
    {
        "name": "GER Infanterie-Division 1940",
        "notes": "Mid-war standard (1939-40 era equipment)",
        "battalions": [
            {"type": "infantry", "count": 9,
             "equip": ["infantry_equipment_2", "infantry_uniforms_2"]},
            {"type": "artillery_brigade", "count": 4,
             "equip": ["artillery_equipment_2", "infantry_uniforms_2",
                       "artyhorse_equipment_0"]},
            {"type": "artillery_brigade_med", "count": 1,
             "equip": ["medartillery_equipment_2", "infantry_uniforms_2",
                       "artyhorse_equipment_0"]},
        ],
        "support": [
            {"type": "DIV_HQ",            "count": 1, "equip": _SUP_DIV_HQ_39},
            {"type": "recon",              "count": 1, "equip": _SUP_RECON_39},
            {"type": "engineer",           "count": 1, "equip": _SUP_ENGINEER_39},
            {"type": "field_hospital",     "count": 1, "equip": _SUP_HOSPITAL_39},
            {"type": "signal_company",     "count": 1, "equip": _SUP_SIGNAL_39},
            {"type": "logistics_company",  "count": 1, "equip": _SUP_LOGISTICS_39},
            {"type": "anti_air",           "count": 1, "equip": _SUP_AA_39},
        ],
    },
    {
        "name": "GER Infanterie-Division 1942",
        "notes": "Late-war standard (inf_eq_3, arty_eq_3)",
        "battalions": [
            {"type": "infantry", "count": 9,
             "equip": ["infantry_equipment_3", "infantry_uniforms_3"]},
            {"type": "artillery_brigade", "count": 4,
             "equip": ["artillery_equipment_3", "infantry_uniforms_3",
                       "artyhorse_equipment_0"]},
            {"type": "artillery_brigade_med", "count": 2,
             "equip": ["medartillery_equipment_3", "infantry_uniforms_3",
                       "artyhorse_equipment_0"]},
        ],
        "support": [
            {"type": "DIV_HQ",              "count": 1, "equip": _SUP_DIV_HQ_39},
            {"type": "recon",                "count": 1, "equip": _SUP_RECON_39},
            {"type": "engineer",             "count": 1, "equip": _SUP_ENGINEER_39},
            {"type": "field_hospital",       "count": 1, "equip": _SUP_HOSPITAL_39},
            {"type": "signal_company",       "count": 1, "equip": _SUP_SIGNAL_39},
            {"type": "logistics_company",    "count": 1, "equip": _SUP_LOGISTICS_39},
            {"type": "maintenance_company",  "count": 1, "equip": _SUP_MAINT_39},
            {"type": "anti_air",             "count": 1, "equip": _SUP_AA_39},
            {"type": "anti_tank",            "count": 1, "equip": _SUP_AT_39},
        ],
    },
    # ── ASSAULT / STURMTRUPPE ────────────────────────────────────────
    {
        "name": "GER Sturmtruppe 1940",
        "notes": "Assault infantry with SMG equipment",
        "battalions": [
            {"type": "infantry_assault", "count": 9,
             "equip": ["SMG_equipment_1", "infantry_uniforms_2"]},
            {"type": "artillery_brigade", "count": 3,
             "equip": ["artillery_equipment_1", "infantry_uniforms_2",
                       "artyhorse_equipment_0"]},
        ],
        "support": [
            {"type": "DIV_HQ",          "count": 1, "equip": _SUP_DIV_HQ_39},
            {"type": "recon",            "count": 1, "equip": _SUP_RECON_39},
            {"type": "engineer",         "count": 1, "equip": _SUP_ENGINEER_39},
            {"type": "signal_company",   "count": 1, "equip": _SUP_SIGNAL_39},
        ],
    },
    # ── PANZER DIVISION ──────────────────────────────────────────────
    {
        "name": "GER Panzer-Division 1940 (placeholder)",
        "notes": "Add tank equip IDs once armor files are parsed",
        "battalions": [
            {"type": "infantry", "count": 4,
             "equip": ["infantry_equipment_2", "infantry_uniforms_2"]},
            {"type": "artillery_brigade_mot", "count": 2,
             "equip": ["artillery_equipment_2", "infantry_uniforms_2",
                       "artytruck_equipment_0"]},
        ],
        "support": [
            {"type": "DIV_HQ",              "count": 1, "equip": _SUP_DIV_HQ_39},
            {"type": "recon",                "count": 1, "equip": _SUP_RECON_39},
            {"type": "engineer",             "count": 1, "equip": _SUP_ENGINEER_39},
            {"type": "maintenance_company",  "count": 1, "equip": _SUP_MAINT_39},
            {"type": "signal_company",       "count": 1, "equip": _SUP_SIGNAL_39},
        ],
    },
    # ── GEBIRGSJÄGER ─────────────────────────────────────────────────
    {
        "name": "GER Gebirgsjäger-Division 1940",
        "notes": "Mountain infantry with mountain artillery",
        "battalions": [
            {"type": "infantry", "count": 9,
             "equip": ["infantry_equipment_2", "infantry_uniforms_2"]},
            {"type": "mountain_artillery_brigade", "count": 3,
             "equip": ["mountain_artillery_equipment_1", "infantry_uniforms_2",
                       "artyhorse_equipment_0"]},
        ],
        "support": [
            {"type": "DIV_HQ",          "count": 1, "equip": _SUP_DIV_HQ_39},
            {"type": "recon",            "count": 1, "equip": _SUP_RECON_39},
            {"type": "engineer",         "count": 1, "equip": _SUP_ENGINEER_39},
            {"type": "field_hospital",   "count": 1, "equip": _SUP_HOSPITAL_39},
            {"type": "logistics_company","count": 1, "equip": _SUP_LOGISTICS_39},
        ],
    },
]


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

# Default doctrine preset — "all WW1 doctrines researched" (defensive picks)
DEFAULT_DOCTRINE = "ww1_full"


def main():
    print("Building equipment database...")
    equip_db = build_equipment_db()
    print(f"  {len(equip_db)} equipment entries loaded.")

    print("Building battalion database...")
    bat_db = build_battalion_db()
    print(f"  {len(bat_db)} battalion types loaded.")

    doctrine = get_preset(DEFAULT_DOCTRINE)
    print(f"Doctrine preset: {doctrine['name']}")

    print("\nCalculating division stats (with doctrine modifiers)...")
    div_stats = []
    for tmpl in DIVISION_TEMPLATES:
        stats = calc_division(tmpl, bat_db, equip_db, modifiers=doctrine)
        div_stats.append(stats)
        print(f"  {stats['name']}: SA={stats['Soft Attack']}, "
              f"Def={stats['Defense']:.2f}, Org={stats['Org']:.2f}, "
              f"Width={stats['Width']}")

    # Also compute without doctrines for comparison
    print("\nCalculating base stats (no doctrines)...")
    div_stats_base = []
    for tmpl in DIVISION_TEMPLATES:
        stats = calc_division(tmpl, bat_db, equip_db)
        stats["name"] = stats["name"] + " [base]"
        div_stats_base.append(stats)

    print("Writing Excel workbook...")
    out = generate_excel(equip_db, bat_db, div_stats + div_stats_base)
    print(f"\nDone!  Saved to: {out}")


if __name__ == "__main__":
    main()
