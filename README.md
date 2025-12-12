# semgrep-ghes-util

CLI tool for syncing GitHub Enterprise Server (GHES) organizations to Semgrep SCM configs. Discovers GitHub orgs not yet onboarded to Semgrep and can create the necessary SCM configurations.

## Installation

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync
```

## Configuration

Set the following environment variables (or use a `.env` file):

| Variable | Required | Description |
|----------|----------|-------------|
| `SEMGREP_APP_TOKEN` | Yes | Semgrep API token |
| `GHES_TOKEN` | Yes | GitHub Enterprise Server token |
| `GHES_URL` | No | GHES URL (can also use `--ghes-url`) |

## Usage

```bash
# List all Semgrep SCM configs
uv run semgrep-ghes-util scm list-configs

# List GHES orgs not in Semgrep
uv run semgrep-ghes-util scm list-missing-configs --ghes-url https://github.example.com

# Create configs for missing orgs
uv run semgrep-ghes-util scm create-missing-configs --ghes-url https://github.example.com

# List all GHES organizations
uv run semgrep-ghes-util ghes list-orgs --ghes-url https://github.example.com
```

## Docker

```bash
# Build
docker build -t semgrep-ghes-util .

# Run with .env file
docker run --rm --env-file .env semgrep-ghes-util scm list-configs

# Run with individual env vars
docker run --rm \
  -e SEMGREP_APP_TOKEN \
  -e GHES_TOKEN \
  -e GHES_URL \
  semgrep-ghes-util scm list-configs
```
