# SwarmTraces importer

Imports a slice of the [SwarmTraces redacted export](https://huggingface.co/datasets/vopi/OpenAI-HF-Hack-SwarmTraces) (`redacted.jsonl`, 189,579 rows) as one run. The export has no agent identities, no timestamps and no messages between agents. Each row is a payload, a response or recovered text, linked to its parent row.

The importer keeps that structure and declares what is missing:

- Each payload becomes a tool call by one **Unattributed (redacted)** agent. Its first response becomes the result.
- Further responses and recovered text become observations that cite their parent row.
- Rows are emitted thread by thread: a root row, then its descendants. Timestamps come from an ordinal clock and are declared `ordinal`. The order inside a thread follows the parent links. The file is grouped by row kind, so the order between threads does not say when anything happened.
- Rows tagged `article-evidence` are marked featured.

It copies row text as published and never classifies or un-redacts it. The dataset's terms ask readers not to identify redacted entities or reconstruct removed information.

```sh
hf download vopi/OpenAI-HF-Hack-SwarmTraces --repo-type dataset --local-dir datasets/swarmtraces
python -m examples.swarmtraces.source --input datasets/swarmtraces --dry-run            # profile only, saves nothing
python -m examples.swarmtraces.source --input datasets/swarmtraces --data data --limit 300 --offset 60000
python -m examples.swarmtraces.source --input datasets/swarmtraces --data data --evidence-only
```

`--offset` and `--limit` count threads (default 500; `--limit 0` keeps all). Importing the same slice again is skipped. Open **Data profile** in the explorer to see what the slice supports: action analysis, but not timing, per-agent or conversation analysis such as MAST. In the transcript, turn on **Show → Tools** and **Observations** to list the rows.
