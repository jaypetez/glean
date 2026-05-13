# Installation

## Docker (recommended)

```bash
git clone https://github.com/jaypetez/glean.git
cd glean
cp .env.example .env       # fill in TELEGRAM_BOT_TOKEN + chat IDs
cp feeds.example.yaml feeds.yaml
docker compose up -d
```

## pip / pipx

```bash
pipx install glean
# or
pip install glean
```

## From source

```bash
git clone https://github.com/jaypetez/glean.git
cd glean
uv venv && uv pip install -e ".[dev]"
```
