"""Real Chromium session with pre-authentication and expiring element refs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from worker.contracts import DocBlock, DocField, Element, Observation, Principal
from worker.tools.network_guard import NetworkGuard


class StaleRef(ValueError):
    """An element belongs to an older observation or page state."""


SNAPSHOT_JS = """() => {
  const nameOf = el => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.labels && el.labels.length) return [...el.labels].map(x => x.innerText.trim()).join(' ');
    return (el.innerText || el.getAttribute('title') || el.name || '').trim();
  };
  const items = [...document.querySelectorAll('a,button,input,select,textarea')].map((el, i) => ({
    role: el.tagName === 'A' ? 'link' : el.tagName === 'BUTTON' ? 'button' :
      el.tagName === 'SELECT' ? 'combobox' : el.tagName === 'TEXTAREA' ? 'textarea' :
      el.type === 'date' ? 'date' : 'textbox',
    name: nameOf(el), value: ['password', 'hidden'].includes(el.type) ? null : (el.value ?? null),
    form_id: el.form?.id || null, submits_form: el.type === 'submit' ||
      (el.tagName === 'BUTTON' && (!el.type || el.type === 'submit')),
    options: el.tagName === 'SELECT' ? [...el.options].map(x => x.text) : [],
    href: el.tagName === 'A' ? el.href : null,
    secret: ['password', 'hidden'].includes(el.type) || el.dataset.secret === 'true', i
  }));
  const documents = [...document.querySelectorAll('article[data-doc-id][data-revision][data-kind]')]
    .map(article => ({doc_id: article.dataset.docId, revision: article.dataset.revision,
      kind: article.dataset.kind,
      fields: [...article.querySelectorAll('dl dt')].map(dt => ({label: dt.innerText.trim(),
        value: dt.nextElementSibling?.innerText.trim() || ''}))}));
  return {title: document.title, text: (document.body?.innerText || '').slice(0, 4000),
    elements: items, documents};
}"""


FORM_JS = """el => {
  const form = el.form || el.closest('form');
  if (!form) return null;
  const fields = {}, secret_fields = [];
  for (const item of form.elements) {
    if (!item.name || item.disabled) continue;
    if (item.type === 'password' || item.dataset.secret === 'true') {
      secret_fields.push(item.name); continue;
    }
    if ((item.type === 'checkbox' || item.type === 'radio') && !item.checked) continue;
    fields[item.name] = item.value;
  }
  return {fields, secret_fields, action_url: form.action, method: form.method.toUpperCase()};
}"""


class BrowserSession:
    def __init__(
        self, run_id: str, browser: Browser, context: BrowserContext, page: Page,
        guard: NetworkGuard, playwright_driver, *, portal_url: str = "", register_url: str = "",
    ):
        self.run_id = run_id
        self.browser = browser
        self.context = context
        self.page = page
        self.guard = guard
        self.driver = playwright_driver
        self.portal_url = portal_url
        self.register_url = register_url
        self.step = 0
        self.current: Observation | None = None
        self._locators: dict[str, int] = {}
        self.offsite_navigation: str | None = None
        self.last_navigation_status: int | None = None
        page.on("framenavigated", self._on_navigation)
        page.on("response", self._on_response)

    def _on_response(self, response) -> None:
        if response.request.is_navigation_request():
            self.last_navigation_status = response.status

    @classmethod
    async def local_test(cls, run_id: str, origins: set[str] | None = None) -> BrowserSession:
        driver = await async_playwright().start()
        browser = await driver.chromium.launch(headless=True)
        context = await browser.new_context(service_workers="block")
        guard = NetworkGuard(run_id, origins or set())
        if origins:
            await guard.attach(context)
        page = await context.new_page()
        return cls(run_id, browser, context, page, guard, driver)

    @classmethod
    async def start(
        cls, run_id: str, principal: Principal, *, portal_url: str = "http://127.0.0.1:8101",
        register_url: str = "http://127.0.0.1:8102", portal_password: str | None = None,
        register_password: str | None = None,
    ) -> BrowserSession:
        driver = await async_playwright().start()
        browser = await driver.chromium.launch(headless=True)
        context = await browser.new_context(service_workers="block")
        guard = NetworkGuard(run_id, {portal_url, register_url})
        await guard.attach(context)
        page = await context.new_page()
        session = cls(run_id, browser, context, page, guard, driver,
                      portal_url=portal_url, register_url=register_url)
        await session.reauthenticate("portal", portal_password=portal_password)
        await session.reauthenticate("register", principal=principal,
                                     register_password=register_password)
        return session

    async def reauthenticate(
        self, app: str, *, principal: Principal | None = None,
        portal_password: str | None = None, register_password: str | None = None,
    ) -> None:
        if app == "portal":
            base_url = self.portal_url
            data = {"password": portal_password or os.getenv("PORTAL_PASSWORD", "portal-demo")}
            cookie_name = "portal_session"
        elif app == "register" and principal:
            base_url = self.register_url
            env_name = f"{principal.user_id.upper()}_PASSWORD"
            data = {"email": principal.email,
                    "password": register_password or os.getenv(env_name, f"{principal.user_id}-demo")}
            cookie_name = "reg_session"
        else:
            raise ValueError("Unknown app or missing principal")
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.post(f"{base_url}/login", data=data)
        if response.status_code != 303 or cookie_name not in response.cookies:
            raise RuntimeError(f"{app} setup authentication failed")
        parsed = urlsplit(base_url)
        await self.context.add_cookies([{
            "name": cookie_name, "value": response.cookies[cookie_name],
            "domain": parsed.hostname, "path": "/", "httpOnly": True,
            "sameSite": "Lax",
        }])

    def _on_navigation(self, frame) -> None:
        if frame != self.page.main_frame:
            return
        if frame.url in {"about:blank", ""} or urlsplit(frame.url).scheme not in {"http", "https"}:
            return
        if not self.guard.navigation_allowed(frame.url):
            self.offsite_navigation = frame.url
            self.guard.blocked.append({"method": "NAVIGATION", "url": frame.url})
            asyncio.create_task(self.page.close())

    async def navigate(self, url: str) -> None:
        if not self.guard.navigation_allowed(url):
            raise ValueError("Origin blocked")
        await self.page.goto(url)
        self.current = None

    async def snapshot(self, *, screenshot_path: Path | None = None) -> Observation:
        raw = await self.page.evaluate(SNAPSHOT_JS)
        content = await self.page.content()
        self.step += 1
        observation_id = uuid4().hex
        self._locators = {}
        elements = []
        for item in raw["elements"]:
            ref = f"e{item['i'] + 1}"
            self._locators[ref] = item["i"]
            elements.append(Element(
                ref=ref, role=item["role"], name=item["name"],
                value=None if item["secret"] else item["value"],
                form_id=item["form_id"], submits_form=item["submits_form"],
                options=item["options"], href=item["href"],
            ))
        documents = [DocBlock(
            doc_id=item["doc_id"], revision=item["revision"], kind=item["kind"],
            fields=[DocField(**field) for field in item["fields"]],
        ) for item in raw["documents"]]
        if screenshot_path:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await self.page.screenshot(path=str(screenshot_path))
        observation = Observation(
            observation_id=observation_id, run_id=self.run_id, step=self.step,
            url=self.page.url, title=raw["title"], text=raw["text"],
            elements=elements, documents=documents,
            content_hash=self._hash_content(content, raw),
            screenshot_path=str(screenshot_path) if screenshot_path else None,
        )
        self.current = observation
        return observation

    @staticmethod
    def _hash_content(content: str, raw: dict) -> str:
        values = [(item["i"], None if item["secret"] else item["value"])
                  for item in raw["elements"]]
        material = json.dumps([content, values], ensure_ascii=False)
        return hashlib.sha256(material.encode()).hexdigest()

    async def _resolve(self, ref: str):
        if not self.current or ref not in self._locators:
            raise StaleRef(ref)
        content = await self.page.content()
        raw = await self.page.evaluate(SNAPSHOT_JS)
        if self._hash_content(content, raw) != self.current.content_hash:
            raise StaleRef(ref)
        return self.page.locator("a,button,input,select,textarea").nth(self._locators[ref])

    async def click(self, ref: str) -> None:
        locator = await self._resolve(ref)
        self.last_navigation_status = None
        await locator.click()
        self.current = None

    async def fill(self, ref: str, value: str) -> None:
        locator = await self._resolve(ref)
        await locator.fill(value)
        self.current = None

    async def select(self, ref: str, option: str) -> None:
        locator = await self._resolve(ref)
        await locator.select_option(label=option)
        self.current = None

    async def capture_form(self, ref: str) -> dict:
        locator = await self._resolve(ref)
        result = await locator.evaluate(FORM_JS)
        if not result or result["method"] != "POST":
            raise ValueError("Control is not a POST form submit")
        return result

    async def close(self) -> None:
        await self.context.close()
        await self.browser.close()
        await self.driver.stop()
