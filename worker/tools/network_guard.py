"""One-shot network write allowance for a Playwright browser context."""

from __future__ import annotations

from urllib.parse import parse_qsl, urljoin, urlsplit

from playwright.async_api import BrowserContext, Route

from worker.contracts import NetworkAllowance


class NetworkGuard:
    def __init__(self, run_id: str, origins: set[str]):
        self.run_id = run_id
        self.origins = origins
        self.allowance: NetworkAllowance | None = None
        self.blocked: list[dict[str, str]] = []

    def arm(self, allowance: NetworkAllowance) -> None:
        if allowance.run_id != self.run_id:
            raise ValueError("Allowance belongs to another run")
        if self.allowance is not None:
            raise ValueError("An allowance is already armed")
        self.allowance = allowance

    def disarm(self) -> None:
        self.allowance = None

    def permit(self, method: str, url: str, content_type: str, body: str) -> bool:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.origins or parsed.path.startswith("/api/"):
            return False
        if method.upper() == "GET":
            return True
        allowed = self.allowance
        if not allowed or allowed.run_id != self.run_id or method.upper() != allowed.method:
            return False
        if url != allowed.url or not content_type.lower().startswith("application/x-www-form-urlencoded"):
            return False
        try:
            pairs = parse_qsl(body, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            return False
        if len(pairs) != len({key for key, _ in pairs}):
            return False
        if dict(pairs) != allowed.body:
            return False
        self.allowance = None
        return True

    async def attach(self, context: BrowserContext) -> None:
        async def intercept(route: Route) -> None:
            request = route.request
            headers = request.headers
            if not self.permit(request.method, request.url, headers.get("content-type", ""),
                               request.post_data or ""):
                self.blocked.append({"method": request.method, "url": request.url})
                await route.abort()
                return
            response = await route.fetch(max_redirects=0)
            location = response.headers.get("location")
            if location and not self.navigation_allowed(urljoin(request.url, location)):
                self.blocked.append({"method": "REDIRECT", "url": urljoin(request.url, location)})
                await route.abort()
                return
            await route.fulfill(response=response)

        await context.route("**/*", intercept)

    def navigation_allowed(self, url: str) -> bool:
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}" in self.origins
