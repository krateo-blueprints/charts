# krateo-blueprints/charts — Krateo Helm registry (GitHub Pages)

Classic Helm registry for all Krateo charts, served from GitHub Pages
with **three channels** under one site. OCI (`oci://ghcr.io/krateo-blueprints/charts/...`)
remains the source of truth; this registry republishes the same chart bytes.

## Channels

| Channel | Add it with | Contents |
|---|---|---|
| **blueprints** | `helm repo add krateo-blueprints https://krateo-blueprints.github.io/charts/blueprints` | User-installable Krateo marketplace blueprints (`Chart.yaml` + `values.schema.json` + `compositiondefinition.yaml` + marketplace metadata). The Krateo marketplace registers this channel. |
| **pages** | `helm repo add krateo-pages https://krateo-blueprints.github.io/charts/pages` | Portal page sets (`krateo.io/kind: page-set`): installable like blueprints, not listed by the Marketplace. |
| **operators** | `helm repo add krateo-operators https://krateo-blueprints.github.io/charts/operators` | Operator/KOG install charts, CRD/helper/target subcharts, plain dependency/app charts. Installable via helm; not rendered as marketplace tiles. |

**How every chart in the organisation is published is decided once, in [PUBLISHING.md](PUBLISHING.md)**, and
`publish-chart.yaml` enforces it. New tarballs are stored in this repository's **Releases**. Entries indexed
before 2026-11-07 keep their original URLs, so no existing release asset may be deleted.

## Layout

- **`gh-pages`** branch (Pages source, `/`): `blueprints/`, `pages/` and `operators/` `index.yaml`, the
  three channel indexes; `icons/`; the 2026 backfill's tarballs; `.nojekyll`.
- GitHub **Releases** of this repository: the tarball store, one release per `<name>-<version>`.
- **`main`**: `.github/workflows/publish-chart.yaml`, the reusable publisher. Callers pin a full commit SHA with its `# 1.x.y` version comment, upgraded by Dependabot (PUBLISHING.md rule 9).

There is no reindex workflow. The old one rebuilt both indexes from the tarballs on gh-pages only,
which would have dropped every entry stored anywhere else. Indexes are only ever merged.

## Onboarding a repository

Follow [PUBLISHING.md](PUBLISHING.md). The call is:

```yaml
  publish-index:
    needs: release
    uses: krateo-blueprints/charts/.github/workflows/publish-chart.yaml@<sha> # 1.0.0
    with:
      source_repo: ${{ github.repository }}
      git_tag: ${{ github.ref_name }}
      channel: blueprints
    secrets:
      PUBLISH_TOKEN: ${{ secrets.CHARTS_PUBLISH_TOKEN }}
```

`CHARTS_PUBLISH_TOKEN` is an **organisation** secret, a classic PAT with `repo` scope, visible to all
repositories. Don't fall back to any other secret.
