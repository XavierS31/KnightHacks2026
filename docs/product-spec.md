# Product specification

RepoFusion helps a developer find complementary open-source tools, prove one useful integration, and improve its interface from evidence gathered by fictional AI personas. The first audience is hackathon developers and judges; the eventual audience is developers exploring repository combinations.

The primary journey is **discovery → integration validation → product v1 → 500 contextual persona trials → evidence-linked improvements → approved v2 → matched 500-persona retest**. Ten featured characters make individual sessions inspectable in a simplified 3D campus. Selecting a character opens its exact session screen and action timeline.

## Required product behavior

- Preserve documentation, issue and source-commit evidence behind each capability claim.
- Check existing combinations and equivalent-purpose products; present findings with uncertainty, never assert novelty from one empty search.
- Integrate one pair through a narrow adapter. Both repositories must work independently on known fixtures before combined validation.
- Expose the real integration through an actual product UI. A fixture pipeline remains a development demonstration until the sources are integrated.
- Generate 500 fictional personas across undergraduate, graduate, faculty, staff and local worker/resident cohorts. Balanced coverage is intentional and is not a statistically representative population.
- Every production persona includes software behavior grounded in real reviews/discussions from sources such as Reddit, Hacker News and general software-review communities. Preserve citations, software context, extraction versions and uncertainty; distinguish reported behavior from model interpretation. See [software behavior](software-behavior.md). This is P0, separate from demographic enrichment.
- Every persona executes a mandatory bounded trial on v1 and v2 and produces feedback, including initial and post-trial relevance, failures and honest stop reasons.
- Show ten characters tied to real persona/session identifiers. Visual character count, browser concurrency, configured personas and completed trials are separate counts.
- Run analyst, prioritizer, UX reviewer, implementer and QA workflows. Apply two or three bounded improvements with human review before promotion to v2.
- Preserve v1 and fixed matched tasks/checks. Compare outcomes with denominators and distinguish infrastructure failures from product problems.

## Priorities and exclusions

P0 is one real integration and one complete improvement cycle. P1 is deeper demographic sourcing, additional relevant tasks, richer research and stronger held-out regressions. P2 is a separate MapLibre overview, screencasting, 3D laptop-screen textures or more integrated products.

Do not introduce AMD/ROCm, self-hosted inference, Figma or Adobe requirements. Do not add Redis, Kubernetes, microservices, vector storage or custom physics to the initial implementation. Do not merge selected source repositories into the orchestration monorepo.

## Trial and acceptance semantics

A mandatory trial attempts one supported representative task, up to six actions, and stops early after deterministic success or a blocking failure. An initially uninterested persona still tries a sample and can report no personal need. Optional tasks are capped at eight actions and occur after mandatory coverage is secured.

Task checks evaluate actual product state/output, independent of model opinion. Synthetic usefulness or preference ratings are not human-user research. A failed trial counts as a completed attempt with a failed outcome only when evidence and feedback exist. Missing, canceled or stalled work must not be shown as successful completion.

## MVP acceptance

One selected pair passes normal/failure integration fixtures; its UI calls the real adapter; all 500 personas have attempted mandatory trials and feedback on each version; ten characters select exact sessions; five engineering roles produce evidence-linked outputs; two or three reviewed improvements produce tested v2; the comparison uses matched tasks and accurate denominators; Hugging Face performs actual runtime inference and Neon persists the core pipeline. Tests, builds, reproducible startup and labeled replay evidence pass.

