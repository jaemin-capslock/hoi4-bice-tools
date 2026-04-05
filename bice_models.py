#!/usr/bin/env python3
"""
bice_models.py — Object-oriented interface for BICE stat calculation.

Wraps the raw dict databases from bice_parser with typed classes that
know their own equipment slots, categories, and stat computation rules.

Usage
-----
    from bice_models import BICEDatabase, Division

    db = BICEDatabase()

    # Inspect a battalion type
    inf = db.battalion("infantry")
    print(inf.slots)       # {'infantry_equipment': 125, 'infantry_uniforms': 125}
    print(inf.categories)  # ['category_army', 'category_all_infantry', ...]

    # Equip with specific gear
    equipped = inf.equip("infantry_equipment_2", "infantry_uniforms_2")
    print(equipped.stats)  # {'soft_attack': 2.1, 'defense': 6.4, ...}

    # Auto-equip by year (picks best available for each slot)
    equipped = inf.equip_auto(year=1939)

    # Build a division with method chaining
    div = (Division("GER Infanterie-Division 1940", db)
        .add_battalion(inf.equip_auto(1939), 9)
        .add_battalion(db.battalion("artillery_brigade").equip_auto(1939), 4)
        .add_support(db.battalion("DIV_HQ").equip("infantry_uniforms_2"))
        .add_support(db.battalion("engineer").equip_auto(1939)))

    from bice_doctrines import get_preset
    stats = div.compute(get_preset("ww1_full"))

Public API
----------
BICEDatabase        — central DB; loads equipment + battalion definitions
BattalionType       — a battalion definition; knows its slots and categories
EquippedBattalion   — a battalion with equipment assigned to slots
Division            — a division template; aggregates stats via compute()
"""

from __future__ import annotations

from bice_parser import (
    build_equipment_db, build_battalion_db,
    COMBAT_STATS, BATTALION_BASE_STATS,
)
from bice_calc import (
    _auto_assign, _calc_raw_stats,
    _apply_doctrine_modifiers, _is_doctrine_format,
    calc_division as _calc_division_func,
)


# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────

class BICEDatabase:
    """Central database holding equipment and battalion definitions.

    Parameters
    ----------
    equip_db : dict, optional
        Pre-built equipment DB (from ``build_equipment_db()``).
        Built automatically if not supplied.
    bat_db : dict, optional
        Pre-built battalion DB (from ``build_battalion_db()``).
        Built automatically if not supplied.
    """

    def __init__(self, equip_db: dict | None = None, bat_db: dict | None = None):
        self._equip_db = equip_db if equip_db is not None else build_equipment_db()
        self._bat_db = bat_db if bat_db is not None else build_battalion_db()

    @property
    def equip_db(self) -> dict:
        return self._equip_db

    @property
    def bat_db(self) -> dict:
        return self._bat_db

    # ── Lookup ──────────────────────────────────

    def battalion(self, name: str) -> BattalionType:
        """Look up a battalion type by ID. Raises KeyError if not found."""
        if name not in self._bat_db:
            raise KeyError(f"Unknown battalion: {name!r}")
        return BattalionType(name, self._bat_db[name], self)

    def equipment(self, eid: str) -> dict:
        """Look up a single equipment entry by ID."""
        if eid not in self._equip_db:
            raise KeyError(f"Unknown equipment: {eid!r}")
        return dict(self._equip_db[eid])

    # ── Equipment search ────────────────────────

    def find_equipment(self, family: str, max_year: int = 9999) -> list[dict]:
        """Find all non-archetype equipment for *family*, up to *max_year*.

        Returns a list sorted by year ascending.
        """
        results = []
        for eq in self._equip_db.values():
            if eq.get("family") != family:
                continue
            if eq.get("is_archetype") in (True, "yes", 1):
                continue
            year = eq.get("year", 0)
            if not isinstance(year, (int, float)):
                continue
            if year <= max_year:
                results.append(eq)
        return sorted(results, key=lambda e: e.get("year", 0))

    def best_equipment(self, family: str, year: int) -> str | None:
        """Return the ID of the best (latest-year) equipment for *family*
        that is available by *year*.  Returns ``None`` if nothing matches.
        """
        candidates = self.find_equipment(family, max_year=year)
        if not candidates:
            return None
        return candidates[-1]["id"]

    # ── Enumeration ─────────────────────────────

    def list_battalions(self) -> list[str]:
        return sorted(self._bat_db.keys())

    def list_equipment_families(self) -> list[str]:
        families: set[str] = set()
        for eq in self._equip_db.values():
            f = eq.get("family")
            if f:
                families.add(f)
        return sorted(families)

    def __repr__(self) -> str:
        return (f"BICEDatabase({len(self._equip_db)} equipment, "
                f"{len(self._bat_db)} battalions)")


# ─────────────────────────────────────────────
#  BATTALION TYPE
# ─────────────────────────────────────────────

class BattalionType:
    """A battalion type definition from the database.

    Created via ``BICEDatabase.battalion(name)``.
    """

    def __init__(self, name: str, raw: dict, db: BICEDatabase):
        self._name = name
        self._raw = raw
        self._db = db

    @property
    def id(self) -> str:
        return self._name

    @property
    def slots(self) -> dict[str, int]:
        """Equipment slots: ``{archetype_family: quantity_needed}``."""
        return dict(self._raw.get("need", {}))

    @property
    def categories(self) -> list[str]:
        return list(self._raw.get("categories", []))

    @property
    def base_stats(self) -> dict[str, float]:
        return {s: float(self._raw.get(s, 0))
                for s in BATTALION_BASE_STATS if s in self._raw}

    @property
    def manpower(self) -> int:
        return int(self._raw.get("manpower", 0))

    @property
    def combat_width(self) -> float:
        return float(self._raw.get("combat_width", 0))

    @property
    def organisation(self) -> float:
        return float(self._raw.get("max_organisation", 0))

    @property
    def transport(self) -> str:
        return self._raw.get("transport", "")

    @property
    def group(self) -> str:
        return self._raw.get("group", "")

    @property
    def is_support(self) -> bool:
        return self.group == "support"

    # ── Equipping ───────────────────────────────

    def equip(self, *equip_ids: str) -> EquippedBattalion:
        """Assign specific equipment IDs to this battalion's slots.

        Equipment is matched to slots by family (archetype).
        Unmatched IDs are silently ignored; unmatched slots are left empty.

        Returns an :class:`EquippedBattalion`.
        """
        assignment = _auto_assign(self._raw, list(equip_ids), self._db.equip_db)
        return EquippedBattalion(self, assignment)

    def equip_auto(self, year: int) -> EquippedBattalion:
        """Auto-equip with the best available equipment for each slot,
        up to the given *year*.

        For each slot archetype, picks the highest-year non-archetype
        equipment entry whose year ≤ *year*.
        """
        equip_ids: list[str] = []
        for slot_family in self.slots:
            best = self._db.best_equipment(slot_family, year)
            if best:
                equip_ids.append(best)
        return self.equip(*equip_ids)

    def __repr__(self) -> str:
        return f"BattalionType({self._name!r}, slots={list(self.slots.keys())})"


# ─────────────────────────────────────────────
#  EQUIPPED BATTALION
# ─────────────────────────────────────────────

class EquippedBattalion:
    """A battalion with specific equipment assigned to its slots.

    Created via ``BattalionType.equip()`` or ``BattalionType.equip_auto()``.
    """

    def __init__(self, bat_type: BattalionType, assignment: dict[str, str]):
        self._type = bat_type
        self._assignment = assignment
        self._cached_stats: dict[str, float] | None = None

    @property
    def type(self) -> BattalionType:
        return self._type

    @property
    def assignment(self) -> dict[str, str]:
        """Current equipment assignment: ``{slot_archetype: specific_equip_id}``."""
        return dict(self._assignment)

    @property
    def equipped_slots(self) -> list[str]:
        return list(self._assignment.keys())

    @property
    def unequipped_slots(self) -> list[str]:
        """Slots that have no equipment assigned."""
        return [s for s in self._type.slots if s not in self._assignment]

    @property
    def stats(self) -> dict[str, float]:
        """Raw combat stats (no modifiers). Cached after first access."""
        if self._cached_stats is None:
            self._cached_stats = _calc_raw_stats(
                self._type._raw, self._assignment, self._type._db.equip_db)
        return dict(self._cached_stats)

    def compute_stats(self, modifiers: dict | None = None) -> dict[str, float]:
        """Compute combat stats with optional doctrine modifiers."""
        stats = self.stats
        if _is_doctrine_format(modifiers):
            stats["max_organisation"] = self._type.organisation
            stats = _apply_doctrine_modifiers(
                stats, self._type.categories, modifiers)
        return stats

    def __repr__(self) -> str:
        filled = len(self._assignment)
        total = len(self._type.slots)
        return (f"EquippedBattalion({self._type.id!r}, "
                f"{filled}/{total} slots filled)")


# ─────────────────────────────────────────────
#  DIVISION
# ─────────────────────────────────────────────

class Division:
    """A division template with line battalions and support companies.

    Supports method chaining for building templates fluently.

    Parameters
    ----------
    name : str
        Division name (shown in Excel output, etc.).
    db : BICEDatabase
        The database to use for stat computation.
    notes : str, optional
        Free-text description.
    """

    def __init__(self, name: str, db: BICEDatabase, notes: str = ""):
        self.name = name
        self.notes = notes
        self._db = db
        self._battalions: list[tuple[EquippedBattalion, int]] = []
        self._support: list[tuple[EquippedBattalion, int]] = []

    # ── Building ────────────────────────────────

    def add_battalion(self, equipped: EquippedBattalion, count: int = 1) -> Division:
        """Add line battalion(s). Returns *self* for chaining."""
        self._battalions.append((equipped, count))
        return self

    def add_support(self, equipped: EquippedBattalion, count: int = 1) -> Division:
        """Add support company/ies. Returns *self* for chaining."""
        self._support.append((equipped, count))
        return self

    # ── Inspection ──────────────────────────────

    @property
    def battalions(self) -> list[tuple[EquippedBattalion, int]]:
        return list(self._battalions)

    @property
    def support(self) -> list[tuple[EquippedBattalion, int]]:
        return list(self._support)

    @property
    def total_line_count(self) -> int:
        return sum(c for _, c in self._battalions)

    @property
    def total_support_count(self) -> int:
        return sum(c for _, c in self._support)

    @property
    def all_unequipped(self) -> dict[str, list[str]]:
        """Map of ``"bat_id (xN)"`` → list of unequipped slot names."""
        result: dict[str, list[str]] = {}
        for bat, count in self._battalions + self._support:
            missing = bat.unequipped_slots
            if missing:
                key = f"{bat.type.id} (x{count})"
                result[key] = missing
        return result

    # ── Computation ─────────────────────────────

    def to_dict(self) -> dict:
        """Convert to the legacy dict template format.

        The ``equip`` field uses the dict form ``{slot: equip_id}``
        so that ``calc_division`` skips re-auto-assignment.
        """
        return {
            "name": self.name,
            "notes": self.notes,
            "battalions": [
                {"type": b.type.id, "count": c, "equip": dict(b.assignment)}
                for b, c in self._battalions
            ],
            "support": [
                {"type": b.type.id, "count": c, "equip": dict(b.assignment)}
                for b, c in self._support
            ],
        }

    def compute(self, modifiers: dict | None = None) -> dict:
        """Compute full division stats with HOI4 aggregation rules.

        Delegates to the functional ``calc_division`` engine,
        preserving a single source of truth for aggregation logic.
        """
        return _calc_division_func(
            self.to_dict(), self._db.bat_db, self._db.equip_db,
            modifiers=modifiers,
        )

    def __repr__(self) -> str:
        n_line = self.total_line_count
        n_sup = self.total_support_count
        return f"Division({self.name!r}, {n_line} line + {n_sup} support)"
