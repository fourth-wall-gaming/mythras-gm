"""Sagas, adventures and fixed history: the structure a storyline is played in.

A storyline's arc holds one act outline at a time, so before this module every
new adventure overwrote the last one and nothing recorded where an adventure
began or ended. Here each storyline keeps:

- a **saga line**, one sentence saying what this protagonist's story is about,
  which every adventure answers to;
- its **adventures**, each moving pitch -> chosen -> prepared -> active ->
  concluded, with the outline kept after the adventure ends;
- a **fixed-history** check, because a storyline behind another one is playing
  dates that are already partly written.

Everything lives in the storyline's state document, so exports, imports and
splits carry it without a schema change. No dice or PC decisions are made here.
"""
from __future__ import annotations

import json

from storyline_tools import CURRENT, decode

STATUSES = ('proposed', 'chosen', 'prepared', 'active', 'concluded', 'abandoned', 'declined')
# Where an adventure may go next. Ending states are terminal: a finished
# adventure is history, and a new one is proposed rather than reopened.
NEXT = {'proposed': {'chosen', 'declined'},
        'chosen': {'prepared', 'declined'},
        'prepared': {'active', 'chosen', 'declined'},
        'active': {'concluded', 'abandoned'},
        'declined': {'proposed'},
        'concluded': set(), 'abandoned': set()}
ENDED = ('concluded', 'abandoned')
SHOWN = 8  # fixed-history lines carried on tick; the command gives the rest


def install(ns):
    """Register the commands. Must run before storyline_tools.install wraps them."""

    def store():
        return ns['_storyline_store']

    def selected(command):
        s = CURRENT.get()
        if not s:
            ns['fail'](f'{command} needs a storyline: select --pc ID or --storyline NAME/ID '
                       '(create-storyline first; a single PC gets one too)')
        return s

    def key(index):
        return ns['eng'].format_time_key(index) if index is not None else None

    def save(driver, s, state):
        store().save_state(driver, s, state)

    def find(state, aid):
        hits = [a for a in state.get('adventures', []) if aid in (a['id'], a['title'])]
        if len(hits) != 1:
            ns['fail'](f'No unique adventure {aid!r} in this storyline; list-adventures shows them')
        return hits[0]

    def span(acts):
        lo = [a['index_from'] for a in acts if a.get('index_from') is not None]
        hi = [a['index_to'] for a in acts if a.get('index_to') is not None]
        return (min(lo) if lo else None, max(hi) if hi else None)

    def arc_from(path):
        return store().parse_arc(path)

    # -- fixed history --------------------------------------------------------
    def fixed(driver, s, lo_minute, hi_minute):
        """What other storylines have already made true in (lo, hi]."""
        st = store()
        esc = ns['escape_string']
        others = [o for o in st.list(driver, s['campaign']) if o['id'] != s['id']]
        lineage = {h['id'] for h in st.state(s).get('history_storylines', [])}
        result = []
        for o in others:
            if o['id'] in lineage:
                continue  # its past up to the split is this party's own history
            o_minute = st.minute(o)
            if o_minute <= lo_minute:
                continue
            rows = ns['_fetch'](driver, f'''match
              $e isa myth-game-event, has id $i, has description $d,
                 has myth-storyline-id "{esc(o['id'])}", has myth-time-index $ti;
              try {{ $e has myth-clock-minutes $mi; }};
              try {{ $e has myth-event-visibility $v; }};
              try {{ $e has myth-canon-status $cs; }};
              fetch {{ "id": $i, "summary": $d, "time_index": $ti, "clock_minutes": $mi,
                       "visibility": $v, "canon": $cs }};''')
            events = []
            for r in rows:
                m = r['clock_minutes'] if r.get('clock_minutes') is not None else r['time_index'] * 360
                if not (lo_minute < m <= hi_minute):
                    continue
                if r.get('canon') not in (None, 'live') or r.get('visibility') == 'meta':
                    continue
                events.append({'id': r['id'], 'when': key(m // 360), 'minute': m,
                               'visibility': r.get('visibility') or 'played', 'summary': r['summary']})
            events.sort(key=lambda e: e['minute'])
            overlapping = []
            for a in st.state(o).get('adventures', []):
                if a['status'] not in ('active',) + ENDED or a.get('started_minute') is None:
                    continue
                end = a.get('ended_minute', o_minute)
                if a['started_minute'] <= hi_minute and end > lo_minute:
                    overlapping.append({'title': a['title'], 'status': a['status'],
                                        'from': key(a['started_minute'] // 360), 'to': key(end // 360),
                                        'outcome': a.get('outcome')})
            if events or overlapping:
                result.append({'storyline': o['name'], 'id': o['id'], 'now': key(o['myth-time-index']),
                               'pcs': o.get('myth-played-pcs'), 'adventures': overlapping,
                               'events': events})
        return result

    def fixed_summary(found):
        return [{'storyline': f['storyline'], 'now': f['now'], 'adventures': f['adventures'],
                 'events': len(f['events']), 'first': [e['summary'] for e in f['events'][:SHOWN]]}
                for f in found]

    # -- what rides on get-context, forecast and tick -------------------------
    def summary(driver, s):
        """The saga line and the adventure in play, carried with the arc.

        For the same reason as the arc: what this protagonist's story is FOR
        must not decay out of context between sessions.
        """
        st = store()
        state = st.state(s)
        saga = state.get('saga') or {}
        advs = state.get('adventures', [])
        active = next((a for a in advs if a['status'] == 'active'), None)
        payload = {'saga': saga.get('line') or
                   'NO SAGA LINE. Agree one sentence with the player on what this '
                   "protagonist's story is about: `set-saga --line ...`."}
        if active:
            payload['adventure'] = {'id': active['id'], 'title': active['title'],
                                    'since': key(active['started_minute'] // 360),
                                    'pitch': active.get('pitch')}
        else:
            last = next((a for a in reversed(advs) if a['status'] in ENDED), None)
            waiting = [a['title'] for a in advs if a['status'] in ('proposed', 'chosen', 'prepared')]
            payload['adventure'] = {
                'status': 'between adventures',
                'last': {'title': last['title'], 'outcome': last.get('outcome')} if last else None,
                'waiting': waiting,
                'guidance': 'Downtime, then pitch the next adventure (BRAINSTORMING.md), '
                            'let the player choose, prepare it (SCENARIO.md) and '
                            '`update-adventure --status active`. Do not improvise a new '
                            'plot into the gap.'}
        ahead = [{'storyline': o['name'], 'now': key(o['myth-time-index'])}
                 for o in st.list(driver, s['campaign'])
                 if o['id'] != s['id'] and st.minute(o) > st.minute(s)]
        if ahead:
            payload['clocks_ahead'] = {
                'storylines': ahead,
                'guidance': 'These protagonists have already played dates after yours. '
                            'What they made true is fixed: run `fixed-history` before '
                            'preparing an adventure or ticking into their dates.'}
        return payload
    ns['_adventure_summary'] = summary
    ns['_fixed_history'] = fixed
    ns['_fixed_summary'] = fixed_summary

    # -- commands -------------------------------------------------------------
    def set_saga(args):
        s = selected('set-saga')
        with ns['get_driver']() as driver:
            state = store().state(s)
            old = state.get('saga')
            history = (old or {}).get('history', [])
            if old and old.get('line'):
                history.append({'line': old['line'], 'set': old.get('set'),
                                'replaced': ns['get_timestamp'](), 'at': key(s['myth-time-index'])})
            state['saga'] = {'line': args.line, 'set': ns['get_timestamp'](),
                             'at': key(s['myth-time-index']), 'history': history}
            save(driver, s, state)
        ns['out']({'success': True, 'saga': args.line, 'previous': [h['line'] for h in history]})

    def add_adventure(args):
        s = selected('add-adventure')
        status = args.status
        if status not in ('proposed', 'active') + ENDED:
            ns['fail']('add-adventure records a new pitch (proposed), adopts the adventure '
                       'already in play (active), or backfills a finished one (concluded/abandoned)')
        with ns['get_driver']() as driver:
            st = store()
            state = st.state(s)
            advs = state.setdefault('adventures', [])
            if any(a['title'] == args.title for a in advs):
                ns['fail']('An adventure with that title already exists in this storyline')
            now = st.minute(s)
            a = {'id': ns['generate_id']('myth-adventure'), 'title': args.title,
                 'pitch': args.pitch, 'status': status, 'proposed': ns['get_timestamp'](),
                 'plan': [x.strip() for x in (args.plan or '').split(',') if x.strip()],
                 'arc': arc_from(args.arc_file) if args.arc_file else [],
                 'history': [{'status': status, 'real': ns['get_timestamp'](), 'at': key(s['myth-time-index'])}]}
            if status == 'active':
                if any(x['status'] == 'active' for x in advs):
                    ns['fail']('This storyline already has an adventure in play; conclude it first')
                if not args.started:
                    ns['fail']('Adopting the adventure in play needs --started (the game date it began)')
                a['started_minute'] = ns['eng'].parse_time_key(args.started) * 360
                # Adopt the outline already loaded rather than demand a new one.
                if not a['arc']:
                    a['arc'] = decode(s.get('myth-arc-json'), [])
                else:
                    st.raw_set(driver, 'myth-storyline', s['id'], 'myth-arc-json', json.dumps(a['arc']))
                    s['myth-arc-json'] = json.dumps(a['arc'])
            if status in ENDED:
                if not (args.started and args.ended and args.outcome):
                    ns['fail']('Backfilling a finished adventure needs --started, --ended and --outcome')
                a['started_minute'] = ns['eng'].parse_time_key(args.started) * 360
                a['ended_minute'] = ns['eng'].parse_time_key(args.ended) * 360
                if a['ended_minute'] > now:
                    ns['fail']("An adventure cannot have ended after this storyline's own date")
                a['outcome'] = args.outcome
            if a.get('started_minute') is not None and a['started_minute'] > now:
                ns['fail']("An adventure cannot have started after this storyline's own date")
            advs.append(a)
            # Keep the record in play order; proposals sort after everything played.
            advs.sort(key=lambda x: (x.get('started_minute') is None, x.get('started_minute') or 0))
            save(driver, s, state)
        ns['out']({'success': True, 'id': a['id'], 'title': a['title'], 'status': status})

    def update_adventure(args):
        s = selected('update-adventure')
        with ns['get_driver']() as driver:
            st = store()
            state = st.state(s)
            advs = state.setdefault('adventures', [])
            a = find(state, args.id)
            for field in ('pitch', 'outcome'):
                if getattr(args, field) is not None:
                    a[field] = getattr(args, field)
            if args.title is not None:
                a['title'] = args.title
            if args.plan is not None:
                a['plan'] = list(dict.fromkeys(a.get('plan', []) + [x.strip() for x in args.plan.split(',') if x.strip()]))
            if args.arc_file:
                a['arc'] = arc_from(args.arc_file)
                if a['status'] == 'active':
                    st.raw_set(driver, 'myth-storyline', s['id'], 'myth-arc-json', json.dumps(a['arc']))
            result = {'success': True, 'id': a['id'], 'title': a['title']}
            to = args.status
            if to and to != a['status']:
                if to not in NEXT[a['status']]:
                    ns['fail'](f"An adventure that is {a['status']} cannot become {to}; "
                               f"next: {', '.join(sorted(NEXT[a['status']])) or 'nothing (it has ended)'}")
                now = st.minute(s)
                if to == 'prepared':
                    if not a.get('arc'):
                        ns['fail']('Preparing needs the act outline: --arc-file (SCENARIO.md section 5)')
                    lo, hi = span(a['arc'])
                    if hi is not None and hi * 360 + 359 > now:
                        result['fixed_history'] = fixed_summary(
                            fixed(driver, s, max(now, (lo or 0) * 360 - 1), hi * 360 + 359))
                    result['readiness'] = ('Run the readiness check (SCENARIO.md section 9) and '
                                           'read the saved records back before activating.')
                if to == 'active':
                    if not (state.get('saga') or {}).get('line'):
                        ns['fail']('Set the saga line first (set-saga): an adventure answers to it')
                    if any(x['status'] == 'active' for x in advs if x is not a):
                        ns['fail']('This storyline already has an adventure in play; conclude it first')
                    a['started_minute'] = now
                    st.raw_set(driver, 'myth-storyline', s['id'], 'myth-arc-json', json.dumps(a['arc']))
                if to in ENDED:
                    if not a.get('outcome'):
                        ns['fail']('Ending an adventure needs --outcome: what it settled, in a sentence or two')
                    # Keep the outline as it stood at the end, revisions included.
                    a['arc'] = decode(s.get('myth-arc-json'), []) or a.get('arc', [])
                    a['ended_minute'] = now
                    st.raw_set(driver, 'myth-storyline', s['id'], 'myth-arc-json', '[]')
                    result['saga'] = (state.get('saga') or {}).get('line')
                    result['next'] = ('Downtime, then pitch the next adventure. Ask whether the '
                                      'saga line still holds; set-saga revises it and keeps the old one.')
                a['status'] = to
                a.setdefault('history', []).append({'status': to, 'real': ns['get_timestamp'](),
                                                    'at': key(now // 360)})
                result['status'] = to
            advs.sort(key=lambda x: (x.get('started_minute') is None, x.get('started_minute') or 0))
            save(driver, s, state)
        ns['out'](result)

    def list_adventures(args):
        s = selected('list-adventures')
        state = store().state(s)
        rows = []
        for a in state.get('adventures', []):
            row = {k: a.get(k) for k in ('id', 'title', 'status', 'pitch', 'outcome', 'plan')}
            row['from'] = key(a['started_minute'] // 360) if a.get('started_minute') is not None else None
            row['to'] = key(a['ended_minute'] // 360) if a.get('ended_minute') is not None else None
            row['acts'] = (a.get('arc') if args.full else
                           [f"{x['act']}. {x['title']}" for x in a.get('arc', [])])
            rows.append(row)
        saga = state.get('saga') or {}
        ns['out']({'success': True, 'saga': saga.get('line'),
                   'earlier_sagas': [h['line'] for h in saga.get('history', [])],
                   'adventures': rows})

    def fixed_history(args):
        s = selected('fixed-history')
        st = store()
        with ns['get_driver']() as driver:
            if args.through:
                hi = ns['eng'].parse_time_key(args.through) * 360 + 359
            else:
                hi = max([st.minute(o) for o in st.list(driver, s['campaign'])] + [st.minute(s)])
            found = fixed(driver, s, st.minute(s), hi)
        ns['out']({'success': True, 'from': key(s['myth-time-index']), 'through': key(hi // 360),
                   'fixed': found,
                   'guidance': 'GM eyes only: this grants no knowledge. These outcomes are '
                               'canon. Play into them, or reconcile explicitly; never '
                               'contradict them silently.'})

    ns['cmd_set_saga'] = set_saga
    ns['cmd_add_adventure'] = add_adventure
    ns['cmd_update_adventure'] = update_adventure
    ns['cmd_list_adventures'] = list_adventures
    ns['cmd_fixed_history'] = fixed_history


def add_parsers(sub):
    """Before storyline_tools.add_parsers, which adds --pc/--storyline to every command."""
    def campaign(p):
        p.add_argument('--campaign', help='defaults to $MYTHRAS_CAMPAIGN, or the only campaign in the database')
        return p
    p = campaign(sub.add_parser('set-saga', help="Set this storyline's saga line; the old one is kept"))
    p.add_argument('--line', required=True, help="One sentence: what this protagonist's story is about")
    p = campaign(sub.add_parser('add-adventure', help='Record a pitch, adopt the adventure in play, or backfill a finished one'))
    p.add_argument('--title', required=True)
    p.add_argument('--pitch', help='The public premise, as pitched to the player')
    p.add_argument('--status', default='proposed', choices=('proposed', 'active') + ENDED)
    p.add_argument('--arc-file', help='Act outline (# ACT headings), as for update-storyline')
    p.add_argument('--plan', help='Comma-separated GM lore IDs holding the preparation')
    p.add_argument('--started', help='Game date it began (adopting or backfilling)')
    p.add_argument('--ended', help='Game date it ended (backfilling)')
    p.add_argument('--outcome', help='What it settled (backfilling)')
    p = campaign(sub.add_parser('update-adventure', help='Move an adventure through pitch, choice, preparation, play and conclusion'))
    p.add_argument('--id', required=True, help='Adventure ID or exact title')
    p.add_argument('--status', choices=STATUSES)
    p.add_argument('--title')
    p.add_argument('--pitch')
    p.add_argument('--arc-file')
    p.add_argument('--plan', help='Comma-separated GM lore IDs to add')
    p.add_argument('--outcome', help='Required to conclude or abandon')
    p = campaign(sub.add_parser('list-adventures', help="This storyline's saga line and every adventure, past and pending"))
    p.add_argument('--full', action='store_true', help='Include each kept act outline')
    p = campaign(sub.add_parser('fixed-history', help='What other storylines have already made true in dates this one has not reached'))
    p.add_argument('--through', help='Look as far as this date (default: the furthest storyline clock)')
