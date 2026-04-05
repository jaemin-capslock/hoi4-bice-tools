#!/usr/bin/env python3
"""
app.py — Minimal Flask web frontend for BICE stat calculator.

Pages:
  /                    — Dashboard overview
  /equipment           — Equipment browser with search/filter
  /battalions          — Battalion reference (slots, categories, base stats)
  /tanks               — German tank designs with computed stats
  /division            — Division designer (add battalions, compute stats)

Run:  python app.py
"""

import io
import os
import re
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify, send_file
from PIL import Image

from bice_parser import build_equipment_db, build_battalion_db, LAND_EQUIP_FAMILIES
from bice_models import BICEDatabase, Division
from bice_tanks import (
    build_module_db, inject_tank_designs, GERMAN_TANK_DESIGNS,
)
from bice_doctrines import get_preset, list_presets
from bice_calc import calc_battalion, calc_division

app = Flask(__name__)

# ─────────────────────────────────────────────
#  LOCALIZATION
# ─────────────────────────────────────────────

_LOC_LINE_RE = re.compile(r'^\s*([A-Za-z0-9_]+):\d*\s+"(.*?)"\s*$')


def _build_loc_db(loc_dir: Path) -> dict[str, str]:
    """Parse all HOI4 localisation yml files into a key→display-name dict."""
    db: dict[str, str] = {}
    if not loc_dir.is_dir():
        return db
    for yml in sorted(loc_dir.glob("*.yml")):
        try:
            text = yml.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = _LOC_LINE_RE.match(line)
            if m:
                key, val = m.group(1), m.group(2)
                # Skip _desc, _short suffixed entries (we want base names)
                # but DO keep them if there's no base entry yet
                if key not in db:
                    db[key] = val
    return db


# ─────────────────────────────────────────────
#  GLOBAL STATE (loaded once at startup)
# ─────────────────────────────────────────────

_MOD_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\394360\1851181613")
_ICON_DIR = _MOD_ROOT / "gfx" / "interface" / "counters" / "divisions_large"
_TECH_DIR = _MOD_ROOT / "gfx" / "interface" / "technologies"

print("Loading databases...")
_equip_db = build_equipment_db()
_bat_db = build_battalion_db()
_module_db = build_module_db()
inject_tank_designs(_equip_db, module_db=_module_db)
_db = BICEDatabase(equip_db=_equip_db, bat_db=_bat_db)
_loc_db = _build_loc_db(_MOD_ROOT / "localisation" / "english")
print(f"  {len(_equip_db)} equipment, {len(_bat_db)} battalions, {len(_module_db)} modules, {len(_loc_db)} loc keys")


_ROMAN = {0: "0", 1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
           6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}
_TRAILING_NUM_RE = re.compile(r"^(.*?)[\s_](\d{1,2})$")


def _smart_title(text: str) -> str:
    """Title-case words, but preserve words that are already uppercase (acronyms)."""
    return " ".join(w if w.isupper() else w.capitalize() for w in text.split())


def _loc(key: str) -> str:
    """Return the localized display name for a key, or a title-cased fallback."""
    if key in _loc_db:
        return _loc_db[key]
    # Fallback: convert snake_case to Title Case, trailing tier digits → Roman
    name = key.replace("_", " ").strip()
    m = _TRAILING_NUM_RE.match(name)
    if m:
        base, num = m.group(1), int(m.group(2))
        # Only convert small numbers (tiers), not years like 1938
        if num <= 10:
            name = f"{base} {_ROMAN[num]}"
    return _smart_title(name)


# Register as Jinja filter so templates can use {{ key|loc }}
app.jinja_env.filters["loc"] = _loc


# ─────────────────────────────────────────────
#  ICON MAPPING & SERVING
# ─────────────────────────────────────────────

# Explicit mapping: battalion ID → icon filename (without _bice_icon.tga suffix)
# Support companies: prefix "support_unit_", line battalions: prefix "unit_"
_BAT_ICON_OVERRIDES = {
    # Support companies
    "DIV_HQ": "support_unit_DIV_HQ",
    "DIV_HQ_car": "support_unit_DIV_HQ_car",
    "DIV_HQ_mot": "support_unit_DIV_HQ_car",
    "DIV_HQ_mech": "support_unit_DIV_HQ_mech",
    "DIV_HQ_arm": "support_unit_DIV_HQ_arm",
    "DIV_HQ_airborne": "support_unit_DIV_HQ_airborne",
    "engineer": "support_unit_engineer",
    "engineer_mot": "support_unit_engineer_mot",
    "engineer_mech": "support_unit_engineer_mech",
    "engineer_arm": "support_unit_engineer_armored",
    "combat_engineer": "support_unit_combat_engineer",
    "combat_engineer_mot": "support_unit_combat_engineer_mot",
    "combat_engineer_mech": "support_unit_combat_engineer_mech",
    "combat_engineer_arm": "support_unit_combat_engineer_armored",
    "airborne_engineer": "support_unit_airborne_engineer",
    "signal_company": "support_unit_signal_company",
    "signal_company_mot": "support_unit_signal_company_mot",
    "recon": "support_unit_recon",
    "recon_cav": "support_unit_recon_cav",
    "recon_mot": "support_unit_recon_mot",
    "recon_ac": "support_unit_recon_ac",
    "recon_mech": "support_unit_recon_mech",
    "field_hospital": "support_unit_field_hospital",
    "field_hospital_cav": "support_unit_field_hospital_car",
    "logistics_company": "support_unit_logistics_company",
    "logistics_company_car": "support_unit_logistics_company_car",
    "logistics_company_mot": "support_unit_logistics_company_mot",
    "logistics_company_mech": "support_unit_logistics_company_mech",
    "maintenance_company": "support_unit_maintenance_company",
    "maintenance_company_arm": "support_unit_maintenance_company_armoured",
    "military_police": "support_unit_military_police",
    "anti_air": "support_unit_anti_air",
    "anti_air_car": "support_unit_anti_air_car",
    "anti_air_heavy": "support_unit_anti_air_hvy",
    "anti_air_heavy_mot": "support_unit_anti_air_hvy_mot",
    "anti_tank": "support_unit_at",
    "anti_tank_mot": "support_unit_at_mot",
    "anti_tank_heavy": "support_unit_at_hvy",
    "artillery_heavy": "support_unit_hvy_art",
    "artillery_heavy_mot": "support_unit_hvy_art_mot",
    "rail_artillery": "support_unit_rail_art",
    "rocket_artillery": "support_unit_rocket_art",
    "spotter_air": "support_unit_spotter_air",
    "arctic_support": "support_unit_arctic_support",
    "desert_support": "support_unit_desert_support",
    "jungle_support": "support_unit_jungle_support",
    "mountain_support": "support_unit_mount_support",
    "amphibious_support": "support_unit_amph_support",
    "paratrooper_support": "support_unit_para_support",
    # Line: artillery variants
    "artillery_brigade": "unit_art",
    "artillery_brigade_med": "unit_art_med",
    "artillery_brigade_mot": "unit_art_mot",
    "artillery_brigade_mot_med": "unit_art_med_mot",
    "artillery_brigade_mnt": "unit_art_mnt",
    "artillery_brigade_mnt_mot": "unit_art_mnt_mot",
    "airborne_artillery_brigade": "unit_art_airborne",
    "anti_tank_brigade": "unit_anti_tank",
    "anti_tank_brigade_med": "unit_anti_tank_med",
    "anti_tank_brigade_mot": "unit_anti_tank_mot",
    "anti_tank_brigade_mot_med": "unit_anti_tank_mot_med",
    "airborne_anti_tank_brigade": "unit_anti_tank_airborne",
    "rocket_artillery_brigade": "unit_rocket_art",
    "motorized_rocket_brigade": "unit_motorized_rocket_brigade",
    "artillery_division": "unit_artillery_division",
    # Line: infantry variants
    "infantry": "unit_infantry",
    "infantry_assault": "unit_infantry_assault",
    "light_infantry": "unit_light_infantry",
    "mountain": "unit_mountain",
    "marine": "unit_marine",
    "marine_assault": "unit_marine_assault",
    "paratrooper": "unit_paratroop",
    "militia": "unit_militia",
    "garrison": "unit_garrison",
    "conscripts": "unit_conscripts",
    "irregular": "unit_irregular",
    "partisan": "unit_partisan",
    "commando": "unit_commando",
    "gurkha": "unit_gurkha",
    "luftwaffe_infantry": "unit_luftwaffe_infantry",
    "nkvd": "unit_nkvd",
    # Line: mobile
    "cavalry": "unit_cavalry",
    "camelry": "unit_camelry",
    "armored_car": "unit_armored_car",
    "motorcycle_infantry": "unit_motorcycle_infantry",
    "motorized": "unit_motorized",
    "motorized_assault": "unit_motorized_assault",
    "semi_motorized": "unit_semi_motorized",
    "semi_motorized_assault": "unit_semi_motorized_assault",
    "mechanized": "unit_mechanized",
    "mechanized_assault": "unit_mechanized_assault",
    "amphibious_mechanized": "unit_amph_lvt",
    "amphibious_mechanized_assault": "unit_amph_lvt_assault",
    "american_amph_lv": "unit_amph_lvt",
    "american_amph_lv_assault": "unit_amph_lvt_assault",
    # Guards
    "guards_infantry": "unit_guards_infantry",
    "guards_infantry_assault": "unit_guards_infantry_assault",
    "guards_cavalry": "unit_guards_cavalry",
    "guards_motorized": "unit_guards_motorized_infantry",
    "guards_motorized_assault": "unit_guards_motorized_infantry_assault",
    "guards_mechanized": "unit_guards_mechanized_infantry",
    "guards_mechanized_assault": "unit_guards_mechanized_infantry_assault",
    "guards_paratrooper": "unit_guards_paratroop",
    "guards_artillery_brigade": "unit_guards_artillery_brigade",
    "guards_artillery_brigade_med": "unit_guards_artillery_brigade_med",
    "guards_artillery_brigade_mot": "unit_guards_artillery_brigade_mot",
    "guards_artillery_brigade_mot_med": "unit_guards_artillery_brigade_mot_med",
    "guards_rocket_artillery_brigade": "unit_guards_rocket_art",
    "guards_motorized_rocket_brigade": "unit_guards_motorized_rocket_brigade",
    # SS
    "ss_infantry": "unit_ss_infantry",
    "ss_infantry_assault": "unit_ss_infantry_assault",
    "ss_light_infantry": "unit_ss_light_infantry",
    "ss_cavalry": "unit_ss_cavalry",
    "ss_motorcycle_infantry": "unit_ss_motorcycle_infantry",
    "ss_semi_motorized": "unit_ss_semi_motorized",
    "ss_motorized": "unit_ss_motorized",
    "ss_motorized_assault": "unit_ss_motorized_assault",
    "ss_mechanized": "unit_ss_mechanized",
    "ss_mechanized_assault": "unit_ss_mechanized_assault",
    "ss_mountain": "unit_ss_mountain",
    "ss_paratrooper": "unit_ss_paratrooper",
    "ss_garrison": "unit_ss_garrison",
    "ss_anti_tank_brigade": "unit_ss_anti_tank",
    "ss_anti_tank_brigade_med": "unit_ss_anti_tank_med",
    "ss_anti_tank_brigade_mot": "unit_ss_anti_tank_mot",
    "ss_anti_tank_brigade_mot_med": "unit_ss_anti_tank_mot_med",
    "ss_artillery_brigade": "unit_ss_art",
    "ss_artillery_brigade_med": "unit_ss_medart",
    "ss_artillery_brigade_mot": "unit_ss_art_mot",
    "ss_artillery_brigade_mot_med": "unit_ss_medart_mot",
    "ss_artillery_brigade_mnt": "unit_ss_art_mnt",
    "ss_artillery_brigade_mnt_mot": "unit_ss_art_mnt_mot",
    "ss_airborne_artillery_brigade": "unit_ss_art_airborne",
    "ss_rocket_artillery_brigade": "unit_ss_rocket_art",
    "ss_motorized_rocket_brigade": "unit_ss_rocket_art_mot",
}

# TRM tank mapping: battalion ID → icon in trm/ subfolder
_TRM_ICON_MAP = {
    "trm_light_armor": "unit_light_tank",
    "trm_light_cs_armor": "unit_light_tank_cs",
    "trm_medium_armor": "unit_medium_tank",
    "trm_medium_cs_armor": "unit_medium_tank_cs",
    "trm_medium_advanced_armor": "unit_medium_tank",
    "trm_medium_advanced_cs_armor": "unit_medium_tank_cs",
    "trm_medium_assault_gun_armor": "unit_medium_tank_assault_gun",
    "trm_medium_at_armor": "unit_medium_tank_at",
    "trm_medium_antiair_armor": "unit_medium_tank_antiair",
    "trm_heavy_armor": "unit_heavy_tank",
    "trm_heavy_cs_armor": "unit_heavy_tank_cs",
    "trm_heavy_assault_gun_armor": "unit_heavy_tank_assault_gun",
    "trm_heavy_at_armor": "unit_heavy_tank_at",
    "trm_superheavy_armor": "unit_superheavy_tank",
    "trm_superheavy_cs_armor": "unit_superheavy_tank_cs",
    "trm_cavalry_armor": "unit_cavalry_tank",
    "trm_cavalry_cs_armor": "unit_cavalry_tank_cs",
    "trm_infantry_armor": "unit_infantry_tank",
    "trm_infantry_cs_armor": "unit_infantry_tank_cs",
    "trm_amphibious_armor": "unit_light_tank_amph",
    "trm_amphibious_cs_armor": "unit_light_tank_amph",
    # Guards
    "trm_guards_medium_advanced_armor": "unit_medium_tank",
    "trm_guards_medium_advanced_cs_armor": "unit_medium_tank_cs",
    "trm_guards_heavy_armor": "unit_heavy_tank",
    "trm_guards_heavy_cs_armor": "unit_heavy_tank_cs",
    # SS
    "trm_ss_light_armor": "unit_light_tank",
    "trm_ss_light_cs_armor": "unit_light_tank_cs",
    "trm_ss_medium_armor": "unit_medium_tank",
    "trm_ss_medium_cs_armor": "unit_medium_tank_cs",
    "trm_ss_medium_advanced_armor": "unit_medium_tank",
    "trm_ss_medium_advanced_cs_armor": "unit_medium_tank_cs",
    "trm_ss_medium_assault_gun_armor": "unit_medium_tank_assault_gun",
    "trm_ss_heavy_armor": "unit_heavy_tank",
    "trm_ss_heavy_cs_armor": "unit_heavy_tank_cs",
}

_png_cache: dict[str, bytes] = {}


def _resolve_icon_path(bat_id: str) -> Path | None:
    """Return the filesystem path to the icon file for a battalion, or None."""
    # Check explicit override
    if bat_id in _BAT_ICON_OVERRIDES:
        p = _ICON_DIR / (_BAT_ICON_OVERRIDES[bat_id] + "_bice_icon.tga")
        if p.exists():
            return p
    # Check TRM tanks
    if bat_id in _TRM_ICON_MAP:
        p = _ICON_DIR / "trm" / (_TRM_ICON_MAP[bat_id] + "_bice_icon.tga")
        if p.exists():
            return p
    # Fallback: try direct match
    for prefix in ("unit_", "support_unit_"):
        p = _ICON_DIR / (prefix + bat_id + "_bice_icon.tga")
        if p.exists():
            return p
    return None


def _build_icon_map() -> dict[str, str]:
    """Build battalion_id → URL path mapping for all battalions with icons."""
    mapping = {}
    for bid in _bat_db:
        p = _resolve_icon_path(bid)
        if p:
            mapping[bid] = f"/icon/bat/{bid}"
    return mapping


def _convert_to_png(filepath: Path) -> bytes:
    """Convert a TGA or DDS file to PNG bytes, with caching."""
    key = str(filepath)
    if key in _png_cache:
        return _png_cache[key]
    img = Image.open(filepath)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    _png_cache[key] = data
    return data


# Pre-build the icon map at startup
_icon_map = _build_icon_map()
print(f"  {len(_icon_map)} battalion icons mapped")


# Pre-compute family -> max year for fast lookup
_family_max_year: dict[str, int] = {}
for _eid, _eq in _equip_db.items():
    if _eq.get("is_archetype") in (True, "yes", 1):
        continue
    _fam = _eq.get("family", "")
    _y = int(_eq.get("year", 0))
    if _fam and _y > _family_max_year.get(_fam, 0):
        _family_max_year[_fam] = _y


def _bat_latest_year(bat_id: str) -> int:
    """Return the latest year of available equipment for a battalion's slots."""
    bat = _bat_db.get(bat_id)
    if not bat:
        return 0
    max_year = 0
    for archetype in bat.get("need", {}):
        y = _family_max_year.get(archetype, 0)
        if y > max_year:
            max_year = y
    return max_year


# ─────────────────────────────────────────────
#  BASE TEMPLATE
# ─────────────────────────────────────────────

_BASE_HEADER = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — BICE Stats</title>
<style>
  :root { --bg: #1a1a2e; --surface: #16213e; --accent: #0f3460; --text: #e0e0e0;
          --muted: #888; --green: #4ecca3; --red: #e74c3c; --gold: #f1c40f; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg);
         color: var(--text); line-height: 1.5; }
  a { color: var(--green); text-decoration: none; }
  a:hover { text-decoration: underline; }

  nav { background: var(--surface); padding: 0.6rem 1.5rem; display: flex;
        gap: 1.5rem; align-items: center; border-bottom: 1px solid var(--accent); }
  nav .brand { font-weight: 700; font-size: 1.1rem; color: var(--gold); }
  nav a { color: var(--text); font-size: 0.9rem; }
  nav a:hover, nav a.active { color: var(--green); }

  .container { max-width: 1400px; margin: 0 auto; padding: 1.5rem; }
  h1 { font-size: 1.4rem; margin-bottom: 1rem; color: var(--gold); }
  h2 { font-size: 1.1rem; margin: 1.2rem 0 0.6rem; color: var(--green); }

  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { padding: 0.35rem 0.6rem; text-align: left; border-bottom: 1px solid #2a2a4a; }
  th { background: var(--accent); color: var(--green); position: sticky; top: 0; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr:hover { background: rgba(78,204,163,0.08); }

  .filters { display: flex; gap: 0.8rem; margin-bottom: 1rem; flex-wrap: wrap; }
  input, select, button { font-size: 0.85rem; padding: 0.4rem 0.7rem;
    background: var(--surface); color: var(--text); border: 1px solid var(--accent);
    border-radius: 4px; }
  button { cursor: pointer; background: var(--accent); }
  button:hover { background: var(--green); color: var(--bg); }
  button.primary { background: var(--green); color: var(--bg); font-weight: 600; }

  .stat-card { display: inline-block; background: var(--surface); border: 1px solid var(--accent);
    border-radius: 6px; padding: 0.8rem 1.2rem; margin: 0.3rem; min-width: 120px; }
  .stat-card .label { font-size: 0.75rem; color: var(--muted); }
  .stat-card .value { font-size: 1.3rem; font-weight: 700; }

  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  @media (max-width: 900px) { .grid-2 { grid-template-columns: 1fr; } }

  .tag { display: inline-block; background: var(--accent); padding: 0.15rem 0.5rem;
    border-radius: 3px; font-size: 0.75rem; margin: 0.1rem; }

  #div-results { margin-top: 1rem; }
  .empty { color: var(--muted); font-style: italic; }
</style>
</head>
<body>
<nav>
  <span class="brand">BICE Stats</span>
  <a href="/" {% if page == 'home' %}class="active"{% endif %}>Dashboard</a>
  <a href="/equipment" {% if page == 'equipment' %}class="active"{% endif %}>Equipment</a>
  <a href="/battalions" {% if page == 'battalions' %}class="active"{% endif %}>Battalions</a>
  <a href="/tanks" {% if page == 'tanks' %}class="active"{% endif %}>Tanks</a>
  <a href="/division" {% if page == 'division' %}class="active"{% endif %}>Division Designer</a>
</nav>
<div class="container">
"""

_BASE_FOOTER = """
</div>
</body>
</html>"""


def _page(content, **kwargs):
    """Render a page with the base layout wrapping the given content template."""
    return render_template_string(_BASE_HEADER + content + _BASE_FOOTER, **kwargs)


# ─────────────────────────────────────────────
#  ICON ROUTES
# ─────────────────────────────────────────────

@app.route("/icon/bat/<bat_id>")
def icon_bat(bat_id):
    """Serve a battalion icon as PNG."""
    p = _resolve_icon_path(bat_id)
    if not p:
        return "", 404
    data = _convert_to_png(p)
    return send_file(io.BytesIO(data), mimetype="image/png",
                     download_name=f"{bat_id}.png")


@app.route("/icon/tech/<path:filename>")
def icon_tech(filename):
    """Serve a tech/equipment icon as PNG."""
    for ext in (".dds", ".tga"):
        p = _TECH_DIR / (filename + ext)
        if p.exists():
            data = _convert_to_png(p)
            return send_file(io.BytesIO(data), mimetype="image/png",
                             download_name=f"{filename}.png")
    return "", 404


@app.route("/icon/tank/<path:icon_name>")
def icon_tank(icon_name):
    """Serve a tank counter icon as PNG."""
    p = _ICON_DIR / (icon_name + "_bice_icon.tga")
    if not p.exists():
        return "", 404
    data = _convert_to_png(p)
    return send_file(io.BytesIO(data), mimetype="image/png",
                     download_name=f"{icon_name}.png")


# ─────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────

@app.route("/")
def home():
    families = set()
    for eq in _equip_db.values():
        f = eq.get("family")
        if f:
            families.add(f)

    return _page("""
<h1>BICE Division Stats Calculator</h1>
<div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem;">
  <div class="stat-card"><div class="label">Equipment</div><div class="value">{{ n_equip }}</div></div>
  <div class="stat-card"><div class="label">Battalions</div><div class="value">{{ n_bat }}</div></div>
  <div class="stat-card"><div class="label">Tank Modules</div><div class="value">{{ n_mod }}</div></div>
  <div class="stat-card"><div class="label">Families</div><div class="value">{{ n_fam }}</div></div>
  <div class="stat-card"><div class="label">Tank Designs</div><div class="value">{{ n_tanks }}</div></div>
  <div class="stat-card"><div class="label">Doctrine Presets</div><div class="value">{{ n_doc }}</div></div>
</div>
<h2>Quick links</h2>
<ul>
  <li><a href="/equipment">Equipment browser</a> -- search and filter all {{ n_equip }} equipment entries</li>
  <li><a href="/battalions">Battalion reference</a> -- slots, categories, and base stats for all {{ n_bat }} battalion types</li>
  <li><a href="/tanks">German tank designs</a> -- {{ n_tanks }} historical designs with computed stats</li>
  <li><a href="/division">Division designer</a> -- build divisions and compute aggregate stats</li>
</ul>
""", title="Dashboard", page="home",
    n_equip=len(_equip_db), n_bat=len(_bat_db), n_mod=len(_module_db),
    n_fam=len(families), n_tanks=len(GERMAN_TANK_DESIGNS), n_doc=len(list_presets()))


# ─────────────────────────────────────────────
#  EQUIPMENT BROWSER
# ─────────────────────────────────────────────

@app.route("/equipment")
def equipment():
    q = request.args.get("q", "").lower()
    family_filter = request.args.get("family", "")

    items = []
    for eid, eq in sorted(_equip_db.items(), key=lambda x: (x[1].get("family",""), x[1].get("year",0))):
        if eq.get("is_archetype") in (True, "yes", 1):
            continue
        if q and q not in eid.lower() and q not in _loc(eid).lower() and q not in _loc(eq.get("family","")).lower():
            continue
        if family_filter and eq.get("family","") != family_filter:
            continue
        items.append(eq)

    families = sorted(set(eq.get("family","") for eq in _equip_db.values()
                          if eq.get("family") and eq.get("is_archetype") not in (True,"yes",1)))

    return _page("""
<h1>Equipment Browser</h1>
<div class="filters">
  <form style="display:flex; gap:0.5rem; flex-wrap:wrap;">
    <input name="q" placeholder="Search..." value="{{ q }}">
    <select name="family">
      <option value="">All families</option>
      {% for f in families %}<option value="{{ f }}" {% if f == family_filter %}selected{% endif %}>{{ f|loc }}</option>{% endfor %}
    </select>
    <button type="submit">Filter</button>
  </form>
  <span style="color:var(--muted); align-self:center;">{{ items|length }} results</span>
</div>
<div style="overflow-x: auto;">
<table>
<tr>
  <th>Name</th><th>Family</th><th>Year</th>
  <th>SA</th><th>HA</th><th>Def</th><th>BT</th><th>AP</th>
  <th>Armor</th><th>Hard%</th><th>Speed</th><th>IC</th><th>Rel%</th>
</tr>
{% for eq in items %}
<tr>
  <td>{{ eq.id|loc }}</td>
  <td>{{ eq.get('family','')|loc }}</td>
  <td class="num">{{ eq.get('year','') }}</td>
  <td class="num">{{ "%.1f"|format(eq.get('soft_attack',0)) }}</td>
  <td class="num">{{ "%.1f"|format(eq.get('hard_attack',0)) }}</td>
  <td class="num">{{ "%.1f"|format(eq.get('defense',0)) }}</td>
  <td class="num">{{ "%.1f"|format(eq.get('breakthrough',0)) }}</td>
  <td class="num">{{ "%.1f"|format(eq.get('ap_attack',0)) }}</td>
  <td class="num">{{ "%.1f"|format(eq.get('armor_value',0)) }}</td>
  <td class="num">{{ "%.0f"|format(eq.get('hardness',0)*100) }}%</td>
  <td class="num">{{ "%.1f"|format(eq.get('maximum_speed',0)) }}</td>
  <td class="num">{{ "%.1f"|format(eq.get('build_cost_ic',0)) }}</td>
  <td class="num">{{ "%.0f"|format(eq.get('reliability',0)*100) }}%</td>
</tr>
{% endfor %}
</table>
</div>
""", title="Equipment", page="equipment", items=items, q=q,
    family_filter=family_filter, families=families)


# ─────────────────────────────────────────────
#  BATTALION REFERENCE
# ─────────────────────────────────────────────

@app.route("/battalions")
def battalions():
    q = request.args.get("q", "").lower()
    group_filter = request.args.get("group", "")

    items = []
    for bid, bat in sorted(_bat_db.items()):
        if q and q not in bid.lower() and q not in _loc(bid).lower():
            continue
        if group_filter and bat.get("group","") != group_filter:
            continue
        items.append(bat)

    groups = sorted(set(b.get("group","") for b in _bat_db.values() if b.get("group")))

    return _page("""
<h1>Battalion Reference</h1>
<div class="filters">
  <form style="display:flex; gap:0.5rem; flex-wrap:wrap;">
    <input name="q" placeholder="Search..." value="{{ q }}">
    <select name="group">
      <option value="">All groups</option>
      {% for g in groups %}<option value="{{ g }}" {% if g == group_filter %}selected{% endif %}>{{ g }}</option>{% endfor %}
    </select>
    <button type="submit">Filter</button>
  </form>
  <span style="color:var(--muted); align-self:center;">{{ items|length }} results</span>
</div>
<div style="overflow-x: auto;">
<table>
<tr>
  <th></th><th>Name</th><th>Group</th><th>Role</th><th>Width</th><th>MP</th><th>Org</th><th>HP</th>
  <th>SA</th><th>HA</th><th>Def</th><th>BT</th><th>Supply</th><th>Train</th>
  <th>Equipment Slots</th>
</tr>
{% for b in items %}
<tr>
  <td>{% if b.id in icon_map %}<img src="{{ icon_map[b.id] }}" height="24" loading="lazy">{% endif %}</td>
  <td><a href="/battalion/{{ b.id }}">{{ b.id|loc }}</a></td>
  <td>{{ b.get('group','') }}</td>
  <td>{% if b.get('group') == 'support' %}<span class="tag" style="background:#8e44ad;">Support</span>{% else %}<span class="tag">Line</span>{% endif %}</td>
  <td class="num">{{ b.get('combat_width','') }}</td>
  <td class="num">{{ b.get('manpower','') }}</td>
  <td class="num">{{ b.get('max_organisation','') }}</td>
  <td class="num">{{ b.get('max_strength','') }}</td>
  <td class="num">{{ "%.1f"|format(b.get('soft_attack',0)) }}</td>
  <td class="num">{{ "%.1f"|format(b.get('hard_attack',0)) }}</td>
  <td class="num">{{ "%.1f"|format(b.get('defense',0)) }}</td>
  <td class="num">{{ "%.1f"|format(b.get('breakthrough',0)) }}</td>
  <td class="num">{{ "%.2f"|format(b.get('supply_consumption',0)) }}</td>
  <td class="num">{{ b.get('training_time','') }}</td>
  <td>{% for s, n in b.get('need',{}).items() %}<span class="tag">{{ s|loc }}:{{ n }}</span>{% endfor %}</td>
</tr>
{% endfor %}
</table>
</div>
""", title="Battalions", page="battalions", items=items, q=q,
    group_filter=group_filter, groups=groups, icon_map=_icon_map)


# ─────────────────────────────────────────────
#  BATTALION DETAIL
# ─────────────────────────────────────────────

@app.route("/battalion/<bat_id>")
def battalion_detail(bat_id):
    bat = _bat_db.get(bat_id)
    if not bat:
        return "Battalion not found", 404

    cats = bat.get("categories", [])
    if isinstance(cats, dict):
        cats = list(cats.keys())

    icon_url = _icon_map.get(bat_id)

    # Build slot data: for each archetype, find available equipment variants
    slot_data = []
    for archetype, qty in bat.get("need", {}).items():
        variants = []
        for eid, eq in _equip_db.items():
            if eq.get("is_archetype") in (True, "yes", 1):
                continue
            if eq.get("family", "") == archetype:
                variants.append({
                    "id": eid,
                    "name": _loc(eid),
                    "year": int(eq.get("year", 0)),
                })
        variants.sort(key=lambda v: v["year"])
        slot_data.append({
            "archetype": archetype,
            "name": _loc(archetype),
            "qty": qty,
            "variants": variants,
        })

    return _page("""
<style>
  .slot-card { background: var(--surface); border: 1px solid var(--accent); border-radius: 6px;
    padding: 0.6rem 0.8rem; margin-bottom: 0.6rem; }
  .slot-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; }
  .slot-header .slot-name { font-weight: 600; font-size: 0.9rem; }
  .slot-header .slot-qty { color: var(--muted); font-size: 0.8rem; }
  .tier-row { display: flex; gap: 0.3rem; flex-wrap: wrap; }
  .tier-btn { padding: 0.25rem 0.6rem; border: 1px solid var(--accent); border-radius: 4px;
    background: var(--bg); color: var(--text); cursor: pointer; font-size: 0.78rem;
    transition: all 0.15s; white-space: nowrap; }
  .tier-btn:hover { border-color: var(--green); background: rgba(78,204,163,0.1); }
  .tier-btn.active { background: var(--green); color: var(--bg); border-color: var(--green); font-weight: 600; }
  .tier-btn .tier-year { font-size: 0.7rem; color: var(--muted); margin-left: 0.2rem; }
  .tier-btn.active .tier-year { color: rgba(26,26,46,0.6); }
  .slot-card[draggable="true"] { cursor: grab; }
  .slot-card.drag-over { border-color: var(--green); background: rgba(78,204,163,0.08); }
</style>
<h1>{% if icon_url %}<img src="{{ icon_url }}" height="32" style="vertical-align:middle; margin-right:0.5rem;">{% endif %}{{ bat.id|loc }}</h1>
<p style="color:var(--muted); font-size:0.85rem;">{{ bat.id }}</p>
<div class="grid-2">
<div>
  <h2>Computed Stats</h2>
  <div id="bat-stats"><p class="empty">Loading...</p></div>
</div>
<div>
  <h2>Equipment Slots</h2>
  <div style="margin-bottom:0.5rem; display:flex; gap:0.5rem; align-items:center;">
    <select id="year-preset" style="width:80px;">
      <option value="1936">1936</option>
      <option value="1939" selected>1939</option>
      <option value="1940">1940</option>
      <option value="1941">1941</option>
      <option value="1942">1942</option>
      <option value="1943">1943</option>
      <option value="1944">1944</option>
    </select>
    <button id="auto-equip-btn">Auto-equip by year</button>
  </div>
  <div id="slot-container"></div>

  <h2>Categories</h2>
  <div>{% for c in cats %}<span class="tag">{{ c|loc }}</span>{% endfor %}</div>
</div>
</div>

<script>
const SLOT_DATA = {{ slot_data_json | safe }};
const BAT_ID = {{ bat_id_json | safe }};
// Track selected equipment per archetype
const selected = {};

function renderSlots() {
  const container = document.getElementById('slot-container');
  let html = '';
  for (const slot of SLOT_DATA) {
    const sel = selected[slot.archetype] || '';
    html += '<div class="slot-card" data-arch="' + slot.archetype + '">';
    html += '<div class="slot-header"><span class="slot-name">' + slot.name + '</span>';
    html += '<span class="slot-qty">&times;' + slot.qty + '</span></div>';
    html += '<div class="tier-row">';
    if (slot.variants.length) {
      for (const v of slot.variants) {
        const act = (v.id === sel) ? ' active' : '';
        html += '<button class="tier-btn' + act + '" data-arch="' + slot.archetype + '" data-eid="' + v.id + '">';
        html += v.name + '<span class="tier-year">' + v.year + '</span></button>';
      }
    } else {
      html += '<span class="empty" style="font-size:0.8rem;">No variants</span>';
    }
    html += '</div></div>';
  }
  container.innerHTML = html;
}

// Event delegation for tier button clicks
document.getElementById('slot-container').addEventListener('click', function(e) {
  const btn = e.target.closest('.tier-btn');
  if (!btn) return;
  const arch = btn.dataset.arch;
  const eid = btn.dataset.eid;
  selected[arch] = eid;
  // Update active states within this slot only
  const card = btn.closest('.slot-card');
  card.querySelectorAll('.tier-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  computeStats();
});

document.getElementById('auto-equip-btn').addEventListener('click', autoEquip);

function autoEquip() {
  const year = parseInt(document.getElementById('year-preset').value) || 1939;
  for (const slot of SLOT_DATA) {
    if (!slot.variants.length) continue;
    let best = slot.variants[0].id;
    for (const v of slot.variants) {
      if (v.year <= year) best = v.id;
    }
    selected[slot.archetype] = best;
  }
  renderSlots();
  computeStats();
}

async function computeStats() {
  const equip = {};
  for (const arch in selected) {
    if (selected[arch]) equip[arch] = selected[arch];
  }
  const res = await fetch('/api/compute_battalion', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({bat_id: BAT_ID, equip})
  });
  const data = await res.json();
  if (data.error) {
    document.getElementById('bat-stats').innerHTML = '<p style="color:var(--red);">' + data.error + '</p>';
    return;
  }
  const order = ['soft_attack','hard_attack','defense','breakthrough','ap_attack',
                 'air_attack','armor_value','hardness','maximum_speed','build_cost_ic',
                 'reliability','max_organisation','max_strength','manpower',
                 'combat_width','supply_consumption','training_time'];
  const labels = {
    soft_attack:'Soft Attack', hard_attack:'Hard Attack', defense:'Defense',
    breakthrough:'Breakthrough', ap_attack:'Armor Piercing', air_attack:'Air Attack',
    armor_value:'Armor', hardness:'Hardness', maximum_speed:'Speed',
    build_cost_ic:'IC Cost', reliability:'Reliability', max_organisation:'Organization',
    max_strength:'HP', manpower:'Manpower', combat_width:'Combat Width',
    supply_consumption:'Supply/day', training_time:'Training Time'
  };
  let html = '<div style="display:flex; flex-wrap:wrap; gap:0.3rem;">';
  for (const k of order) {
    if (data.stats[k] !== undefined && data.stats[k] !== 0) {
      let val = data.stats[k];
      if (k === 'hardness' || k === 'reliability') val = (val * 100).toFixed(0) + '%';
      else if (typeof val === 'number') val = val.toFixed(2);
      html += '<div class="stat-card"><div class="label">' + (labels[k]||k) + '</div><div class="value">' + val + '</div></div>';
    }
  }
  html += '</div>';
  document.getElementById('bat-stats').innerHTML = html;
}

// Initialize: auto-equip to 1939 on load
autoEquip();
</script>
""", title=_loc(bat_id), page="battalions", bat=bat, cats=cats, icon_url=icon_url,
    slot_data=slot_data,
    slot_data_json=__import__('json').dumps(slot_data),
    bat_id_json=__import__('json').dumps(bat_id))


# ─────────────────────────────────────────────
#  TANK DESIGNS
# ─────────────────────────────────────────────

_TANK_CLASS_ICON = {
    "light": "trm/unit_light_tank",
    "medium": "trm/unit_medium_tank",
    "medium_advanced": "trm/unit_medium_tank",
    "medium_assault_gun": "trm/unit_medium_tank_assault_gun",
    "heavy": "trm/unit_heavy_tank",
    "superheavy": "trm/unit_superheavy_tank",
    "cavalry": "trm/unit_cavalry_tank",
    "infantry": "trm/unit_infantry_tank",
}


@app.route("/tanks")
def tanks():
    designs = []
    for d in GERMAN_TANK_DESIGNS:
        s = d.compute_stats(_equip_db, _module_db)
        icon_name = _TANK_CLASS_ICON.get(d.tank_class, "")
        icon_url = ""
        if icon_name:
            p = _ICON_DIR / (icon_name + "_bice_icon.tga")
            if p.exists():
                icon_url = "/icon/tank/" + icon_name
        designs.append({
            "name": d.name, "tank_class": d.tank_class, "icon": icon_url,
            "year": getattr(d, "_year_override", "") or "",
            "sa": s.get("soft_attack", 0), "ha": s.get("hard_attack", 0),
            "defense": s.get("defense", 0), "bt": s.get("breakthrough", 0),
            "ap": s.get("ap_attack", 0), "armor": s.get("armor_value", 0),
            "hardness": s.get("hardness", 0), "speed": s.get("maximum_speed", 0),
            "ic": s.get("build_cost_ic", 0), "rel": s.get("reliability", 0),
        })

    return _page("""
<h1>German Tank Designs</h1>
<p style="color:var(--muted); margin-bottom:1rem;">
  Stats computed from chassis + {{ n_mod }} TRM modules.
</p>
<div style="overflow-x: auto;">
<table>
<tr>
  <th></th><th>Name</th><th>Class</th><th>Year</th>
  <th>SA</th><th>HA</th><th>Def</th><th>BT</th><th>AP</th>
  <th>Armor</th><th>Hard%</th><th>Speed</th><th>IC</th><th>Rel%</th>
</tr>
{% for d in designs %}
<tr>
  <td>{% if d.icon %}<img src="{{ d.icon }}" height="24" loading="lazy">{% endif %}</td>
  <td><strong>{{ d.name }}</strong></td>
  <td>{{ d.tank_class }}</td>
  <td class="num">{{ d.year }}</td>
  <td class="num">{{ "%.1f"|format(d.sa) }}</td>
  <td class="num">{{ "%.1f"|format(d.ha) }}</td>
  <td class="num">{{ "%.1f"|format(d.defense) }}</td>
  <td class="num">{{ "%.1f"|format(d.bt) }}</td>
  <td class="num">{{ "%.1f"|format(d.ap) }}</td>
  <td class="num">{{ "%.1f"|format(d.armor) }}</td>
  <td class="num">{{ "%.0f"|format(d.hardness * 100) }}%</td>
  <td class="num">{{ "%.1f"|format(d.speed) }}</td>
  <td class="num">{{ "%.1f"|format(d.ic) }}</td>
  <td class="num">{{ "%.0f"|format(d.rel * 100) }}%</td>
</tr>
{% endfor %}
</table>
</div>
""", title="Tanks", page="tanks", designs=designs, n_mod=len(_module_db))


# ─────────────────────────────────────────────
#  DIVISION DESIGNER
# ─────────────────────────────────────────────

@app.route("/division")
def division_page():
    presets = list_presets()

    # Build structured battalion data for JS: [{id, group, icon, maxYear, isSupport}, ...]
    bat_data = []
    for bid in sorted(_bat_db.keys()):
        bat = _bat_db[bid]
        group = bat.get("group", "")
        is_support = (group == "support")
        icon = _icon_map.get(bid, "")
        max_year = _bat_latest_year(bid)
        bat_data.append({
            "id": bid, "name": _loc(bid), "group": group, "icon": icon,
            "maxYear": max_year, "isSupport": is_support,
            "width": bat.get("combat_width", 0),
        })

    groups = sorted(set(b["group"] for b in bat_data if b["group"]))

    return _page("""
<h1>Division Designer</h1>
<style>
  .bat-picker { max-height: 320px; overflow-y: auto; border: 1px solid var(--accent);
    border-radius: 4px; background: var(--surface); }
  .bat-picker .bat-row { display: flex; align-items: center; gap: 0.5rem;
    padding: 0.25rem 0.5rem; cursor: pointer; font-size: 0.82rem; }
  .bat-picker .bat-row:hover { background: rgba(78,204,163,0.12); }
  .bat-picker .bat-row.selected { background: rgba(78,204,163,0.2); }
  .bat-picker .bat-row img { height: 20px; flex-shrink: 0; }
  .bat-picker .bat-row .bid { flex: 1; }
  .bat-picker .bat-row .meta { color: var(--muted); font-size: 0.75rem; }
  .bat-picker .group-hdr { padding: 0.3rem 0.5rem; font-size: 0.75rem; font-weight: 700;
    color: var(--gold); background: rgba(15,52,96,0.5); position: sticky; top: 0; }
  .div-list-icon { height: 20px; vertical-align: middle; margin-right: 0.3rem; }
</style>

<div class="grid-2">
<div>
  <h2>Battalion Picker</h2>
  <div class="filters" style="margin-bottom:0.5rem;">
    <input id="bat-search" placeholder="Search battalions..." oninput="filterBats()" style="flex:1;">
    <select id="group-filter" onchange="filterBats()">
      <option value="">All groups</option>
      {% for g in groups %}<option value="{{ g }}">{{ g }}</option>{% endfor %}
    </select>
    <select id="year-filter" onchange="filterBats()">
      <option value="">Any year</option>
      <option value="1936">1936+</option>
      <option value="1939" selected>1939+</option>
      <option value="1940">1940+</option>
      <option value="1941">1941+</option>
      <option value="1942">1942+</option>
      <option value="1943">1943+</option>
      <option value="1944">1944+</option>
    </select>
  </div>
  <div class="bat-picker" id="bat-picker"></div>
  <div style="margin-top:0.5rem; display:flex; gap:0.5rem; align-items:center; flex-wrap:wrap;">
    <label style="font-size:0.82rem;">Count:</label>
    <input id="bat-count" type="number" value="1" min="1" max="20" style="width:50px;">
    <label style="font-size:0.82rem;">Equip year:</label>
    <input id="bat-year" type="number" value="1939" min="1918" max="1948" style="width:60px;">
    <button onclick="addSelected(false)">+ Line</button>
    <button onclick="addSelected(true)">+ Support</button>
  </div>

  <h2 style="margin-top:0.8rem;">Division</h2>
  <div id="bat-list"></div>

  <h2 style="margin-top:0.8rem;">Doctrine</h2>
  <select id="doctrine-select">
    {% for p in presets %}<option value="{{ p }}" {% if p == 'ww1_full' %}selected{% endif %}>{{ p }}</option>{% endfor %}
  </select>
  <div style="margin-top:0.8rem;">
    <button class="primary" onclick="compute()">Compute Division Stats</button>
  </div>
</div>
<div>
  <h2>Division Stats</h2>
  <div id="div-results"><p class="empty">Add battalions and click Compute.</p></div>
</div>
</div>

<script>
const BAT_DATA = {{ bat_data_json | safe }};
let selectedBat = null;
let battalions = [];

function filterBats() {
  const q = document.getElementById('bat-search').value.toLowerCase();
  const gf = document.getElementById('group-filter').value;
  const yf = parseInt(document.getElementById('year-filter').value) || 0;

  let filtered = BAT_DATA.filter(b => {
    if (q && !b.id.toLowerCase().includes(q) && !b.name.toLowerCase().includes(q) && !b.group.toLowerCase().includes(q)) return false;
    if (gf && b.group !== gf) return false;
    if (yf && b.maxYear > 0 && b.maxYear < yf) return false;
    return true;
  });

  // Group by group
  const grouped = {};
  filtered.forEach(b => {
    const g = b.group || 'other';
    if (!grouped[g]) grouped[g] = [];
    grouped[g].push(b);
  });

  const picker = document.getElementById('bat-picker');
  let html = '';
  const sortedGroups = Object.keys(grouped).sort();
  for (const g of sortedGroups) {
    html += '<div class="group-hdr">' + g + ' (' + grouped[g].length + ')</div>';
    for (const b of grouped[g]) {
      const sel = (selectedBat === b.id) ? ' selected' : '';
      const icon = b.icon ? '<img src="' + b.icon + '" loading="lazy">' : '';
      const yr = b.maxYear ? 'up to ' + b.maxYear : '';
      const w = b.width ? 'W:' + b.width : '';
      const sup = b.isSupport ? '<span class="tag" style="background:#8e44ad;font-size:0.65rem;">SUP</span>' : '';
      html += '<div class="bat-row' + sel + '" data-bid="' + b.id + '" data-sup="' + (b.isSupport?1:0) + '">' +
              icon + '<span class="bid">' + b.name + '</span>' + sup +
              '<span class="meta">' + [w, yr].filter(Boolean).join(' | ') + '</span></div>';
    }
  }
  if (!filtered.length) html = '<div style="padding:1rem;" class="empty">No matches</div>';
  picker.innerHTML = html;
}

// Event delegation for picker clicks
document.getElementById('bat-picker').addEventListener('click', function(e) {
  const row = e.target.closest('.bat-row');
  if (!row) return;
  selectBat(row.dataset.bid);
});
document.getElementById('bat-picker').addEventListener('dblclick', function(e) {
  const row = e.target.closest('.bat-row');
  if (!row) return;
  selectedBat = row.dataset.bid;
  addSelected(row.dataset.sup === '1');
});

function selectBat(id) {
  selectedBat = id;
  document.querySelectorAll('.bat-row').forEach(r => r.classList.remove('selected'));
  const el = document.querySelector('.bat-row[data-bid="' + id + '"]');
  if (el) el.classList.add('selected');
}

function addSelected(isSupport) {
  if (!selectedBat) return;
  const count = isSupport ? 1 : (parseInt(document.getElementById('bat-count').value) || 1);
  const year = parseInt(document.getElementById('bat-year').value) || 1939;
  const bat = BAT_DATA.find(b => b.id === selectedBat);
  const icon = bat ? bat.icon : '';
  const name = bat ? bat.name : selectedBat;
  battalions.push({type: selectedBat, name, count, year, support: isSupport, icon});
  renderList();
}

function removeBat(idx) {
  battalions.splice(idx, 1);
  renderList();
}

function renderList() {
  const el = document.getElementById('bat-list');
  if (!battalions.length) { el.innerHTML = '<p class="empty">No units added yet. Select a battalion above and click + Line or + Support.</p>'; return; }
  let html = '<table><tr><th></th><th>Type</th><th>#</th><th>Year</th><th>Role</th><th></th></tr>';
  battalions.forEach((b, i) => {
    const icon = b.icon ? '<img src="' + b.icon + '" class="div-list-icon" loading="lazy">' : '';
    html += '<tr><td>' + icon + '</td><td>' + b.name + '</td><td class="num">' + b.count +
            '</td><td class="num">' + b.year +
            '</td><td>' + (b.support ? '<span class="tag" style="background:#8e44ad;">Support</span>' : 'Line') +
            '</td><td><button onclick="removeBat(' + i + ')">x</button></td></tr>';
  });
  html += '</table>';
  el.innerHTML = html;
}

async function compute() {
  const doctrine = document.getElementById('doctrine-select').value;
  const res = await fetch('/api/compute_division', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({battalions, doctrine})
  });
  const data = await res.json();
  if (data.error) {
    document.getElementById('div-results').innerHTML = '<p style="color:var(--red);">' + data.error + '</p>';
    return;
  }
  let html = '<div style="display:flex; flex-wrap:wrap; gap:0.3rem;">';
  const order = ['Width','Manpower','HP','Org','Soft Attack','Hard Attack','Defense',
                 'Breakthrough','Air Attack','Hardness','Speed (km/h)',
                 'Suppression','Collateral','IC Cost','Supply/day','Training (days)'];
  for (const k of order) {
    if (data.stats[k] !== undefined) {
      html += '<div class="stat-card"><div class="label">' + k + '</div><div class="value">' +
              (typeof data.stats[k] === 'number' ? data.stats[k].toFixed(2) : data.stats[k]) +
              '</div></div>';
    }
  }
  html += '</div>';
  if (data.warnings && data.warnings.length) {
    html += '<h2>Warnings</h2><ul>';
    data.warnings.forEach(w => html += '<li style="color:var(--gold);">' + w + '</li>');
    html += '</ul>';
  }
  document.getElementById('div-results').innerHTML = html;
}

filterBats();
renderList();
</script>
""", title="Division Designer", page="division",
    presets=presets, groups=groups,
    bat_data_json=__import__('json').dumps(bat_data))


# ─────────────────────────────────────────────
#  API: COMPUTE DIVISION
# ─────────────────────────────────────────────

@app.route("/api/compute_division", methods=["POST"])
def api_compute_division():
    data = request.get_json()
    if not data or not data.get("battalions"):
        return jsonify({"error": "No battalions specified"})

    warnings = []
    template_bats = []
    template_sups = []

    for entry in data["battalions"]:
        bat_type = entry["type"]
        count = entry.get("count", 1)
        year = entry.get("year", 1939)
        is_support = entry.get("support", False)

        if bat_type not in _bat_db:
            warnings.append(f"Unknown battalion: {bat_type}")
            continue

        # Auto-equip by year
        try:
            bt = _db.battalion(bat_type)
            equipped = bt.equip_auto(year)
            equip_dict = dict(equipped.assignment)
            missing = equipped.unequipped_slots
            if missing:
                warnings.append(f"{bat_type}: missing equipment for {', '.join(missing)}")
        except Exception as e:
            warnings.append(f"{bat_type}: {e}")
            equip_dict = {}

        unit = {"type": bat_type, "count": count, "equip": equip_dict}
        if is_support:
            template_sups.append(unit)
        else:
            template_bats.append(unit)

    template = {
        "name": "Web Designer Division",
        "battalions": template_bats,
        "support": template_sups,
    }

    doctrine_name = data.get("doctrine", "none")
    try:
        modifiers = get_preset(doctrine_name)
    except KeyError:
        modifiers = None

    try:
        stats = calc_division(template, _bat_db, _equip_db, modifiers=modifiers)
    except Exception as e:
        return jsonify({"error": str(e)})

    return jsonify({"stats": stats, "warnings": warnings})


# ─────────────────────────────────────────────
#  API: COMPUTE BATTALION
# ─────────────────────────────────────────────

@app.route("/api/compute_battalion", methods=["POST"])
def api_compute_battalion():
    data = request.get_json()
    if not data or not data.get("bat_id"):
        return jsonify({"error": "No battalion specified"})

    bat_id = data["bat_id"]
    if bat_id not in _bat_db:
        return jsonify({"error": f"Unknown battalion: {bat_id}"})

    equip_map = data.get("equip", {})
    equip_list = list(equip_map.values())

    try:
        stats = calc_battalion(bat_id, equip_list, _bat_db, _equip_db)
    except Exception as e:
        return jsonify({"error": str(e)})

    return jsonify({"stats": stats})


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStarting BICE Stats web server...")
    print("Open http://127.0.0.1:5000 in your browser\n")
    app.run(debug=False, port=5000)
