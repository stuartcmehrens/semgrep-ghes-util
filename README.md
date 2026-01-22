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
uv run semgrep-ghes-util --ghes-url https://github.example.com scm list-missing-configs

# List all GHES organizations
uv run semgrep-ghes-util --ghes-url https://github.example.com ghes list-orgs
```

### Creating SCM configs

The recommended workflow for onboarding multiple orgs:

**Step 1: Create a config for one org first**

```bash
uv run semgrep-ghes-util --ghes-url https://github.example.com scm create-config --ghes-org my-first-org
```

This will output the SCM ID needed for subsequent configs:

```
Created SCM config for my-first-org
  ID: 53632
  SCM ID: 138447

Use --scm-id 138447 with create-missing-configs to reuse this token.
```

**Step 2: Preview what would be created**

```bash
uv run semgrep-ghes-util --ghes-url https://github.example.com scm create-missing-configs --dry-run
```

**Step 3: Create configs for remaining orgs**

Use the `--scm-id` from step 1 to reuse the same token for all remaining orgs:

```bash
uv run semgrep-ghes-util --ghes-url https://github.example.com scm create-missing-configs --scm-id 138447
```

Alternatively, create configs without token reuse (uses `GHES_TOKEN` for each org):

```bash
uv run semgrep-ghes-util --ghes-url https://github.example.com scm create-missing-configs
```

### Updating SCM configs

Bulk update SCM configs matching a GHES URL. Only the properties you specify will be updated.

**Available properties:**

| Flag | Description |
|------|-------------|
| `--subscribe` | Subscribe to webhooks (true/false) |
| `--auto-scan` | Enable auto-scanning (true/false) |
| `--use-network-broker` | Use network broker (true/false) |
| `--diff-enabled` | Enable diff scanning (true/false) |

**Examples:**

```bash
# Preview what would be updated (dry-run)
uv run semgrep-ghes-util --ghes-url https://github.example.com scm update-configs --subscribe true --dry-run

# Update all configs for the GHES instance
uv run semgrep-ghes-util --ghes-url https://github.example.com scm update-configs --subscribe true

# Update specific orgs only
uv run semgrep-ghes-util --ghes-url https://github.example.com scm update-configs --orgs org1 org2 --auto-scan true

# Update multiple properties at once
uv run semgrep-ghes-util --ghes-url https://github.example.com scm update-configs --subscribe true --auto-scan false --diff-enabled true
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
