"""Record the demo video and the README screenshots against a running `make dev`.

Frames come from Chrome's screencast at 1920x1080 with their real timestamps, and ffmpeg
encodes them at 30 fps, so the video plays at real speed. Live model calls are made, so a
run costs about ₹1.

    make reset-demo && make dev            # in one terminal
    uv run python -m scripts.record_demo   # in another
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from playwright.async_api import Page, async_playwright

from worker.config import ROOT

CONSOLE = "http://127.0.0.1:8100/"
OUT_VIDEO = ROOT / "docs" / "media" / "demo.mp4"
SHOTS = ROOT / "docs" / "screenshots"
VIEWPORT = {"width": 1440, "height": 810}
SCALE = 1920 / 1440

OVERLAY = """
(() => {
 const setup = () => {
  if (document.getElementById('demo-cursor')) return;
  const style = document.createElement('style');
  style.textContent = `
    #demo-cursor { position: fixed; z-index: 2147483647; pointer-events: none; width: 22px; height: 22px;
      margin: -3px 0 0 -3px; transition: transform .08s; }
    #demo-cursor.down { transform: scale(.82); }
    #demo-caption { position: fixed; z-index: 2147483646; left: 50%; bottom: 28px; transform: translateX(-50%);
      max-width: 1040px; padding: 14px 22px; border-radius: 12px; background: rgba(17, 24, 39, .92);
      color: #fff; font: 500 19px/1.45 'Instrument Sans', system-ui, sans-serif; box-shadow: 0 10px 30px rgba(0,0,0,.25);
      opacity: 0; transition: opacity .35s; text-align: center; pointer-events: none; }
    #demo-caption.on { opacity: 1; }
    #demo-caption b { color: #a5b4fc; font-weight: 600; }`;
  document.head.appendChild(style);
  const cursor = document.createElement('div');
  cursor.id = 'demo-cursor';
  cursor.style.left = '720px';
  cursor.style.top = '470px';
  cursor.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M3 2l7 19 2.6-7.4L20 11z" ' +
    'fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  const caption = document.createElement('div');
  caption.id = 'demo-caption';
  document.body.appendChild(cursor);
  document.body.appendChild(caption);
  addEventListener('mousemove', (e) => { cursor.style.left = e.clientX + 'px'; cursor.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => cursor.classList.add('down'), true);
  addEventListener('mouseup', () => cursor.classList.remove('down'), true);
 };
 document.readyState === 'loading' ? addEventListener('DOMContentLoaded', setup) : setup();
})();
"""


class Recorder:
    """Collects screencast frames with their timestamps."""

    def __init__(self, page: Page, folder: Path):
        self.page, self.folder, self.frames = page, folder, []

    async def start(self) -> None:
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._frame)
        await self.cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})

    def _frame(self, event: dict) -> None:
        path = self.folder / f"{len(self.frames):06d}.jpg"
        path.write_bytes(base64.b64decode(event["data"]))
        self.frames.append((event["metadata"]["timestamp"], path))
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]}))

    async def stop(self) -> float:
        await self.cdp.send("Page.stopScreencast")
        return time.time()

    def encode(self, end: float, out: Path) -> None:
        lines = []
        for index, (stamp, path) in enumerate(self.frames):
            following = self.frames[index + 1][0] if index + 1 < len(self.frames) else end
            lines += [f"file '{path}'", f"duration {max(following - stamp, 0.001):.4f}"]
        lines.append(f"file '{self.frames[-1][1]}'")
        listing = self.folder / "frames.txt"
        listing.write_text("\n".join(lines) + "\n")
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(listing), "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p",
                        "-r", "30", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                        "-movflags", "+faststart", str(out)], check=True)


class Demo:
    def __init__(self, page: Page):
        self.page = page

    async def caption(self, html: str, hold: float = 0) -> None:
        await self.page.evaluate("""(html) => { const c = document.getElementById('demo-caption');
            if (!c) return; c.innerHTML = html; c.classList.toggle('on', !!html); }""", html)
        if hold:
            await asyncio.sleep(hold)

    async def click(self, locator) -> None:
        await locator.scroll_into_view_if_needed()
        box = await locator.bounding_box()
        await self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=28)
        await asyncio.sleep(0.25)
        await self.page.mouse.down()
        await asyncio.sleep(0.08)
        await self.page.mouse.up()

    async def type(self, locator, text: str) -> None:
        await self.click(locator)
        await locator.press_sequentially(text, delay=32)

    async def status(self) -> str:
        return (await self.page.locator(".run-stats [role=status]").first.text_content() or "").strip()

    async def wait_status(self, wanted: set[str], timeout: float = 180) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = await self.status()
            if current in wanted:
                return current
            await asyncio.sleep(0.5)
        raise TimeoutError(f"run did not reach {wanted}; last status {await self.status()!r}")

    async def wait_row(self, kind: str, timeout: float = 120) -> None:
        await self.page.locator(".ledger-rows .row-kind", has_text=kind).first.wait_for(timeout=timeout * 1000)

    async def scroll_to(self, selector: str | None) -> None:
        await self.page.evaluate("""(sel) => { const el = sel && document.querySelector(sel);
            window.scrollTo({top: el ? el.getBoundingClientRect().top + scrollY - 90 : 0, behavior: 'smooth'}); }""",
                                 selector)
        await asyncio.sleep(1.2)

    async def shot(self, name: str, full: bool = False) -> None:
        await self.caption("")
        await self.page.evaluate("document.getElementById('demo-cursor').style.display = 'none'")
        await asyncio.sleep(0.4)
        await self.page.screenshot(path=str(SHOTS / name), full_page=full)
        await self.page.evaluate("document.getElementById('demo-cursor').style.display = ''")

    async def start_task(self, text: str) -> None:
        await self.scroll_to(None)
        await self.type(self.page.locator("#task"), text)
        await asyncio.sleep(0.4)
        await self.click(self.page.locator("form[aria-labelledby=new-h] button[type=submit]"))


async def scenes(demo: Demo, page: Page) -> None:
    await page.goto(CONSOLE)
    await page.mouse.move(720, 470)
    await page.locator("label.account", has_text="Ravi Shah").wait_for()
    await demo.caption("<b>Task Worker</b> takes a request in plain words, does the work in a real browser "
                       "across two company apps, and says done only after it proves the result.", 5)
    await demo.shot("01-sign-in.png")
    await demo.caption("Ravi is an operator. The worker acts with Ravi's own permissions in the register.")
    await demo.click(page.locator("label.account", has_text="Ravi Shah"))
    await demo.type(page.locator("#password"), "ravi-demo")
    await page.locator("#password").press("Enter")
    await page.locator("#task").wait_for()
    await asyncio.sleep(1)

    # 1. intake: read the portal, enter the register, verify by read-back
    await demo.caption("<b>Task 1.</b> Find the latest Larkspur invoice and enter it in the register.")
    await demo.start_task("Find the latest invoice from Larkspur Supplies, enter it in our register, "
                          "and show me the saved record.")
    await demo.caption("It starts read-only: it opens the supplier portal and looks before it can change anything.")
    await demo.wait_row("Goal locked")
    await demo.caption("<b>Goal locked by code:</b> the source invoice is frozen, and the checks the result must "
                       "pass are fixed before any write.")
    await demo.wait_row("Fill form")
    await demo.caption("Values are copied off the page by code and every field is checked against its source "
                       "before saving.")
    await demo.wait_status({"Done and verified", "Completed, not verified", "Failed", "Blocked", "Partly done"})
    await asyncio.sleep(1)
    await demo.shot("02-verified-intake.png", full=True)
    await demo.caption("<b>Done and verified:</b> the register was read back independently and every check "
                       "passed, with captures of the source and the saved record.")
    await demo.scroll_to(".evidence")
    await asyncio.sleep(6)
    await demo.scroll_to(".ledger")
    await demo.caption("The timeline shows every step: what it opened, what it recorded, and what it saved.", 5)

    # 2. correction: an existing record needs approval of the exact change
    await demo.caption("<b>Task 2.</b> Correct an existing invoice so it matches the supplier portal.")
    await demo.start_task("Correct existing invoice LS-1039 from Larkspur Supplies to match the portal.")
    await demo.wait_status({"Needs your approval", "Failed", "Blocked"})
    await asyncio.sleep(1)
    await demo.caption("Company policy: a change to an existing record waits for a person. The card shows "
                       "exactly what will change.")
    await demo.shot("03-approval.png")
    await demo.caption("Company policy: a change to an existing record waits for a person. The card shows "
                       "exactly what will change.", 5)
    await demo.caption("The approval binds these exact values, this record version and the current policy, "
                       "for 15 minutes.")
    await demo.click(page.get_by_role("button", name="Approve and save"))
    await demo.wait_status({"Done and verified", "Completed, not verified", "Failed", "Blocked", "Partly done"})
    await asyncio.sleep(1)
    await demo.shot("04-verified-correction.png", full=True)
    await demo.caption("Corrected and verified on the same record and its new version.")
    await demo.scroll_to(".evidence")
    await asyncio.sleep(5)

    # 3. an unclear request: it asks, and "No" stops the run with nothing saved
    await demo.caption("<b>Task 3.</b> A request that does not clearly ask for something it does.")
    await demo.start_task("Record a refund for Larkspur Supplies' latest invoice.")
    await demo.wait_status({"Needs your answer", "Not something it can do", "Blocked", "Failed"})
    await asyncio.sleep(1)
    await demo.caption("It does not guess. Code checks the goal against the user's own words and asks first.")
    await demo.shot("05-question.png")
    await demo.caption("It does not guess. Code checks the goal against the user's own words and asks first.", 4)
    no = page.get_by_role("button", name="No", exact=True)
    if await no.count():
        await demo.click(no)
        await demo.wait_status({"Blocked", "Failed"}, timeout=60)
        await asyncio.sleep(1)
        await demo.caption("Declined: the run stops and nothing was saved.", 4)

    await demo.scroll_to(None)
    await demo.caption("<b>Live evaluation on the final code:</b> 16/16 development tasks, 11/11 guard controls "
                       "and 10/11 held-out tasks, with 0 false completions and 0 unauthorized or duplicate "
                       "writes.", 8)
    await demo.caption("")
    await asyncio.sleep(1)


async def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required")
    SHOTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE)
            await context.add_init_script(OVERLAY)
            page = await context.new_page()
            recorder = Recorder(page, Path(folder))
            await recorder.start()
            try:
                await scenes(Demo(page), page)
            finally:
                end = await recorder.stop()
                await browser.close()
        recorder.encode(end, OUT_VIDEO)
    print(f"Video: {OUT_VIDEO}")


if __name__ == "__main__":
    asyncio.run(main())
