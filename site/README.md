# Public website and wiki

The site is standalone HTML/CSS/JS. It reuses the explorer's colors, typographic approach, and logo. The demo (2:44, H.264/AAC, about 27 MB) is stored in `assets/demo.mp4`. It is byte-identical to `demo-video/swarm-lens-demo.mp4`, which `demo-video/` builds; keep the two identical so Git stores the video once, and replace both together. `demo-poster.jpg` is a frame from it. No analytics, external fonts, CDN scripts, or framework build is required.

Preview: `python3 -m http.server 8771 --bind 127.0.0.1 --directory site`.

Deployment uses `.github/workflows/pages.yml`. Pull requests build and check the site without publishing. Merging to `main` publishes only `site/` to https://agencyenterprise.github.io/swarm_lens/. Enable GitHub Pages with **GitHub Actions** as its source in the new repository settings. Never publish the repository root or local workspace data.

Wiki source is maintained in `docs/wiki/` and published alongside the website at https://agencyenterprise.github.io/swarm_lens/wiki/Home.html. All documentation changes go through pull requests in this repository. The native GitHub Wiki is not the publishing target: it is a separate repository without this PR review flow.

The documentation structure takes inspiration from Dear ImGui's task-oriented wiki index (https://github.com/ocornut/imgui/wiki) and Neovim's motivation/architecture guidance (https://github.com/neovim/neovim/wiki/Introduction). No popularity ranking is claimed and no prose was copied.

Research claims are deliberately limited to implemented functionality. Do not add benchmark performance, publication, or endorsement claims without supporting evidence. The quickstart uses `main`; update both website and wiki when the documented interface changes.

The browsable wiki is included at `wiki/Home.html`. After editing `docs/wiki/`, run `npm ci && npm run build:site` and commit the generated HTML with the Markdown. The Pages build checks that the generated pages match the reviewed source; no runtime Markdown rendering is required.
