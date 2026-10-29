"""Import a slice of the SwarmTraces redacted export as one Swarm Lens run, by its structure only.

The export (huggingface.co/datasets/vopi/OpenAI-HF-Hack-SwarmTraces, `redacted.jsonl`) has no agent identities
and no timestamps: each row is a payload, a response to a payload, or recovered text, linked by `parent_id` and
grouped by kind in the file. This importer says so instead of inventing what is missing:

- every payload is a tool call by one "Unattributed (redacted)" agent, with its first response as the result;
- further responses and recovered text are observations that cite their parent row;
- rows are emitted thread by thread (a root row, then its descendants), with timestamps from an ordinal clock
  declared `ordinal`: the order inside a thread follows the parent links, the order between threads does not
  record when anything happened;
- rows tagged `article-evidence` are marked featured.

It copies row text as published and never classifies or un-redacts it. The dataset's terms ask readers not to
identify redacted entities or reconstruct removed information.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from swarm_lens import Fact, Framework
from swarm_lens.adapters.sqlite import SQLiteHistory
from swarm_lens.application.profile import profile
from swarm_lens.application.uncertainty import OrdinalClock, declared_profile, provenance, unattributed_agent

ADAPTER = 'swarmtraces/v1'
EVIDENCE_TAG = 'article-evidence'
TASK = 'Redacted agent traces from a security incident (SwarmTraces): payloads, responses and recovered text'
DECLARED = declared_profile(
    time_grade='ordinal', attribution='unattributed',
    missing=['agent identities', 'timestamps', 'messages between agents'],
    notes='Only parent links are real: each payload is followed by its responses and recovered text. The file is '
          'grouped by row kind, so the order between threads is not the order things happened. One stand-in '
          'agent holds every payload.')


def read_rows(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def is_evidence(row):
    return EVIDENCE_TAG in (row.get('tags') or '').split(';')


def threads(rows):
    """Root rows (no parent in the file) in file order, and each row's children in file order."""
    ids = {row['id'] for row in rows}
    roots, children = [], defaultdict(list)
    for row in rows:
        (children[row['parent_id']] if row['parent_id'] in ids else roots).append(row)
    return roots, children


def select(rows, *, offset=0, limit=None, evidence_only=False):
    """Whole threads in thread order: each root row followed by its descendants.

    `offset` and `limit` count threads, not rows. `evidence_only` keeps threads that hold an evidence row.
    """
    roots, children = threads(rows)

    def thread(row):
        yield row
        for child in children[row['id']]:
            yield from thread(child)

    picked = [list(thread(root)) for root in roots]
    if evidence_only:
        picked = [group for group in picked if any(is_evidence(row) for row in group)]
    else:
        picked = picked[offset:offset + limit if limit else None]
    return [row for group in picked for row in group]


class TraceSource:
    """Facts for selected rows, in the order given (thread order from `select`)."""

    def __init__(self, rows):
        self.rows = rows

    def facts(self):
        clock = OrdinalClock()
        start = clock.tick()
        yield Fact('environment.updated', {'task': TASK, 'goal': TASK,
                                           'metadata': {'declared_profile': DECLARED}}, start,
                   provenance('ordinal', adapter=ADAPTER))
        yield unattributed_agent(start, reason='SwarmTraces redacts agent identities.',
                                 **provenance('ordinal', adapter=ADAPTER))
        payloads = {row['id'] for row in self.rows if row['kind'] == 'payload'}
        answered, called = defaultdict(list), {}
        for row in self.rows:
            if row['kind'] == 'response' and row['parent_id'] in payloads:
                answered[row['parent_id']].append(row['id'])
        for row in self.rows:
            at = clock.tick()
            source = provenance('ordinal', adapter=ADAPTER, row=row['id'], cite=row['cite'],
                                **({'featured': True} if is_evidence(row) else {}))
            meta = {'cite': row['cite'], 'tags': row['tags'], 'parent_id': row['parent_id']}
            if row['kind'] == 'payload':
                called[row['id']] = meta
                running = row['id'] in answered
                yield Fact('tool.started' if running else 'tool.recorded', {
                    'id': row['id'], 'agent_id': 'unattributed', 'tool_name': 'payload',
                    'arguments': {'text': row['text']}, 'status': 'running' if running else 'unknown',
                    'metadata': meta}, at, source)
            elif row['kind'] == 'response' and answered.get(row['parent_id'], [None])[0] == row['id']:
                yield Fact('tool.completed', {'id': row['parent_id'], 'status': 'completed', 'result': row['text'],
                                              'metadata': {**called[row['parent_id']], 'response_id': row['id'], 'response_cite': row['cite'],
                                                           'responses': len(answered[row['parent_id']])}}, at, source)
            else:
                yield Fact('observation.recorded', {'type': row['kind'], 'content': row['text'],
                                                    'metadata': {**meta, 'row_id': row['id']}}, at, source)


def import_slice(dataset, data, *, name=None, offset=0, limit=None, evidence_only=False, dry_run=False):
    path = Path(dataset) / 'redacted.jsonl'
    rows = select(read_rows(path), offset=offset, limit=limit, evidence_only=evidence_only)
    if not rows:
        raise SystemExit('No rows match this slice.')
    source = TraceSource(rows)
    if dry_run:
        return {'rows': len(rows), 'profile': profile(Framework.dry_run(source))}
    filters = {'offset': offset, 'limit': limit, 'evidence_only': evidence_only}
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    key = f"{ADAPTER}:{digest}:{json.dumps(filters, sort_keys=True)}"
    framework = Framework(SQLiteHistory(Path(data) / 'history.sqlite'))
    for run in framework.store.runs():
        if run.metadata.get('example_key') == key:
            return {'skipped': 'already imported', 'run_id': run.id, 'filters': filters}
    window = f"threads {offset + 1}–{offset + limit}" if limit else f"threads from {offset + 1}"
    title = name or f"SwarmTraces · {'evidence threads' if evidence_only else window}"
    branch = framework.create_run(title, metadata={
        'source_type': 'swarmtraces', 'example_key': key, 'filters': filters, 'redacted_sha256': digest,
        'task_title': TASK, 'declared_profile': DECLARED})
    framework.ingest(branch.id, source)
    state = framework.state(branch.id)
    return {'branch_id': branch.id, 'name': title, 'rows': len(rows), 'events': state.cursor,
            'tool_calls': len(state.tools)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', type=Path, required=True, help='Folder that holds redacted.jsonl')
    parser.add_argument('--data', type=Path, default=Path('data'), help='Swarm Lens data folder')
    parser.add_argument('--offset', type=int, default=0, help='Skip this many threads (root rows, file order)')
    parser.add_argument('--limit', type=int, default=500, help='Keep this many threads; 0 keeps all of them')
    parser.add_argument('--evidence-only', action='store_true', help='Only threads that hold an article-evidence row')
    parser.add_argument('--dry-run', action='store_true', help='Print the data profile and save nothing')
    parser.add_argument('--name', help='Run name shown in the picker')
    args = parser.parse_args()
    print(json.dumps(import_slice(args.input, args.data, name=args.name, offset=args.offset,
                                  limit=args.limit or None, evidence_only=args.evidence_only,
                                  dry_run=args.dry_run), indent=2))


if __name__ == '__main__':
    main()
