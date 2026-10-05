# Getting started

## Install and open the explorer

You need Python 3.11 or newer and Git. (If you plan to use the CrewAI integration, use Python 3.12; that's the version we test it on.)

```sh
git clone https://github.com/agencyenterprise/swarm_lens.git
cd swarm_lens
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[web]'
swarm-lens --data data --port 8765
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in PowerShell instead.

Then open <http://127.0.0.1:8765>. Press Ctrl+C in the terminal to stop the server. The browser assets come prebuilt, so you only need Node.js if you're changing the frontend.

## Load a trace

Choose your starting point:

- **Use a public recording:** import the bundled AI Village replay or ACIArena pairs from [Examples and datasets](Examples-and-datasets). The catalog also links the German wiki export and AI Village's Hugging Face dataset, with access and adapter requirements.
- **Bring your own conversation:** choose **⋯ → Import trace** and paste a transcript. Structured source files need a matching adapter; see the [integration guide](https://github.com/agencyenterprise/swarm_lens/blob/main/docs/integration.md).
- **Run your own agents:** follow [Live collection and branching](Live-collection-and-branching) to collect a custom CrewAI run and inspect its saved trace.

Published a useful dataset? We welcome PRs adding its public link and import instructions to the [dataset catalog](Examples-and-datasets).

If the run picker is empty, the workspace just doesn't have any runs yet. The `--data` flag points at the directory holding your SQLite history, artifacts, and other stores, so use the same path every time you restart or your runs will seem to vanish.

## Add MAST analysis (optional)

```sh
python -m pip install -e '.[mast]'
```

Set `OPENAI_API_KEY` in your shell or in a local `.env`, then restart the server. Choose **⋯ → MAST trace analysis → Analyze with MAST**. Before anything is sent, you'll see a size preview, which is free. Submitting sends the trace to the model provider and you'll be billed for it. Importing and replaying traces never calls a model.

## Next

[Explore traces](Explore-traces) · [Live collection](Live-collection-and-branching) · [Troubleshooting](Troubleshooting)
