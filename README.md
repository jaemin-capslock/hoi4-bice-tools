# BICE Division Stats Calculator

A Python toolkit for computing and comparing division stats from the **Black ICE (BICE)** mod for Hearts of Iron IV. Parses the mod's Clausewitz script files directly, so stat data is always in sync with the installed mod version.

## Quick start

```bash
pip install openpyxl
cd bice_tools
python bice_stats_gen.py          # generates ~/Desktop/BICE_Stats.xlsx
python test_bice.py -v            # run the test suite
```

## Modules

| File | Purpose |
|---|---|
| `bice_parser.py` | HOI4 Clausewitz format parser; builds equipment DB (1500+ entries) and battalion DB (300+ sub-unit types) from mod files |
| `bice_calc.py` | Stat calculator: per-battalion and full-division aggregation with category-aware doctrine modifiers |
| `bice_doctrines.py` | Doctrine modifier presets (WW1 full defensive/offensive; extensible for WW2 branches) |
| `bice_viz.py` | Excel workbook writer: Division Comparison, Equipment Reference, Battalion Reference, raw dump |
| `bice_stats_gen.py` | CLI entry point with sample German division templates |
| `test_bice.py` | 123 unit + integration tests |

## API usage

```python
from bice_parser    import build_equipment_db, build_battalion_db
from bice_calc      import calc_battalion, calc_battalions, calc_division
from bice_doctrines import get_preset

equip_db = build_equipment_db()
bat_db   = build_battalion_db()
```

### Per-battalion stats

```python
stats = calc_battalion(
    "infantry",
    ["infantry_equipment_2", "infantry_uniforms_2"],
    bat_db, equip_db,
)
# stats = {"soft_attack": 2.1, "defense": 6.4, "breakthrough": 0.9, ...}
```

### Batch comparison

```python
results = calc_battalions({
    "infantry":          ["infantry_equipment_2", "infantry_uniforms_2"],
    "artillery_brigade": ["artillery_equipment_2", "infantry_uniforms_2",
                          "artyhorse_equipment_0"],
}, bat_db, equip_db)
```

### Division designer

```python
template = {
    "name": "9 Inf / 4 Art / 1 Med Art",
    "battalions": [
        {"type": "infantry",              "count": 9,
         "equip": ["infantry_equipment_2", "infantry_uniforms_2"]},
        {"type": "artillery_brigade",     "count": 4,
         "equip": ["artillery_equipment_2", "infantry_uniforms_2",
                   "artyhorse_equipment_0"]},
        {"type": "artillery_brigade_med", "count": 1,
         "equip": ["medartillery_equipment_2", "infantry_uniforms_2",
                   "artyhorse_equipment_0"]},
    ],
    "support": [
        {"type": "DIV_HQ",          "count": 1, "equip": ["infantry_uniforms_2"]},
        {"type": "engineer",         "count": 1, "equip": ["infantry_equipment_2",
                  "infantry_uniforms_2", "support_equipment_1"]},
        {"type": "signal_company",   "count": 1, "equip": ["infantry_uniforms_2",
                  "support_equipment_1", "radio_equipment_0"]},
        {"type": "recon",            "count": 1, "equip": ["infantry_equipment_2",
                  "infantry_uniforms_2", "recon_equipment_1"]},
    ],
}

stats = calc_division(template, bat_db, equip_db)
# {"Soft Attack": 85.9, "Defense": 5.39, "Org": 21.02, "Width": 25.5, ...}
```

### Doctrine modifiers

Doctrine presets apply category-aware bonuses per-battalion before division
aggregation, matching HOI4's stacking rules.

```python
from bice_doctrines import get_preset, list_presets

print(list_presets())
# ['none', 'ww1_full', 'ww1_full_def', 'ww1_full_off']

doctrine = get_preset("ww1_full")   # all WW1 doctrines, defensive XOR picks

stats = calc_division(template, bat_db, equip_db, modifiers=doctrine)
# SA jumps from 85.9 -> 105.2 (arty +30%), Def from 5.39 -> 7.69 (inf +50%)
```

Custom modifiers can also be passed directly:

```python
# Simple flat/multiplicative (legacy format)
calc_division(template, bat_db, equip_db,
              modifiers={"multiplicative": {"soft_attack": 0.10}})

# Category-aware (doctrine format)
calc_division(template, bat_db, equip_db, modifiers={
    "category_mult": {
        "category_all_infantry": {"defense": 0.50, "breakthrough": 0.19},
    },
    "category_flat": {
        "category_all_infantry": {"max_organisation": 5.0},
    },
})
```

## Division stat aggregation rules

These match HOI4's internal formulas:

| Stat | Rule |
|---|---|
| HP, Soft Attack, Hard Attack, Air Attack, Collateral, Suppression, IC Cost | Sum across all battalions (count x stat) |
| Organization, Defense, Breakthrough, Hardness | Weighted average by battalion manpower |
| Speed | Minimum across non-support battalion transport equipment |
| Combat Width | Sum (support companies contribute 0) |
| Training Time | Maximum across all battalions |

Equipment stats contribute their face value once per slot (NOT multiplied by
the quantity needed).

## Support companies

BICE has 79 support company types. Key IDs for templates:

| Role | Battalion ID | Notes |
|---|---|---|
| Division HQ | `DIV_HQ` | Horse/car/mech/armored variants |
| Signal | `signal_company` | Also `signal_company_mot` |
| Engineer | `engineer` | Also `combat_engineer`, motorized/mech/armored variants |
| Recon | `recon` | Also `recon_cav`, `recon_mot`, `recon_ac`, `recon_mech` |
| Field Hospital | `field_hospital` | Also `field_hospital_cav` |
| Logistics | `logistics_company` | Also car/mot/mech variants |
| Maintenance | `maintenance_company` | Also `maintenance_company_arm` |
| Military Police | `military_police` | |
| Anti-Air | `anti_air` | Also `anti_air_car`, heavy/heavy_mot |
| Anti-Tank | `anti_tank` | Also `anti_tank_mot`, heavy variants |
| Heavy Artillery | `artillery_heavy` | Also `artillery_heavy_mot` |
| Rocket Artillery | `rocket_artillery` | |
| Spotter Planes | `spotter_air` | |

## Doctrine presets

| Preset | Description |
|---|---|
| `none` | No doctrine bonuses |
| `ww1_full` / `ww1_full_def` | All 55 WW1 land doctrine techs; defensive XOR (MG_support_infantry) |
| `ww1_full_off` | All WW1 techs; offensive XOR (Infantry_support_MG) |

Key WW1 cumulative bonuses (defensive picks):

| Category | Defense | Breakthrough | Soft Attack | Hard Attack | Flat Org |
|---|---|---|---|---|---|
| All Infantry | +50% | +19% | - | +10% | +5 |
| Light Infantry | - | +19% (stacks) | - | - | - |
| Artillery | +35% | +35% | +30% | - | +2 |
| All Armor | +30% | +38% | +30% | +30% | +6 |
| Cavalry | +5% | +5% | +10% | - | +10 |
| DIV HQ | - | - | - | - | +10 |

### Tank designer

```python
from bice_tanks import build_module_db, inject_tank_designs, GERMAN_TANK_DESIGNS, get_design

# Tank stats are computed from chassis + modules (TRM system)
module_db = build_module_db()   # 1136 tank modules

# See pre-built German designs
for d in GERMAN_TANK_DESIGNS:
    stats = d.compute_stats(equip_db, module_db)
    print(f"{d.name}: SA={stats['soft_attack']:.1f}, HA={stats['hard_attack']:.1f}, "
          f"Armor={stats['armor_value']:.1f}, IC={stats['build_cost_ic']:.1f}")

# Inject designs into equipment DB for use in division templates
inject_tank_designs(equip_db, module_db=module_db)

# Use in a division
from bice_models import BICEDatabase, Division
db = BICEDatabase(equip_db=equip_db, bat_db=bat_db)
div = (Division("1. Panzer-Division 1942", db)
    .add_battalion(db.battalion("trm_medium_armor").equip("tank_design_pzkpfw_iv_f2"), 4)
    .add_battalion(db.battalion("infantry").equip_auto(1939), 6)
    .add_support(db.battalion("DIV_HQ").equip("infantry_uniforms_2")))
stats = div.compute(get_preset("ww1_full"))
```

### OOP interface

```python
from bice_models import BICEDatabase, Division

db = BICEDatabase()

# Inspect battalion types and their equipment slots
inf = db.battalion("infantry")
print(inf.slots)       # {'infantry_equipment': 125, 'infantry_uniforms': 125}
print(inf.categories)  # ['category_army', 'category_all_infantry', ...]

# Auto-equip by year
equipped = inf.equip_auto(year=1939)
print(equipped.unequipped_slots)  # [] — all slots filled

# Build divisions with method chaining
div = (Division("GER Infanterie-Division 1940", db)
    .add_battalion(db.battalion("infantry").equip_auto(1939), 9)
    .add_battalion(db.battalion("artillery_brigade").equip_auto(1939), 4)
    .add_support(db.battalion("DIV_HQ").equip("infantry_uniforms_2"))
    .add_support(db.battalion("engineer").equip_auto(1939)))

stats = div.compute(get_preset("ww1_full"))
```

## German tank designs

| Name | Class | SA | HA | AP | Armor | Hardness | Speed | IC |
|---|---|---|---|---|---|---|---|---|
| PzKpfw I A | Light | 4.2 | 1.2 | 3.0 | 11.8 | 66% | 8.7 | 10.8 |
| PzKpfw I B | Light | 4.2 | 1.2 | 3.0 | 11.8 | 66% | 9.8 | 11.3 |
| PzKpfw II A | Light | 6.3 | 3.3 | 14.1 | 13.6 | 69% | 10.5 | 15.6 |
| PzKpfw III E | Medium | 7.4 | 5.7 | 19.6 | 20.0 | 72% | 11.9 | 22.3 |
| PzKpfw III J | Medium | 8.9 | 10.9 | 32.6 | 29.0 | 76% | 11.1 | 25.6 |
| PzKpfw IV D | Medium | 9.7 | 5.7 | 16.6 | 20.0 | 72% | 11.5 | 24.7 |
| PzKpfw IV F2 | Medium | 11.6 | 14.4 | 40.6 | 29.0 | 76% | 10.7 | 28.2 |
| PzKpfw IV H | Medium | 11.8 | 15.1 | 42.6 | 40.8 | 80% | 10.0 | 30.2 |
| Panther D | Med. Advanced | 13.9 | 23.0 | 121.8 | 41.7 | 82% | 13.3 | 39.4 |
| Panther G | Med. Advanced | 13.9 | 23.0 | 121.8 | 41.7 | 82% | 13.3 | 39.8 |
| StuG III G | Medium (AG) | 10.6 | 13.8 | 40.6 | 40.8 | 80% | 10.0 | 26.7 |
| Neubaufahrzeug | Heavy | 10.4 | 7.1 | 36.1 | 14.9 | 70% | 10.9 | 25.4 |
| Tiger I | Heavy | 16.0 | 19.3 | 47.8 | 47.9 | 81% | 12.5 | 44.4 |
| Tiger II | Heavy | 17.6 | 29.9 | 148.9 | 65.2 | 86% | 11.4 | 51.3 |

### German division templates

```python
from bice_german_templates import build_german_templates, list_template_names
from bice_doctrines import get_preset

db = BICEDatabase()
divs = build_german_templates(db)                   # 22 divisions, default years
divs_42 = build_german_templates(db, year=1942)     # override equipment year

for d in divs:
    stats = d.compute(get_preset("ww1_full"))
    print(f"{d.name}: SA={stats['Soft Attack']:.1f}, Def={stats['Defense']:.1f}")
```

### Division analysis

```python
from bice_analysis import compare_divisions, analyze_equipment_value, print_full_report

reports = compare_divisions(divs, get_preset("ww1_full"))
for r in reports[:5]:
    print(f"{r.name}: SA/W={r.sa_per_width:.2f}, score={r.overall_score:.1f}")

upgrades = analyze_equipment_value(db, max_year=1942)
for u in upgrades[:5]:
    print(f"{u.from_id} -> {u.to_id}: value={u.value_score:.2f}")

# Full report to stdout
print_full_report(db, divs, modifiers=get_preset("ww1_full"))
```

## Reliability and HP mechanics

Key defines from BICE (affect equipment loss and combat performance):

| Define | Value | Effect |
|---|---|---|
| `EQUIPMENT_COMBAT_LOSS_FACTOR` | 0.60 | 60% of strength damage becomes equipment loss |
| `RELIABILTY_RECOVERY` | 0.30 | 30% of "destroyed" equipment recovered after battle |
| `ATTRITION_EQUIPMENT_LOSS_CHANCE` | 0.0016 | Base chance/tick of attrition equipment loss (divided by reliability) |
| `RELIABILITY_ORG_REGAIN` | -0.50 | Low reliability slows org regain up to 50% |
| `RELIABILITY_ORG_MOVING` | -1.00 | Low reliability doubles org loss while moving |
| `RELIABILITY_WEATHER` | 3.00 | Low reliability triples weather impact |
| `LAND_COMBAT_STR_DAMAGE_MODIFIER` | 0.10 | 10% global strength damage modifier |
| `LAND_COMBAT_ORG_DAMAGE_MODIFIER` | 0.05 | 5% global org damage modifier |

Net equipment loss per damage point: ~0.42 (0.60 x 0.70).
Reliability below 0.6 causes cascading problems (org drain + attrition).

## Project structure

```
bice_tools/
  bice_parser.py              # Clausewitz parser + DB builders
  bice_calc.py                # Stat calculator engine
  bice_models.py              # OOP interface (BICEDatabase, Division, etc.)
  bice_tanks.py               # TRM tank design system + German presets
  bice_doctrines.py           # Doctrine modifier presets
  bice_german_templates.py    # 16 German division templates from AI/historical data
  bice_analysis.py            # Division comparison + equipment upgrade analysis
  bice_viz.py                 # Excel visualization
  bice_stats_gen.py           # CLI entry point + sample templates
  app.py                      # Flask web frontend (5 pages + API)
  test_bice.py                # 123 unit + integration tests
  README.md                   # This file
```

## Requirements

- Python 3.10+
- `openpyxl` (for Excel output)
- BICE mod installed (Steam Workshop ID `1851181613`)

## Mod path

By default, the parser looks for the BICE mod at:
```
C:\Program Files (x86)\Steam\steamapps\workshop\content\394360\1851181613
```

To override, pass a custom path to the DB builders:
```python
from pathlib import Path
equip_db = build_equipment_db(equip_dir=Path("/custom/path/common/units/equipment"))
bat_db   = build_battalion_db(units_dir=Path("/custom/path/common/units"))
```
