#!/usr/bin/env bash
# Seed the Veilwrack campaign into TypeDB via the mythras_gm.py CLI.
# Usage: bash skills/mythras-gm/setting/seed_veilwrack.sh
# Prints the campaign id on completion. Idempotence: NOT idempotent — run once,
# or delete the campaign first.

set -euo pipefail
CLI="uv run python skills/mythras-gm/mythras_gm.py"

jqid() { python3 -c "import sys,json;print(json.load(sys.stdin)['id'])"; }

echo "== Creating campaign =="
CAMPAIGN=$($CLI create-campaign \
  --name "The Veilwrack: The Stilling" \
  --description "An original sky-realm campaign. Winged Alar peoples on the floating bone-spires of dead sky-leviathans face the Stilling: the wind itself is dying." \
  --game-date "Year 1001 After the Settling, season of the High Gales" \
  2>/dev/null | jqid)
echo "campaign: $CAMPAIGN"

echo "== Locations =="
$CLI add-location --campaign "$CAMPAIGN" --name "Suruveil's Crown" --type spire \
  --description "Capital of the Veilwrack; the largest Spire in the world, visibly a titanic horned skull in low light." \
  --narrative "Seat of the Spirarchy and home of the Quillate archive-guild. Population about 200,000 Alar of all three kindreds. The sealed Tenth Gallery of the palace contains the Founding Compact. Marrower gangs work the spire-roots below; the upper galleries are Roak guild-halls; the Moult is currently anchored windward." 2>/dev/null | jqid
$CLI add-location --campaign "$CAMPAIGN" --name "The Moult" --type roost \
  --description "The Vael nation: a migrating flotilla of kite-rafts and tethered gliders, thousands strong." \
  --narrative "Anchored windward of the Crown after abandoning two ancestral windlanes to Stillings. Mood: grief masked as restlessness. The lane-charts the Moult keeps are the best Stilling data in the world, and the Spirarchy wants them." 2>/dev/null | jqid
$CLI add-location --campaign "$CAMPAIGN" --name "Greywake" --type stilled-zone \
  --description "The drowned Spire: sank into the Undermist five years ago at the heart of the oldest Stilling. Nine thousand died." \
  --narrative "Its top hundred feet still jut from the cloud-sea. The Hushed roost there in their hundreds, a silent congregation. Holds a Compact-era killing harpoon and the first whole copy of the Founding Compact. Stilling Potency 80." 2>/dev/null | jqid
$CLI add-location --campaign "$CAMPAIGN" --name "Lanternfall Spire" --type spire \
  --description "A roost-spire of about three thousand, mostly Roak lamp-crafters. Its windlane began Stilling this season." \
  --narrative "Intro adventure site: evacuation under pressure. The lane-shrine beacon-horn still works. A Stillwight hunts the dead stretch of lane, and a Hushed child follows evacuees out — it remembers its mother, who is among them." 2>/dev/null | jqid

echo "== Factions =="
$CLI add-faction --campaign "$CAMPAIGN" --name "The Gale Wardens" \
  --description "Rangers, rescue-fliers, and Stilling-surveyors. The player characters' company." \
  --narrative "Part rescue service, part research expedition, part heresy in feathers. Commander: Esk Veil-Torn (Vael, f), who lost her wing-sister at Greywake. Field data shows the Stillings are accelerating and are not random; the Spirarchy suppresses this." 2>/dev/null | jqid
$CLI add-faction --campaign "$CAMPAIGN" --name "The Spirarchy of Suruveil's Crown" \
  --description "Ruling council of the capital. Order, continuity, legitimacy." \
  --narrative "Led by Spirarch Velute the Ninth: not a villain, a custodian of an inherited lie she believes necessary. Punishes still-panic as sedition. Keeps the Founding Compact sealed in the Tenth Gallery." 2>/dev/null | jqid
$CLI add-faction --campaign "$CAMPAIGN" --name "The Quillate" \
  --description "The Roak archive-guild: the longest unbroken written record in the world." \
  --narrative "The Record has a hole exactly one thousand years deep, cut deliberately. High Quill Orrocan knows the hole exists and is terrified of what unsealing it does to Roak legitimacy. Potential ally." 2>/dev/null | jqid
$CLI add-faction --campaign "$CAMPAIGN" --name "The Hushed Choir" \
  --description "A cult that worships the Stilling as the world's overdue sabbath. They walk into still zones singing." \
  --narrative "Partially right about everything. Their interlocutor Cantor Hssh (a Hushed, formerly Ossuin) writes beautifully and wants the PCs to understand the Stilling is the world breathing in. They know a working Windworker spending MP daily makes a Stilling recede." 2>/dev/null | jqid
$CLI add-faction --campaign "$CAMPAIGN" --name "The Marrowers" \
  --description "Industrial guild tapping spire-marrow breath as lift-gas. Profitable. Catastrophic." \
  --narrative "Tapped spires sink measurably faster. They ran the numbers; they burned the numbers. Magnate Brell Coinfeather still has a copy and is buyable, once." 2>/dev/null | jqid

echo "== Creature templates =="
$CLI add-template --campaign "$CAMPAIGN" --name "Hushed Alar" --species avian \
  --stats '{"STR":9,"CON":13,"SIZ":9,"DEX":14,"INT":10,"POW":14,"CHA":4}' \
  --skills '{"Athletics":43,"Brawn":38,"Endurance":56,"Evade":48,"Perception":44,"Stealth":64,"Willpower":58}' \
  --combat-styles '{"Grasp of the Quiet":45}' \
  --equipment '[{"name":"Talons","damage":"1d4","size":"S"}]' \
  --description "An Alar emptied by a Stilling: silent, grey-rooted feathers, cannot fly, extends 3m of dead air. Quieting Grip on Grip effect: opposed Endurance vs 60 or +1 Fatigue per round held. Immune to exertion Fatigue and asphyxiation. Death-burst: 5m Endurance roll or Winded." 2>/dev/null | jqid
$CLI add-template --campaign "$CAMPAIGN" --name "Stillwight" --species humanoid \
  --stats '{"STR":6,"CON":12,"SIZ":10,"DEX":16,"INT":4,"POW":16,"CHA":3}' \
  --skills '{"Endurance":54,"Evade":52,"Perception":58,"Stealth":78}' \
  --combat-styles '{"Envelop":50}' \
  --equipment '[{"name":"Smother","damage":"0","size":"M"}]' \
  --description "Glass-jellyfish predator of dead air, 2m bell, near-invisible (Formidable Perception to spot). Envelop = leaping attack at head; victim asphyxiates per SRD. Weapons under M pass through on normal success. Single hit location (Bell, HP 8). Splits in two after a kill." 2>/dev/null | jqid
$CLI add-template --campaign "$CAMPAIGN" --name "Sky-Drake" --species winged-quadruped \
  --stats '{"STR":22,"CON":15,"SIZ":24,"DEX":13,"INT":5,"POW":10,"CHA":3}' \
  --skills '{"Athletics":65,"Brawn":72,"Endurance":60,"Evade":36,"Flight":70,"Perception":62,"Track":55}' \
  --combat-styles '{"Stoop and Rend":62}' \
  --equipment '[{"name":"Bite","damage":"1d8","size":"L"},{"name":"Claw","damage":"1d6","size":"M"},{"name":"Tail-lash","damage":"1d6","size":"M"}]' \
  --armor '{"Head":4,"Forequarters":4,"Hindquarters":4,"Right Wing":4,"Left Wing":4,"Right Front Leg":4,"Left Front Leg":4,"Right Hind Leg":4,"Left Hind Leg":4}' \
  --description "Apex predator of the windlanes: 7m wingspan raptor-lizard. Opens with diving charge (+2 DM steps, Hard attack). Flees at half chest HP." 2>/dev/null | jqid
$CLI add-template --campaign "$CAMPAIGN" --name "Marrower Bravo" --species avian \
  --stats '{"STR":13,"CON":12,"SIZ":10,"DEX":14,"INT":9,"POW":9,"CHA":9}' \
  --skills '{"Athletics":47,"Brawn":43,"Endurance":48,"Evade":42,"Flight":52,"Perception":38,"Stealth":40,"Willpower":36}' \
  --combat-styles '{"Rootworks Scrapper":48}' \
  --equipment '[{"name":"Talon-hook","damage":"1d6+1","size":"M"},{"name":"Buckler","damage":"1d3","size":"M"}]' \
  --armor '{"Chest":2,"Abdomen":2}' \
  --description "Spire-root tough of the Marrower gangs. Talon-hook can Sunder." 2>/dev/null | jqid
$CLI add-template --campaign "$CAMPAIGN" --name "Warden Skirmisher" --species avian \
  --stats '{"STR":11,"CON":12,"SIZ":9,"DEX":16,"INT":12,"POW":11,"CHA":11}' \
  --skills '{"Athletics":52,"Endurance":50,"Evade":55,"First Aid":45,"Flight":62,"Perception":48,"Stealth":44,"Willpower":40}' \
  --combat-styles '{"Warden Skirmisher":55}' \
  --equipment '[{"name":"Wingspear","damage":"1d8+1","size":"M"},{"name":"Stormbow","damage":"1d8","size":"L"},{"name":"Dagger","damage":"1d4+1","size":"S"}]' \
  --armor '{"Chest":5,"Head":2}' \
  --description "Typical Gale Warden flight-mate. Skirmishing trait: may shoot while flying at a Run." 2>/dev/null | jqid

echo "== Opening scene =="
$CLI set-scene --campaign "$CAMPAIGN" \
  --scene "Warden roost, Suruveil's Crown. Commander Esk Veil-Torn briefs the company: the Lanternfall windlane is going still, and three thousand lamp-crafters need a way out before the season turns." 2>/dev/null >/dev/null
$CLI log-event --campaign "$CAMPAIGN" --type gm-note --session 0 \
  --summary "Campaign seeded: Veilwrack setting, 4 locations, 5 factions, 5 creature templates." 2>/dev/null >/dev/null

echo ""
echo "DONE. Campaign id: $CAMPAIGN"
