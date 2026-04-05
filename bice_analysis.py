#!/usr/bin/env python3
"""
bice_analysis.py — Division and equipment analysis for BICE.

Computes efficiency metrics, compares divisions, and identifies
optimal equipment research/production priorities.

Public API
----------
analyze_division(div, doctrine)     → DivisionReport
compare_divisions(divs, doctrine)   → ComparisonTable
analyze_equipment_value(db, year)   → list[EquipUpgrade]
print_report(divisions, doctrine)   → prints formatted analysis

Key HOI4 Mechanics (BICE defines)
---------------------------------
EQUIPMENT_COMBAT_LOSS_FACTOR = 0.60
    60% of strength damage → equipment loss. Higher reliability reduces this.

RELIABILTY_RECOVERY = 0.3
    30% of "destroyed" equipment is recovered after battle.

ATTRITION_EQUIPMENT_LOSS_CHANCE = 0.0016
    Base chance per tick of losing equipment to attrition.
    Divided by equipment reliability.

RELIABILITY_ORG_REGAIN = -0.5
    Low reliability → up to 50% slower org regain.

RELIABILITY_ORG_MOVING = -1.0
    Low reliability → up to 100% more org loss while moving.

So reliability is a critical hidden multiplier that affects:
  - Equipment casualties in combat (more losses with low reliability)
  - Equipment attrition on march (higher chance with low reliability)
  - Organization recovery speed (slower with low reliability)
  - Organization drain while moving (faster with low reliability)

HP / Strength relationship:
  - max_strength = HP of the battalion (equipment hitpoints)
  - When strength is damaged, equipment is lost proportionally
  - Higher HP does NOT reduce equipment loss per hit — it means you
    have more equipment to lose but can absorb more total damage
  - Equipment loss = strength_damage × EQUIPMENT_COMBAT_LOSS_FACTOR (0.60)
  - Of that, RELIABILTY_RECOVERY (0.30) is recovered after battle
  - Net equipment loss per damage point ≈ 0.60 × 0.70 = 0.42
"""

from __future__ import annotations
from dataclasses import dataclass, field
from bice_models import BICEDatabase, Division


# ─────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────

@dataclass
class DivisionReport:
    """Analysis report for a single division."""
    name: str
    stats: dict
    width: float = 0.0
    manpower: int = 0
    ic_cost: float = 0.0

    # Efficiency metrics (per combat width)
    sa_per_width: float = 0.0
    ha_per_width: float = 0.0
    def_per_width: float = 0.0
    bt_per_width: float = 0.0
    org_per_width: float = 0.0

    # Cost efficiency (per IC)
    sa_per_ic: float = 0.0
    ha_per_ic: float = 0.0
    def_per_ic: float = 0.0

    # Manpower efficiency
    sa_per_mp: float = 0.0
    def_per_mp: float = 0.0

    # Composite scores
    offensive_score: float = 0.0  # SA + HA weighted
    defensive_score: float = 0.0  # Def + Org weighted
    overall_score: float = 0.0    # Balanced


@dataclass
class EquipUpgrade:
    """Value assessment for upgrading equipment."""
    family: str
    from_id: str
    to_id: str
    from_year: int
    to_year: int
    stat_deltas: dict[str, float] = field(default_factory=dict)
    ic_delta: float = 0.0
    value_score: float = 0.0  # higher = more valuable upgrade


# ─────────────────────────────────────────────
#  DIVISION ANALYSIS
# ─────────────────────────────────────────────

def analyze_division(div: Division, modifiers: dict | None = None) -> DivisionReport:
    """Compute a full analysis report for a division."""
    stats = div.compute(modifiers)

    width = stats.get("Width", 0)
    mp = stats.get("Manpower", 0)
    ic = stats.get("IC Cost", 0)
    sa = stats.get("Soft Attack", 0)
    ha = stats.get("Hard Attack", 0)
    defense = stats.get("Defense", 0)
    bt = stats.get("Breakthrough", 0)
    org = stats.get("Org", 0)

    report = DivisionReport(
        name=div.name,
        stats=stats,
        width=width,
        manpower=mp,
        ic_cost=ic,
    )

    # Per-width efficiency
    if width > 0:
        report.sa_per_width = sa / width
        report.ha_per_width = ha / width
        report.def_per_width = defense / width
        report.bt_per_width = bt / width
        report.org_per_width = org / width

    # Per-IC efficiency
    if ic > 0:
        report.sa_per_ic = sa / ic
        report.ha_per_ic = ha / ic
        report.def_per_ic = defense / ic

    # Per-manpower efficiency
    if mp > 0:
        report.sa_per_mp = sa / mp * 1000  # per 1000 manpower
        report.def_per_mp = defense / mp * 1000

    # Composite scores
    # Offensive: SA matters most vs soft targets, HA vs hard
    # Weight SA more since most targets are soft in HOI4
    report.offensive_score = sa * 0.7 + ha * 0.3
    # Defensive: defense when defending, org keeps you in the fight
    report.defensive_score = defense * 0.6 + org * 0.4
    # Overall: balanced mix
    report.overall_score = (
        report.offensive_score * 0.4
        + report.defensive_score * 0.4
        + bt * 0.2
    )

    return report


def compare_divisions(
    divisions: list[Division],
    modifiers: dict | None = None,
) -> list[DivisionReport]:
    """Analyze and rank multiple divisions."""
    reports = [analyze_division(d, modifiers) for d in divisions]
    return sorted(reports, key=lambda r: r.overall_score, reverse=True)


# ─────────────────────────────────────────────
#  EQUIPMENT VALUE ANALYSIS
# ─────────────────────────────────────────────

_VALUE_STATS = {
    "soft_attack": 3.0,
    "hard_attack": 2.0,
    "defense": 2.5,
    "breakthrough": 2.0,
    "ap_attack": 1.0,
    "armor_value": 1.5,
    "air_attack": 1.0,
    "reliability": 5.0,     # reliability is very impactful
    "maximum_speed": 0.5,
}


def analyze_equipment_value(
    db: BICEDatabase,
    max_year: int = 1945,
) -> list[EquipUpgrade]:
    """Find the most valuable equipment upgrades across all families.

    Compares consecutive tiers within each equipment family and scores
    the stat improvements relative to IC cost increase.
    """
    upgrades: list[EquipUpgrade] = []

    for family in db.list_equipment_families():
        variants = db.find_equipment(family, max_year=max_year)
        if len(variants) < 2:
            continue

        for i in range(len(variants) - 1):
            old = variants[i]
            new = variants[i + 1]

            deltas: dict[str, float] = {}
            value = 0.0

            for stat, weight in _VALUE_STATS.items():
                old_val = float(old.get(stat, 0))
                new_val = float(new.get(stat, 0))
                delta = new_val - old_val
                if abs(delta) > 0.001:
                    deltas[stat] = round(delta, 3)
                    # Normalize by old value for % improvement
                    if old_val > 0:
                        pct_change = delta / old_val
                    else:
                        pct_change = delta  # absolute if base was 0
                    value += pct_change * weight

            old_ic = float(old.get("build_cost_ic", 0))
            new_ic = float(new.get("build_cost_ic", 0))
            ic_delta = new_ic - old_ic

            # Penalize upgrades that cost much more IC
            if old_ic > 0 and ic_delta > 0:
                ic_penalty = (ic_delta / old_ic) * 0.5
                value -= ic_penalty

            upgrades.append(EquipUpgrade(
                family=family,
                from_id=old.get("id", "?"),
                to_id=new.get("id", "?"),
                from_year=int(old.get("year", 0)),
                to_year=int(new.get("year", 0)),
                stat_deltas=deltas,
                ic_delta=round(ic_delta, 2),
                value_score=round(value, 3),
            ))

    return sorted(upgrades, key=lambda u: u.value_score, reverse=True)


# ─────────────────────────────────────────────
#  REPORTING
# ─────────────────────────────────────────────

def format_division_table(reports: list[DivisionReport]) -> str:
    """Format a comparison table as a string."""
    lines = []
    header = (
        f"{'Division':<42} {'Width':>5} {'SA':>7} {'HA':>7} "
        f"{'Def':>6} {'BT':>6} {'Org':>5} {'IC':>7} "
        f"{'SA/W':>5} {'Def/W':>5} {'Score':>6}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for r in reports:
        lines.append(
            f"{r.name:<42} {r.width:>5.1f} {r.stats.get('Soft Attack', 0):>7.1f} "
            f"{r.stats.get('Hard Attack', 0):>7.1f} {r.stats.get('Defense', 0):>6.1f} "
            f"{r.stats.get('Breakthrough', 0):>6.1f} {r.stats.get('Org', 0):>5.1f} "
            f"{r.ic_cost:>7.1f} {r.sa_per_width:>5.2f} {r.def_per_width:>5.2f} "
            f"{r.overall_score:>6.1f}"
        )

    return "\n".join(lines)


def format_equipment_table(upgrades: list[EquipUpgrade], top_n: int = 20) -> str:
    """Format top equipment upgrades as a string."""
    lines = []
    header = (
        f"{'From':<30} {'->':>2} {'To':<30} {'Year':>4}->{'Year':>4} "
        f"{'IC +/-':>6} {'Value':>6}  Key Changes"
    )
    lines.append(header)
    lines.append("-" * 120)

    for u in upgrades[:top_n]:
        changes = ", ".join(
            f"{s}: {d:+.2f}" for s, d in sorted(u.stat_deltas.items())
            if abs(d) > 0.01
        )
        lines.append(
            f"{u.from_id:<30} -> {u.to_id:<30} {u.from_year:>4}->{u.to_year:>4} "
            f"{u.ic_delta:>+6.1f} {u.value_score:>6.2f}  {changes}"
        )

    return "\n".join(lines)


def print_full_report(
    db: BICEDatabase,
    divisions: list[Division],
    modifiers: dict | None = None,
    equipment_year: int = 1945,
):
    """Print a comprehensive analysis to stdout."""
    print("=" * 120)
    print("  BICE DIVISION ANALYSIS REPORT")
    print("=" * 120)

    # Division comparison
    print("\n--- DIVISION COMPARISON (sorted by overall score) ---\n")
    reports = compare_divisions(divisions, modifiers)
    print(format_division_table(reports))

    # Best offensive divisions
    print("\n--- TOP 5 OFFENSIVE (SA + HA per width) ---\n")
    by_offense = sorted(reports, key=lambda r: r.sa_per_width + r.ha_per_width, reverse=True)
    for i, r in enumerate(by_offense[:5], 1):
        sa_w = r.sa_per_width
        ha_w = r.ha_per_width
        print(f"  {i}. {r.name}: SA/W={sa_w:.2f}, HA/W={ha_w:.2f}, "
              f"total attack/W={sa_w + ha_w:.2f}")

    # Best defensive divisions
    print("\n--- TOP 5 DEFENSIVE (Def + Org per width) ---\n")
    by_defense = sorted(reports, key=lambda r: r.def_per_width + r.org_per_width, reverse=True)
    for i, r in enumerate(by_defense[:5], 1):
        print(f"  {i}. {r.name}: Def/W={r.def_per_width:.2f}, "
              f"Org/W={r.org_per_width:.2f}, Def={r.stats.get('Defense', 0):.1f}")

    # Most cost-efficient
    print("\n--- TOP 5 COST-EFFICIENT (SA per IC) ---\n")
    by_cost = sorted(reports, key=lambda r: r.sa_per_ic, reverse=True)
    for i, r in enumerate(by_cost[:5], 1):
        print(f"  {i}. {r.name}: SA/IC={r.sa_per_ic:.3f}, "
              f"IC={r.ic_cost:.1f}, SA={r.stats.get('Soft Attack', 0):.1f}")

    # Equipment value analysis
    print("\n\n--- TOP 20 EQUIPMENT UPGRADES (by value score) ---\n")
    upgrades = analyze_equipment_value(db, max_year=equipment_year)
    print(format_equipment_table(upgrades, top_n=20))

    # Reliability analysis
    print("\n\n--- RELIABILITY IMPACT ANALYSIS ---\n")
    print("  HOI4 BICE Reliability Mechanics:")
    print("  - Equipment combat loss = strength_damage x 0.60")
    print("  - Equipment recovery after battle = 30% of losses")
    print("  - Net loss per damage point ~= 0.42 of equipment")
    print("  - Attrition equipment loss chance = 0.0016 / reliability")
    print("  - Org regain penalty: up to -50% with low reliability")
    print("  - Org drain while moving: up to +100% with low reliability")
    print("  - Weather impact: 3x multiplier with low reliability")
    print()
    print("  -> Reliability above ~0.8 is safe. Below 0.6 causes cascading problems.")
    print("  -> High-reliability equipment saves more IC long-term than low-IC alternatives.")
    print("  -> Motor vehicles and tanks are most affected (they have lowest base reliability).")

    print("\n" + "=" * 120)
