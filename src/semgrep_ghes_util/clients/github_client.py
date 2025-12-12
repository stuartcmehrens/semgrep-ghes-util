from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class GithubApiError(Exception):
    """Exception raised for GitHub API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: requests.Response | None = None,
    ):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


def create_retry_session(
    retries: int = 5,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = (500, 502, 503, 504),
) -> requests.Session:
    """Create a requests session with retry logic."""
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


@dataclass
class GithubOrganization:
    """GitHub organization."""

    id: int
    login: str
    description: str | None = None
    url: str | None = None


class GithubClient:
    """Client for GitHub Enterprise Server API."""

    def __init__(self, base_url: str, token: str):
        """Initialize the GitHub client.

        Args:
            base_url: Base URL of the GHES instance (e.g., https://github.example.com)
            token: Personal access token or GitHub App token
        """
        # Normalize base URL - remove trailing slash, ensure /api/v3
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/api/v3"):
            self.base_url = f"{self.base_url}/api/v3"

        self.session = create_retry_session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _handle_response(self, response: requests.Response) -> dict | list:
        """Handle API response and raise appropriate errors."""
        if response.status_code >= 400:
            try:
                error_body = response.json()
                message = error_body.get("message", response.text)
            except Exception:
                message = response.text or f"HTTP {response.status_code}"

            raise GithubApiError(
                f"GitHub API error: {message}",
                status_code=response.status_code,
                response=response,
            )
        return response.json()

    def list_organizations(self) -> list[GithubOrganization]:
        """List all organizations on the GHES instance.

        GET /organizations

        Note: This endpoint requires admin access on GHES to list all orgs.
        It paginates through all organizations using the 'since' parameter.
        """
        orgs: list[GithubOrganization] = []
        since: int | None = None

        while True:
            params = {"per_page": 100}
            if since:
                params["since"] = since

            response = self.session.get(
                f"{self.base_url}/organizations",
                params=params,
            )
            data = self._handle_response(response)

            if not data:
                break

            for org in data:
                orgs.append(
                    GithubOrganization(
                        id=org["id"],
                        login=org["login"],
                        description=org.get("description"),
                        url=org.get("url"),
                    )
                )

            # GitHub uses 'since' param with the last org ID for pagination
            since = data[-1]["id"]

            # If we got fewer than requested, we're done
            if len(data) < 100:
                break

        return orgs
