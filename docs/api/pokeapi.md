# PokeAPI client

HTTP client for [PokeAPI](https://pokeapi.co). All responses are cached locally
so the network is never hit during simulation once the cache is warm.

Retries up to 3 times on HTTP 429/5xx and network errors using a linear ramp
with random jitter (250 ms, 500 ms, 750 ms + up to 100 ms jitter per attempt).

::: pokerena.data.pokeapi
