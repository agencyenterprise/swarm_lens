# Examples and datasets

Start with a public recording, import your own trace, or run your own agents and collect a new dataset. Saved replay does not call a model. Live execution and optional LLM analysis do.

## Choose a dataset

| Dataset | Useful for | How to start in SwarmLens |
| --- | --- | --- |
| [AI Village public research replay](https://theaidigest.org/village/goal/perform-novel-research), by AI Digest / AI Village | Long conversations and collaboration across agents | **Ready to import:** the selected May 11–15, 2026 recording is bundled; use the command below. |
| ACIArena control/attack recordings | Comparing a shared task with and without an attack | **Ready to import:** bundled pairs; follow the medical debate recipe below. |
| [German wiki agent message board](https://collusion.wiki/explorer/download) | Studying information sharing through public wiki edits | **Public download; adapter needed:** start with a small page history as described below. |
| [AI Village on Hugging Face](https://huggingface.co/datasets/aidigestorg/ai-village) | Broader chat, activity, memory and computer-use research | **Access approval and adapter needed:** the dataset card is public; files are gated under research terms. This is distinct from the bundled public replay. |

## Quick start: AI Village public recording

After the [quickstart installation](Getting-started), run from the repository root with your virtual environment active:

```sh
python -m examples.crewai.ai_village_research import --data data
swarm-lens --data data --port 8765
```

Open the explorer and select **Perform novel research!** in the run picker. This imports the bundled recording without a provider key or Hugging Face token. Use the same `--data` directory when restarting the server. The selected public sessions contain chat and activity notices, not the agents' private memories or full computer sessions. See the [AI Village guide](https://github.com/agencyenterprise/swarm_lens/blob/main/docs/ai-village.md) for provenance and continuation instructions.

## Explore the German wiki data

The [download page](https://collusion.wiki/explorer/download) offers page metadata, full-text revisions, chronological events, agent labels and a provenance manifest. Begin with one page and its revision history rather than importing the entire archive.

Download the export and retain its manifest and checksums. For a quick text inspection, prepare a readable transcript from a small selection and use **⋯ → Import trace**. To preserve native timestamps, page IDs and revision relationships, write a source adapter using the [integration guide](https://github.com/agencyenterprise/swarm_lens/blob/main/docs/integration.md). There is no dedicated German wiki importer yet; `examples/messageboard` imports a different simulator format.

These records show observable wiki edits. They do not establish which agents read each edit, so an adapter should not invent delivery links or private state. Attribute the source to the investigators listed on [collusion.wiki](https://collusion.wiki/).

## Explore the full AI Village dataset

Request access through the [Hugging Face dataset card](https://huggingface.co/datasets/aidigestorg/ai-village) and follow its research terms and attribution requirements. Start with `village-transcript.json` for chat, then consult `SCHEMA.md` for richer tables. The bundled public-replay importer does not accept these full-dataset files; map a selected subset through a source adapter. For an immediate first run, use the bundled recording above.

## The medical debate from the demo

From the repository root on `main`, with your virtual environment active:

```sh
python -m pip install -e '.[web,aciarena,mast]'
git submodule update --init vendor/aciarena
python -m examples.aciarena.samples import \
  --input examples/aciarena/samples/llm-debate-medicine-misalign-20261004 \
  --data data
swarm-lens --data data --port 8765
```

The `aciarena` extra pulls in some heavy ML dependencies; if you'd rather keep them out of your main environment, the [ACIArena guide](https://github.com/agencyenterprise/swarm_lens/blob/main/examples/aciarena/README.md) uses a separate `.venv-aciarena`.

This imports files that are already in the repo. It doesn't regenerate them and doesn't call a model.

In the run picker you'll find two runs: **ACIArena · LLMDebate · medicine-000 · Without attack · 20 rounds** and the same run **With malicious agent**. Each has 64 model responses: three opening answers, 20 rounds of three-agent debate, and a final aggregation. The question is about dental impression materials. It's a benchmark task, not medical advice.

The malicious agent is upstream's `MisalignAgent`. In both runs, the native grader marked the final answer incorrect and the attack unsuccessful. Those two labels don't tell you whether anything spread between agents; that's a separate question you'd answer by reading the trace.

## Other bundled examples

| Folder under `examples/aciarena/samples/` | What's in it |
| --- | --- |
| `llm-debate-pair-20261003` | Math debate: control vs. name-leak injection |
| `mad-medicine-misalign-20261004` | Medical MAD control/attack pair; the moderator settles it after the opening answers, so there are no debate rounds |
| `llm-debate-code-malicious-report-20261004` | Code scenario, GPT-4o mini |
| `llm-debate-code-malicious-report-gpt4o-20261004` | Code scenario, GPT-4o |
| `llm-debate-code-malicious-report-gemini31pro-20261004` | Code scenario, Gemini via OpenRouter |

Import any of them with the same command, swapping in the folder name. For MAD, "20 rounds" is the maximum, not a promise; the moderator can end the debate early, and in the bundled pair it ends before the first round.

## Generating your own data

The generator covers math, medicine, and code scenarios, runs control and attack conditions in pairs, and can run them concurrently. It needs API credentials and makes paid model calls. The [ACIArena guide](https://github.com/agencyenterprise/swarm_lens/blob/main/examples/aciarena/README.md) has the commands, budgets, and manifest format, and explains how upstream attacks differ from our local `medicine-wrong-option` extension.

The 30-task wrong-option batch and the medical message-board simulator dataset are not bundled. The selected AI Village public replay is bundled; its full Hugging Face dataset is not.

## What to keep for each experiment

Hold on to the manifest, the source revision, trace hashes, model settings, the exact inputs and outputs, the delivery links between agents, and the native grader output. Upstream's option-letter extraction occasionally misreads an answer, so look at the raw response before trusting a grader label.

## Bring your own data

For an existing conversation, choose **⋯ → Import trace** and paste a readable transcript. For structured data, implement a source adapter that maps your records to SwarmLens facts; the [integration guide](https://github.com/agencyenterprise/swarm_lens/blob/main/docs/integration.md) describes that contract. Arbitrary JSON, CSV and benchmark archives are not automatically interchangeable.

To generate a custom dataset, instrument your own CrewAI application using the [live collection guide](Live-collection-and-branching), or use the ACIArena generator above. Keep the saved recording so others can inspect it without rerunning the agents. A live continuation is a new execution, not a reproduction of missing original runtime state.

## Contribute a public dataset

**Have you published a multi-agent dataset? We encourage you to open a PR linking to it.** Small recordings, custom experiments and adapters are welcome alongside larger public datasets.

Edit [this catalog's Markdown source](https://github.com/agencyenterprise/swarm_lens/blob/main/docs/wiki/Examples-and-datasets.md) on a branch and [open a pull request](https://github.com/agencyenterprise/swarm_lens/compare). Include:

- A stable public dataset link, creator attribution, and license or access terms.
- What the records contain, their format, approximate size, and a useful small starting subset.
- Import instructions or an adapter link; explicitly state when an adapter is still needed.
- Available timestamps, agent identities and interaction links, plus known gaps or inferred fields.

Link to publicly hosted files rather than adding large archives to this repository. Share only data you have permission to publish, with secrets and personal information removed. Run `npm run build:site` and include the generated wiki HTML in your PR. A catalog entry does not require a new importer; being clear about compatibility helps others contribute one.
