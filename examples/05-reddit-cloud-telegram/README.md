# 05 — Reddit → Telegram with a cloud LLM and personalized ranking

A self-contained glean example that watches curated subreddits, ranks posts with a personalized cloud-LLM prompt, summarizes the winners, and sends the digest to Telegram every 2 hours.

**Cloud LLM is the differentiator here:** the default setup uses **OpenAI `gpt-4o-mini`**, with an **Anthropic** swap documented below. There is **no Ollama container, no GPU requirement, and no 5 GB model pull**.

One container only: `glean-ex05-glean` on host port `9095`, attached to the private bridge network `glean-ex05`.

## Requirements

- Docker 24+ with `docker compose` v2
- `curl` (used by the setup scripts for the health check)
- A Telegram bot token plus two chat IDs:
  - the destination chat for digests
  - the ops chat for failure/recovery alerts
- **One** cloud LLM API key:
  - `OPENAI_API_KEY` (default path), or
  - `ANTHROPIC_API_KEY` (after switching the config block)

No Ollama. No GPU. No local model download.

## Cost estimate

With the default settings (`gpt-4o-mini`, two subreddit sources, `max_llm_calls_per_run: 80`), a reasonable rule of thumb is **<= $0.01 per tick** and often **well under $1/month** at `every 2h`.

That is **informative, not a guarantee**. Actual cost depends on token pricing, prompt size, how many Reddit posts survive ranking, and whether you change the schedule or LLM.

## One-shot setup

1. Copy `.env.example` to `.env` and fill in the required values.
2. Run the setup script for your platform:

```bash
./setup.sh
```

```powershell
./setup.ps1
```

The script validates the environment, starts `glean-ex05-glean`, waits for `http://127.0.0.1:9095/healthz`, and dry-runs the `reddit-ml` feed so you can see output immediately.

## Getting a Telegram bot + chat IDs

Follow the existing walkthrough in [`docs/getting-started/quickstart.md`](../../docs/getting-started/quickstart.md). It covers:

- creating the bot with [@BotFather](https://t.me/BotFather)
- adding it to a DM or group
- calling `https://api.telegram.org/bot<TOKEN>/getUpdates`
- copying the correct `chat.id`

This example uses:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_OPS_CHAT_ID`

## Pick your LLM

The shipped `feeds.yaml` defaults to OpenAI because more users already have an OpenAI-compatible key:

```yaml
defaults:
  llm:
    provider: openai
    model: gpt-4o-mini
```

To switch to Anthropic, change the `defaults.llm` block like this:

```diff
 defaults:
   llm:
-    provider: openai
-    model: gpt-4o-mini
+    provider: anthropic
+    model: claude-haiku-4-5
```

Then set `ANTHROPIC_API_KEY` in `.env` instead of `OPENAI_API_KEY`.

The setup scripts check that your selected provider matches the API key you supplied, so a default OpenAI config with only `ANTHROPIC_API_KEY` set will fail fast with a clear message.

## What the feed does

| Setting | Value |
|---|---|
| Schedule | `every 2h` |
| Feed name | `reddit-ml` |
| Sources | `r/LocalLLaMA` top/day + `r/MachineLearning` top/day |
| Pipeline | `dedup → rank → summarize → digest` |
| Ranking filter | personalized startup-ML prompt, `min_relevance: 0.55` |
| Summary style | one sentence, <=25 words, factual only |
| LLM | `openai:gpt-4o-mini` by default |
| Sinks | Telegram + dashboard (`keep_last_n: 50`) |
| Bootstrap | `skip-and-mark` |
| Cost guard | `max_llm_calls_per_run: 80` |

## Editing the ranking prompt

The personalization story lives in the `rank.prompt` block in `feeds.yaml`:

```yaml
- rank:
    prompt: |
      Score 0-1 based on whether this would interest someone who builds
      ML systems for a startup. Prioritize concrete launches, benchmark
      deep-dives, and engineering writeups. Penalize memes, vent threads,
      and pure-theory speculation.
```

Rewrite that prompt for **your** taste:

- prefer research over launches
- reward infra / MLOps posts more heavily
- penalize benchmarks if you only care about product launches
- lower or raise `min_relevance` to make the feed broader or stricter

If you only change one thing in this example, make it the ranking prompt.

## Viewing digests in the browser

This example keeps recent digests in the built-in dashboard sink, so you can inspect them in the web UI even though delivery happens through Telegram.

1. Get the auto-generated API key:

   ```bash
   docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY | head -1
   ```

2. Open <http://127.0.0.1:9095/>.
3. Paste the API key when prompted.
4. Open the Digests view to inspect the last 50 rendered runs.

## Customizing subreddits

The built-in Reddit source constructor accepts `subreddit`, `sort`, `timeframe`, and optional `limit`, which matches this example's YAML.

To watch different communities, edit or duplicate the source blocks:

```yaml
sources:
  - type: reddit
    subreddit: LocalLLaMA
    sort: top
    timeframe: day
  - type: reddit
    subreddit: MachineLearning
    sort: top
    timeframe: day
```

Useful tweaks:

- swap `MachineLearning` for `MLOps`, `artificial`, `compsci`, or another curated subreddit
- change `sort: top` to `hot`, `new`, or `controversial`
- widen or narrow `timeframe` when using `top` / `controversial`
- add `limit: 10` or `limit: 50` if you want to change how many Reddit posts are fetched per source

After editing `feeds.yaml`, restart glean:

```bash
docker compose -f docker-compose.yml restart glean
```

## Teardown

```bash
./teardown.sh
```

```powershell
./teardown.ps1
```

This stops the container, removes volumes, deletes the local `data/` directory, and removes `.env` so you can start fresh.

## Going further

- [Skills and structured extraction](../../docs/concepts/skills.md)
- [Telegram sink how-to](../../docs/how-to/sinks/telegram.md)
- [Concepts index](../../docs/concepts/index.md)
