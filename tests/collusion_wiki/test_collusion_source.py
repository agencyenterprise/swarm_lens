import json

import pytest

from examples.collusion_wiki.source import import_slice
from swarm_lens import Framework
from swarm_lens.adapters.sqlite import SQLiteHistory


def revision(rev_id, page, at, label, body, *, base=None, hunks=(), grade='reqlog', ip16='10.0'):
    return {'rev_id': rev_id, 'page_key': page, 'wiki': 'dse', 'name': page.title(), 'time': at, 'label': label,
            'ip16': ip16, 'body': body, 'diff_base': base, 'hunks': list(hunks), 'change_summary': '*', 'seq': 1,
            'time_grade': grade, 'body_len': len(body), 'diff_base_reason': None, 'relation_type': None,
            'related_event_id': None, 'round_id': None}


REVISIONS = [
    revision('r1', 'relay', '2026-06-16T09:00:00Z', 'agent-a', 'first line'),
    revision('r2', 'relay', '2026-06-16T09:01:00Z', 'agent-b', 'first line\nsecond line', base='r1',
             hunks=[{'op': 'insert', 'a0': 1, 'a1': 1, 'b0': 1, 'b1': 2}]),
    revision('r3', 'other', '2026-06-16T09:02:00Z', '', 'unlabelled', grade='write_date'),
]
EVENTS = [{'event_id': 'e1', 'event_type': 'delete', 'time': '2026-06-16T09:03:00Z', 'page_key': 'relay',
           'actor_label': 'admin', 'change_summary': 'Seite gelöscht.', 'ip16': None, 'time_grade': 'rclog'}]
PAGES = [{'page_key': 'relay', 'page_family': 'relay-coordination'}, {'page_key': 'other', 'page_family': 'misc'}]


@pytest.fixture
def dataset(tmp_path):
    folder = tmp_path / 'wiki'
    folder.mkdir()
    for name, rows in (('revisions', REVISIONS), ('events', EVENTS), ('pages', PAGES)):
        (folder / f'{name}.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return folder


def test_pages_become_channels_with_declared_attribution_and_time_grades(dataset, tmp_path):
    imported = import_slice(dataset, tmp_path / 'data')
    assert imported['agents'] == 3 and imported['pages'] == 2 and imported['messages'] == 4
    framework = Framework(SQLiteHistory(tmp_path / 'data' / 'history.sqlite'))
    state = framework.state(imported['branch_id'])
    assert state.messages['r2'].content == 'second line' and state.messages['r2'].reply_to_id == 'r1'
    assert state.messages['e1'].role == 'human'
    assert {a.id: a.metadata['attribution'] for a in state.agents.values()} == {
        'label:agent-a': 'pseudonymous', 'label:agent-b': 'pseudonymous', 'unlabeled:10.0': 'unattributed'}
    grades = {e.data.get('id'): e.source['time_grade'] for e in framework.history(imported['branch_id'])
              if e.kind == 'message.created'}
    assert grades == {'r1': 'exact', 'r2': 'exact', 'r3': 'approximate', 'e1': 'exact'}
    assert import_slice(dataset, tmp_path / 'data')['skipped'] == 'already imported'


def test_dry_run_reports_the_profile_of_a_filtered_slice(dataset, tmp_path):
    preview = import_slice(dataset, tmp_path / 'data', dry_run=True, family='relay-coordination')
    report = preview['profile']
    assert preview['revisions'] == 2 and report['declared']['attribution'] == 'pseudonymous'
    assert {k: v['status'] for k, v in report['dimensions'].items()} == {
        'actors': 'present', 'time': 'present', 'conversation': 'present', 'actions': 'absent'}
    assert not (tmp_path / 'data' / 'history.sqlite').exists()
