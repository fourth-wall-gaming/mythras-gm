---
id: "vehicle/handling-and-maneuvers"
title: "Handling & Maneuvers (chase & vehicle combat)"
category: "vehicle"
domain: "vehicle"
topic: "chase"
kind: "procedure"
summary: "Resolving evasive maneuvers via Drive/Pilot rolls modified by Handling, and the Loss of Control table on failure."
facets: {"phase": ["movement", "attack"], "kind": ["procedure"], "action": ["outmaneuver", "evade"], "condition": ["mounted", "charging"]}
links: ["vehicle/statistics", "vehicle/weapons"]
---

Evasive or sudden maneuvers require a successful Drive/Pilot roll to retain control. The GM may rule an ambitious maneuver demands a higher difficulty grade. Failure means control is lost: roll on the Loss of Control table (terrestrial only; adapt effects for aircraft and spacecraft -- e.g. a spin instead of a skid).

A vehicle's inherent Handling sets the starting difficulty for the Drive roll: Easy, Standard, Hard, Formidable, or Herculean. The maneuver's difficulty grade is then applied on top of Handling to find the final difficulty. (Example: a gyrostabilized motorcycle has Easy Handling; a 180-degree skid-turn rated +1 grade makes the roll Standard; on a non-stabilized bike it would be Hard.)

Superior Handling is a Trait; without it, default Handling is Standard for Large and smaller vehicles. Huge vehicles are inherently Formidable and Enormous Herculean, and the GM may rule some maneuvers simply impossible at great size.

**Loss of Control Table** (1d100):
- 01-25 Swerve: speed drops 1 step for 5 seconds.
- 26-40 Skid: speed drops 2 steps for 10 seconds.
- 41-50 Severe Skid: ends facing wrong way, standstill for 15 seconds.
- 51-60 Roll: 3d10 Structure damage; occupants roll Endurance or take 1d10 to 1d3 locations.
- 61-70 Severe Roll: 3d10+10 damage; occupants take 1d10 even on success, 2d10 on failure.
- 71-80 Write-Off: vehicle reduced to 0 Structure; occupant damage as Severe Roll.
- 81-90 Explosion: as above, fuel ignites within 1d20+10 seconds; if not clear, 1d6 burn to 1d6 locations.
- 91-98 Immediate Explosion: as above but immediate.
- 99-00 Catastrophic Crash: occupants roll Endurance or die instantly; Write-Off damage regardless.
