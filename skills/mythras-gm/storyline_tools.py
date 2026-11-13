"""Persistent party/storyline clocks and temporal read models.

Campaign time is a high-water mark, never the clock of an inactive PC. A
ContextVar selects a storyline for one command only (including in-process
callers/tests); low-level storage stays shared and canonical. Legacy campaigns
without storylines retain their original behaviour. No dice or PC decisions
are made here.
"""
from __future__ import annotations

import contextvars
import functools
import json
import os

CURRENT = contextvars.ContextVar('mythras_storyline', default=None)
LOCAL_CASCADE = contextvars.ContextVar('mythras_local_cascade', default=False)
FIELDS = ('myth-time-index', 'myth-clock-minutes', 'myth-game-date',
          'myth-current-scene', 'myth-session-number', 'myth-played-pcs',
          'myth-arc-json', 'myth-storyline-state-json')
TAGGED = ('myth-game-event', 'myth-beat', 'myth-agenda', 'myth-fact', 'myth-encounter')
ADMIN = {'create_storyline', 'list_storylines', 'update_storyline', 'assign_storyline', 'assign_storyline_record', 'split_storyline',
         'load_schema', 'doctor', 'setup', 'export_campaign', 'import_campaign',
         'delete_campaign', 'create_campaign', 'list_campaigns'}
SCOPED = {'get_context', 'set_scene', 'get_campaign', 'update_campaign', 'tick',
          'forecast', 'timeline', 'add_fact', 'establish_fact', 'learn',
          'track_who_knows', 'character_view', 'get_log', 'log_event', 'get_knowledge',
          'set_knowledge', 'fire_beat', 'add_agenda', 'add_beat', 'start_encounter',
          'rest_character', 'add_timed_effect'}


def csv(value):
    return list(dict.fromkeys(x.strip() for x in (value or '').split(',') if x.strip()))


def decode(value, default):
    return json.loads(value) if isinstance(value, str) and value else (value or default)


def at_or_before(value, now):
    if isinstance(value, list):
        value = value[0] if value else None
    return value is None or value <= now


def effect_state(extras, minute):
    """Pure projection: no expiration charges, no automatic refunds or rest."""
    effects = []
    reserved = 0
    for stored in extras.get('timed_effects', []):
        e = dict(stored)
        e['active'] = bool(e.get('active', True) and e['ends_at_minute'] > minute)
        e['remaining_minutes'] = max(0, e['ends_at_minute'] - minute) if e['active'] else 0
        if e['active']:
            reserved += e.get('reserved_mp', 0)
        effects.append(e)
    lodging = extras.get('lodging') or {}
    return effects, reserved, lodging


class Store:
    def __init__(self, ns):
        self.g = ns
        self.raw_get = ns['_get_entity']
        self.raw_set = ns['_set_attr']
        self.raw_link = ns['_link_to_campaign']
        self.raw_place = ns['_place_character']

    def fail(self, text):
        self.g['fail'](text)

    def supported(self, driver):
        return 'myth-storyline-state-json' in self.g['declared'](driver, 'myth-storyline-state-json')

    def list(self, driver, campaign):
        if not self.supported(driver):
            return []
        esc = self.g['escape_string']
        rows = self.g['_fetch'](driver, f'''match
          $c isa myth-campaign, has id "{esc(campaign)}";
          (campaign: $c, element: $s) isa myth-campaign-membership;
          $s isa myth-storyline, has id $i;
          fetch {{ "id": $i }};''')
        return [self.read(driver, r['id'], campaign) for r in rows]

    def read(self, driver, sid, campaign):
        s = self.raw_get(driver, 'myth-storyline', sid, list(FIELDS))
        if s:
            s['campaign'] = campaign
        return s

    def state(self, s):
        return decode(s.get('myth-storyline-state-json'), {})

    def minute(self, s):
        return s.get('myth-clock-minutes') if s.get('myth-clock-minutes') is not None else s['myth-time-index'] * 360

    def save_state(self, driver, s, state):
        self.raw_set(driver, 'myth-storyline', s['id'], 'myth-storyline-state-json', json.dumps(state))
        s['myth-storyline-state-json'] = json.dumps(state)

    def select(self, args, name):
        if name in ADMIN:
            return None
        pc = getattr(args, 'pc', None)
        selector = getattr(args, 'storyline', None) or (None if pc else os.getenv('MYTHRAS_STORYLINE'))
        if selector == 'world':
            if pc:
                self.fail('--pc cannot be combined with --storyline world')
            return None
        campaign = getattr(args, 'campaign', None)
        if not campaign and not (selector or pc):
            return None
        campaign = campaign or self.g['resolve_campaign'](None)
        with self.g['get_driver']() as driver:
            stories = self.list(driver, campaign)
            if not stories:
                if selector or pc:
                    self.fail('No storylines in this campaign. Run create-storyline first (load-schema if needed).')
                return None
            chosen = [s for s in stories if (not selector or selector in (s['id'], s['name']))
                      and (not pc or pc in csv(s.get('myth-played-pcs')))]
            if selector or pc:
                if len(chosen) != 1:
                    self.fail('Storyline selector must identify exactly one storyline in this campaign')
                return chosen[0]
            if name in SCOPED:
                self.fail('This campaign has storyline clocks. Select --pc ID or --storyline NAME/ID; use --storyline world explicitly for world administration.')
        return None

    def scope_events(self, driver, rows, campaign):
        s = CURRENT.get()
        if not s:
            return rows
        esc = self.g['escape_string']
        meta = self.g['_fetch'](driver, f'''match
          $c isa myth-campaign, has id "{esc(campaign)}";
          (campaign: $c, element: $e) isa myth-campaign-membership;
          $e isa myth-game-event, has id $i;
          try {{ $e has myth-storyline-id $sid; }};
          try {{ $e has myth-time-index $ti; }};
          try {{ $e has myth-clock-minutes $mi; }};
          fetch {{ "id": $i, "storyline": $sid, "time_index": $ti, "clock_minutes": $mi }};''')
        by_id = {r['id']: r for r in meta}
        participants = self.g['_event_participants'](driver, campaign)
        members = set(csv(s.get('myth-played-pcs')))
        out = []
        for row in rows:
            m = by_id.get(row['id'], {})
            if not at_or_before(m.get('time_index'), s['myth-time-index']):
                continue
            if m.get('clock_minutes') is not None and m['clock_minutes'] > self.minute(s):
                continue
            owner = m.get('storyline')
            if owner and owner != s['id']:
                lineage = decode(s.get('myth-storyline-state-json'), {}).get('history_storylines', [])
                inherited = any(h['id'] == owner and m.get('time_index') is not None
                                and (m.get('clock_minutes') if m.get('clock_minutes') is not None else m['time_index'] * 360) <= h['through_minute'] for h in lineage)
                if not inherited:
                    continue
            # Legacy undated events cannot safely be dated by real-world write
            # time. Keep own-PC history; hide unknown offscreen/NPC-only events
            # until update-event --when backfills their actual game date.
            if owner is None and m.get('time_index') is None:
                involved = {i for i, _ in participants.get(row['id'], [])}
                if not involved.intersection(members):
                    continue
            out.append({**row, **{k: v for k, v in m.items() if k != 'id'}})
        return out

    def metadata(self, driver, etype, campaign):
        if not self.supported(driver):
            return {}
        esc = self.g['escape_string']
        rows = self.g['_fetch'](driver, f'''match
          $c isa myth-campaign, has id "{esc(campaign)}";
          (campaign: $c, element: $e) isa myth-campaign-membership;
          $e isa {etype}, has id $i;
          try {{ $e has myth-storyline-id $sid; }};
          fetch {{ "id": $i, "storyline": $sid }};''')
        return {r['id']: r.get('storyline') for r in rows}

    def owns(self, driver, etype, eid):
        r = self.raw_get(driver, etype, eid, ['myth-storyline-id'])
        return (r or {}).get('myth-storyline-id')

    def guard_pc(self, driver, cid):
        s = CURRENT.get()
        if not s:
            return
        c = self.raw_get(driver, 'myth-character', cid, ['myth-char-type'])
        if c and c.get('myth-char-type') == 'pc' and cid not in csv(s.get('myth-played-pcs')):
            self.fail('PC is not a member of the selected storyline; select their own storyline')

    def filter_records(self, driver, rows, etype, campaign):
        s = CURRENT.get()
        if not s:
            return rows
        owners = self.metadata(driver, etype, campaign)
        if LOCAL_CASCADE.get() and etype != 'myth-fact':
            return [r for r in rows if owners.get(r['id']) == s['id']]
        if etype == 'myth-fact':
            # Established truths are shared, knowledge is still per character.
            return [r for r in rows if
                    (r['status'] != 'established' or at_or_before(r.get('time_index'), s['myth-time-index']))
                    and (r['status'] == 'established' or owners.get(r['id']) in ((s['id'],) if LOCAL_CASCADE.get() else (None, s['id'])))]
        return [r for r in rows if owners.get(r['id']) in (None, s['id'])]

    def clock_payload(self, s):
        return {'id': s['id'], 'name': s['name'],
                'pcs': csv(s.get('myth-played-pcs')),
                'now': self.g['eng'].format_time_key(s['myth-time-index']),
                'minute_in_watch': self.minute(s) % 360,
                'scene': s.get('myth-current-scene'),
                'session': s.get('myth-session-number')}

    def create(self, args):
        eng = self.g['eng']
        try:
            index = eng.parse_time_key(args.at)
        except ValueError as e:
            self.fail(str(e))
        members = csv(args.pcs)
        if not members:
            self.fail('A storyline needs at least one PC')
        with self.g['get_driver']() as driver:
            if not self.supported(driver):
                self.fail('Storyline schema unavailable; run load-schema')
            stories = self.list(driver, args.campaign)
            if any(s['name'] == args.name for s in stories):
                self.fail('A storyline with that name already exists')
            self.validate_members(driver, args.campaign, members)
            if any(set(members).intersection(csv(s.get('myth-played-pcs'))) for s in stories):
                self.fail('A PC already belongs to a storyline; use assign-storyline to move them')
            sid = self.g['generate_id']('myth-storyline')
            esc = self.g['escape_string']
            camp = self.raw_get(driver, 'myth-campaign', args.campaign, ['myth-session-number', 'myth-time-index'])
            if not camp:
                self.fail('No such campaign')
            state = {'positions': {}, 'effect_clock_version': 1}
            q = f'''insert $s isa myth-storyline, has id "{sid}", has name "{esc(args.name)}",
              has myth-time-index {index}, has myth-clock-minutes {index * 360 + args.minute},
              has myth-game-date "{esc(args.at)}", has myth-played-pcs "{esc(','.join(members))}",
              has myth-session-number {args.session if args.session is not None else camp.get('myth-session-number') or 0},
              has myth-current-scene "{esc(args.scene or '')}",
              has myth-storyline-state-json "{esc(json.dumps(state))}";
            '''
            self.g['_write'](driver, q)
            self.raw_link(driver, args.campaign, sid, 'myth-storyline')
            s = self.read(driver, sid, args.campaign)
            if camp.get('myth-time-index') is None or index > camp['myth-time-index']:
                self.raw_set(driver, 'myth-campaign', args.campaign, 'myth-time-index', index, quote=False)
            if args.arc_file:
                self.set_arc(driver, sid, args.arc_file)
        self.g['out']({'success': True, 'id': sid, 'storyline': self.clock_payload(s)})

    def validate_members(self, driver, campaign, members):
        esc = self.g['escape_string']
        for cid in members:
            rows = self.g['_fetch'](driver, f'''match
              $c isa myth-campaign, has id "{esc(campaign)}";
              (campaign: $c, element: $p) isa myth-campaign-membership;
              $p isa myth-character, has id "{esc(cid)}", has myth-char-type "pc";
              fetch {{ "id": $p.id }};''')
            if not rows:
                self.fail(f'PC {cid} is not in this campaign')

    def set_arc(self, driver, sid, path):
        acts = self.g['_parse_arc_acts'](path)
        eng = self.g['eng']
        for a in acts:
            keys = [w for w in a['when'].replace('to', ' ').split()
                    if __import__('re').match(r'^d-?\d+(/\w+)?$', w)]
            try:
                a['index_from'] = eng.parse_time_key(keys[0] if '/' in keys[0] else keys[0] + '/dawn')
                a['index_to'] = eng.parse_time_key(keys[-1] if '/' in keys[-1] else keys[-1] + '/night')
            except (IndexError, ValueError):
                a['index_from'] = a['index_to'] = None
        self.raw_set(driver, 'myth-storyline', sid, 'myth-arc-json', json.dumps(acts))

    def list_command(self, args):
        with self.g['get_driver']() as driver:
            rows = self.list(driver, args.campaign)
            world = self.raw_get(driver, 'myth-campaign', args.campaign, ['myth-time-index'])
        self.g['out']({'success': True, 'storylines': [self.clock_payload(s) for s in rows],
                       'world_high_water': self.g['eng'].format_time_key(world['myth-time-index'])
                       if world and world.get('myth-time-index') is not None else None})

    def update(self, args):
        with self.g['get_driver']() as driver:
            found = [s for s in self.list(driver, args.campaign) if args.id in (s['id'], s['name'])]
            if len(found) != 1:
                self.fail('No unique storyline in this campaign')
            s = found[0]
            if args.at:
                idx = self.g['eng'].parse_time_key(args.at)
                target = idx * 360 + args.minute
                if target < self.minute(s) and not args.rewind:
                    self.fail('Refusing storyline rewind; use --rewind for an explicit correction')
            if args.scene is not None:
                self.raw_set(driver, 'myth-storyline', s['id'], 'myth-current-scene', args.scene)
            if args.session is not None:
                self.raw_set(driver, 'myth-storyline', s['id'], 'myth-session-number', args.session, quote=False)
            if args.arc_file:
                self.set_arc(driver, s['id'], args.arc_file)
            if args.at:
                idx = self.g['eng'].parse_time_key(args.at)
                target = idx * 360 + args.minute
                if target < self.minute(s) and not args.rewind:
                    self.fail('Refusing storyline rewind; use --rewind for an explicit correction')
                self.raw_set(driver, 'myth-storyline', s['id'], 'myth-time-index', idx, quote=False)
                self.raw_set(driver, 'myth-storyline', s['id'], 'myth-clock-minutes', target, quote=False)
                self.raw_set(driver, 'myth-storyline', s['id'], 'myth-game-date', args.at)
                world = self.raw_get(driver, 'myth-campaign', args.campaign, ['myth-time-index'])
                if world.get('myth-time-index') is None or idx > world['myth-time-index']:
                    self.raw_set(driver, 'myth-campaign', args.campaign, 'myth-time-index', idx, quote=False)
            result = self.read(driver, s['id'], args.campaign)
        self.g['out']({'success': True, 'storyline': self.clock_payload(result)})

    def assign(self, args):
        """Move PCs to a shared cursor only after their dates are synchronised."""
        members = csv(args.pcs)
        with self.g['get_driver']() as driver:
            stories = self.list(driver, args.campaign)
            target = next((s for s in stories if args.id in (s['id'], s['name'])), None)
            if not target:
                self.fail('No destination storyline')
            self.validate_members(driver, args.campaign, members)
            for s in stories:
                if s['id'] != target['id'] and set(members).intersection(csv(s.get('myth-played-pcs'))):
                    if self.minute(s) != self.minute(target):
                        self.fail('Synchronise storyline dates/minutes through play before joining; no silent catch-up or recovery')
            state = decode(target.get('myth-storyline-state-json'), {})
            history = state.setdefault('history_storylines', [])
            for source in stories:
                if source['id'] != target['id'] and set(members).intersection(csv(source.get('myth-played-pcs'))):
                    history.extend(decode(source.get('myth-storyline-state-json'), {}).get('history_storylines', []))
                    history.append({'id': source['id'], 'through_minute': self.minute(source)})
            self.raw_set(driver, 'myth-storyline', target['id'], 'myth-storyline-state-json', json.dumps(state))
            for s in stories:
                old = csv(s.get('myth-played-pcs'))
                new = list(dict.fromkeys(old + members)) if s['id'] == target['id'] else [x for x in old if x not in members]
                if new != old:
                    self.raw_set(driver, 'myth-storyline', s['id'], 'myth-played-pcs', ','.join(new))
        self.g['out']({'success': True, 'id': target['id'], 'joined': members})

    def add_effect(self, args):
        s = CURRENT.get()
        if not s or args.id not in csv(s.get('myth-played-pcs')):
            self.fail('Timed effects require selecting the owner PC storyline')
        if args.minutes <= 0 or args.reserved_mp < 0:
            self.fail('Duration must be positive and reserved MP nonnegative')
        with self.g['get_driver']() as driver:
            self.guard_pc(driver, args.id)
            c = self.g['_load_character'](driver, args.id)
            ex = c.get('myth-extras-json') or {}
            effects = ex.setdefault('timed_effects', [])
            eid = self.g['generate_id']('myth-effect')
            effects.append({'id': eid, 'name': args.name, 'active': True,
                            'started_at_minute': self.minute(s),
                            'ends_at_minute': self.minute(s) + args.minutes,
                            'reserved_mp': args.reserved_mp})
            self.g['_set_attr'](driver, 'myth-character', args.id, 'myth-extras-json', json.dumps(ex))
        self.g['out']({'success': True, 'id': eid, 'expires_at_minute': self.minute(s) + args.minutes,
                       'cost_note': 'Records a previously paid casting; does not spend MP again'})

    def rest(self, args):
        s = CURRENT.get()
        if not s or args.id not in csv(s.get('myth-played-pcs')):
            self.fail('Rest requires selecting a member PC storyline')
        if args.hours < 0.25 or (args.kind == 'full' and args.hours < 8):
            self.fail('Full rest needs at least eight hours; short rest at least fifteen minutes')
        if args.kind == 'full' and not args.safe:
            self.fail('Confirm safe sheltered rest with --safe; danger/distraction requires manual adjudication')
        with self.g['get_driver']() as driver:
            self.guard_pc(driver, args.id)
            c = self.g['_load_character'](driver, args.id)
            ex = c.get('myth-extras-json') or {}
            legacy = [e for e in ex.get('active_magic', []) if e.get('active') is not False
                      and not e.get('clock_migrated')]
            if legacy:
                self.fail('Migrate legacy active_magic to add-timed-effect before automatic rest recovery')
        # A normal tick does all expiry/due checks for this party once. It does
        # not assume every companion also slept or restore their resources.
        import argparse
        result = self.capture(self.g['cmd_tick'], argparse.Namespace(
            campaign=s['campaign'], pc=None, storyline=s['id'],
            to=None, minutes=round(args.hours * 60), rewind=False, set_date=None))
        if not result.get('success'):
            self.fail(result.get('error', 'Could not advance rest'))
        with self.g['get_driver']() as driver:
            s.update(self.read(driver, s['id'], s['campaign']))
            c = self.g['_load_character'](driver, args.id)
            ex = c.get('myth-extras-json') or {}
            effects, reserved, _ = effect_state(ex, self.minute(s))
            ex['timed_effects'] = effects
            maximum = (c.get('myth-attributes-json') or {}).get('magic_points',
                        (c.get('myth-characteristics-json') or {}).get('POW', 0))
            cap = max(0, maximum - reserved)
            old = c.get('myth-magic-current') or 0
            mp = cap if args.kind == 'full' else min(cap, old + int(args.hours * 4))
            # Do not silently grant recovery through lingering legacy effects.
            legacy = [e for e in ex.get('active_magic', []) if e.get('active') is not False
                      and not e.get('clock_migrated')]
            if legacy:
                self.fail('Migrate legacy active_magic to add-timed-effect before automatic rest recovery')
            self.g['_set_attr'](driver, 'myth-character', args.id, 'myth-extras-json', json.dumps(ex))
            self.g['_set_attr'](driver, 'myth-character', args.id, 'myth-magic-current', mp, quote=False)
            if args.kind == 'full':
                self.g['_set_attr'](driver, 'myth-character', args.id, 'myth-fatigue', 'Fresh')
        self.g['out']({'success': True, 'id': args.id, 'magic_current': mp,
                       'reserved_mp': reserved, 'luck_current': c.get('myth-luck-current'),
                       'elapsed_minutes': round(args.hours * 60), 'tick': result})

    @staticmethod
    def capture(fn, args):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(args)
        return json.loads(buf.getvalue().splitlines()[-1])

    def location_at(self, driver, cid):
        s = CURRENT.get()
        esc = self.g['escape_string']
        rows = self.g['_fetch'](driver, f'''match
          $c isa myth-character, has id "{esc(cid)}";
          (located: $c, location: $l) isa myth-presence;
          fetch {{ "id": $l.id, "name": $l.name }};''')
        current = rows[0] if rows else None
        if s:
            h = self.raw_get(driver, 'myth-character', cid, ['myth-state-history-json']) or {}
            history = decode(h.get('myth-state-history-json'), {})
            if '@location' in history:
                return history_value(history['@location'], self.minute(s))
        return current

    def record_character(self, driver, cid, field, before, after):
        s = CURRENT.get()
        h = self.raw_get(driver, 'myth-character', cid, ['myth-state-history-json']) or {}
        history = decode(h.get('myth-state-history-json'), {})
        values = history.setdefault(field, {'baseline': before, 'versions': []})
        minute = self.minute(s)
        versions = [v for v in values['versions'] if v['minute'] != minute]
        versions.append({'minute': minute, 'value': after, 'storyline': s['id']})
        versions.sort(key=lambda v: v['minute'])
        values['versions'] = versions
        self.raw_set(driver, 'myth-character', cid, 'myth-state-history-json', json.dumps(history))
        return minute >= versions[-1]['minute']

    def project_present(self, driver, loc):
        s = CURRENT.get()
        if not s:
            return None
        esc = self.g['escape_string']
        rows = self.g['_fetch'](driver, f'''match
          $c isa myth-campaign, has id "{esc(s['campaign'])}";
          (campaign: $c, element: $p) isa myth-campaign-membership;
          $p isa myth-character, has id $i, has name $n;
          fetch {{ "id": $i, "name": $n }};''')
        return sorted(r['name'] for r in rows if (self.location_at(driver, r['id']) or {}).get('id') == loc)


def history_value(series, minute):
    values = [v for v in series.get('versions', []) if v['minute'] <= minute]
    return max(values, key=lambda v: v['minute'])['value'] if values else series.get('baseline')


def install(ns):
    """Install one temporal boundary shared by CLI and in-process callers.

    The scoped campaign read model overlays only scene/clock/session/arc/member
    fields. Actual campaign identity, rules, lore and high-water time remain
    shared. Private raw methods in Store are used only for migration/admin.
    """
    store = Store(ns)
    ns['_storyline_store'] = store
    ns['_scope_events'] = store.scope_events
    ns['_location_at'] = store.location_at
    ns['_storyline_present'] = store.project_present
    ns['_current_storyline'] = CURRENT.get
    raw_out = ns['out']

    def out(obj):
        s = CURRENT.get()
        if s and isinstance(obj, dict):
            obj = dict(obj)
            obj['storyline'] = store.clock_payload(s)
            with ns['get_driver']() as driver:
                world = store.raw_get(driver, 'myth-campaign', s['campaign'], ['myth-time-index'])
            obj['world_high_water'] = ns['eng'].format_time_key(world['myth-time-index']) if world and world.get('myth-time-index') is not None else None
            cards = obj.get('player_characters', [])
            if 'character' in obj and isinstance(obj['character'], dict):
                cards = cards + [obj['character']]
            for card in cards:
                cid = card.get('id')
                if cid not in csv(s.get('myth-played-pcs')):
                    continue
                with ns['get_driver']() as driver:
                    c = ns['_load_character'](driver, cid)
                ex = c.get('myth-extras-json') or {}
                effects, reserved, lodging = effect_state(ex, store.minute(s))
                prepaid = False
                if lodging.get('through'):
                    try:
                        end = (ns['eng'].parse_time_key(lodging['through']) + 1) * 360
                        prepaid = bool(lodging.get('key_held') and store.minute(s) < end)
                    except ValueError:
                        pass
                card['clock_status'] = {'timed_effects': effects, 'reserved_mp': reserved,
                    'lodging': {'paid_through': lodging.get('through'), 'prepaid_active': prepaid}}
        raw_out(obj)
    ns['out'] = out

    def get(driver, etype, eid, attrs):
        value = store.raw_get(driver, etype, eid, attrs)
        s = CURRENT.get()
        if value and s and etype == 'myth-campaign' and eid == s['campaign']:
            value.update({k: s.get(k) for k in attrs if k in FIELDS})
        if value and s and etype == 'myth-character' and store.supported(driver):
            h = store.raw_get(driver, etype, eid, ['myth-state-history-json']) or {}
            history = decode(h.get('myth-state-history-json'), {})
            for k in attrs:
                if k in history:
                    value[k] = history_value(history[k], store.minute(s))
        return value
    ns['_get_entity'] = get

    def set_attr(driver, etype, eid, attr, value, quote=True):
        s = CURRENT.get()
        if s and etype == 'myth-campaign' and eid == s['campaign'] and attr in FIELDS:
            store.raw_set(driver, 'myth-storyline', s['id'], attr, value, quote)
            s[attr] = value
            return
        if s and etype == 'myth-character' and attr != 'myth-state-history-json':
            store.guard_pc(driver, eid)
            before = (get(driver, etype, eid, [attr]) or {}).get(attr)
            if not store.record_character(driver, eid, attr, before, value):
                return  # an earlier version never overwrites the latest state
        if s and etype in TAGGED:
            owner = store.owns(driver, etype, eid)
            if owner and owner != s['id']:
                store.fail('Cannot mutate another storyline record; use its selector or explicit world administration')
        store.raw_set(driver, etype, eid, attr, value, quote)
    ns['_set_attr'] = set_attr

    def link(driver, campaign, eid, etype):
        store.raw_link(driver, campaign, eid, etype)
        s = CURRENT.get()
        if s and etype in TAGGED:
            store.raw_set(driver, etype, eid, 'myth-storyline-id', s['id'])
            if etype in ('myth-game-event', 'myth-encounter', 'myth-agenda'):
                store.raw_set(driver, etype, eid, 'myth-time-index', s['myth-time-index'], quote=False)
            if etype == 'myth-game-event':
                store.raw_set(driver, etype, eid, 'myth-clock-minutes', store.minute(s), quote=False)
                store.raw_set(driver, etype, eid, 'myth-session-number', s.get('myth-session-number') or 0, quote=False)
    ns['_link_to_campaign'] = link

    def place(driver, cid, loc):
        s = CURRENT.get()
        if s:
            store.guard_pc(driver, cid)
            before = store.location_at(driver, cid)
            target = store.raw_get(driver, 'myth-location', loc, [])
            if not target:
                store.fail('No such location')
            if not store.record_character(driver, cid, '@location', before, target):
                return
        store.raw_place(driver, cid, loc)
    ns['_place_character'] = place

    store._raw_beats = ns['_campaign_beats']
    for fname, etype in [('_campaign_beats', 'myth-beat'),
                          ('_campaign_agendas', 'myth-agenda'),
                          ('_campaign_facts', 'myth-fact')]:
        raw = ns[fname]
        def records(driver, campaign, _raw=raw, _etype=etype):
            return store.filter_records(driver, _raw(driver, campaign), _etype, campaign)
        ns[fname] = records

    raw_edges = ns['_knowledge_edges']
    def edges(driver, campaign):
        rows = raw_edges(driver, campaign)
        s = CURRENT.get()
        return [r for r in rows if at_or_before(r.get('since'), s['myth-time-index'])] if s else rows
    ns['_knowledge_edges'] = edges
    raw_subjects = ns['_subject_knowledge_edges']
    def subjects(driver, knower_id=None, subject_id=None):
        rows = raw_subjects(driver, knower_id=knower_id, subject_id=subject_id)
        s = CURRENT.get()
        # Undated legacy interpretations are not safe historical evidence.
        return [r for r in rows if r.get('since') is not None and
                at_or_before(r['since'], s['myth-time-index'])] if s else rows
    ns['_subject_knowledge_edges'] = subjects

    raw_knowledge = ns['_write_knowledge']
    def write_knowledge(driver, knower, fact, certainty, source, since):
        s = CURRENT.get()
        if s:
            since = s['myth-time-index'] if since is None else since
            f = store.raw_get(driver, 'myth-fact', fact, ['myth-time-index'])
            if since > s['myth-time-index'] or (f and f.get('myth-time-index') is not None and f['myth-time-index'] > since):
                store.fail('Cannot learn a fact from the future of this storyline')
        return raw_knowledge(driver, knower, fact, certainty, source, since)
    ns['_write_knowledge'] = write_knowledge

    raw_presence = ns['_pc_presence']
    def pc_presence(driver, campaign):
        s = CURRENT.get()
        if not s:
            return raw_presence(driver, campaign)
        ids = csv(s.get('myth-played-pcs'))
        return ids, [(store.location_at(driver, p) or {}).get('id') for p in ids]
    ns['_pc_presence'] = pc_presence

    # Shared resolved beats are immutable outcomes, even when another party
    # encounters the same operation at its earlier date.
    raw_cascade = ns['_cascade']
    def cascade(driver, campaign, *args, **kwargs):
        s = CURRENT.get()
        world = store.raw_get(driver, 'myth-campaign', campaign, ['myth-time-index']) if s else None
        local = bool(s and world and world.get('myth-time-index') is not None
                     and s['myth-time-index'] < world['myth-time-index'])
        token = LOCAL_CASCADE.set(local)
        try:
            return raw_cascade(driver, campaign, *args, **kwargs)
        finally:
            LOCAL_CASCADE.reset(token)
    ns['_cascade'] = cascade

    raw_fire = ns['cmd_fire_beat']
    def fire(args):
        with ns['get_driver']() as driver:
            b = ns['_beat_record'](driver, args.id)
            if b and b['status'] in ('played', 'narrated', 'preempted', 'cancelled'):
                if b['status'] != args.outcome:
                    store.fail('Beat is already resolved; reconcile the existing outcome instead of replaying it')
                out({'success': True, 'id': args.id, 'outcome': b['status'], 'already_resolved': True})
                return
            s = CURRENT.get()
            if s and b and b.get('time_index') is not None and b['time_index'] > s['myth-time-index']:
                store.fail('Beat has not reached the selected storyline date')
        raw_fire(args)
    ns['cmd_fire_beat'] = fire

    raw_tick = ns['cmd_tick']
    def tick(args):
        s = CURRENT.get()
        delta = getattr(args, 'minutes', None)
        if not s:
            if delta is not None:
                store.fail('--minutes requires a storyline clock')
            return raw_tick(args)
        old_minute = store.minute(s)
        if delta is not None:
            if delta < 0 and not args.rewind:
                store.fail('Refusing to move storyline time backwards')
            minute = old_minute + delta
            args.to = ns['eng'].format_time_key(minute // 360)
        else:
            target_index = ns['eng'].parse_time_key(args.to)
            minute = old_minute if target_index == s['myth-time-index'] else target_index * 360
        if minute < old_minute and not args.rewind:
            store.fail('Refusing to move storyline time backwards')
        # No global cascade during an earlier camera: past play must not wake,
        # cancel or retire operations using another camera's future status.
        with ns['get_driver']() as driver:
            world = store.raw_get(driver, 'myth-campaign', s['campaign'], ['myth-time-index'])
        historical = world.get('myth-time-index') is not None and minute // 360 < world['myth-time-index']
        payload = store.capture(raw_tick, args)
        with ns['get_driver']() as driver:
            set_attr(driver, 'myth-campaign', s['campaign'], 'myth-clock-minutes', minute, quote=False)
            set_attr(driver, 'myth-campaign', s['campaign'], 'myth-game-date', args.to)
            # High-water is monotonic, even under an explicit local correction.
            high = world.get('myth-time-index')
            if high is None or minute // 360 > high:
                store.raw_set(driver, 'myth-campaign', s['campaign'], 'myth-time-index', minute // 360, quote=False)
            expired = []
            for cid in csv(s.get('myth-played-pcs')):
                c = ns['_load_character'](driver, cid)
                ex = c.get('myth-extras-json') or {}
                effects, _, _ = effect_state(ex, minute)
                expired.extend({'pc': cid, 'id': e['id'], 'name': e['name']} for old, e in zip(ex.get('timed_effects', []), effects) if old.get('active', True) and not e['active'])
                if effects != ex.get('timed_effects', []):
                    ex['timed_effects'] = effects
                    set_attr(driver, 'myth-character', cid, 'myth-extras-json', json.dumps(ex))
            # Present existing shared outcomes to the GM, not to the party's
            # knowledge; they cannot be rolled again in this camera.
            all_beats = store._raw_beats(driver, s['campaign'])
            payload['resolved_shared_events'] = [
                {'id': b['id'], 'title': b['title'], 'outcome': b['status'], 'when': b.get('when')}
                for b in all_beats if b['status'] in ('played', 'narrated')
                and b.get('time_index') is not None and old_minute // 360 < b['time_index'] <= minute // 360
                and store.owns(driver, 'myth-beat', b['id']) is None]
        payload['expired_effects'] = expired
        payload['historical_camera'] = historical
        payload['minute_in_watch'] = minute % 360
        out(payload)
    ns['cmd_tick'] = tick

    ns['cmd_create_storyline'] = store.create
    ns['cmd_list_storylines'] = store.list_command
    ns['cmd_update_storyline'] = store.update
    ns['cmd_assign_storyline'] = store.assign
    ns['cmd_assign_storyline_record'] = lambda args: assign_record(store, args)
    ns['cmd_split_storyline'] = lambda args: split_storyline(store, args)
    ns['cmd_add_timed_effect'] = store.add_effect
    ns['cmd_rest_character'] = store.rest
    ns['cmd_dismiss_effect'] = lambda args: dismiss_effect(store, args)

    # Scope selection is per invocation, not process-global, which also keeps
    # direct handler calls and nested rest->tick commands isolated in tests.
    for key, fn in list(ns.items()):
        if not key.startswith('cmd_') or not callable(fn):
            continue
        name = key[4:]
        def wrap(args, _fn=fn, _name=name):
            selected = store.select(args, _name)
            token = CURRENT.set(selected)
            try:
                if selected:
                    encounter_commands = {'get_encounter', 'add_combatant', 'roll_initiative', 'attack_roll',
                        'resolve_attack', 'resolve_effects', 'next_round', 'end_encounter'}
                    if _name == 'get_fact':
                        with ns['get_driver']() as driver:
                            f = store.raw_get(driver, 'myth-fact', args.id, ['myth-time-index', 'myth-fact-status'])
                        if f and f.get('myth-fact-status') == 'established' and not at_or_before(f.get('myth-time-index'), selected['myth-time-index']):
                            store.fail('Fact is in the future of this storyline')
                    if _name in encounter_commands:
                        eid = getattr(args, 'encounter', None) or getattr(args, 'id', None)
                        with ns['get_driver']() as driver:
                            e = store.raw_get(driver, 'myth-encounter', eid, ['myth-storyline-id', 'myth-time-index'])
                        if e and (e.get('myth-storyline-id') not in (None, selected['id'])
                                  or not at_or_before(e.get('myth-time-index'), selected['myth-time-index'])):
                            store.fail('Encounter is outside the selected storyline or in its future')
                    if getattr(args, 'since', None) is not None and args.since > selected['myth-time-index']:
                        store.fail('Cannot record future knowledge in this storyline')
                    if _name == 'update_campaign' and getattr(args, 'played', None) is not None and set(csv(args.played)) != set(csv(selected.get('myth-played-pcs'))):
                        store.fail('Use assign-storyline to change party membership')
                    if hasattr(args, 'since') and args.since is None:
                        args.since = selected['myth-time-index']
                    if _name in ('add_fact', 'establish_fact'):
                        if getattr(args, 'when', None) is None and getattr(args, 'status', 'established') == 'established':
                            args.when = ns['eng'].format_time_key(selected['myth-time-index'])
                        if getattr(args, 'when', None) and getattr(args, 'status', 'established') == 'established' and ns['eng'].parse_time_key(args.when) > selected['myth-time-index']:
                            store.fail('Cannot establish future truth in this storyline; use world administration')
                    if _name == 'update_event' and getattr(args, 'when', None):
                        with ns['get_driver']() as driver:
                            store.raw_set(driver, 'myth-game-event', args.id, 'myth-time-index', ns['eng'].parse_time_key(args.when), quote=False)
                return _fn(args)
            finally:
                CURRENT.reset(token)
        ns[key] = functools.wraps(fn)(wrap)
    return store


def add_parsers(sub):
    def campaign(p):
        p.add_argument('--campaign', help='defaults to $MYTHRAS_CAMPAIGN, or the only campaign in the database')
        return p
    p = campaign(sub.add_parser('create-storyline', help='Create an independent PC/party clock'))
    p.add_argument('--name', required=True)
    p.add_argument('--pcs', required=True, help='Comma-separated PC IDs; one storyline per PC')
    p.add_argument('--at', required=True, help='Actual local game date, not current global date')
    p.add_argument('--minute', type=int, default=0, choices=range(360), metavar='0..359')
    p.add_argument('--scene')
    p.add_argument('--session', type=int)
    p.add_argument('--arc-file')
    campaign(sub.add_parser('list-storylines', help='List local clocks and the shared high-water mark'))
    p = campaign(sub.add_parser('update-storyline', help='Correct storyline scene/date/session or load its arc'))
    p.add_argument('--id', required=True)
    p.add_argument('--scene')
    p.add_argument('--at')
    p.add_argument('--minute', type=int, default=0, choices=range(360), metavar='0..359')
    p.add_argument('--session', type=int)
    p.add_argument('--arc-file')
    p.add_argument('--rewind', action='store_true')
    p = campaign(sub.add_parser('assign-storyline', help='Join a party only when local clocks agree'))
    p.add_argument('--id', required=True)
    p.add_argument('--pcs', required=True)
    p = campaign(sub.add_parser('split-storyline', help='Give selected party members a new clock at the same time'))
    p.add_argument('--id', required=True, help='Source storyline ID/name')
    p.add_argument('--name', required=True, help='New storyline name')
    p.add_argument('--pcs', required=True)
    p.add_argument('--scene')
    p = campaign(sub.add_parser('assign-storyline-record', help='Backfill existing record ownership and optional actual game date'))
    ids = p.add_mutually_exclusive_group(required=True)
    ids.add_argument('--id')
    ids.add_argument('--ids', help='Comma-separated record IDs')
    p.add_argument('--to', required=True, help='Destination storyline ID/name, or world')
    p.add_argument('--when', help='Actual game date; omitted preserves existing date')
    p = campaign(sub.add_parser('add-timed-effect', help='Track a paid effect against its caster storyline clock'))
    p.add_argument('--id', required=True)
    p.add_argument('--name', required=True)
    p.add_argument('--minutes', type=int, required=True)
    p.add_argument('--reserved-mp', type=int, default=0)
    p = campaign(sub.add_parser('dismiss-effect', help='End this PC timed effect without refunding MP'))
    p.add_argument('--id', required=True)
    p.add_argument('--effect', required=True)
    p = campaign(sub.add_parser('rest-character', help='Advance local time and recover this PC only'))
    p.add_argument('--id', required=True)
    p.add_argument('--hours', type=float, required=True)
    p.add_argument('--kind', choices=['full', 'short'], default='full')
    p.add_argument('--safe', action='store_true')
    entity_commands = {'brief', 'update-character', 'move-character', 'apply-damage', 'heal',
        'award-experience', 'improve-skill', 'roll-skill', 'roll-opposed', 'get-agenda',
        'update-agenda', 'revise-beat', 'get-encounter', 'next-round', 'add-combatant',
        'attack-roll', 'resolve-effects', 'resolve-attack', 'roll-initiative', 'end-encounter',
        'update-event', 'revise-fact', 'forget', 'require-fact', 'add-consequence', 'retire-canon'}
    for command, p in sub.choices.items():
        if command in entity_commands and not any('--campaign' in a.option_strings for a in p._actions):
            p.add_argument('--campaign', help='defaults to $MYTHRAS_CAMPAIGN, or the only campaign in the database; used for storyline selection')
        p.add_argument('--storyline', help='Storyline ID/name, or world for explicit unscoped administration')
        p.add_argument('--pc', help='Select the storyline containing this PC ID')


def export_state(gm, campaign, outdir):
    """Native clocks and temporal metadata are part of a lossless save export."""
    import pathlib
    store = gm._storyline_store
    with gm.get_driver() as driver:
        stories = store.list(driver, campaign)
        tags = {}
        for etype in TAGGED:
            rows = store.metadata(driver, etype, campaign)
            tags[etype] = []
            for eid, owner in rows.items():
                rec = store.raw_get(driver, etype, eid, ['myth-time-index'] + (['myth-clock-minutes'] if etype == 'myth-game-event' else [])) or {}
                if owner or rec.get('myth-time-index') is not None:
                    tags[etype].append({'id': eid, 'storyline': owner,
                                        'time_index': rec.get('myth-time-index'), 'clock_minutes': rec.get('myth-clock-minutes')})
        histories = gm._fetch(driver, f'''match
          $c isa myth-campaign, has id "{gm.escape_string(campaign)}";
          (campaign: $c, element: $p) isa myth-campaign-membership;
          $p isa myth-character, has id $i, has myth-state-history-json $h;
          fetch {{ "id": $i, "history": $h }};''') if store.supported(driver) else []
    payload = {'version': 1, 'storylines': stories, 'metadata': tags,
               'character_histories': [{'id': r['id'], 'history': decode(r['history'], {})} for r in histories]}
    pathlib.Path(outdir, 'storylines.json').write_text(json.dumps(payload, indent=2) + '\n')


def import_state(gm, payload, campaign, idmap):
    def remap(value):
        if isinstance(value, str):
            if value.startswith(('{', '[')):
                try:
                    return json.dumps(remap(json.loads(value)))
                except ValueError:
                    pass
            return idmap.get(value, value)
        if isinstance(value, list):
            return [remap(v) for v in value]
        if isinstance(value, dict):
            return {idmap.get(k, k): remap(v) for k, v in value.items()}
        return value
    store = gm._storyline_store
    with gm.get_driver() as driver:
        if payload.get('storylines') and not store.supported(driver):
            gm.fail('Import contains storyline clocks; load-schema before importing')
        for old in payload.get('storylines', []):
            r = remap(old)
            sid = r['id']
            gm._write(driver, f'''insert $s isa myth-storyline,
              has id "{gm.escape_string(sid)}", has name "{gm.escape_string(r['name'])}";''')
            store.raw_link(driver, campaign, sid, 'myth-storyline')
            for attr in FIELDS:
                val = r.get(attr)
                if val is None:
                    continue
                if attr == 'myth-played-pcs':
                    val = ','.join(idmap.get(x, x) for x in csv(old.get(attr)))
                elif attr.endswith('-json'):
                    val = json.dumps(remap(decode(old.get(attr), {} if attr.endswith('state-json') else [])))
                store.raw_set(driver, 'myth-storyline', sid, attr, val,
                              quote=attr not in ('myth-time-index', 'myth-clock-minutes', 'myth-session-number'))
        for etype, rows in payload.get('metadata', {}).items():
            if etype not in TAGGED:
                continue
            for old in rows:
                r = remap(old)
                if r.get('storyline'):
                    store.raw_set(driver, etype, r['id'], 'myth-storyline-id', r['storyline'])
                if etype == 'myth-game-event' and r.get('clock_minutes') is not None:
                    store.raw_set(driver, etype, r['id'], 'myth-clock-minutes', r['clock_minutes'], quote=False)
                if r.get('time_index') is not None:
                    store.raw_set(driver, etype, r['id'], 'myth-time-index', r['time_index'], quote=False)
        for r in payload.get('character_histories', []):
            store.raw_set(driver, 'myth-character', idmap.get(r['id'], r['id']),
                          'myth-state-history-json', json.dumps(remap(r['history'])))


def assign_record(store, args):
    """Explicit ownership/date backfill for existing records, never implicit cloning."""
    ids = csv(args.ids or args.id)
    with store.g['get_driver']() as driver:
        stories = store.list(driver, args.campaign)
        target = next((s for s in stories if args.to in (s['id'], s['name'])), None)
        if args.to != 'world' and not target:
            store.fail('No destination storyline in this campaign')
        records = []
        esc = store.g['escape_string']
        for eid in ids:
            etype = store.g['_resolve_entity_type'](driver, eid, TAGGED)
            if not etype:
                store.fail(f'{eid} is not an event, operation, encounter or fact')
            linked = store.g['_fetch'](driver, f'''match
              $c isa myth-campaign, has id "{esc(args.campaign)}";
              $e isa {etype}, has id "{esc(eid)}";
              (campaign: $c, element: $e) isa myth-campaign-membership;
              fetch {{ "id": $e.id }};''')
            if not linked:
                store.fail('Record is not in this campaign')
            records.append((eid, etype))
        for eid, etype in records:
            if target:
                store.raw_set(driver, etype, eid, 'myth-storyline-id', target['id'])
            else:
                store.g['_write'](driver, f'''match $e isa {etype}, has id "{esc(eid)}", has myth-storyline-id $s;
                  delete has $s of $e;''')
            if args.when:
                store.raw_set(driver, etype, eid, 'myth-time-index', store.g['eng'].parse_time_key(args.when), quote=False)
    store.g['out']({'success': True, 'assigned': ids, 'to': target['id'] if target else 'world'})


def dismiss_effect(store, args):
    s = CURRENT.get()
    if not s or args.id not in csv(s.get('myth-played-pcs')):
        store.fail('Select the effect owner storyline and a member PC')
    with store.g['get_driver']() as driver:
        c = store.g['_load_character'](driver, args.id)
        ex = c.get('myth-extras-json') or {}
        found = next((e for e in ex.get('timed_effects', []) if e['id'] == args.effect), None)
        if not found:
            store.fail('No such timed effect for this PC')
        found.update(active=False, ended_at_minute=store.minute(s), ended_reason='dismissed', remaining_minutes=0)
        store.g['_set_attr'](driver, 'myth-character', args.id, 'myth-extras-json', json.dumps(ex))
    store.g['out']({'success': True, 'id': args.effect, 'dismissed': True,
                   'magic_current': c.get('myth-magic-current'),
                   'recovery_note': 'Dismissal frees reserved capacity; it does not refund spent MP'})


def split_storyline(store, args):
    members = csv(args.pcs)
    with store.g['get_driver']() as driver:
        stories = store.list(driver, args.campaign)
        source = next((s for s in stories if args.id in (s['id'], s['name'])), None)
        if not source or not members or not set(members).issubset(csv(source.get('myth-played-pcs'))):
            store.fail('Split PCs must belong to the source storyline')
        if any(s['name'] == args.name for s in stories):
            store.fail('Storyline name already exists')
        sid = store.g['generate_id']('myth-storyline')
        esc = store.g['escape_string']
        fields = {k: source[k] for k in FIELDS if source.get(k) is not None}
        fields['myth-played-pcs'] = ','.join(members)
        if args.scene is not None:
            fields['myth-current-scene'] = args.scene
        state = decode(fields.get('myth-storyline-state-json'), {})
        state.setdefault('history_storylines', []).append({'id': source['id'], 'through_minute': store.minute(source)})
        fields['myth-storyline-state-json'] = json.dumps(state)
        attrs = []
        for attr, val in fields.items():
            literal = str(val) if attr in ('myth-time-index','myth-clock-minutes','myth-session-number') else '"' + esc(val) + '"'
            attrs.append(f'has {attr} {literal}')
        remain = ','.join(p for p in csv(source.get('myth-played-pcs')) if p not in members)
        store.g['_write'](driver,
            f'insert $s isa myth-storyline, has id "{sid}", has name "{esc(args.name)}", ' + ', '.join(attrs) + ';',
            f'''match $s isa myth-storyline, has id "{esc(source['id'])}", has myth-played-pcs $p;
                delete has $p of $s;''',
            f'''match $s isa myth-storyline, has id "{esc(source['id'])}";
                insert $s has myth-played-pcs "{esc(remain)}";''')
        store.raw_link(driver, args.campaign, sid, 'myth-storyline')
    store.g['out']({'success': True, 'id': sid, 'split': members,
                   'at': store.g['eng'].format_time_key(source['myth-time-index'])})
