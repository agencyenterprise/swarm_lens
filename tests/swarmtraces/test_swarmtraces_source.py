import json

import pytest

from examples.swarmtraces.source import TraceSource, import_slice, select
from swarm_lens import Framework
from swarm_lens.adapters.sqlite import SQLiteHistory


def row(id, kind, parent=None, tags=''):
    return {'id': id, 'cite': f'{id}:00', 'kind': kind, 'parent_id': parent, 'time_utc': None, 'tags': tags,
            'text': f'text of {id}'}


# Grouped by kind, like the published file: payloads first, then responses, then recovered text.
ROWS = [row('R1', 'payload'), row('R2', 'payload'), row('R3', 'payload'),
        row('R4', 'response', 'R1'), row('R5', 'response', 'R1'), row('R6', 'response'),
        row('R7', 'recovered_text', 'R2', 'article-evidence;appendix-request'), row('R8', 'recovered_text')]


@pytest.fixture
def dataset(tmp_path):
    folder = tmp_path / 'swarmtraces'
    folder.mkdir()
    (folder / 'redacted.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in ROWS))
    return folder


def ids(rows):
    return [r['id'] for r in rows]


def test_slices_are_whole_threads_in_thread_order():
    assert ids(select(ROWS)) == ['R1', 'R4', 'R5', 'R2', 'R7', 'R3', 'R6', 'R8']
    assert ids(select(ROWS, offset=1, limit=2)) == ['R2', 'R7', 'R3']
    assert ids(select(ROWS, evidence_only=True)) == ['R2', 'R7']


def test_payloads_become_unattributed_tool_calls_with_their_first_response():
    events = Framework.dry_run(TraceSource(select(ROWS)))
    kinds = [(e.kind, e.data.get('id') or e.data.get('type')) for e in events]
    assert kinds[:2] == [('environment.updated', 'environment'), ('agent.added', 'unattributed')]
    assert kinds[2:] == [('tool.started', 'R1'), ('tool.completed', 'R1'), ('observation.recorded', 'response'),
                         ('tool.recorded', 'R2'), ('observation.recorded', 'recovered_text'),
                         ('tool.recorded', 'R3'), ('observation.recorded', 'response'),
                         ('observation.recorded', 'recovered_text')]
    completed = events[3].data
    assert completed['result'] == 'text of R4' and completed['metadata']['responses'] == 2
    assert completed['metadata']['cite'] == 'R1:00' and completed['metadata']['response_id'] == 'R4'
    assert events[4].data['metadata']['parent_id'] == 'R1'
    assert all(e.source['time_grade'] == 'ordinal' for e in events)
    assert [e.source.get('row') for e in events if e.source.get('featured')] == ['R7']
    assert events[0].occurred_at < events[-1].occurred_at


def test_dry_run_profiles_without_saving_and_import_runs_once(dataset, tmp_path):
    preview = import_slice(dataset, tmp_path / 'data', dry_run=True)
    assert preview['rows'] == 8
    dimensions = preview['profile']['dimensions']
    assert {k: v['status'] for k, v in dimensions.items()} == {
        'actors': 'absent', 'time': 'absent', 'conversation': 'absent', 'actions': 'partial'}
    assert not (tmp_path / 'data' / 'history.sqlite').exists()
    imported = import_slice(dataset, tmp_path / 'data', limit=2)
    assert imported['name'] == 'SwarmTraces · threads 1–2' and imported['tool_calls'] == 2
    assert import_slice(dataset, tmp_path / 'data', limit=2)['skipped'] == 'already imported'
    run = Framework(SQLiteHistory(tmp_path / 'data' / 'history.sqlite')).store.runs()[0]
    assert run.metadata['declared_profile']['time_grade'] == 'ordinal'
