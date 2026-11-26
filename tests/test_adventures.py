"""Sagas, the adventure lifecycle and fixed history, against a throwaway database."""
import pytest

from test_storylines import call, world  # noqa: F401  (fixture)

ARC = """# ACT I - d8 to d9 · THE COMMISSION
**For:** taking the job.

# ACT II - d10 to d12 · THE HUNT
**For:** finding out who.
"""


@pytest.fixture
def arc(tmp_path):
    p = tmp_path / 'arc.md'
    p.write_text(ARC)
    return str(p)


def test_context_carries_saga_and_adventure_state(world):
    w = world; c = w['campaign']
    ctx = call('get-context', campaign=c, pc=w['a'], compact=True)
    assert ctx['saga'].startswith('NO SAGA LINE')
    assert ctx['adventure']['status'] == 'between adventures'
    # Hrill has played to d23, so Nimras on d8 is behind a clock.
    assert ctx['clocks_ahead']['storylines'] == [{'storyline': 'Hrill', 'now': 'd23/day'}]
    assert 'clocks_ahead' not in call('get-context', campaign=c, pc=w['b'], compact=True)
    call('set-saga', campaign=c, pc=w['a'], line='A freelance mage earns a name in a city that eats them.')
    out = call('set-saga', campaign=c, pc=w['a'], line='A freelance mage finds out who they owe.')
    assert out['previous'] == ['A freelance mage earns a name in a city that eats them.']
    assert call('get-context', campaign=c, pc=w['a'], compact=True)['saga'].endswith('who they owe.')


def test_lifecycle_keeps_the_finished_outline(world, arc):
    w = world; c = w['campaign']
    a = call('add-adventure', campaign=c, pc=w['a'], title='Glass Hounds', pitch='A teacher vanishes.')['id']
    call('add-adventure', campaign=c, pc=w['a'], title='The Unchosen', pitch='Another pitch.')
    # Out of order: a pitch cannot be played before it is chosen and prepared.
    call('update-adventure', campaign=c, pc=w['a'], id=a, status='active', ok=False)
    call('update-adventure', campaign=c, pc=w['a'], id=a, status='chosen')
    call('update-adventure', campaign=c, pc=w['a'], id=a, status='prepared', ok=False)  # no outline
    prep = call('update-adventure', campaign=c, pc=w['a'], id=a, status='prepared', arc_file=arc)
    assert 'readiness' in prep
    call('update-adventure', campaign=c, pc=w['a'], id=a, status='active', ok=False)  # no saga line
    call('set-saga', campaign=c, pc=w['a'], line='A mage earns a name.')
    call('update-adventure', campaign=c, pc=w['a'], id=a, status='active')
    ctx = call('get-context', campaign=c, pc=w['a'], compact=True)
    assert ctx['adventure']['title'] == 'Glass Hounds' and ctx['adventure']['since'] == 'd8/day'
    assert [x['act'] for x in ctx['arc']['acts']] == ['I', 'II']
    b = call('add-adventure', campaign=c, pc=w['a'], title='Second', pitch='x')['id']
    call('update-adventure', campaign=c, pc=w['a'], id=b, status='chosen')
    call('update-adventure', campaign=c, pc=w['a'], id=b, status='prepared', arc_file=arc)
    call('update-adventure', campaign=c, pc=w['a'], id=b, status='active', ok=False)  # one at a time
    call('update-adventure', campaign=c, pc=w['a'], id=a, status='concluded', ok=False)  # no outcome
    call('tick', campaign=c, pc=w['a'], to='d10/day')
    done = call('update-adventure', campaign=c, pc=w['a'], id=a, status='concluded',
                outcome='The teacher came home.')
    assert done['saga'] == 'A mage earns a name.'
    call('update-adventure', campaign=c, pc=w['a'], id=a, status='active', ok=False)  # ended is ended
    ctx = call('get-context', campaign=c, pc=w['a'], compact=True)
    assert ctx['adventure']['last']['title'] == 'Glass Hounds'
    assert ctx['arc']['acts'] == []
    listed = call('list-adventures', campaign=c, pc=w['a'])['adventures']
    first = listed[0]
    assert (first['title'], first['from'], first['to']) == ('Glass Hounds', 'd8/day', 'd10/day')
    assert first['acts'] == ['I. THE COMMISSION', 'II. THE HUNT']
    # Hrill's storyline has none of this.
    assert call('list-adventures', campaign=c, pc=w['b'])['adventures'] == []


def test_backfill_and_adopt_for_games_already_running(world, arc):
    w = world; c = w['campaign']
    call('update-storyline', campaign=c, id=w['sb'], arc_file=arc)
    call('add-adventure', campaign=c, pc=w['b'], title='The Road', status='concluded',
         started='d7/day', ended='d17/day', outcome='Crossed the pass.')
    call('add-adventure', campaign=c, pc=w['b'], title='Too late', status='concluded',
         started='d7/day', ended='d30/day', outcome='x', ok=False)  # after the storyline's date
    call('add-adventure', campaign=c, pc=w['b'], title='Now', status='active', ok=False)  # needs --started
    call('add-adventure', campaign=c, pc=w['b'], title='The Shore', status='active', started='d17/day')
    rows = call('list-adventures', campaign=c, pc=w['b'])['adventures']
    assert [r['title'] for r in rows] == ['The Road', 'The Shore']
    assert rows[1]['acts'] == ['I. THE COMMISSION', 'II. THE HUNT']  # adopted the loaded outline


def test_unscoped_adventure_commands_refuse(world):
    w = world; c = w['campaign']
    out = call('set-saga', campaign=c, storyline='world', line='x', ok=False)
    assert 'storyline' in out['error']


def test_fixed_history_shows_what_a_later_clock_made_true(world, arc):
    w = world; c = w['campaign']
    call('log-event', campaign=c, pc=w['b'], type='scene', summary='Hrill burned the bridge', involves=w['b'])
    call('add-adventure', campaign=c, pc=w['b'], title='Bridges', status='concluded',
         started='d20/day', ended='d23/day', outcome='The bridge is gone.')
    found = call('fixed-history', campaign=c, pc=w['a'])
    assert found['through'] == 'd23/day'
    hrill = found['fixed'][0]
    assert hrill['storyline'] == 'Hrill'
    assert [e['summary'] for e in hrill['events']] == ['Hrill burned the bridge']
    assert hrill['adventures'][0]['title'] == 'Bridges'
    # Looking only as far as d12 sees nothing of Hrill's d20-d23.
    assert call('fixed-history', campaign=c, pc=w['a'], through='d12/night')['fixed'] == []
    # Preparing an adventure that runs into Hrill's dates reports the overlap.
    a = call('add-adventure', campaign=c, pc=w['a'], title='Late', pitch='x')['id']
    call('update-adventure', campaign=c, pc=w['a'], id=a, status='chosen')
    prep = call('update-adventure', campaign=c, pc=w['a'], id=a, status='prepared', arc_file=arc)
    assert prep.get('fixed_history', []) == []  # d8-d12 is clear
    # Ticking into Hrill's dates carries the warning.
    out = call('tick', campaign=c, pc=w['a'], to='d23/day')
    assert out['fixed_history']['entered'][0]['first'] == ['Hrill burned the bridge']
    # The leader sees nothing fixed ahead of it.
    assert call('fixed-history', campaign=c, pc=w['b'])['fixed'] == []


def test_saga_and_adventures_survive_export(world, tmp_path):
    w = world; c = w['campaign']
    call('set-saga', campaign=c, pc=w['a'], line='A mage earns a name.')
    call('add-adventure', campaign=c, pc=w['a'], title='Glass Hounds', status='concluded',
         started='d7/day', ended='d8/day', outcome='Home.')
    call('export-campaign', campaign=c, storyline='world', output=str(tmp_path / 'save'))
    imported = call('import-campaign', path=str(tmp_path / 'save'), new_ids=True)['id']
    story = next(s for s in call('list-storylines', campaign=imported)['storylines'] if s['name'] == 'Nimras')
    listed = call('list-adventures', campaign=imported, storyline=story['id'])
    assert listed['saga'] == 'A mage earns a name.'
    assert [(a['title'], a['outcome']) for a in listed['adventures']] == [('Glass Hounds', 'Home.')]
