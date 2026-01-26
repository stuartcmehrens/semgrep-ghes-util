from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class SemgrepApiError(Exception):
    """Exception raised for Semgrep API errors."""

    def __init__(self, message: str, status_code: int | None = None, response: requests.Response | None = None):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


def create_retry_session(
    retries: int = 5,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = (500, 502, 503, 504),
) -> requests.Session:
    """Create a requests session with retry logic.

    Args:
        retries: Number of retries to attempt
        backoff_factor: Factor for exponential backoff (0.5 = 0.5s, 1s, 2s, 4s, 8s)
        status_forcelist: HTTP status codes to retry on
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST", "PATCH", "DELETE"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


class ScmType(Enum):
    """SCM provider types."""

    GITHUB = "SCM_TYPE_GITHUB"
    GITHUB_ENTERPRISE = "SCM_TYPE_GITHUB_ENTERPRISE"
    GITLAB = "SCM_TYPE_GITLAB"
    GITLAB_SELFMANAGED = "SCM_TYPE_GITLAB_SELFMANAGED"
    BITBUCKET = "SCM_TYPE_BITBUCKET"
    BITBUCKET_DATACENTER = "SCM_TYPE_BITBUCKET_DATACENTER"
    AZURE_DEVOPS = "SCM_TYPE_AZURE_DEVOPS"
    UNKNOWN = "SCM_TYPE_UNKNOWN"


class GithubEntityType(Enum):
    """GitHub entity types."""

    ORG = "GITHUB_ENTITY_TYPE_ORG"
    USER = "GITHUB_ENTITY_TYPE_USER"


@dataclass
class Deployment:
    """Semgrep deployment info."""

    id: int
    name: str
    slug: str
    display_name: str | None = None


@dataclass
class ScmStatus:
    """SCM config status."""

    checked: datetime | None = None
    ok: bool = False
    error: str | None = None


@dataclass
class ScmTokenScopes:
    """Token permission scopes."""

    read_metadata: bool = False
    read_pull_request: bool = False
    write_pull_request_comment: bool = False
    read_contents: bool = False
    read_members: bool = False
    manage_webhooks: bool = False
    write_contents: bool = False


@dataclass
class ScmCheckResult:
    """Result from checking an SCM config's health."""

    status: ScmStatus
    token_scopes: ScmTokenScopes | None = None


@dataclass
class ScmConfig:
    """SCM configuration."""

    id: str
    type: str
    namespace: str
    source_id: str | None = None
    base_url: str | None = None
    status: ScmStatus | None = None
    installed: bool = False
    suspended: bool = False
    github_entity_type: str | None = None
    auto_scan: bool = False
    use_network_broker: bool = False
    token_scopes: ScmTokenScopes | None = None
    last_successful_sync_at: datetime | None = None
    scm_id: str | None = None


class SemgrepClient:
    """Client for Semgrep API v2."""

    BASE_URL = "https://semgrep.dev/api"

    def __init__(self, token: str):
        self.token = token
        self.session = create_retry_session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        self._deployment: Deployment | None = None

    def _handle_response(self, response: requests.Response) -> dict:
        """Handle API response and raise appropriate errors."""
        if response.status_code >= 400:
            try:
                error_body = response.json()
                message = error_body.get("message", error_body.get("error", response.text))
            except Exception:
                message = response.text or f"HTTP {response.status_code}"

            raise SemgrepApiError(
                f"Semgrep API error: {message}",
                status_code=response.status_code,
                response=response,
            )
        return response.json()

    @property
    def deployment(self) -> Deployment:
        """Get deployment, fetching from API if not cached."""
        if self._deployment is None:
            self._deployment = self.get_deployment()
        return self._deployment

    def get_deployment(self) -> Deployment:
        """Get deployment info for the current token.

        GET /api/agent/deployment
        """
        response = self.session.get(f"{self.BASE_URL}/agent/deployment")
        data = self._handle_response(response)["deployment"]
        return Deployment(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            display_name=data.get("display_name"),
        )

    def _parse_scm_config(self, data: dict) -> ScmConfig:
        """Parse SCM config from API response."""
        status = None
        if "status" in data:
            status_data = data["status"]
            checked = None
            if status_data.get("checked"):
                checked = datetime.fromisoformat(
                    status_data["checked"].replace("Z", "+00:00")
                )
            status = ScmStatus(
                checked=checked,
                ok=status_data.get("ok", False),
                error=status_data.get("error"),
            )

        token_scopes = None
        if "tokenScopes" in data:
            scopes = data["tokenScopes"]
            token_scopes = ScmTokenScopes(
                read_metadata=scopes.get("readMetadata", False),
                read_pull_request=scopes.get("readPullRequest", False),
                write_pull_request_comment=scopes.get("writePullRequestComment", False),
            )

        last_sync = None
        if data.get("lastSuccessfulSyncAt"):
            last_sync = datetime.fromisoformat(
                data["lastSuccessfulSyncAt"].replace("Z", "+00:00")
            )

        return ScmConfig(
            id=data["id"],
            type=data["type"],
            namespace=data["namespace"],
            source_id=data.get("sourceId"),
            base_url=data.get("baseUrl"),
            status=status,
            installed=data.get("installed", False),
            suspended=data.get("suspended", False),
            github_entity_type=data.get("githubEntityType"),
            auto_scan=data.get("autoScan", False),
            use_network_broker=data.get("useNetworkBroker", False),
            token_scopes=token_scopes,
            last_successful_sync_at=last_sync,
            scm_id=data.get("scmId"),
        )

    def list_scm_configs(self) -> list[ScmConfig]:
        """List all SCM configs for the deployment.

        GET /api/scm/deployments/{deploymentId}/configs
        """
        configs: list[ScmConfig] = []
        cursor: str | None = None

        while True:
            params = {"cursor": cursor} if cursor else {}
            response = self.session.get(
                f"{self.BASE_URL}/scm/deployments/{self.deployment.id}/configs",
                params=params,
            )
            data = self._handle_response(response)

            for config in data.get("configs", []):
                configs.append(self._parse_scm_config(config))

            cursor = data.get("cursor")
            if not cursor:
                break

        return configs

    def create_scm_config(
        self,
        scm_type: ScmType,
        namespace: str,
        base_url: str,
        access_token: str | None = None,
        source_id: str | None = None,
        scm_config_id: int | None = None,
        subscribe: bool = True,
        auto_scan: bool = False,
        diff_enabled: bool = True,
    ) -> ScmConfig:
        """Create a new SCM config.

        POST /api/scm/deployments/{deploymentId}/configs

        Args:
            scm_type: Type of SCM (e.g., GITHUB_ENTERPRISE)
            namespace: Organization/group name
            base_url: Base URL of the SCM instance (e.g., https://github.example.com)
            access_token: Access token for the SCM (optional if reusing token via scm_config_id)
            source_id: Optional source identifier
            scm_config_id: Optional ID of existing config to reuse token from
            subscribe: Whether to auto-subscribe to webhooks
            auto_scan: Whether to enable auto-scanning
            diff_enabled: Whether to enable diff scanning (within auto_scan_settings)
        """
        body: dict = {
            "type": scm_type.value,
            "namespace": namespace,
            "baseUrl": base_url,
            "subscribe": subscribe,
            "autoScan": auto_scan,
            "autoScanSettings": {
                "diffEnabled": diff_enabled,
            },
        }

        if access_token:
            body["accessToken"] = access_token
        if source_id:
            body["sourceId"] = source_id
        if scm_config_id:
            body["scmConfigId"] = scm_config_id

        response = self.session.post(
            f"{self.BASE_URL}/scm/deployments/{self.deployment.id}/configs",
            json=body,
        )
        data = self._handle_response(response)
        return self._parse_scm_config(data["config"])

    def patch_scm_config(
        self,
        config_id: str,
        subscribe: bool | None = None,
        auto_scan: bool | None = None,
        use_network_broker: bool | None = None,
        diff_enabled: bool | None = None,
    ) -> ScmConfig:
        """Update an existing SCM config.

        PATCH /api/scm/deployments/{deploymentId}/configs/{configId}

        Args:
            config_id: The config ID to update
            subscribe: Whether to auto-subscribe to webhooks
            auto_scan: Whether to enable auto-scanning
            use_network_broker: Whether to use network broker
            diff_enabled: Whether to enable diff scanning (within auto_scan_settings)

        Only fields that are not None will be included in the update.
        """
        body: dict = {}

        if subscribe is not None:
            body["subscribe"] = subscribe
        if auto_scan is not None:
            body["autoScan"] = auto_scan
        if use_network_broker is not None:
            body["useNetworkBroker"] = use_network_broker
        if diff_enabled is not None:
            body["autoScanSettings"] = {"diffEnabled": diff_enabled}

        response = self.session.patch(
            f"{self.BASE_URL}/scm/deployments/{self.deployment.id}/configs/{config_id}",
            json=body,
        )
        data = self._handle_response(response)
        return self._parse_scm_config(data["config"])

    def check_scm_config(self, config_id: str) -> ScmCheckResult:
        """Check the health of an SCM config.

        GET /api/scm/deployments/{deploymentId}/configs/{configId}/check

        Args:
            config_id: The config ID to check

        Returns:
            ScmCheckResult with status and token scopes
        """
        response = self.session.get(
            f"{self.BASE_URL}/scm/deployments/{self.deployment.id}/configs/{config_id}/check",
        )
        data = self._handle_response(response)

        status_data = data.get("status", {})
        checked = None
        if status_data.get("checked"):
            checked = datetime.fromisoformat(
                status_data["checked"].replace("Z", "+00:00")
            )
        status = ScmStatus(
            checked=checked,
            ok=status_data.get("ok", False),
            error=status_data.get("error"),
        )

        token_scopes = None
        if "tokenScopes" in data:
            scopes = data["tokenScopes"]
            token_scopes = ScmTokenScopes(
                read_metadata=scopes.get("readMetadata", False),
                read_pull_request=scopes.get("readPullRequest", False),
                write_pull_request_comment=scopes.get("writePullRequestComment", False),
                read_contents=scopes.get("readContents", False),
                read_members=scopes.get("readMembers", False),
                manage_webhooks=scopes.get("manageWebhooks", False),
                write_contents=scopes.get("writeContents", False),
            )

        return ScmCheckResult(status=status, token_scopes=token_scopes)
