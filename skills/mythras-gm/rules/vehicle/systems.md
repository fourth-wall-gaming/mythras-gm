---
id: "vehicle/systems"
title: "Vehicle Systems"
category: "vehicle"
domain: "vehicle"
topic: "systems"
kind: "reference-list"
summary: "How penetrating damage affects vital vehicle Systems, with system-hit capacity by size and the component damage table."
facets: {"phase": ["combat-round"], "kind": ["reference-list"]}
links: ["vehicle/statistics", "vehicle/vehicle-combat"]
---

Each time damage penetrates the Hull, there is a chance equal to the penetrating damage that a vital System is affected. (Example: 10 damage on a Speedboat with 3 Hull and 24 Structure becomes 7 to Structure and a 7% chance to damage a System.)

System durability depends on vehicle Size, modelled as the number of Hits a System can take rather than raw damage. One hit destroys a Small vehicle's System; Medium takes two; Large three, and so on. A damaged but not destroyed System loses function proportionate to hits taken -- either a percentage reduction or a Grade penalty to System tasks.

**System Damage Table** (Size | System Hits | Loss per Hit):
- Small | 1 | 100% - Destroyed
- Medium | 2 | 1 Grade or 50%
- Large | 3 | 1 Grade or 33%
- Huge | 4 | 1 Grade or 25%
- Enormous | 5 | 1 Grade or 20%
- Colossal | 6 | 1 Grade or 16%

(Example: an Enormous Land Ironclad with 5 System Hits, hit twice in the Drive, loses 40% power, dropping Slow speed two Grades to Ponderous.)

**System Component Damage Table** (1d10 | System | Damaged | Destroyed):
- 1 Cargo: possessions proportional to damage destroyed | all cargo destroyed.
- 2 Comms: +1 Grade to Comms rolls per hit | cannot communicate or spoof sensors.
- 3 Controls: +1 Grade to Boating/Drive/Pilot per hit, immediate Control roll | cannot steer or change course.
- 4 Drive: Speed reduced proportional to damage | vehicle stops dead; aircraft crash.
- 5 Crew: passengers proportional to damage suffer a Major Wound and roll Endurance or die | occupants die.
- 6 Engine/Fuel: Speed reduced proportional to damage, electronics +1 Grade | destroyed in a disastrous explosion.
- 7 Sensors: +1 Grade to Sensor/Navigation/Weapon rolls per hit | vehicle rendered blind.
- 8 Weapons: weapon systems proportional to damage become inoperative | cannot fire weapons.
- 9-0 None: no system struck; just Structure damage.
