---
title: "Installation — glean Getting Started"
description: Install glean with Docker, pip, pipx, or a source checkout.
---

# Installation

## Docker (recommended)

Run the published image directly after creating `.env`, `feeds.yaml`, and a `data` directory:

```bash
mkdir -p data
docker run -d \
  --name glean \
  --restart unless-stopped \
  --env-file .env \
  -p 127.0.0.1:9090:9090 \
  -v "$(pwd)/data:/data" \
  -v "$(pwd)/feeds.yaml:/etc/glean/feeds.yaml:ro" \
  ghcr.io/jaypetez/glean:1.3.0
```

For local Ollama, use Compose so glean and Ollama share a Docker network:

```yaml
services:
  glean:
    image: ghcr.io/jaypetez/glean:1.3.0
    depends_on: [ollama]
    env_file: [.env]
    volumes:
      - ./data:/data
      - ./feeds.yaml:/etc/glean/feeds.yaml:ro
    ports:
      - "127.0.0.1:9090:9090"
    networks: [glean]

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    networks: [glean]

volumes:
  ollama-models:

networks:
  glean:
    driver: bridge
```

Start it:

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:7b
docker compose up -d glean
```

The web UI and health endpoint listen on `http://127.0.0.1:9090`.

## Standalone binary

Standalone binaries are attached to each [GitHub release](https://github.com/jaypetez/glean/releases). Download the asset for your platform, make it executable on Unix-like systems, and run `glean version`:

```bash
chmod +x glean-linux-x86_64
./glean-linux-x86_64 version
```

Release assets are published for Linux, macOS, and Windows. Use the Docker image when you also want the managed container runtime and persistent `/data` volume layout.

## `.deb` / `.rpm` / `.apk`

Linux packages are published on the [releases page](https://github.com/jaypetez/glean/releases) for distro package managers.

Debian or Ubuntu:

```bash
sudo apt install ./glean_1.3.0_linux_amd64.deb
```

Fedora, RHEL, or compatible systems:

```bash
sudo rpm -i ./glean-1.3.0-1.x86_64.rpm
```

Alpine:

```bash
sudo apk add --allow-untrusted ./glean_1.3.0_linux_amd64.apk
```

Choose the package that matches your CPU architecture.

## From source

Source installs are for contributors who want to run tests, build the UI, or work on plugins.

```bash
git clone https://github.com/jaypetez/glean.git
cd glean
uv sync --locked --all-extras
uv run glean version
```
