from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, Playwright
import json
from typing import Any

class BrowserController:
    def __init__(self, headless: bool = False) -> None:
        self.playwright: Playwright = sync_playwright().start()
        self.browser: Browser = self.playwright.chromium.launch(headless=headless,channel="chrome")
        self.context: BrowserContext = self.browser.new_context()
        self.page: Page = self.context.new_page()

    def goto(self, url: str) -> None:
        """Navigate to the given URL and wait for full page load."""
        self.page.goto(url)
        self.page.wait_for_load_state("load")

    def get_dom(self) -> str:
        """Return the current DOM as an HTML string, along with options for select fields."""
        html = self.page.content()
        selects = self.page.query_selector_all("select")
        select_info : list[dict[str, Any]]= []

        for select in selects:
            name = select.get_attribute("name") or select.get_attribute("id")
            options = select.query_selector_all("option")
            values = [opt.get_attribute("value") for opt in options]
            select_info.append({"field": name, "options": values})

        return json.dumps({
            "html": html,
            "select_fields": select_info
        })

    def click(self, selector: str) -> None:
        """Click the element specified by the CSS selector."""
        self.page.click(selector)

    def fill(self, selector: str, text: str) -> None:
        """Fill the element specified by the CSS selector with the given text."""
        self.page.fill(selector, text)
        
    def select(self, selector: str, value: str) -> None:
        """Select the value from the element specified by the CSS selector."""
        self.page.select_option(selector, value)
    
    def upload(self, selector: str, file_path: str) -> None:
        self.page.set_input_files(selector, file_path)

    def close(self) -> None:
        """Close the browser and stop the Playwright instance."""
        self.browser.close()
        self.playwright.stop()
