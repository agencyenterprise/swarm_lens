# Repository workflow

- The active repository is `agencyenterprise/swarm_lens`.
- Never commit or push changes in `agencyenterprise/fractal_swarm_lens`; its hackathon submission is frozen for review.
- Make changes on a feature branch and open a pull request against `main`. Never push directly to `main` or merge without user authorization.
- Website and wiki changes follow the same PR workflow. Edit `docs/wiki/`, run `npm run build:site`, and include the generated `site/wiki/` files.
- Publish only `site/` through the Pages workflow after merge. Do not push directly to a publishing branch or a separate wiki repository.
