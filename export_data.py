#!/usr/bin/env python3
"""Export BICE mod data to JSON for the static GitHub Pages calculator."""

import json
import sys
import os

# Add bice_tools to path
sys.path.insert(0, os.path.dirname(__file__))

from bice_parser import build_equipment_db, build_battalion_db
from bice_models import BICEDatabase
from bice_tanks import build_module_db, inject_tank_designs, GERMAN_TANK_DESIGNS
from bice_doctrines import DOCTRINE_PRESETS, list_presets, get_preset
from bice_calc import _BAT_RESULT_STATS

print("Building databases...")
equip_db = build_equipment_db()
bat_db = build_battalion_db()
module_db = build_module_db()
inject_tank_designs(equip_db, module_db=module_db)
db = BICEDatabase(equip_db=equip_db, bat_db=bat_db)

# ── 1. Equipment (non-archetype, land families) ──
print("Exporting equipment...")
equipment = []
for eid, eq in sorted(equip_db.items(), key=lambda x: (x[1].get("family",""), x[1].get("year",0))):
    if eq.get("is_archetype") in (True, "yes", 1):
        continue
    equipment.append({
        "id": eid,
        "family": eq.get("family", ""),
        "year": int(eq.get("year", 0)),
        "soft_attack": round(float(eq.get("soft_attack", 0)), 2),
        "hard_attack": round(float(eq.get("hard_attack", 0)), 2),
        "defense": round(float(eq.get("defense", 0)), 2),
        "breakthrough": round(float(eq.get("breakthrough", 0)), 2),
        "ap_attack": round(float(eq.get("ap_attack", 0)), 2),
        "air_attack": round(float(eq.get("air_attack", 0)), 2),
        "armor_value": round(float(eq.get("armor_value", 0)), 2),
        "hardness": round(float(eq.get("hardness", 0)), 4),
        "maximum_speed": round(float(eq.get("maximum_speed", 0)), 2),
        "build_cost_ic": round(float(eq.get("build_cost_ic", 0)), 2),
        "reliability": round(float(eq.get("reliability", 0)), 4),
        "additional_collateral_damage": round(float(eq.get("additional_collateral_damage", 0)), 2),
        "suppression": round(float(eq.get("suppression", 0)), 2),
        "fuel_consumption": round(float(eq.get("fuel_consumption", 0)), 2),
    })
print(f"  {len(equipment)} equipment entries")

# ── 2. Battalions ──
print("Exporting battalions...")
battalions = []
for bid, bat in sorted(bat_db.items()):
    cats = bat.get("categories", [])
    if isinstance(cats, dict):
        cats = list(cats.keys())
    battalions.append({
        "id": bid,
        "group": bat.get("group", ""),
        "combat_width": float(bat.get("combat_width", 0)),
        "manpower": float(bat.get("manpower", 0)),
        "max_organisation": float(bat.get("max_organisation", 0)),
        "max_strength": float(bat.get("max_strength", 0)),
        "weight": float(bat.get("weight", 0)),
        "supply_consumption": round(float(bat.get("supply_consumption", 0)), 4),
        "training_time": int(bat.get("training_time", 0)),
        "transport": bat.get("transport", ""),
        "soft_attack": round(float(bat.get("soft_attack", 0)), 2),
        "hard_attack": round(float(bat.get("hard_attack", 0)), 2),
        "defense": round(float(bat.get("defense", 0)), 2),
        "breakthrough": round(float(bat.get("breakthrough", 0)), 2),
        "categories": cats,
        "need": bat.get("need", {}),
    })
print(f"  {len(battalions)} battalions")

# ── 3. Tank designs (pre-computed stats) ──
print("Exporting tank designs...")
tanks = []
for d in GERMAN_TANK_DESIGNS:
    s = d.compute_stats(equip_db, module_db)
    tanks.append({
        "name": d.name,
        "tank_class": d.tank_class,
        "year": getattr(d, "_year_override", None) or "",
        "soft_attack": round(s.get("soft_attack", 0), 2),
        "hard_attack": round(s.get("hard_attack", 0), 2),
        "defense": round(s.get("defense", 0), 2),
        "breakthrough": round(s.get("breakthrough", 0), 2),
        "ap_attack": round(s.get("ap_attack", 0), 2),
        "armor_value": round(s.get("armor_value", 0), 2),
        "hardness": round(s.get("hardness", 0), 4),
        "maximum_speed": round(s.get("maximum_speed", 0), 2),
        "build_cost_ic": round(s.get("build_cost_ic", 0), 2),
        "reliability": round(s.get("reliability", 0), 4),
    })
print(f"  {len(tanks)} tank designs")

# ── 4. Doctrine presets ──
print("Exporting doctrine presets...")
doctrines = {}
for name in list_presets():
    preset = get_preset(name)
    doctrines[name] = {
        "name": preset.get("name", name),
        "category_mult": preset.get("category_mult", {}),
        "category_flat": preset.get("category_flat", {}),
        "division": preset.get("division", {}),
    }
print(f"  {len(doctrines)} presets")

# ── 5. Family→equipment lookup (for auto-equip) ──
print("Building family index...")
family_index = {}  # family → [{id, year}, ...] sorted by year
for e in equipment:
    fam = e["family"]
    if not fam:
        continue
    if fam not in family_index:
        family_index[fam] = []
    family_index[fam].append({"id": e["id"], "year": e["year"]})
# Sort each family by year
for fam in family_index:
    family_index[fam].sort(key=lambda x: x["year"])
print(f"  {len(family_index)} families")

# ── Write output ──
out_dir = sys.argv[1] if len(sys.argv) > 1 else "."

data = {
    "equipment": equipment,
    "battalions": battalions,
    "tanks": tanks,
    "doctrines": doctrines,
    "family_index": family_index,
}

outpath = os.path.join(out_dir, "bice_data.json")
with open(outpath, "w", encoding="utf-8") as f:
    json.dump(data, f, separators=(",", ":"))

size_mb = os.path.getsize(outpath) / 1024 / 1024
print(f"\nWrote {outpath} ({size_mb:.1f} MB)")
print("Done!")
