# How every krateo-blueprints chart is published

This is the one publishing standard for every chart in the krateo-blueprints organisation. Diego
decided it on 2026-11-07. A repository that publishes charts follows it. Anything it doesn't cover
is decided here first and then applied everywhere, never repository by repository.

The rules that can be checked are checked by `publish-chart.yaml`, so a caller that ignores them
fails its release instead of publishing something wrong.

## Why there is a standard

On 2026-11-07, the Marketplace was installing OpenStack 0.2.0 when GHCR held 0.3.36, and
`openstack-nova-operator-kog` 0.1.0, an architecture its team had deleted. About 25 repositories
pushed only to GHCR, and the Marketplace never saw them. The 11 that did call the publisher all
fell back to an org token that had stopped authenticating, and nothing has entered the index since
2026-10-09. The publisher also created one GitHub release per chart in each caller, and five
callers' "Latest" ended up on a single chart. Two published archives carried a CompositionDefinition
pinned to a version other than their own (gcp 0.1.5 shipping 0.1.0, azure 0.1.3 shipping 0.1.0).
No release reported any of this.

## The standard

1. **Every chart is packaged once and published twice, with the same bytes.**
   - **GHCR:** first, at `oci://ghcr.io/krateo-blueprints/charts/<name>:<version>`. Every chart in
     this organisation publishes to that registry and no other.
   - **The index here:** second, by `publish-chart.yaml`. A chart that is in GHCR and not in the
     index is not published, because the Marketplace installs from the index and nothing
     re-resolves it against GHCR.

   A chart nobody has cleared to be public is outside this rule: its GHCR package stays private
   and it is not indexed. Indexing makes a chart public (rule 5), so leaving it out is a decision,
   and the release says so. krateo-selfservice-blueprint's tenant charts are an example.

   GHCR is the source of truth, so what goes to the index is the archive GHCR holds, not a second
   package. A repository that packages its own charts hands the archives it pushed. A repository
   on the shared `krateo-platformops/.github` `release-oci.yaml` pulls each chart back from GHCR
   after that workflow runs. That covers a version the workflow skipped because it was already
   published identically: a fresh `helm package` would have new mtimes and different bytes.

   **How the Marketplace picks versions** (Diego, 2026-11-07): the live index leads. For any chart
   whose newest version lists a `https://github.com/krateo-blueprints/<repo>` URL in `sources:`,
   the portal shows the live index's versions first, newest first. The catalog snapshot bundled in
   `krateo-marketplace-catalog` is the fallback: it serves offline and air-gapped installs, and
   names the live index doesn't have. So a chart without that `sources:` entry never updates in
   the Marketplace, however often it is published.

2. **The channel follows from the content, not from preference.**
   - **`blueprints`:** a chart with `values.schema.json` and a CompositionDefinition. These are the
     Marketplace's charts.
   - **`pages`:** a chart with `values.schema.json` and a CompositionDefinition whose `Chart.yaml`
     declares `annotations: krateo.io/kind: page-set`, meaning a set of portal pages installed by
     the Composer. It is published and installable like a blueprint, but the Marketplace doesn't
     list it. Diego decided on 2026-11-07 that page sets stay off the Marketplace.
   - **`operators`:** every other chart, such as operators, KOGs without a CompositionDefinition,
     and helper or CRD charts.

   The publisher refuses a chart sent to any channel other than its own. The caller passes one
   `channel:` per call, and the publisher's refusal arrives after the GHCR push, so the caller's
   release must check each chart's channel itself, before pushing anything. A repository with
   charts of more than one kind uploads one artifact per channel and calls the publisher once per
   channel.

3. **A blueprint or page-set archive is self-describing.** The archive must contain, at its root:
   - `values.schema.json`;
   - `compositiondefinition.yaml`, whose `spec.chart.url` is
     `oci://ghcr.io/krateo-blueprints/charts/<name>` and whose `spec.chart.version` is the
     chart's own version.

   `Chart.yaml` must have an absolute https `icon` and a non-empty `keywords` list. The
   Marketplace turns `keywords` into filter chips, so they must be words a user would filter by:
   the domain (`openstack`, `dns`, `events`) and the kind (`blueprint`, `controller`). Words true of
   every chart (`krateo`, `helm`, `chart`) make a chip that filters nothing, so leave them out.

   Every chart, in every channel, lists the repository that builds it in `Chart.yaml` `sources:`,
   as `https://github.com/<owner>/<repo>`, next to any upstream projects. That entry is what makes a
   chart appear and update in the Marketplace (rule 1). That is
   how a pinned chart is traced back to the commit and CI run that built it (the installer's
   `check-pin-ci`).

   A chart meant to be pinned as an installer component must also meet the installer's component
   contract in krateo-platformops/installer. For example, a closed `values.schema.json` declares
   `global`, which is injected at install. That contract is the installer's to version, so it is
   referenced here and not copied. A publish can't catch a missing `global`: `helm lint` validates
   `values.yaml`, which has none. Copy the stamped CompositionDefinition into the chart directory
   before `helm package`, then check the archive itself: `helm package` succeeds whether the file
   is there or not.

4. **A chart's version and its CompositionDefinition's version are one number, and the release
   proves it.** The publisher refuses a CompositionDefinition whose version isn't the chart's. A
   repository's own release must also refuse a chart whose version doesn't match the version it
   claims to release. Which shape that takes depends on how the repository versions its charts:
   - **Charts that version together (the default):** the committed files carry `CHART_VERSION`,
     the release stamps it from the git tag, and tag, chart and CompositionDefinition are all one
     number.
   - **Charts that version independently:** this applies where a chart's version is a served API
     version that other charts depend on. For example, `kubernetes-cluster` names
     `composition.krateo.io/v0-6-3`, which must equal `baremetal-host` 0.6.3. Stamping every chart
     from one tag would re-point and stop serving versions for charts that didn't change. These
     repositories commit literal versions, and their release refuses any chart whose
     CompositionDefinition, or any dependent apiVersion reference, disagrees with it
     (openstack-ironic-operator-kog's `check-examples`).
   - **Charts whose author tool writes the version:** the Blueprint Composer writes a literal
     version and merging releases it. builder-scaffold's release refuses a tag, a `Chart.yaml` and
     a CompositionDefinition that differ.

   An unguarded literal is how 0.2.0 and 0.1.0 outlived every later release.

5. **Tarballs are stored in this repository's Releases.** There is one release per
   `<name>-<version>`, created with `--latest=false`, and its notes record the publishing
   repository. Because this repository is public, a chart from a private repository still
   downloads.
   - **Publishing makes a chart public.** That includes one from a private repository, so publish
     only what may be public.
   - **The caller's release page is never touched.**

6. **One owner per chart name.** The first repository to publish a name owns it. Before it writes
   anything, the publisher refuses another repository's version of that name and refuses to
   overwrite a stored version. It finds the owner from, in order: the entry's `krateo.io/source-repo`
   annotation; this repository's release notes for that version; the repository named in the
   entry's URL; the first organisation repository in the entry's `sources`.
   - **Unresolved names:** 37 names from the 2026 backfill resolve to none of these. The first
     repository to publish one after this standard claims it, and the release notes record the
     claim, so it resolves from then on.
   - **Disputes:** if the wrong repository claims a name, it is fixed here, by hand, in the
     release notes, never by publishing over it.

7. **One token: the org secret `CHARTS_PUBLISH_TOKEN`.** It is a classic PAT with `repo` scope,
   visible to all repositories, and it has no fallback. `RELEASE_FEED_TOKEN` is for the
   release-notes feed and is never used for the index. The publisher checks that the token can
   write here before it does anything else, so a dead token fails at the first step with a message
   that says so. A caller's own token check gates its GHCR push: the push job depends on the check.
   Making only the publisher call depend on it changes nothing, because that call already runs after
   the push. A check that also reads the packaged archives can't simply be moved in front; split it
   into a token check before the push and an archive check after packaging. The check tests the same
   secret the caller passes to the publisher, and its shape as well as its presence: a token with
   whitespace in it is refused before the push. That's the only check that runs before anything is
   pushed (openstack-ironic-operator-kog, krateo-arubacloud-provider-kog#54). Never print the
   value. With no valid token, a release produces nothing, not
   even the GHCR artifact. When dropping an old fallback, change both places: a check left on
   `CHARTS_PUBLISH_TOKEN || RELEASE_FEED_TOKEN` validates a token the publish no longer sends, and
   nothing fails to warn you.

   The publisher also refuses a token containing whitespace or a control character, usually a
   trailing newline from piping into `gh secret set`. Such a token authenticates, then breaks any
   use that builds a URL from it, so no check of whether the token works can see the problem. In
   github-provider-kog's 0.7.6 run, the publisher's own write check passed with that value and the
   clone failed two steps later, in the same job. It never puts the token in a URL; git authenticates through `gh`'s credential
   helper. Checking before the push is a mitigation, not a guarantee: the publisher can still fail
   after a caller's GHCR push. A half-published version is not lost and needs no new
   version number. Publishing again is safe: the store re-uploads its own version, the index merge
   keeps existing entries, and an unchanged index is not committed. How to publish again depends on
   where the cause was:
   - **Outside the publisher**, such as the secret: re-run the failed publisher job.
   - **In the publisher:** re-running the job reuses the old pin, so it fails the same way. Re-pin
     the caller to the fixed publisher on `main`, then run the release again for the same version:
     `workflow_dispatch`, or re-push the tag. The GHCR push skips an identical version, and the
     index then receives it.

8. **The release isn't done until the Marketplace can install it.** The publisher reads the served
   `index.yaml` until every chart it published is listed at its version, then installs each one
   anonymously with `helm pull --repo`, the path the Marketplace uses. If either check fails, the
   release fails. Callers don't need their own check.

9. **Every reusable workflow a repository calls is pinned by full commit SHA, with what that commit
   is in a comment, and Dependabot upgrades it.** For example:
   `publish-chart.yaml@<40-character sha> # 1.1.0`. This covers the publisher, `release-preflight.yaml`
   and `pinned-uses.yaml` here, and every other repository's reusable workflow, for example
   krateo-platformops/.github's `lint-docs.yaml`, `release-notes.yaml`, `security.yml`, `release-oci.yaml`
   and `component-image-build.yaml`.

   A movable ref, whether a branch like `main` or a tag like `1`, lets whoever moves it run code in
   every caller at once, with whatever the caller passes or grants. The publisher receives
   `CHARTS_PUBLISH_TOKEN`, an org-wide write token; `release-oci.yaml` runs with `packages: write`;
   `security.yml` runs with `security-events: write`. A movable ref also changes a caller's CI with no
   commit in the caller, so a green run can't be reproduced. A SHA can't move. On 2026-11-18, 136
   reusable `uses:` in 51 repositories were movable, the publisher itself `@main` in 12 (#20).
   - **The comment:** `# X.Y.Z`, the tag that commit carries, is the preferred form, because
     Dependabot advances it. `# main YYYY-MM-DD`, the date of a commit on the publisher's `main`,
     exists only for a publisher with no tags.
     - **Why it is transitional:** `# main YYYY-MM-DD` is for a publisher with no tags. Dependabot cannot
       advance such a pin, so it is transitional: a repository on this form is waiting on its publisher
       to tag, and moves to `# X.Y.Z` when it does. The dated pins are then replaced, not kept as a second
       way to pin. krateo-platformops/.github is tagged from `1.0.0`, so pin `# 1.0.0`.
     - **Resolve with `^{}`:** an annotated tag is resolved with `^{}` both when pinning and when
       reviewing a pin.
     - **Rewrite the explanation too:** a caller whose comment explains the dated form ("no tags yet")
       now holds a stale explanation. The re-pin rewrites that comment as well as the commit.
     krateo-platformops/.github published its first tag, `1.0.0`, on 2026-11-18. The annotated tag
     object is `0b109bb3f15f1f80d97c0aa1f1dcae6eb070fbeb`, and it peels to
     `e1d3e99215e80ae56eca4a67e9e061b2c73168b8`, the merge of its #64 (#23). So:
     - the preferred form for it is now `# 1.0.0`, so a `# main YYYY-MM-DD` pin into it moves to
       `# X.Y.Z`. At `e1d3e99` the change is the comment alone;
     - resolve the tag with `^{}`, both when pinning and when reviewing a pin. `refs/tags/1.0.0` is the
       tag object `0b109bb…`, not the commit, and comparing a pin against it shows a false mismatch;
     - Dependabot advances the pin from there;
     - `pinned-uses.yaml` still accepts the dated form, but prints a notice for every dated pin into
       a tagged repository and counts them in its summary.
   - **A deliberate float is recorded at the line, dated, with its reason.** A repository may choose
     to follow an org-owned reusable workflow's branch instead of a commit. It says so where it
     happens, either inline:

     ```yaml
         uses: krateo-platformops/.github/.github/workflows/security.yml@main # floating: 2026-11-07 <reason>
     ```

     or, for a rationale longer than a line, with the marker alone and the reason as the comment block
     immediately above the `uses:` line, inside the same job, with no blank line between:

     ```yaml
         # <reason, as many lines as it needs>
         uses: krateo-platformops/.github/.github/workflows/release-notes.yaml@main # floating: 2026-11-07
     ```

     `pinned-uses.yaml` treats this as a third comment form, beside `# X.Y.Z` and `# main YYYY-MM-DD`,
     and accepts it only when what it can verify holds. It refuses:
     - a missing or impossible date (the date makes a float's age visible);
     - no reason, inline or in the block above;
     - an owner outside the org-owned list (`krateo-platformops`, `krateo-blueprints`), since nobody
       floats code someone else controls;
     - the publisher, `krateo-blueprints/charts/.github/workflows/publish-chart.yaml`, which receives
       `CHARTS_PUBLISH_TOKEN` and is always pinned;
     - `floating` on a 40-hex pin, which is meaningless;
     - a tag or an abbreviated SHA. With no network lookup, a ref that looks like a version (`1`,
       `1.1.0`, `v7`) or is 7 to 39 hex characters reads as one, so a branch named like that is
       refused.

     Each accepted float is printed with its file, line, date and reason. The summary line always
     reads `P not pinned, F floating, I cross-org secrets inherit`, so a float is never hidden behind
     a bare "0 not pinned". A float gets no Dependabot pull request, by definition: it moves whenever
     the branch does. (Diego, for openstack-nova-operator-kog, 2026-11-07, reaffirmed 2026-11-18:
     nova floats its krateo-platformops/.github workflows at `main`; the publisher stays pinned.)
   - **Enforced, not described:** every repository calls `pinned-uses.yaml` from its lint, pinned the
     same way. It refuses any non-local `uses:` of a reusable workflow whose ref is not 40 hex
     characters with one of those two comments, unless it is a recorded float as above:

     ```yaml
       pinned-uses:
         uses: krateo-blueprints/charts/.github/workflows/pinned-uses.yaml@<sha> # 1.2.0
     ```

     Local workflows (`./...`) move with the caller's own commit and are not checked. Actions
     (`owner/repo@ref`, such as `actions/checkout`) are out of this rule's scope (#20, decided
     2026-11-18), except the shared chart-push action, which rule 14 pins the same way and
     `pinned-uses.yaml` checks.
   - **Inside shared reusables too.** A caller that pins a reusable by SHA freezes only that file's
     text. A reusable that calls another workflow or action at `@main` still changes under every
     pinned caller with no commit in any of them. The github-provider-kog and azuredevops-provider-kog
     sessions found this independently on 2026-11-18, in krateo-platformops/.github's
     `release-oci.yaml`. So a reusable pins everything it calls by commit, transitively:
     - **Order:** leaves first, then their callers. A pinned commit must contain what it pins.
     - **Bumped together:** internal calls are pinned inside the file and bumped together (Diego).
     - **No float:** a reusable never floats, so `pinned-uses.yaml` refuses a recorded float in any
       file with `on: workflow_call`.
     - **Enforcement:** this repository's reusables are checked by its own `this-repository` job.
       krateo-platformops/.github checks its internal calls with its own `test-internal-pins.yaml`
       (krateo-platformops/.github#60).
   - **Secrets cross organisations by name, never by `inherit`.** `secrets: inherit` passes nothing
     to a reusable workflow owned by another organisation, and nothing reports it: the called
     workflow reads each secret as empty. krateo-platformops/.github's `release-notes.yaml` then
     skips every step and reports success, so openstack-keystone-operator-kog 0.4.1 and 0.4.2
     shipped without notes while the org secret was set (openstack-keystone-operator-kog#33,
     krateo-platformops/.github#57). Pass each secret the reusable declares under `secrets:` by name.
     `pinned-uses.yaml` refuses an uncommented `secrets: inherit` on any `uses:` whose owner is not
     the caller's; a comment that mentions it is fine, and so is `inherit` within one organisation.
   - **Releases here:** tags are plain semver with no `v` prefix (the organisation's convention), and
     each release is cut as a tag such as `1.0.0` on `main`.
   - **Pin the commit, not the tag object.** Release tags are annotated, so `git ls-remote` on
     `refs/tags/1.0.0` and the GitHub tags page give the tag object's SHA (for `1.0.0`,
     `54acb674…`), and Actions won't run a workflow pinned to it. Take the commit with
     `git ls-remote https://github.com/krateo-blueprints/charts 'refs/tags/1.0.0^{}'`. For `1.0.0`
     that is `a2d63ba50e138b17f678528d6d6be3afef48715a`.
   - **Upgrades:** every caller has `.github/dependabot.yml` with the `github-actions` ecosystem, so a
     new release of a tagged reusable workflow arrives as a reviewed pull request in each repository
     rather than silently. That is how a fix like #5 or #6 still reaches everyone. A `# main
     YYYY-MM-DD` pin has no tag for Dependabot to follow; it is moved by hand, deliberately.
     Three lessons from moving these pins (openstack-ironic-operator-kog, 2026-11-18):
     - **Record the command, not the output.** A pin's SHA appears exactly once, on its `uses:` line.
       The defect is a comment line holding a **40-hex SHA equal to a `uses:` pin's SHA in the same
       file**, for example the pinned `1e6210ab…` repeated in a comment above it
       (openstack-ironic-operator-kog `release-chart.yaml:287` before its #126). Dependabot does not
       update that copy, so it goes stale on the next bump. Short references to commits that nothing
       pins (a measurement baseline, a history note, an upstream ref) are provenance, and they're
       welcome. The test is `^\s*(?:-\s+)?uses:\s*\S+@([0-9a-f]{40})\b` over the file's
       uncommented lines for its pins, then a comment's 40-hex match counts only if it is in that set.
       A copy of the pin is replaced by how to re-resolve it:

       ```yaml
           # Resolve with: git ls-remote https://github.com/krateo-blueprints/charts 'refs/tags/X.Y.Z^{}'
           uses: krateo-blueprints/charts/.github/workflows/publish-chart.yaml@<sha> # X.Y.Z
       ```

       That command prints nothing in three cases: the tag is gone, the repository is the wrong one,
       or the network failed. The openstack-nova-operator-kog session first asked
       krateo-platformops/.github for charts tags. So run the control first: `git ls-remote --tags
       <repo> | wc -l` must be greater than 0 before an empty answer is read as "no such tag".

     - **Exclusion is not grouping.** The defect is charts pins excluded from a group **and** in no
       group of their own. An exclusion paired with a dedicated charts group is the fixed state.
       Excluding `krateo-blueprints/charts*` from a Dependabot group,
       so that charts pins are reviewed separately, makes each charts pin its own pull request. Merged
       one at a time, they drift apart, and the repository pins two charts versions. Use a dedicated
       group instead, so all of a repository's charts pins move together in one pull request:

       ```yaml
       version: 2
       updates:
         - package-ecosystem: github-actions
           directory: /
           schedule:
             interval: weekly
           groups:
             krateo-charts:
               patterns:
                 - "krateo-blueprints/charts*"
             krateo-platformops:
               patterns:
                 - "krateo-platformops/.github*"
       ```

     - **For `publish-chart.yaml`, compare the contract, not the diff size.** It is on the release
       path, and a broken contract shows up only when a tag is pushed. Before moving its pin, compare
       `on.workflow_call` at both SHAs: its `inputs` (names, `required`, types) and its `secrets`. Read
       the file at each SHA, for example `gh api -H 'Accept: application/vnd.github.raw'
       'repos/krateo-blueprints/charts/contents/.github/workflows/publish-chart.yaml?ref=<sha>'`. A
       small diff can still add a required input, and a large one may change none.

10. **Released commits passed lint.** The caller's release refuses a commit with no successful lint
    run. That check belongs to the caller's workflow, because only the caller knows its own lint.

11. **A blueprint declares who can see it, and whoever registers it grants that.** The portal's
    Blueprints page shows a user only the CompositionDefinitions in namespaces where they may
    `list compositiondefinitions.core.krateo.io` (krateo-platformops/portal#261). The grant belongs
    in the CompositionDefinition's namespace, which only the registrar knows. The blueprint's own
    chart renders in each instance's namespace, after an instance exists, so it can't make the
    grant. A blueprint declares its reader groups (default `admins` and `devs`, the portal's
    `blueprints-page.readerGroups`), and the grant comes from:
    - **the installer**, for catalog blueprints, through the component's `readerGroups`, which
      renders a Role and RoleBinding in the definition's namespace;
    - **a manifest published beside the CompositionDefinition**, for manual registration.
      krateo-openstack-blueprint's `portal-visibility-rbac.yaml` is an example.

12. **A release runs the repository's own preflight before it publishes anything.** Some
    preconditions only the repository can state, such as a fixture in `examples/` that names the
    version being released, which nothing stamps. Written as a comment, such a precondition gets
    missed: openstack-neutron-operator-kog's example Composition named `v0-1-0` through 0.1.1. So:
    - **The hook:** a repository that has such a precondition ships it as an executable
      `hack/release-preflight`. It receives the version being released as `$1`, and a non-zero exit
      refuses the release.
    - **The call:** every release calls this repository's reusable `release-preflight.yaml` as a job
      of its own, pinned like the publisher (rule 9). The job that pushes to GHCR declares `needs:`
      on it, so every later step does too. A refusal then stamps, pushes, indexes and releases
      nothing, and needs no new version number.
    - **The version, before anything else:** the job first checks the version against rule 13's pattern,
      `^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$`, and refuses anything else, hook or no hook.
      - **Why it runs here:** publish-chart refuses the same versions, but at index time, after the
        caller's GHCR push. A version only publish-chart refused would be pushed and never indexed, the
        half-state this preflight exists to prevent.
      - **Found by:** github-provider-kog#111. Its own earlier check, `^[0-9]+\.[0-9]+\.[0-9]+$`, accepted
        `0.015.0`. A repository's own version check is never looser than this one.
      - **One pattern:** it is byte-identical in `release-preflight.yaml` and `publish-chart.yaml`, and
        `test/release-preflight/run-cases.py` fails if the two differ.
    - **Repositories without the hook:** the version check still runs; otherwise the job passes and says
      so, so every repository can call it unconditionally.
    - **A hook that can't run:** a `hack/release-preflight` that exists but is not an executable
      file fails the job. A lost executable bit would otherwise skip the guard exactly when it was
      meant to run.
    - **What the hook gets:** the caller's checkout at the commit that triggered the release, read-only
      contents permission, no secrets.

    ```yaml
      preflight:
        uses: krateo-blueprints/charts/.github/workflows/release-preflight.yaml@<sha> # 1.1.0
        with:
          version: ${{ github.ref_name }}

      release:
        needs:
          - preflight   # and the token check (rule 7)
    ```

13. **Pre-releases are never indexed.** The publisher refuses any chart whose version is not a
    plain `X.Y.Z`: no `v`, no leading zeros, no `-prerelease`, no `+build`. Every channel is
    covered. An index entry is never removed, and the Marketplace offers the live index's versions
    newest first, so a pre-release that got in would be offered to users permanently.

    A repository may still publish pre-releases to GHCR, at the same
    `oci://ghcr.io/krateo-blueprints/charts/<name>` path, to verify a commit before tagging it.
    krateo-openstack-blueprint's `prerelease.yaml` does this, at `X.Y.Z-main.g<sha7>`. Such a
    workflow doesn't call this publisher and doesn't hold `CHARTS_PUBLISH_TOKEN`. Helm resolves an
    OCI chart with no `--version` to the newest version that isn't a pre-release, so it installs a
    pre-release only when someone asks for that exact version.

    The same pattern is checked twice:
    - **First, before any push:** `release-preflight.yaml` (rule 12) refuses the release version
      before the caller's GHCR push.
    - **Second, at index time:** a pre-release handed to the publisher by mistake fails the content
      gate before anything is stored.

    Both use one pattern, kept byte-identical by a test. Measured on 2026-11-18, all 3,186 entries in the `blueprints` and `operators` indexes
    were already plain `X.Y.Z`, so the rule refuses nothing that has ever been published.

14. **Every chart is pushed through one shared action, which survives GHCR's tag race.** GHCR
    sometimes accepts a chart's manifest PUT and then answers 404 to the GET by digest that helm's
    Tag step makes about a second later:

    ```
    Error: failed to perform "Tag" on destination: sha256:<digest>: not found
    ```

    The push fails and leaves an untagged manifest behind. On 2026-11-13 this failed portal 1.8.115
    and 1.8.116. On 2026-11-18 it failed the keycloak operator KOG 0.11.0 release and
    krateo-blueprints/rabbitmq-operator-blueprint's pre-release run 44279368853. A bare `helm push`
    has nothing between that error and a red release, and a per-repository copy of the fix drifts.
    So there is one implementation (Diego, 2026-11-18): krateo-platformops/.github's `chart-push`
    action, the one `release-oci.yaml` already pushes through.
    - **The action:** a workflow pushes each packaged chart with
      `krateo-platformops/.github/.github/actions/chart-push`, in push mode or locate mode. It is pinned like a reusable
      workflow (rule 9), by full commit SHA with the tag in a comment, `# X.Y.Z`.
      krateo-platformops/.github is tagged since `1.0.0` (#23), so Dependabot advances the pin, and
      the transitional `# main YYYY-MM-DD` is no longer needed. It is never floated, because it
      receives the caller's registry write credentials:

      ```yaml
          - name: Push the chart
            id: push
            uses: krateo-platformops/.github/.github/actions/chart-push@e1d3e99215e80ae56eca4a67e9e061b2c73168b8 # 1.0.0
            with:
              chart: dist/<name>-<version>.tgz
              repository: oci://ghcr.io/krateo-blueprints/charts
              registry-username: ${{ github.actor }}
              registry-password: ${{ secrets.GITHUB_TOKEN }}
      ```

      Credentials are inputs passed by name, never through `secrets: inherit`, which carries nothing
      across organisations (rule 9). The action refuses an empty input before anything is sent, logs
      in with the token on stdin, and outputs the pushed manifest digest as `digest`. The caller
      sets up helm and grants `packages: write`.

      **Locate mode** is for a loop over several charts in one step. With no inputs, the action only
      outputs the path of its `push.sh`, and the loop runs that script once per chart. Push mode and
      locate mode run the same `push.sh`. `release-oci.yaml` pushes each chart this way:

      ```yaml
          - name: Locate the shared chart push
            id: chart-push
            uses: krateo-platformops/.github/.github/actions/chart-push@e1d3e99215e80ae56eca4a67e9e061b2c73168b8 # 1.0.0
          - name: Push every chart
            env:
              CHART_PUSH: ${{ steps.chart-push.outputs.path }}
              REGISTRY_USERNAME: ${{ github.actor }}       # push.sh's read-back, after helm registry login
              REGISTRY_PASSWORD: ${{ secrets.GITHUB_TOKEN }}
            run: |
              for tgz in dist/*.tgz; do
                bash "${CHART_PUSH}" "$tgz" oci://ghcr.io/krateo-blueprints/charts
              done
      ```

      `e1d3e99215e80ae56eca4a67e9e061b2c73168b8` is tag `1.0.0` of krateo-platformops/.github,
      the merge of its #64, committed 2026-11-18. Its chart-push is the one #63 left:
      - #59 brought the digest-safe retry;
      - #61 took the last `| head -n1` reads out of it;
      - #63 moved the read-back's credentials and Bearer token off curl's command line onto its stdin.

      A pin at `653ac1e`, #63's merge, runs the same files. At `1.0.0`, `push.sh` has sha256
      `e291264346502fac37f1df85d7c48d8794193b489c5d3ef84c7c7f583f317b03` and `action.yml`
      `3ee0aca665b798c37da7179cd23a2b2d84f7da3990eac1a538d46e75b01bffce`. The example names a commit
      so it can be copied as is; pin the newest commit that changed the action.
    - **What it retries:** that exact error and nothing else. It waits, polling up to 10 times 3 s
      apart, until the registry serves bytes that hash to the digest, then pushes the same untouched
      archive again. helm takes the manifest's created time from the archive's modification time
      (v3.19.0 and v4), so the second push has the same digest. If it reports another digest, the
      push fails rather than leave the tag on a manifest other than the one first pushed. Any other
      error fails at once, and so does a digest still not served after the last poll. The action
      and its tests (the 7 cases and 6 mutants it was written with) live in
      krateo-platformops/.github, not here.
    - **Shared reusables too:** a reusable workflow that pushes charts for its callers pushes through
      the same action, pinned the same way. `release-oci.yaml`'s pin is krateo-platformops/.github#60,
      together with every other internal call there (rule 9, inside shared reusables).
    - **No bare push:** a `helm push` or `oras push` in any workflow is refused. `pinned-uses.yaml`
      checks this beside rule 9, so every repository that already runs it from its lint is checked
      with no new job. It refuses every uncommented line that runs either command; a line that is a
      YAML or shell comment is not a push. The check is textual:
      - It refuses prose that names a command, such as a step name or an `echo` message. Reword it.
      - **Scripts are read too.** It reads every workflow file, and also every `*.sh`, `*.mk` and
        `Makefile` anywhere in the checkout. So a push inside a script or a make target a workflow runs
        is refused like one in a `run:` block. A heredoc line counts as live, since it runs.
        krateo-openstack-blueprint's `hack/publish-charts.sh` passed 1.4.0 that way, until 1.4.1
        closed the gap.
        - In a script, use locate mode: `bash "${CHART_PUSH}" <tgz> <oci repo>`, with CHART_PUSH
          exported from the action's `path` output.
        - Other files are not read: a Python script that runs it, or a push through a variable
          (`$HELM push`). Such pushes are replaced by the action, not hidden from the check. A `.py` is
          left out because a comment-line filter would count docstring prose as code, and the 2026-11-18
          scan of all 103 repositories found no `.py` that runs helm.
        - The summary line counts the scripts scanned, so "0 script(s)" shows when there was
          nothing to read.
      - It can't tell an `oras push` of a chart from one of another artifact, so a non-chart
        `oras push` is decided here first.

## Scope

This standard covers every repository in the krateo-blueprints organisation. builder-scaffold also
seeds repositories in other owners' accounts and on self-hosted SCMs. Those have no
`CHARTS_PUBLISH_TOKEN` and publish to their own registry, so the scaffold runs the index publish
only when `github.repository_owner` is `krateo-blueprints`.

## What is never done

- **Deleting a per-chart release or a stored tarball.** About 1,247 entries indexed before this
  standard resolve through per-chart releases in the callers' repositories, and the rest resolve
  here or on gh-pages. Deleting one breaks that version for everyone.
- **Removing or editing an index entry.** Diego decided on 2026-11-07 that the 2026-08-19 backfill's
  stale or misfiled entries are superseded, not removed. Examples are nova 0.1.0,
  hyperdx-provider 0.1.2 in `blueprints` and hetzner-object-storage-kog 0.1.0 in `operators`. The
  next release under this standard adds a newer version, which the Marketplace offers first.
- **Rebuilding an index from scratch.** `helm repo index` without `--merge` drops every entry whose
  tarball isn't in the directory it indexes. The old `reconcile.yaml` did exactly that, from
  gh-pages only, so it has been removed.
- **Publishing by hand.** A one-off backfill is how the index came to describe a pipeline that no
  longer existed.

## Calling the publisher

```yaml
  publish-index:
    needs: release        # your job that pushed to GHCR and uploaded the .tgz as artifact "charts-dist"
    uses: krateo-blueprints/charts/.github/workflows/publish-chart.yaml@<sha> # 1.0.0
    with:
      source_repo: ${{ github.repository }}
      git_tag: ${{ github.ref_name }}
      channel: blueprints   # a repo with both kinds uploads two artifacts and calls once per channel
    secrets:
      PUBLISH_TOKEN: ${{ secrets.CHARTS_PUBLISH_TOKEN }}
```

krateo-blueprints/krateo-openstack-blueprint's `release-tag.yaml` is a complete caller covering
rules 1 to 4 and 10 (rule 12's preflight job is to be added there once `release-preflight.yaml` is tagged): placeholder stamping, the CompositionDefinition copied into each chart, archive
assertions, a lint check and the call.
