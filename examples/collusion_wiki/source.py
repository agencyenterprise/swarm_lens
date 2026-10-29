"""Import a filtered slice of the collusion.wiki public export as one Swarm Lens run.

Pages become channels, edit labels become agents, saved revisions become messages (showing the
lines each edit added), and admin deletions/recreations become messages and observations on the page.

The export's labels are stable names for actors whose identity is not published, so labelled agents are declared
pseudonymous. Edits without a label are grouped by /16 network only, which may merge several actors, so that agent
is declared unattributed. Each row's corroboration grade becomes a time grade: request and recent-changes logs
are exact to the second; a database write date is approximate.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from swarm_lens import Fact, Framework
from swarm_lens.adapters.sqlite import SQLiteHistory
from swarm_lens.application.profile import profile
from swarm_lens.application.uncertainty import declared_profile, provenance

ADAPTER = 'collusion-wiki/v1'
# Only short page bodies are kept whole in metadata; content always holds the added text.
MAX_BODY_IN_METADATA = 20_000
TIME_GRADES = {'reqlog': 'exact', 'rclog': 'exact', 'write_date': 'approximate'}
DECLARED = declared_profile(
    time_grade='exact', attribution='pseudonymous', missing=['real actor identities'],
    notes='Agents are the export\'s published labels. Unlabelled edits are grouped by /16 network, which may merge '
          'actors. A few saves carry only a database write date.')


def read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def agent_id(label, ip16):
    return f"label:{label}" if label else f"unlabeled:{ip16 or 'unknown'}"


def added_text(revision):
    """Lines this revision inserted or replaced; the whole body for a page creation."""
    lines = revision['body'].splitlines()
    if revision['diff_base'] is None:
        return revision['body']
    added = [line for hunk in revision['hunks'] if hunk['op'] in ('insert', 'replace')
             for line in lines[hunk['b0']:hunk['b1']]]
    removed = sum(hunk['a1'] - hunk['a0'] for hunk in revision['hunks'] if hunk['op'] in ('delete', 'replace'))
    text = '\n'.join(added)
    if not text and removed:
        return f"(removed {removed} line{'s' if removed != 1 else ''})"
    return text or '(no textual change)'


class WikiSource:
    """Facts for selected revisions and page events, in time order."""

    def __init__(self, revisions, events, pages, task):
        self.revisions, self.events, self.pages, self.task = revisions, events, pages, task

    def fact(self, kind, data, at, ref, grade='exact'):
        return Fact(kind, data, at, provenance(grade, adapter=ADAPTER, ref=ref))

    def rows(self):
        items = [(r['time'], 0, r['rev_id'], 'revision', r) for r in self.revisions]
        items += [(e['time'], 1, e['event_id'], e['event_type'], e) for e in self.events]
        return sorted(items, key=lambda item: item[:3])

    def facts(self):
        rows = self.rows()
        if not rows:
            return
        yield self.fact('environment.updated', {'task': self.task, 'goal': self.task,
                                                'metadata': {'declared_profile': DECLARED}}, rows[0][0], 'selection')
        agents, members, last_message = set(), {}, {}
        for at, _, ref, kind, row in rows:
            page, grade = row['page_key'], TIME_GRADES.get(row.get('time_grade'), 'approximate')
            if page not in members:
                meta = self.pages.get(page, {})
                members[page] = []
                yield self.fact('channel.created', {
                    'id': page, 'name': f"{row['wiki']}/{row.get('name') or row.get('page')}",
                    'metadata': {k: meta.get(k) for k in ('page_family', 'page_family_confidence', 'n_revs',
                                                          'n_deletions', 'n_recreations', 'n_labels')}}, at, page)
            if kind == 'revision':
                sender = agent_id(row['label'], row['ip16'])
                if sender not in agents:
                    agents.add(sender)
                    attribution = {'attribution': 'pseudonymous'} if row['label'] else {
                        'attribution': 'unattributed', 'attribution_reason': 'Unlabelled edits grouped by /16 network'}
                    yield self.fact('agent.added', {'id': sender, 'name': row['label'] or f"(unlabeled {row['ip16']})",
                                                    'metadata': {'first_ip16': row['ip16'], **attribution}}, at, sender)
                if sender not in members[page]:
                    members[page].append(sender)
                    yield self.fact('channel.updated', {'id': page, 'members': list(members[page])}, at, page)
                summary = row['change_summary']
                content = added_text(row)
                if summary and summary != '*':
                    content = f"**Edit summary:** {summary}\n\n{content}"
                metadata = {'rev_id': row['rev_id'], 'seq': row['seq'], 'ip16': row['ip16'],
                            'time_grade': row['time_grade'], 'body_len': row['body_len'],
                            'diff_base_reason': row['diff_base_reason'], 'relation_type': row['relation_type'],
                            'related_event_id': row['related_event_id'], 'round_id': row['round_id']}
                if row['body_len'] <= MAX_BODY_IN_METADATA:
                    metadata['body'] = row['body']
                yield self.fact('message.created', {'id': row['rev_id'], 'channel_id': page, 'sender_id': sender,
                                                    'content': content, 'reply_to_id': last_message.get(page),
                                                    'metadata': metadata}, at, ref, grade)
                last_message[page] = row['rev_id']
            elif kind == 'delete':
                actor = row.get('actor_label') or 'admin'
                yield self.fact('message.created', {
                    'id': row['event_id'], 'channel_id': page, 'role': 'human', 'sender_name': actor,
                    'content': f"Page deleted by {actor}" + (f": {row['change_summary']}" if row.get('change_summary') else ''),
                    'reply_to_id': last_message.get(page), 'metadata': {'ip16': row.get('ip16'), 'event': row}}, at, ref, grade)
                last_message[page] = row['event_id']
            else:
                yield self.fact('observation.recorded', {'type': f"wiki_{kind}",
                                                         'content': f"{kind} on {page} by {row.get('actor_label')}",
                                                         'record': row}, at, ref, grade)


def select(dataset, *, wiki=None, family=None, page=None, label=None, since=None, until=None, limit=None):
    pages = {p['page_key']: p for p in read_jsonl(dataset / 'pages.jsonl')}
    page_pattern = re.compile(page) if page else None

    def keep(page_key, wiki_name, name, at):
        meta = pages.get(page_key, {})
        return ((not wiki or wiki_name == wiki) and (not family or meta.get('page_family') == family)
                and (not page_pattern or page_pattern.search(name or ''))
                and (not since or at >= since) and (not until or at < until))

    revisions = [r for r in read_jsonl(dataset / 'revisions.jsonl')
                 if keep(r['page_key'], r['wiki'], r['name'], r['time']) and (not label or r['label'] == label)]
    revisions.sort(key=lambda r: (r['time'], r['rev_id']))
    if limit:
        revisions = revisions[:limit]
    selected = {r['page_key'] for r in revisions}
    # Deletions after the last kept edit still matter (they end a page), unless --limit truncated the slice.
    end = revisions[-1]['time'] if limit and revisions else until
    events = [e for e in read_jsonl(dataset / 'events.jsonl')
              if e['event_type'] in ('delete', 'revert') and e.get('page_key') in selected
              and (not since or e['time'] >= since) and (not end or e['time'] <= end)]
    return revisions, events, pages


def import_slice(dataset, data, name=None, dry_run=False, **filters):
    dataset = Path(dataset)
    revisions, events, pages = select(dataset, **filters)
    if not revisions:
        raise SystemExit('No revisions match these filters.')
    active = {k: v for k, v in filters.items() if v}
    if dry_run:
        return {'revisions': len(revisions), 'profile': profile(Framework.dry_run(WikiSource(revisions, events, pages, 'dry run')))}
    digest = hashlib.sha256((dataset / 'revisions.jsonl').read_bytes()).hexdigest()
    key = f"{ADAPTER}:{digest}:{json.dumps(active, sort_keys=True)}"
    framework = Framework(SQLiteHistory(Path(data) / 'history.sqlite'))
    for run in framework.store.runs():
        if run.metadata.get('example_key') == key:
            return {'skipped': 'already imported', 'run_id': run.id, 'filters': active}
    title = name or 'collusion.wiki · ' + (' · '.join(f"{k}={v}" for k, v in active.items()) or 'all edits')
    task = f"Agent edits on public wikis ({', '.join(f'{k}={v}' for k, v in active.items()) or 'all'})"
    branch = framework.create_run(title, metadata={
        'source_type': 'collusion-wiki', 'example_key': key, 'filters': active, 'revisions_sha256': digest,
        'task_title': task, 'start': revisions[0]['time'], 'end': revisions[-1]['time'], 'declared_profile': DECLARED})
    framework.ingest(branch.id, WikiSource(revisions, events, pages, task))
    state = framework.state(branch.id)
    return {'branch_id': branch.id, 'name': title, 'events': state.cursor, 'agents': len(state.agents),
            'pages': len(state.channels), 'messages': len(state.messages),
            'window': [revisions[0]['time'], revisions[-1]['time']]}


def summarize(dataset):
    """Print page families and top editors so a slice can be chosen before importing."""
    from collections import Counter
    pages = read_jsonl(Path(dataset) / 'pages.jsonl')
    revisions = read_jsonl(Path(dataset) / 'revisions.jsonl')
    family = {p['page_key']: p['page_family'] for p in pages}
    print('wikis:', Counter(r['wiki'] for r in revisions).most_common())
    print('\nrevisions by page family:')
    for name, count in Counter(family.get(r['page_key']) for r in revisions).most_common(25):
        print(f"  {count:6}  {name}")
    print('\ntop editors:')
    for name, count in Counter(r['label'] or '(unlabeled)' for r in revisions).most_common(20):
        print(f"  {count:6}  {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['summary', 'import'])
    parser.add_argument('--input', type=Path, required=True, help='Folder with the expanded collusion.wiki export')
    parser.add_argument('--data', type=Path, default=Path('data'), help='Swarm Lens data folder')
    parser.add_argument('--wiki', help='dse, probier, fractal or dorfwiki')
    parser.add_argument('--family', help='page_family from pages.jsonl, e.g. relay-coordination')
    parser.add_argument('--page', help='Regular expression matched against page names')
    parser.add_argument('--label', help='Only edits by this agent label')
    parser.add_argument('--since', help='ISO time, inclusive (e.g. 2026-06-18)')
    parser.add_argument('--until', help='ISO time, exclusive')
    parser.add_argument('--limit', type=int, help='Keep only the first N matching revisions')
    parser.add_argument('--name', help='Run name shown in the picker')
    parser.add_argument('--dry-run', action='store_true', help='Print the data profile of the slice and save nothing')
    args = parser.parse_args()
    if args.command == 'summary':
        return summarize(args.input)
    print(json.dumps(import_slice(args.input, args.data, args.name, args.dry_run, wiki=args.wiki, family=args.family,
                                  page=args.page, label=args.label, since=args.since, until=args.until,
                                  limit=args.limit), indent=2))


if __name__ == '__main__':
    main()
