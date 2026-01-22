import argparse
import os
import sys
import time

from dotenv import load_dotenv

from semgrep_ghes_util.clients.github_client import GithubClient
from semgrep_ghes_util.clients.semgrep_client import ScmType, SemgrepClient


def parse_bool(value: str) -> bool:
    """Parse a boolean string value."""
    if value.lower() in ("true", "1", "yes"):
        return True
    elif value.lower() in ("false", "0", "no"):
        return False
    else:
        raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}. Use 'true' or 'false'.")


def get_env_or_exit(var_name: str) -> str:
    """Get an environment variable or exit with an error."""
    value = os.environ.get(var_name)
    if not value:
        print(f"Error: {var_name} environment variable is required", file=sys.stderr)
        sys.exit(1)
    return value


# SCM commands
def cmd_scm_list_configs(args: argparse.Namespace) -> None:
    """List all Semgrep SCM configs."""
    semgrep_token = get_env_or_exit("SEMGREP_APP_TOKEN")
    client = SemgrepClient(semgrep_token)

    print(f"Deployment: {client.deployment.name} ({client.deployment.slug})\n")

    configs = client.list_scm_configs()
    if not configs:
        print("No SCM configs found.")
        return

    print(f"Found {len(configs)} SCM config(s):\n")
    for config in configs:
        status = "✓" if config.status and config.status.ok else "✗"
        print(f"  [{status}] {config.namespace}")
        print(f"      Type: {config.type}")
        if config.base_url:
            print(f"      URL: {config.base_url}")
        print(f"      ID: {config.id}")
        print()


def get_missing_orgs(
    ghes_url: str,
    ghes_token: str,
    semgrep_token: str,
) -> tuple[list, list]:
    """Get GHES orgs that don't have Semgrep SCM configs.

    Returns:
        Tuple of (missing_orgs, existing_configs_for_ghes)
    """
    # Normalize GHES URL for comparison
    normalized_ghes_url = ghes_url.rstrip("/").lower()

    github_client = GithubClient(ghes_url, ghes_token)
    semgrep_client = SemgrepClient(semgrep_token)

    # Get all GHES orgs
    ghes_orgs = github_client.list_organizations()
    ghes_org_names = {org.login.lower() for org in ghes_orgs}

    # Get all Semgrep SCM configs and filter to ones matching this GHES instance
    all_configs = semgrep_client.list_scm_configs()
    ghes_configs = [
        config for config in all_configs
        if config.base_url and config.base_url.rstrip("/").lower() == normalized_ghes_url
    ]

    # Find orgs that already have configs
    configured_orgs = {config.namespace.lower() for config in ghes_configs}

    # Find missing orgs
    missing_org_names = ghes_org_names - configured_orgs
    missing_orgs = [org for org in ghes_orgs if org.login.lower() in missing_org_names]

    return missing_orgs, ghes_configs


def cmd_scm_list_missing_configs(args: argparse.Namespace) -> None:
    """List GHES orgs not onboarded to Semgrep."""
    semgrep_token = get_env_or_exit("SEMGREP_APP_TOKEN")
    ghes_token = get_env_or_exit("GHES_TOKEN")

    print(f"GHES: {args.ghes_url}\n")

    missing_orgs, existing_configs = get_missing_orgs(
        args.ghes_url, ghes_token, semgrep_token
    )

    print(f"Existing SCM configs for this GHES: {len(existing_configs)}")
    for config in existing_configs:
        status = "✓" if config.status and config.status.ok else "✗"
        print(f"  [{status}] {config.namespace}")

    print()

    if not missing_orgs:
        print("All GHES organizations are onboarded to Semgrep.")
        return

    print(f"Missing SCM configs ({len(missing_orgs)} org(s)):\n")
    for org in missing_orgs:
        print(f"  {org.login}")


def cmd_scm_create_config(args: argparse.Namespace) -> None:
    """Create a single Semgrep SCM config for one GHES org."""
    semgrep_token = get_env_or_exit("SEMGREP_APP_TOKEN")
    ghes_token = get_env_or_exit("GHES_TOKEN")

    print(f"GHES: {args.ghes_url}")
    print(f"Org: {args.ghes_org}\n")

    if args.dry_run:
        print("Dry-run mode - the following SCM config would be created:\n")
        print(f"  {args.ghes_org}")
        print(f"      Type: {ScmType.GITHUB_ENTERPRISE.value}")
        print(f"      URL: {args.ghes_url}")
        return

    semgrep_client = SemgrepClient(semgrep_token)

    try:
        config = semgrep_client.create_scm_config(
            scm_type=ScmType.GITHUB_ENTERPRISE,
            namespace=args.ghes_org,
            base_url=args.ghes_url,
            access_token=ghes_token,
        )
        print(f"Created SCM config for {args.ghes_org}")
        print(f"  ID: {config.id}")
        print(f"  SCM ID: {config.scm_id}")
        print()
        print(f"Use --scm-id {config.scm_id} with create-missing-configs to reuse this token.")

    except Exception as e:
        print(f"Failed to create config: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_scm_create_missing_configs(args: argparse.Namespace) -> None:
    """Create Semgrep SCM configs for GHES orgs not yet onboarded."""
    semgrep_token = get_env_or_exit("SEMGREP_APP_TOKEN")
    ghes_token = get_env_or_exit("GHES_TOKEN")

    print(f"GHES: {args.ghes_url}\n")

    # Fetch GHES orgs and Semgrep configs
    github_client = GithubClient(args.ghes_url, ghes_token)
    semgrep_client = SemgrepClient(semgrep_token)

    ghes_orgs = github_client.list_organizations()
    ghes_org_map = {org.login.lower(): org for org in ghes_orgs}

    all_configs = semgrep_client.list_scm_configs()
    normalized_ghes_url = args.ghes_url.rstrip("/").lower()
    existing_configs = [
        config for config in all_configs
        if config.base_url and config.base_url.rstrip("/").lower() == normalized_ghes_url
    ]
    configured_orgs = {config.namespace.lower() for config in existing_configs}

    # Determine which orgs to create configs for
    specified_org_names: list[str] | None = None
    if args.orgs:
        specified_org_names = args.orgs
    elif args.orgs_file:
        specified_org_names = [
            line.strip() for line in args.orgs_file
            if line.strip() and not line.strip().startswith("#")
        ]
        args.orgs_file.close()

    if specified_org_names:
        # User specified orgs - validate they exist on GHES
        orgs_to_create = []
        for org_name in specified_org_names:
            org = ghes_org_map.get(org_name.lower())
            if org:
                orgs_to_create.append(org)
            else:
                print(f"  ⚠ Org not found on GHES: {org_name}")

        if not orgs_to_create:
            print("\nNo valid orgs to create configs for.")
            return

        print(f"\nCreating configs for {len(orgs_to_create)} specified org(s)...\n")
    else:
        # Discover missing orgs
        orgs_to_create = [
            org for org in ghes_orgs
            if org.login.lower() not in configured_orgs
        ]

        if not orgs_to_create:
            print("All GHES organizations are already onboarded to Semgrep.")
            return

        print(f"Creating {len(orgs_to_create)} missing SCM config(s)...\n")

    # Dry-run mode: print what would be created and exit
    if args.dry_run:
        print("Dry-run mode - the following SCM configs would be created:\n")
        for org in orgs_to_create:
            print(f"  {org.login}")
            print(f"      Type: {ScmType.GITHUB_ENTERPRISE.value}")
            print(f"      URL: {args.ghes_url}")
            print()
        print(f"Total: {len(orgs_to_create)} config(s) would be created.")
        return

    if args.scm_id:
        print(f"Using token from SCM ID: {args.scm_id}\n")
    else:
        print("Using GHES_TOKEN for each org\n")

    created = 0
    failed = 0

    for i, org in enumerate(orgs_to_create):
        try:
            if args.scm_id:
                # Reuse token from specified config
                semgrep_client.create_scm_config(
                    scm_type=ScmType.GITHUB_ENTERPRISE,
                    namespace=org.login,
                    base_url=args.ghes_url,
                    scm_config_id=args.scm_id,
                )
            else:
                # Use the GHES token directly
                semgrep_client.create_scm_config(
                    scm_type=ScmType.GITHUB_ENTERPRISE,
                    namespace=org.login,
                    base_url=args.ghes_url,
                    access_token=ghes_token,
                )

            print(f"  ✓ Created: {org.login}")
            created += 1

        except Exception as e:
            print(f"  ✗ Failed: {org.login} - {e}")
            failed += 1

        # Delay between requests (skip after last one)
        if args.delay > 0 and i < len(orgs_to_create) - 1:
            time.sleep(args.delay)

    print()
    print(f"Done. Created: {created}, Failed: {failed}")


def cmd_scm_update_configs(args: argparse.Namespace) -> None:
    """Update Semgrep SCM configs matching the GHES URL."""
    semgrep_token = get_env_or_exit("SEMGREP_APP_TOKEN")

    print(f"GHES: {args.ghes_url}\n")

    semgrep_client = SemgrepClient(semgrep_token)

    # Get all configs and filter by GHES URL
    all_configs = semgrep_client.list_scm_configs()
    normalized_ghes_url = args.ghes_url.rstrip("/").lower()
    matching_configs = [
        config for config in all_configs
        if config.base_url and config.base_url.rstrip("/").lower() == normalized_ghes_url
    ]

    # Optionally filter by org names
    if args.orgs:
        org_names_lower = {org.lower() for org in args.orgs}
        matching_configs = [
            config for config in matching_configs
            if config.namespace.lower() in org_names_lower
        ]

    if not matching_configs:
        print("No matching SCM configs found.")
        return

    # Build update payload from provided flags
    updates: dict[str, bool | None] = {
        "subscribe": args.subscribe,
        "auto_scan": args.auto_scan,
        "use_network_broker": args.use_network_broker,
        "diff_enabled": args.diff_enabled,
    }

    # Filter to only non-None values
    updates_to_apply = {k: v for k, v in updates.items() if v is not None}

    if not updates_to_apply:
        print("No updates specified. Use flags like --subscribe true to specify updates.")
        return

    print(f"Found {len(matching_configs)} matching config(s).")
    print(f"Updates to apply: {updates_to_apply}\n")

    if args.dry_run:
        print("Dry-run mode - the following configs would be updated:\n")
        for config in matching_configs:
            print(f"  {config.namespace} (ID: {config.id})")
        print(f"\nTotal: {len(matching_configs)} config(s) would be updated.")
        return

    updated = 0
    failed = 0

    for i, config in enumerate(matching_configs):
        try:
            semgrep_client.patch_scm_config(
                config_id=config.id,
                subscribe=args.subscribe,
                auto_scan=args.auto_scan,
                use_network_broker=args.use_network_broker,
                diff_enabled=args.diff_enabled,
            )
            print(f"  ✓ Updated: {config.namespace}")
            updated += 1

        except Exception as e:
            print(f"  ✗ Failed: {config.namespace} - {e}")
            failed += 1

        # Delay between requests (skip after last one)
        if args.delay > 0 and i < len(matching_configs) - 1:
            time.sleep(args.delay)

    print()
    print(f"Done. Updated: {updated}, Failed: {failed}")


# GHES commands
def cmd_ghes_list_orgs(args: argparse.Namespace) -> None:
    """List all organizations on GHES."""
    ghes_token = get_env_or_exit("GHES_TOKEN")
    client = GithubClient(args.ghes_url, ghes_token)

    print(f"GHES: {args.ghes_url}\n")

    orgs = client.list_organizations()
    if not orgs:
        print("No organizations found.")
        return

    print(f"Found {len(orgs)} organization(s):\n")
    for org in orgs:
        print(f"  {org.login}")
        if org.description:
            print(f"      {org.description}")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="semgrep-ghes-util",
        description="Tools for managing Semgrep SCM configs with GitHub Enterprise Server",
    )

    parser.add_argument(
        "--ghes-url",
        default=os.environ.get("GHES_URL"),
        help="GitHub Enterprise Server URL (e.g., https://github.example.com). Can also be set via GHES_URL env var.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # SCM command group
    scm_parser = subparsers.add_parser("scm", help="Semgrep SCM config operations")
    scm_subparsers = scm_parser.add_subparsers(dest="scm_command", required=True)

    scm_list_configs = scm_subparsers.add_parser(
        "list-configs",
        help="List all Semgrep SCM configs",
    )
    scm_list_configs.set_defaults(func=cmd_scm_list_configs)

    scm_list_missing = scm_subparsers.add_parser(
        "list-missing-configs",
        help="List GHES orgs not onboarded to Semgrep",
    )
    scm_list_missing.set_defaults(func=cmd_scm_list_missing_configs)

    scm_create_config = scm_subparsers.add_parser(
        "create-config",
        help="Create a single SCM config for one GHES org",
    )
    scm_create_config.add_argument(
        "--ghes-org",
        required=True,
        metavar="ORG",
        help="Organization name to create config for.",
    )
    scm_create_config.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without making any changes.",
    )
    scm_create_config.set_defaults(func=cmd_scm_create_config)

    scm_create_missing = scm_subparsers.add_parser(
        "create-missing-configs",
        help="Create SCM configs for GHES orgs not yet onboarded",
    )
    orgs_group = scm_create_missing.add_mutually_exclusive_group()
    orgs_group.add_argument(
        "--orgs",
        nargs="+",
        metavar="ORG",
        help="Specific org names to create configs for.",
    )
    orgs_group.add_argument(
        "--orgs-file",
        type=argparse.FileType("r"),
        metavar="FILE",
        help="File containing org names (one per line).",
    )
    scm_create_missing.add_argument(
        "--scm-id",
        type=int,
        metavar="ID",
        help="SCM ID of an existing config to reuse token from. Get this from 'scm create-config'.",
    )
    scm_create_missing.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without making any changes.",
    )
    scm_create_missing.add_argument(
        "--delay",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Delay between creating each config (default: 1.0 seconds).",
    )
    scm_create_missing.set_defaults(func=cmd_scm_create_missing_configs)

    scm_update_configs = scm_subparsers.add_parser(
        "update-configs",
        help="Update SCM configs matching the GHES URL",
    )
    scm_update_configs.add_argument(
        "--orgs",
        nargs="+",
        metavar="ORG",
        help="Specific org names to update (if not provided, updates all matching GHES URL).",
    )
    scm_update_configs.add_argument(
        "--subscribe",
        type=parse_bool,
        metavar="BOOL",
        help="Set subscribe to webhooks (true/false).",
    )
    scm_update_configs.add_argument(
        "--auto-scan",
        type=parse_bool,
        metavar="BOOL",
        help="Set auto-scan enabled (true/false).",
    )
    scm_update_configs.add_argument(
        "--use-network-broker",
        type=parse_bool,
        metavar="BOOL",
        help="Set use network broker (true/false).",
    )
    scm_update_configs.add_argument(
        "--diff-enabled",
        type=parse_bool,
        metavar="BOOL",
        help="Set diff scanning enabled (true/false).",
    )
    scm_update_configs.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be updated without making any changes.",
    )
    scm_update_configs.add_argument(
        "--delay",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Delay between updating each config (default: 1.0 seconds).",
    )
    scm_update_configs.set_defaults(func=cmd_scm_update_configs)

    # GHES command group
    ghes_parser = subparsers.add_parser("ghes", help="GitHub Enterprise Server operations")
    ghes_subparsers = ghes_parser.add_subparsers(dest="ghes_command", required=True)

    ghes_list_orgs = ghes_subparsers.add_parser(
        "list-orgs",
        help="List all organizations on GHES",
    )
    ghes_list_orgs.set_defaults(func=cmd_ghes_list_orgs)

    args = parser.parse_args()

    # Check GHES URL for commands that need it
    needs_ghes_url = args.command == "ghes" or (
        args.command == "scm" and args.scm_command in ["list-missing-configs", "create-config", "create-missing-configs", "update-configs"]
    )
    if needs_ghes_url and not args.ghes_url:
        parser.error("--ghes-url is required (or set GHES_URL environment variable)")

    args.func(args)
