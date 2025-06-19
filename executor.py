from typing import Any
from browser_controller import BrowserController
import logging

logger = logging.getLogger("JobApplicationAgent")

class InstructionExecutor:
    def __init__(self, browser: BrowserController) -> None:
        self.browser: BrowserController = browser
    
    def execute(self, instruction: dict[str, Any]) -> bool:
        """
        Executes a single instruction. Returns True if the instruction was successfully executed,
        False if there was an error or the action is 'done'.

        Expected instruction format:
        {
            "action": "click" | "fill" | "select" | "upload" | "submit" | "done" | "intervene",
            "selector": "css-selector",
            "text": "value to fill"  # only needed if action is "fill"
        }
        """
        action: str = instruction.get("action", "")
        selector: str = instruction.get("selector", "")
        text: str = instruction.get("text", "")

        if not selector and action!="done":
            logger.error("[Executor] ❌ No selector provided.")
            return False
        
        logger.info(f"[Executor] Executing: {instruction}")
        for attempt in range(3):  # Retry logic
            if attempt>0:
                logger.warning(f"[Executor] Retrying instruction: Attempt {attempt+1}")
            try:
                if action == "click":
                    self.browser.click(selector)
                elif action == "fill":
                    self.browser.fill(selector, text)
                elif action == "select":
                    self.browser.select(selector, text)
                elif action == "upload":
                    self.browser.upload(selector, text)
                elif action == "submit":
                    self.browser.click(selector)
                elif action == "done":
                    logger.info("[Executor] ✅ Phase complete.")
                else:
                    logger.error(f"[Executor] ❌ Unknown action: {action}")
                    return False
                logger.info(f"[Executor] ✅ Success: {action} on {selector}")
                return True
            except Exception as e:
                logger.warning(f"[Executor] ⚠️ Attempt {attempt+1} failed for {action} on {selector}: with exeception: {e}")
        logger.error(f"[Executor] ❌ Failed for {action} on {selector} after retries.")
        return False
