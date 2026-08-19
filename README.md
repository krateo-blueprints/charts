# krateo-blueprints/charts — Krateo Helm registry (GitHub Pages)

Classic Helm registry for all Krateo charts, served from GitHub Pages
with **two channels** under one site. OCI (`oci://ghcr.io/krateo-blueprints/charts/...`)
remains the source of truth; this registry republishes the same chart bytes.

## Channels

| Channel | Add it with | Contents |
|---|---|---|
| **blueprints** | `helm repo add krateo-blueprints https://krateo-blueprints.github.io/charts/blueprints` | User-installable Krateo marketplace blueprints (`Chart.yaml` + `values.schema.json` + `compositiondefinition.yaml` + marketplace metadata). The Krateo marketplace registers this channel. |
| **operators** | `helm repo add krateo-operators https://krateo-blueprints.github.io/charts/operators` | Operator/KOG install charts, CRD/helper/target subcharts, plain dependency/app charts. Installable via helm; not rendered as marketplace tiles. |

Both indices' `urls:` dereference to the shared GitHub **Releases** blob store of this repo.

## Layout

- **`gh-pages`** branch (Pages source, `/`):
  - `blueprints/index.yaml`, `operators/index.yaml` — the two channel indices
  - `icons/<name>/<file>` — shared, Pages-hosted icons
  - `.nojekyll` — serve files verbatim (no Jekyll)
- GitHub **Releases** of this repo — the `.tgz` blob store (release tag = `<name>-<version>`)
- **`main`** branch — automation:
  - `.github/workflows/publish-chart.yaml` — reusable publisher (`workflow_call`)
  - `.github/workflows/reconcile.yaml` — nightly index reconciler (rebuilds both indices from the Release-asset set)

## Onboarding a source repo

After your existing OCI `helm push`, upload the packaged charts as an artifact named
`charts-dist` (optionally include an `icons/` directory inside it for Pages-hosted
icons), then call the reusable publisher once per channel:

```yaml
  publish-classic:
    needs: release            # the existing OCI job; it uploads dist/*.tgz as artifact "charts-dist"
    uses: krateo-blueprints/charts/.github/workflows/publish-chart.yaml@main
    with:
      source_repo: ${{ github.repository }}
      git_tag: ${{ github.ref_name }}
      channel: blueprints     # or "operators"; use a matrix for mixed repos
    secrets:
      PUBLISH_TOKEN: ${{ secrets.CHARTS_PUBLISH_TOKEN }}
```

Mixed repos (some blueprints, some operator/helper charts) use a matrix:

```yaml
    strategy:
      matrix:
        channel:
          - blueprints
          - operators
    with:
      channel: ${{ matrix.channel }}
```

### Token setup (`CHARTS_PUBLISH_TOKEN`)

The reusable publisher pushes into this repo from each source repo, so it needs a
token with write access here. Create a **classic Personal Access Token** with the
**`repo`** scope — classic tokens have no granular `contents:write`; `repo` is the
scope that grants content (and Release) writes. Then add it as the secret
`CHARTS_PUBLISH_TOKEN` on **every source repo** (this is a user account, so there are
no org-level secrets — set it per repo):

```bash
# create the PAT in the UI: https://github.com/settings/tokens/new?scopes=repo
PAT=ghp_xxx   # the classic repo-scope token
for r in $(gh repo list krateo-blueprints --limit 300 --json name --jq '.[].name'); do
  gh secret set CHARTS_PUBLISH_TOKEN --repo "krateo-blueprints/$r" --body "$PAT"
done
```

## Rules

- **Channel routing.** A chart enters `blueprints` only if it is a full blueprint:
  `values.schema.json` + `compositiondefinition.yaml` + an absolute-`https` `icon`.
  The publisher hard-gates this — schema-less KOG/operator charts must be promoted
  first, or published to `operators`.
- **Icons** must be absolute `https` (a Pages `/icons` path or a commit-SHA-pinned
  `raw.githubusercontent.com` URL). Never a `github.com/.../blob/...` URL — it serves
  HTML and renders blank.
- **Names** are unique *per channel*. Every chart is stamped with
  `annotations.krateo.io/source-repo`; the publisher refuses to overwrite a name
  already owned by a different source repo (loud CI failure instead of silent overwrite).
- **OCI stays the source of truth.** This registry republishes the *same bytes* the
  OCI job already produced.

The full design (architecture, collision policy, KOG-promotion workstream, backfill)
lives in `HELM_GHPAGES_PUBLISHING_PLAN.md`.
