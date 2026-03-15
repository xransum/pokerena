# Smogon tiers

Loads and parses Smogon tier assignments from Pokemon Showdown's
`formats-data.ts` source files on GitHub.

Supports Gens 1-9. Falls back to a hard-coded Gen 1 tier map if the network
is unavailable, and defaults all other gens to OU on failure.

::: pokerena.data.smogon
