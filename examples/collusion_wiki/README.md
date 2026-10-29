# collusion.wiki importer

Imports a filtered slice of the [collusion.wiki](https://collusion.wiki) public export (from collusion.wiki/explorer/download) as one run. Pages become channels, edit labels become agents, and saved revisions become messages that show the lines each edit added, replying to the page's previous revision. Admin deletions become human messages, and reverts become observations.

What the importer declares:

- Labelled agents are `pseudonymous`: the labels are stable, but the export does not say who the actors are. Unlabelled edits are grouped by /16 network, which may merge actors, so that agent is `unattributed`.
- Each row's corroboration grade becomes a time grade: request and recent-changes logs are `exact`, and a database write date is `approximate`.

```sh
python -m examples.collusion_wiki.source summary --input datasets/collusion-wiki            # page families, top editors
python -m examples.collusion_wiki.source import --input datasets/collusion-wiki --family relay-coordination --dry-run
python -m examples.collusion_wiki.source import --input datasets/collusion-wiki --data data --family relay-coordination
```

Filters: `--wiki`, `--family`, `--page` (regular expression), `--label`, `--since`, `--until` and `--limit`. Importing the same slice again is skipped.
