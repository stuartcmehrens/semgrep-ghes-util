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
| `GHES_URL` | No | GHES URL (can also use `--ghes-url` on commands) |

## Usage

### Listing SCM configs

```bash
# List all Semgrep SCM configs
uv run semgrep-ghes-util scm list-configs

# List only unhealthy SCM configs
uv run semgrep-ghes-util scm list-configs --unhealthy-only

# List SCM configs for a specific GHES instance
uv run semgrep-ghes-util scm list-configs --ghes-url https://github.example.com

# List GHES orgs not in Semgrep
uv run semgrep-ghes-util scm list-missing-configs --ghes-url https://github.example.com

# List all GHES organizations
uv run semgrep-ghes-util ghes list-orgs --ghes-url https://github.example.com
```

**list-configs flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--ghes-url` | all | Filter to configs for this GHES instance |
| `--unhealthy-only` | false | Only show unhealthy SCM configs |
| `--required-scopes` | - | Comma-separated scopes to require (see below) |

#### Health checks and token scopes

By default, health checks only verify **connection status** (can Semgrep reach the SCM?). Use `--required-scopes` to also require specific token permissions:

```bash
# Basic health check (connection only)
uv run semgrep-ghes-util scm list-configs --unhealthy-only

# Require read access for scanning
uv run semgrep-ghes-util scm list-configs --unhealthy-only \
  --required-scopes read_metadata,read_contents

# Require full managed scanning capabilities
uv run semgrep-ghes-util scm list-configs --unhealthy-only \
  --required-scopes read_metadata,read_contents,read_pull_request,write_pull_request_comment,manage_webhooks
```

**Available scopes:**

| Scope | Description |
|-------|-------------|
| `read_metadata` | Read repo metadata |
| `read_contents` | Read file contents |
| `read_pull_request` | Read PR information |
| `write_pull_request_comment` | Post PR comments (for findings) |
| `read_members` | Read org membership |
| `manage_webhooks` | Create/manage webhooks |
| `write_contents` | Write file contents (optional, for autofix) |

### Creating SCM configs

SCM configs connect Semgrep to your GitHub organizations. There are two common use cases:

1. **Connection only** (default) - Establishes a connection to the GitHub org without enabling scanning. Useful when you want to set up the connection first and enable scanning later via the Semgrep UI or `update-configs`.

2. **Managed scanning** - Creates the connection AND enables Semgrep to automatically scan repos. This requires webhooks (`--subscribe`) and typically full scans (`--auto-scan`). Optionally enable PR/MR diff scanning (`--diff-enabled`).

#### Connection-only configs (default)

Create configs that only establish the connection, without enabling webhooks or scanning:

```bash
# Create for a single org
uv run semgrep-ghes-util scm create-config --ghes-url https://github.example.com --ghes-org my-org

# Create for all missing orgs
uv run semgrep-ghes-util scm create-missing-configs --ghes-url https://github.example.com
```

#### Managed scanning configs

Create configs with webhooks and scanning enabled for full Semgrep managed scanning:

```bash
# Create for a single org with managed scanning
uv run semgrep-ghes-util scm create-config --ghes-url https://github.example.com --ghes-org my-org \
  --subscribe --auto-scan --diff-enabled

# Create for all missing orgs with managed scanning
uv run semgrep-ghes-util scm create-missing-configs --ghes-url https://github.example.com \
  --subscribe --auto-scan --diff-enabled
```

| Flag | What it does |
|------|--------------|
| `--subscribe` | Creates webhooks so Semgrep receives events from GitHub |
| `--auto-scan` | Enables automatic full scans on push to default branch |
| `--diff-enabled` | Enables diff scans on pull requests |

#### Recommended workflow for multiple orgs

When onboarding many orgs, create one config first to verify the token works, then use its SCM ID to reuse the token for remaining orgs:

**Step 1: Create and verify a single config**

```bash
uv run semgrep-ghes-util scm create-config --ghes-url https://github.example.com --ghes-org my-first-org \
  --subscribe --auto-scan --diff-enabled
```

This outputs the SCM ID and health status:

```
Created SCM config for my-first-org
  SCM ID: 138447

Checking SCM health...
  ✓ Connected
  Token scopes: read_metadata, read_pull_request, write_pull_request_comment, read_contents, read_members, manage_webhooks, write_contents

Use --scm-id 138447 with create-missing-configs to reuse this token.
```

**Step 2: Preview remaining orgs**

```bash
uv run semgrep-ghes-util scm create-missing-configs --ghes-url https://github.example.com --dry-run
```

**Step 3: Create configs for remaining orgs (reusing the token)**

```bash
uv run semgrep-ghes-util scm create-missing-configs --ghes-url https://github.example.com \
  --scm-id 138447 --subscribe --auto-scan --diff-enabled
```

#### Creating configs for specific orgs

```bash
# By name
uv run semgrep-ghes-util scm create-missing-configs --ghes-url https://github.example.com \
  --orgs org1 org2 org3

# From file (one org per line)
uv run semgrep-ghes-util scm create-missing-configs --ghes-url https://github.example.com \
  --orgs-file orgs.txt
```

#### All create config flags

| Flag | Default | Description |
|------|---------|-------------|
| `--subscribe` | disabled | Subscribe to webhooks |
| `--auto-scan` | disabled | Enable auto-scanning |
| `--diff-enabled` | disabled | Enable diff scanning |
| `--scm-id` | - | Reuse token from an existing SCM config (create-missing-configs only) |
| `--orgs` | all missing | Specific orgs to create (create-missing-configs only) |
| `--orgs-file` | - | File with org names, one per line (create-missing-configs only) |
| `--delay` | 1.0 | Seconds between creating each config (create-missing-configs only) |
| `--dry-run` | false | Preview without making changes |

### Updating SCM configs

Bulk update SCM configs matching a GHES URL. Only the properties you specify will be updated.

**Available flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--subscribe` | - | Subscribe to webhooks (true/false) |
| `--auto-scan` | - | Enable auto-scanning (true/false) |
| `--use-network-broker` | - | Use network broker (true/false) |
| `--diff-enabled` | - | Enable diff scanning (true/false) |
| `--orgs` | all | Specific org names to update |
| `--dry-run` | false | Preview without making changes |
| `--delay` | 1.0 | Seconds between updates |

**Examples:**

```bash
# Preview what would be updated (dry-run)
uv run semgrep-ghes-util scm update-configs --ghes-url https://github.example.com --subscribe true --dry-run

# Update all configs for the GHES instance
uv run semgrep-ghes-util scm update-configs --ghes-url https://github.example.com --subscribe true

# Update specific orgs only
uv run semgrep-ghes-util scm update-configs --ghes-url https://github.example.com --orgs org1 org2 --auto-scan true

# Update multiple properties at once
uv run semgrep-ghes-util scm update-configs --ghes-url https://github.example.com --subscribe true --auto-scan false --diff-enabled true
```

### Checking SCM config health

Check the health status of SCM configs, including connection status and token scopes.

```bash
# Check all configs for a GHES instance (connection only)
uv run semgrep-ghes-util scm check-configs --ghes-url https://github.example.com

# Check specific orgs only
uv run semgrep-ghes-util scm check-configs --ghes-url https://github.example.com --orgs org1 org2

# Check with specific scope requirements
uv run semgrep-ghes-util scm check-configs --ghes-url https://github.example.com \
  --required-scopes read_metadata,read_contents
```

**Available flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--orgs` | all | Specific org names to check |
| `--required-scopes` | - | Comma-separated scopes to require for health |
| `--delay` | 0.25 | Seconds between checks |

### Deleting SCM configs

Delete SCM configs for specific orgs. The `--orgs` flag is required to prevent accidental deletion.

```bash
# Preview what would be deleted (dry-run)
uv run semgrep-ghes-util scm delete-configs --ghes-url https://github.example.com --orgs org1 org2 --dry-run

# Delete specific orgs
uv run semgrep-ghes-util scm delete-configs --ghes-url https://github.example.com --orgs org1 org2
```

**Available flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--orgs` | required | Org names to delete |
| `--dry-run` | false | Preview without deleting |
| `--delay` | 0.5 | Seconds between deletions |

### Onboarding repos to managed scans

Bulk onboard uninitialized repos to Semgrep managed scans. This command:
- Fetches repos that haven't been scanned yet
- Filters out archived repos automatically
- Optionally filters to only repos with healthy SCM configs

**Examples:**

```bash
# Preview what would be onboarded (dry-run)
uv run semgrep-ghes-util scm onboard-repos --dry-run

# Onboard all uninitialized repos
uv run semgrep-ghes-util scm onboard-repos

# Onboard repos for a specific GHES instance only
uv run semgrep-ghes-util scm onboard-repos --ghes-url https://github.example.com

# Onboard without checking SCM health
uv run semgrep-ghes-util scm onboard-repos --check-scm false

# Customize batch size
uv run semgrep-ghes-util scm onboard-repos --batch-size 100
```

**Available flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--ghes-url` | all | Filter to repos from this GHES instance |
| `--dry-run` | false | Preview without making changes |
| `--full-scan` | true | Enable full scanning (true/false) |
| `--diff-scan` | true | Enable diff scanning (true/false, currently hardcoded to disabled) |
| `--batch-size` | 250 | Repos per batch |
| `--check-scm` | true | Only onboard repos with healthy SCM configs (true/false) |
| `--required-scopes` | - | Comma-separated scopes to require when --check-scm is true |
| `--delay` | 1.0 | Seconds between batches |

### Triggering scans

Trigger scans for repos that haven't had a full scan yet. This command:
- Fetches initialized repos (already onboarded)
- Filters out archived repos automatically
- Checks each repo for existing full scans (can be skipped)
- Triggers scans in batches with configurable delays

**Examples:**

```bash
# Preview what would be triggered (dry-run)
uv run semgrep-ghes-util scm trigger-scans --dry-run

# Trigger scans, checking for existing scans first
uv run semgrep-ghes-util scm trigger-scans

# Skip the existing scan check (faster for large repos)
uv run semgrep-ghes-util scm trigger-scans --skip-scan-check

# Trigger for a specific GHES instance
uv run semgrep-ghes-util scm trigger-scans --ghes-url https://github.example.com

# Customize batch size and delays (for reducing system load)
uv run semgrep-ghes-util scm trigger-scans --batch-size 10 --delay 5
```

**Available flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--ghes-url` | all | Filter to repos from this GHES instance |
| `--dry-run` | false | Preview without triggering |
| `--batch-size` | 10 | Scans to trigger per batch |
| `--check-scm` | true | Only scan repos with healthy SCM configs (true/false) |
| `--required-scopes` | - | Comma-separated scopes to require when --check-scm is true |
| `--delay` | 1.0 | Seconds between trigger batches |
| `--check-delay` | 0.1 | Seconds between checking each repo for existing scans |
| `--skip-scan-check` | false | Skip checking for existing scans, trigger for all repos |

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
