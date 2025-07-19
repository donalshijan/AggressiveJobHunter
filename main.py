from typing import Any, Optional
from browser_controller import BrowserController
from llm_agent import LLMAgent
from executor import InstructionExecutor
import json
import logging
from plyer import notification
import os

APPLICATIONS_PER_SITE_LIMIT = 10
# Create logger
logger = logging.getLogger("JobApplicationAgent")
logger.setLevel(logging.DEBUG)  # Set default level

# Formatter
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# File handler (logs to a file)
file_handler = logging.FileHandler("agent.log", mode="w")  # Change mode to 'a' to append to logs from previous run, 'w' will truncate and start appending logs from current run
file_handler.setLevel(logging.DEBUG)  # Show all levels in file
file_handler.setFormatter(formatter)

# Console handler (logs to stdout)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Show all levels in file
console_handler.setFormatter(formatter)

# Attach handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)


def load_json(path: str) -> dict[str,str]:
    with open(path, 'r') as f:
        return json.load(f)
    
def focus_browser():
    try:
        os.system('''/usr/bin/osascript -e 'tell application "Google Chrome" to activate' ''')
    except Exception as e:
        logger.warning(f"[Main] ⚠️ Could not focus browser: {e}")
    
def request_manual_intervention(message:str, phase:str) -> None:
    logger.warning(f"⚠️[Main]  MANUAL INTERVENTION NEEDED [{phase}]⚠️")
    logger.info(f"[Main] Reason: {message}")
    focus_browser()
    logger.info("[Main] Browser is open. Please take the necessary action and press [Enter] to resume...")
    notify_user(message)
    input("[Paused] Press Enter when ready to continue...")
    logger.info("[Main] Resuming autonomous control.")
    
def notify_user(message: str) -> None:
    # Desktop notification
    try:
        if callable(notification.notify):
            notification.notify( 
                title="🛑 Manual Intervention Required",
                message=message,
                timeout=10
            )
    except Exception as e:
        logger.warning(f"[Main] ⚠️ Notification failed: {e}")
    
    # Audible alert (macOS example)
    try:
        os.system(f'say "{message}"')  # macOS only
    except Exception as e:
        logger.warning(f"[Main] ⚠️ Audio alert failed: {e}")
        
def main() -> None:
    # 1. Define applicant preferences
    applicant_preferences: dict[str,str] = load_json("applicant_preferences.json")
    applicant_data: dict[str,str] = load_json("applicant_data.json")
    applicant_credentials: dict[str,str] = load_json("applicant_credentials.json")
    
    # 2. Initialize components
    logger.info(f"[Main] Initializing Browser Controller")
    browser: BrowserController = BrowserController(headless=False)
    logger.info(f"[Main] Initializing Instruction Executor")
    executor: InstructionExecutor = InstructionExecutor(browser)
    logger.info(f"[Main] Initializing LLMAgent for login phase")
    login_agent: LLMAgent = LLMAgent('login')
    logger.info(f"[Main] Initializing LLMAgent for search phase")
    search_agent: LLMAgent = LLMAgent('search')
    logger.info(f"[Main] Initializing LLMAgent for application phase")
    application_agent: LLMAgent = LLMAgent('application')

    # 3. For each site login, search and apply
    for site in applicant_preferences["sites"]:
        logger.info(f"[Main] Navigating to {site}...")
        browser.goto(site)

        # --- Phase 1: Login ---
        loggedIn: bool = False
        if site in applicant_credentials:
            while True:
                logger.info("[Main] (Login Phase) Fetching DOM")
                dom_html = browser.get_dom()
                logger.info("[Main] (Login Phase) Asking LLM for next action")
                instructions = login_agent.ask(dom_html, {
                    "site" : site,
                    "phase": "login",
                    "job_seeker_credentials": applicant_credentials
                })
                
                if not instructions:
                    logger.info("[Main] (Login Phase) No more instructions. Proceeding to search phase.")
                    break
                
                for instr in instructions:
                    if instr["action"] == "intervene":
                        request_manual_intervention(instr['text'],'login')
                    else:
                        success : bool = executor.execute(instr)
                        if not success:
                            logger.error(f"[Main] ❌ Failed login instruction: {instr}")
                            break
                        else: 
                            logger.info(f"[Main] ✅ Successfully executed login instruction: {instr}")
                            if instr.get("action") == "done":
                                logger.info("[Main] Login phase completed.")
                                loggedIn = True
                if loggedIn:
                    break
        else:
            logger.warning(f"[Main] No login credentials for site: {site}. Skipping.")
            continue
        
        if not loggedIn:
            logger.warning(f"[Main] Login did not succeed for site: {site}. Skipping.")
            continue
        
        # --- Phase 2: Search ---
        searched_jobs : bool = False
        while True:
            logger.info("[Main] (Search Phase) Fetching DOM")
            dom_html: str = browser.get_dom()
            logger.info("[Main] (Search Phase) Asking LLM for next action")
            search_instructions = search_agent.ask(dom_html, {
                "phase": "search",
                "job_seeker_preferences": applicant_preferences
            })

            if not search_instructions:
                logger.info("[Main] (Search Phase) No more instructions. Proceeding to application phase.")
                break

            logger.info(f"[Main] LLM Search Instructions:\n{json.dumps(search_instructions, indent=2)}")
            for instr in search_instructions:
                if instr["action"] == "intervene":
                    request_manual_intervention(instr['text'],'search')
                else:
                    success : bool = executor.execute(instr)
                    if not success:
                        logger.error(f"[Main] ❌ Failed search instruction: {instr}")
                        break
                    else: 
                        logger.info("[Main] ✅ Successfully executed search instruction.")
                        if instr.get("action") == "done":
                            logger.info("[Main] Search phase completed.")
                            searched_jobs=True
                            break
            if searched_jobs:
                break
            
        if not searched_jobs:
            logger.warning(f"[Main] Search did not succeed for site: {site}. Skipping.")
            continue
        
        # --- Phase 3:  Apply ---
        applied: bool = False
        number_of_applications_made : int = 0
        while True:
            # 4. Get current page content
            logger.info("[Main] Fetching DOM")
            dom_html: str = browser.get_dom()
            
            logger.info(f"[Main] Fetched DOM:\n{dom_html}")
            
            # 5. Ask LLM agent: what next?
            logger.info("[Main] Asking LLM for next action")
            instructions: Optional[list[dict[str, Any]]] = application_agent.ask(dom_html, {
                "phase" : "application",
                "applicant_preferences": applicant_preferences,
                "applicant_data": applicant_data
            })

            # Defensive: check if LLM failed to return valid JSON
            if not instructions:
                logger.warning("[Main] ⚠️ LLM did not return valid instructions. Skipping...")
                break
            
            logger.info(f"[Main] LLM Instructions: {json.dumps(instructions, indent=2)}")

            # Support single or batch instruction
            for instr in instructions:
                if instr["action"] == "intervene":
                    request_manual_intervention(instr['text'],'application')
                else:
                    success = executor.execute(instr)
                    if not success:
                        logger.error(f"[Main] ❌ Failed to execute apply instruction: {instructions}")
                        break
                    else: 
                        logger.info("[Main] ✅ Successfully executed apply instruction.")
                        if instr.get("action") == "done":
                            logger.info("[Main] Application phase completed.")
                            applied=True
                            break
            
            if applied:
                number_of_applications_made += 1
                applied = False
                
            if number_of_applications_made == APPLICATIONS_PER_SITE_LIMIT:
                break
                    

    browser.close()

if __name__ == "__main__":
    main()
