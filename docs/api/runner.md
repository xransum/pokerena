# Tournament runner

Orchestrates the three-phase tournament structure:

- **Phase 1** -- full round robin within each Smogon tier
- **Phase 2** -- adjacent-tier playoffs between tier champions
- **Phase 3** -- grand final round robin among all playoff winners

Battle processing is parallelized with `ProcessPoolExecutor`.

::: pokerena.tournament.runner
