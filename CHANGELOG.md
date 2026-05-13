# Changelog

## [1.1.0](https://github.com/jaypetez/glean/compare/v1.0.0...v1.1.0) (2026-05-13)


### Features

* add base_url override for Telegram sink ([#44](https://github.com/jaypetez/glean/issues/44)) ([52f12aa](https://github.com/jaypetez/glean/commit/52f12aa7f421e9beea7c9847899e4b5a23030fd6))
* add Discord, ntfy.sh, and Slack sinks ([#41](https://github.com/jaypetez/glean/issues/41)) ([9ede3f2](https://github.com/jaypetez/glean/commit/9ede3f2d71218d0cc2d664dc58f878820bbfc606))
* add Sink plugin architecture ([#40](https://github.com/jaypetez/glean/issues/40)) ([6aabd04](https://github.com/jaypetez/glean/commit/6aabd04b3c5a91bcd1812710099824f0a901852c))
* add Webhook and File sinks ([#42](https://github.com/jaypetez/glean/issues/42)) ([8b8fd8f](https://github.com/jaypetez/glean/commit/8b8fd8f251c7684f092bce65dc145159d76007d7))
* apply_skill pipeline stage ([#59](https://github.com/jaypetez/glean/issues/59)) ([9fb3ff8](https://github.com/jaypetez/glean/commit/9fb3ff84f9c206c7826956186022bfbf06a8bee7))
* extract search backends into pluggable layer + add Serper/Exa/MWMBL ([#52](https://github.com/jaypetez/glean/issues/52)) ([098357c](https://github.com/jaypetez/glean/commit/098357c0836df3bf823ed2d41398502128815f21))
* per-source LLM model dispatch ([#58](https://github.com/jaypetez/glean/issues/58)) ([a706c49](https://github.com/jaypetez/glean/commit/a706c49e756c50a010ec075e34ff56f52a08002d))
* ship SearXNG as default-disabled docker-compose service ([#51](https://github.com/jaypetez/glean/issues/51)) ([b7b026e](https://github.com/jaypetez/glean/commit/b7b026eaa50d10b924601d72991d189804a7c0df))
* SkillConfig + LLMProvider.extract() foundation ([#57](https://github.com/jaypetez/glean/issues/57)) ([a937b4f](https://github.com/jaypetez/glean/commit/a937b4f3c98d12dc50418c2da8250deb25a548e0))


### Bug Fixes

* install glean non-editable in Docker so it survives the runtime stage ([#56](https://github.com/jaypetez/glean/issues/56)) ([b4bb461](https://github.com/jaypetez/glean/commit/b4bb461893be303c22211ee6fe9fa2503fc038ab))


### Documentation

* add sink plugin guide and config reference ([#43](https://github.com/jaypetez/glean/issues/43)) ([4704acf](https://github.com/jaypetez/glean/commit/4704acfd300e8b08d992afac60defdbbcb045733))
* refresh README and hero SVG with v1.0 features ([#55](https://github.com/jaypetez/glean/issues/55)) ([6b7f72d](https://github.com/jaypetez/glean/commit/6b7f72d4ea70e4c9f4dd6f17aacc521de479ce83))
* search backend plugin guide + config reference ([#54](https://github.com/jaypetez/glean/issues/54)) ([9d2e328](https://github.com/jaypetez/glean/commit/9d2e3285b657f5671ca2cfa48b3abfdd6bf524f1))
* skills + per-source LLM guides + 4 example skills ([#60](https://github.com/jaypetez/glean/issues/60)) ([e4e1d93](https://github.com/jaypetez/glean/commit/e4e1d9337e43e416fc8488f6a17185aa480ef203))
