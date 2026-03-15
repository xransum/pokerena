# Loader

Assembles `Pokemon` model instances from PokeAPI and Smogon data.

Fetching is parallelized with 20 concurrent threads (`ThreadPoolExecutor`).
The network is only hit on a cold cache; all subsequent runs use the disk cache.

::: pokerena.data.loader
