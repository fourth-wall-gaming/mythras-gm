"""Independent PC clocks against a disposable TypeDB database, never a live save."""
import contextlib
import io
import json

import pytest
import mythras_gm as gm
import storyline_tools as st


def call(cmd, ok=True, **flags):
    argv = [cmd]
    for k, v in flags.items():
        if v is None or v is False:
            continue
        argv.append('--' + k.replace('_', '-'))
        if v is not True:
            argv.append(str(v))
    args = gm.build_parser().parse_args(argv)
    gm._resolve_aliases(args)
    out = io.StringIO()
    exit_code = 0
    try:
        with contextlib.redirect_stdout(out):
            getattr(gm, 'cmd_' + cmd.replace('-', '_'))(args)
    except SystemExit as e:
        exit_code = e.code
    result = json.loads(out.getvalue().splitlines()[-1])
    if ok:
        assert exit_code == 0, result
        assert result.get('success'), result
    else:
        assert result.get('success') is False, result
    return result


@pytest.fixture
def world(throwaway_database):
    if throwaway_database is None:
        pytest.skip('TypeDB required')
    c = call('create-campaign', name='Storyline regression')['id']
    stats = json.dumps(dict(STR=11, CON=12, SIZ=11, DEX=12, INT=14, POW=15, CHA=12))
    a = call('create-character', campaign=c, name='Nimras test', type='pc', species='humanoid', stats=stats)['id']
    b = call('create-character', campaign=c, name='Hrill test', type='pc', species='humanoid', stats=stats)['id']
    npc = call('create-character', campaign=c, name='Shared host', type='npc', species='humanoid', stats=stats)['id']
    x = call('add-location', campaign=c, name='First house')['id']
    y = call('add-location', campaign=c, name='Second house')['id']
    call('tick', campaign=c, to='d23/day')
    sa = call('create-storyline', campaign=c, name='Nimras', pcs=a, at='d8/day', scene='A scene', session=8)['id']
    sb = call('create-storyline', campaign=c, name='Hrill', pcs=b, at='d23/day', scene='B scene', session=12)['id']
    return dict(campaign=c, a=a, b=b, npc=npc, x=x, y=y, sa=sa, sb=sb)


def test_independent_clocks_scene_and_high_water(world):
    w = world; c = w['campaign']
    a = call('get-context', campaign=c, pc=w['a'], compact=True)
    assert a['world_clock'] == 'd8/day'
    assert a['world_high_water'] == 'd23/day'
    assert a['campaign']['myth-current-scene'] == 'A scene'
    assert [p['id'] for p in a['player_characters']] == [w['a']]
    call('set-scene', campaign=c, pc=w['a'], scene='A changed')
    call('tick', campaign=c, pc=w['a'], to='d8/dusk')
    b = call('get-context', campaign=c, pc=w['b'], compact=True)
    assert b['world_clock'] == 'd23/day'
    assert b['campaign']['myth-current-scene'] == 'B scene'
    assert call('get-campaign', campaign=c, storyline='world')['campaign']['myth-time-index'] == gm.eng.parse_time_key('d23/day')
    call('tick', campaign=c, pc=w['a'], to='d7/day', ok=False)
    call('get-context', campaign=c, compact=True, ok=False)
    assert st.CURRENT.get() is None


def test_minute_clock_and_effect_expiry(world):
    w = world; c = w['campaign']
    call('add-timed-effect', campaign=c, pc=w['a'], id=w['a'], name='Disguise', minutes=15, reserved_mp=1)
    out = call('tick', campaign=c, pc=w['a'], minutes=13)
    assert out['storyline']['minute_in_watch'] == 13
    a = call('get-character', campaign=c, pc=w['a'], id=w['a'])['character']
    assert a['myth-extras-json']['timed_effects'][0]['remaining_minutes'] == 2
    call('tick', campaign=c, pc=w['a'], minutes=2)
    a = call('get-character', campaign=c, pc=w['a'], id=w['a'])['character']
    assert a['myth-extras-json']['timed_effects'][0]['active'] is False
    assert call('get-context', campaign=c, pc=w['b'], compact=True)['world_clock'] == 'd23/day'


def test_future_knowledge_and_subject_notes_hidden(world):
    w = world; c = w['campaign']
    f = call('add-fact', campaign=c, storyline='world', statement='A future secret', status='established', when='d20/day', learned_by=w['a'])['id']
    call('set-knowledge', campaign=c, storyline='world', knower=w['a'], subject=w['npc'], note='Future read', since=gm.eng.parse_time_key('d20/day'))
    v = call('character-view', campaign=c, pc=w['a'], id=w['a'])
    assert not v['knows'] and not v['reads']
    call('learn', campaign=c, pc=w['a'], knower=w['a'], fact=f, ok=False)
    call('add-fact', campaign=c, pc=w['a'], statement='No early future', status='established', when='d20/day', ok=False)
    call('set-knowledge', campaign=c, pc=w['a'], knower=w['a'], subject=w['npc'], note='No early read', since=gm.eng.parse_time_key('d20/day'), ok=False)
    call('tick', campaign=c, pc=w['a'], to='d20/day')
    v = call('character-view', campaign=c, pc=w['a'], id=w['a'])
    assert v['knows'][0]['statement'] == 'A future secret'
    assert v['reads'][0]['reads_it_as'] == 'Future read'


def test_journal_is_scoped_and_dated(world):
    w = world; c = w['campaign']
    call('log-event', campaign=c, pc=w['a'], type='scene', summary='Nimras day8', involves=w['a'])
    call('log-event', campaign=c, pc=w['b'], type='scene', summary='Hrill day23', involves=w['b'])
    a = call('get-log', campaign=c, pc=w['a'], limit=20)
    assert [e['summary'] for e in a['events']] == ['Nimras day8']
    b = call('get-context', campaign=c, pc=w['b'], compact=True)
    assert [e['summary'] for e in b['recent_events']] == ['Hrill day23']
    assert b['campaign']['myth-session-number'] == 12


def test_shared_beat_is_resolved_once(world):
    w = world; c = w['campaign']
    ag = call('add-agenda', campaign=c, storyline='world', holder=w['npc'], title='Shared operation')['id']
    b = call('add-beat', campaign=c, storyline='world', agenda=ag, title='Single outcome', when='d8/dusk')['id']
    call('fire-beat', campaign=c, storyline='world', id=b, outcome='narrated', advance=1)
    again = call('fire-beat', campaign=c, pc=w['a'], id=b, outcome='narrated', advance=1)
    assert again['already_resolved']
    assert call('get-agenda', id=ag)['agenda']['clock']['filled'] == 1
    call('fire-beat', campaign=c, pc=w['a'], id=b, outcome='played', ok=False)
    out = call('tick', campaign=c, pc=w['a'], to='d8/dusk')
    assert [b['id'] for b in out['resolved_shared_events']] == [b]
    assert b not in [r['id'] for r in out['due_beats']]


def test_owned_operations_do_not_cross_storylines(world):
    w = world; c = w['campaign']
    ag = call('add-agenda', campaign=c, pc=w['b'], holder=w['npc'], title='Hrill operation')['id']
    beat = call('add-beat', campaign=c, pc=w['b'], agenda=ag, title='Hrill beat', when='d23/dusk')['id']
    assert not call('forecast', campaign=c, pc=w['a'])['thread']
    assert call('forecast', campaign=c, pc=w['b'])['thread'][0]['id'] == beat
    call('advance-agenda', campaign=c, pc=w['a'], id=ag, by=1, ok=False)


def test_rest_changes_only_resting_pc_and_respects_reservations(world):
    w = world; c = w['campaign']
    call('update-character', campaign=c, pc=w['a'], id=w['a'], magic_current=3, luck=2)
    call('update-character', campaign=c, pc=w['b'], id=w['b'], magic_current=4, luck=1)
    call('add-timed-effect', campaign=c, pc=w['a'], id=w['a'], name='Long spell', minutes=720, reserved_mp=1)
    result = call('rest-character', campaign=c, pc=w['a'], id=w['a'], hours=8, safe=True)
    assert result['magic_current'] == 14
    assert result['luck_current'] == 2
    a = call('get-character', campaign=c, pc=w['a'], id=w['a'])['character']
    assert a['myth-magic-current'] == 14
    b = call('get-character', campaign=c, pc=w['b'], id=w['b'])['character']
    assert b['myth-magic-current'] == 4 and b['myth-luck-current'] == 1
    call('update-character', campaign=c, pc=w['a'], id=w['b'], magic_current=15, ok=False)


def test_shared_npc_state_and_presence_are_temporal(world):
    w = world; c = w['campaign']
    call('move-character', campaign=c, pc=w['b'], id=w['npc'], location=w['y'])
    call('update-character', campaign=c, pc=w['b'], id=w['npc'], status='dead')
    call('move-character', campaign=c, pc=w['a'], id=w['npc'], location=w['x'])
    # Past edits leave the future physical state intact.
    a = call('brief', campaign=c, pc=w['a'], id=w['npc'])
    b = call('brief', campaign=c, pc=w['b'], id=w['npc'])
    assert a['location'] == 'First house' and a['status'] == 'active'
    assert b['location'] == 'Second house' and b['status'] == 'dead'


def test_join_requires_synchronisation_and_shares_cursor(world):
    w = world; c = w['campaign']
    call('assign-storyline', campaign=c, id=w['sb'], pcs=w['a'], ok=False)
    call('tick', campaign=c, pc=w['a'], to='d23/day')
    call('assign-storyline', campaign=c, id=w['sb'], pcs=w['a'])
    call('tick', campaign=c, pc=w['b'], minutes=12)
    assert call('get-context', campaign=c, pc=w['a'], compact=True)['storyline']['minute_in_watch'] == 12


def test_wrong_campaign_pc_and_exception_do_not_retain_scope(world):
    w = world
    c2 = call('create-campaign', name='Other campaign')['id']
    call('get-context', campaign=c2, pc=w['a'], compact=True, ok=False)
    assert st.CURRENT.get() is None
    call('tick', campaign=w['campaign'], pc=w['a'], to='d0/day', ok=False)
    assert st.CURRENT.get() is None


def test_duplicate_pc_membership_is_rejected(world):
    w = world
    call('create-storyline', campaign=w['campaign'], name='Duplicate', pcs=w['a'], at='d8/day', ok=False)


def test_effect_projection_pure():
    ex = {'timed_effects': [{'name':'Spell', 'active':True, 'ends_at_minute':10, 'reserved_mp':1}]}
    effects, reserved, _ = st.effect_state(ex, 10)
    assert reserved == 0 and effects[0]['active'] is False
    assert ex['timed_effects'][0]['active'] is True


def test_export_import_preserves_and_remaps_storylines(world, tmp_path):
    w = world; c = w['campaign']
    call('log-event', campaign=c, pc=w['a'], type='scene', summary='A temporal scene', involves=w['a'])
    call('move-character', campaign=c, pc=w['a'], id=w['npc'], location=w['x'])
    call('add-timed-effect', campaign=c, pc=w['a'], id=w['a'], name='Disguise', minutes=15, reserved_mp=1)
    call('export-campaign', campaign=c, storyline='world', output=str(tmp_path / 'save'))
    result = call('import-campaign', path=str(tmp_path / 'save'), new_ids=True)
    imported = result['id']
    stories = call('list-storylines', campaign=imported)['storylines']
    a = next(x for x in stories if x['name'] == 'Nimras')
    assert a['now'] == 'd8/day' and a['pcs'][0] != w['a']
    context = call('get-context', campaign=imported, storyline=a['id'], compact=True)
    assert context['campaign']['myth-current-scene'] == 'A scene'
    assert context['recent_events'][0]['summary'] == 'A temporal scene'
    assert context['world_high_water'] == 'd23/day'
    call('tick', campaign=imported, pc=a['pcs'][0], minutes=15)
    pc = call('get-character', campaign=imported, pc=a['pcs'][0], id=a['pcs'][0])['character']
    assert pc['myth-extras-json']['timed_effects'][0]['active'] is False


def test_explicit_pc_overrides_environment_storyline(world, monkeypatch):
    w = world
    monkeypatch.setenv('MYTHRAS_STORYLINE', w['sa'])
    assert call('get-context', campaign=w['campaign'], pc=w['b'], compact=True)['world_clock'] == 'd23/day'


def test_failed_clock_correction_does_not_change_scene(world):
    w = world
    call('update-storyline', campaign=w['campaign'], id=w['sa'], at='d0/day', scene='Do not write', ok=False)
    assert call('get-context', campaign=w['campaign'], pc=w['a'], compact=True)['campaign']['myth-current-scene'] == 'A scene'


def test_encounter_views_do_not_leak_between_cameras(world):
    w = world; c = w['campaign']
    encounter = call('start-encounter', campaign=c, pc=w['b'], name='Future fight')['id']
    assert call('get-context', campaign=c, pc=w['a'], compact=True)['encounters'] == []
    call('get-encounter', campaign=c, pc=w['a'], encounter=encounter, ok=False)
    assert call('get-context', campaign=c, pc=w['b'], compact=True)['encounters'][0]['id'] == encounter


def test_lodging_uses_own_clock_and_never_charges_automatically(world):
    w = world; c = w['campaign']
    call('update-character', campaign=c, pc=w['a'], id=w['a'], extras=json.dumps({'lodging':{'through':'d8/night','key_held':True},'wealth':{'gp':10}}))
    a = call('get-character', campaign=c, pc=w['a'], id=w['a'])['character']
    assert a['clock_status']['lodging']['prepaid_active']
    call('tick', campaign=c, pc=w['b'], to='d24/day')
    assert call('get-character', campaign=c, pc=w['a'], id=w['a'])['character']['clock_status']['lodging']['prepaid_active']
    call('tick', campaign=c, pc=w['a'], to='d9/dawn')
    a = call('get-character', campaign=c, pc=w['a'], id=w['a'])['character']
    assert not a['clock_status']['lodging']['prepaid_active']
    assert a['myth-extras-json']['wealth']['gp'] == 10


def test_historical_cascade_settles_only_owned_future_plans(world):
    w = world; c = w['campaign']
    fact = call('add-fact', campaign=c, pc=w['a'], statement='Own trigger', status='established')['id']
    ag = call('add-agenda', campaign=c, pc=w['a'], holder=w['a'], title='Own gated plan', status='dormant')['id']
    call('require-fact', campaign=c, pc=w['a'], agenda=ag, fact=fact)
    other = call('add-fact', campaign=c, pc=w['b'], statement='Other future', when='d25/day')['id']
    call('learn', campaign=c, pc=w['a'], knower=w['a'], fact=fact)
    call('tick', campaign=c, pc=w['a'], minutes=1)
    assert call('get-agenda', campaign=c, pc=w['a'], id=ag)['agenda']['status'] == 'active'
    assert call('get-fact', campaign=c, storyline='world', id=other)['fact']['status'] == 'not-yet-true'


def test_record_backfill_and_explicit_effect_dismissal(world):
    w = world; c = w['campaign']
    eid = call('log-event', campaign=c, storyline='world', type='scene', summary='Legacy dated', involves=w['a'])['id']
    call('assign-storyline-record', campaign=c, id=eid, to=w['sa'], when='d8/day')
    assert call('get-log', campaign=c, pc=w['a'], limit=5)['events'][0]['summary'] == 'Legacy dated'
    effect = call('add-timed-effect', campaign=c, pc=w['a'], id=w['a'], name='Long spell', minutes=720, reserved_mp=1)['id']
    call('update-character', campaign=c, pc=w['a'], id=w['a'], magic_current=14)
    call('dismiss-effect', campaign=c, pc=w['a'], id=w['a'], effect=effect)
    char = call('get-character', campaign=c, pc=w['a'], id=w['a'])['character']
    assert char['myth-magic-current'] == 14
    assert char['clock_status']['reserved_mp'] == 0
    call('rest-character', campaign=c, pc=w['a'], id=w['a'], hours=0.25, kind='short')
    assert call('get-character', campaign=c, pc=w['a'], id=w['a'])['character']['myth-magic-current'] == 15


def test_split_retains_history_and_isolates_future(world):
    w = world; c = w['campaign']
    before = call('log-event', campaign=c, pc=w['a'], type='scene', summary='Before split', involves=w['a'])['id']
    new = call('split-storyline', campaign=c, id=w['sa'], name='New path', pcs=w['a'])['id']
    assert call('get-context', campaign=c, pc=w['a'], compact=True)['storyline']['id'] == new
    assert before in [e['id'] for e in call('get-log', campaign=c, pc=w['a'], limit=10)['events']]
    call('tick', campaign=c, storyline=w['sa'], minutes=400)
    later = call('log-event', campaign=c, storyline=w['sa'], type='scene', summary='Other path', involves=w['a'])['id']
    call('tick', campaign=c, pc=w['a'], minutes=500)
    assert later not in [e['id'] for e in call('get-log', campaign=c, pc=w['a'], limit=10)['events']]
