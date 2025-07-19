import requests
import json
from typing import Union, Optional, Any , cast
import logging
import os
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
import re

def extract_json_block(text: str) -> str:
    # Remove triple backtick wrappers if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()

logger = logging.getLogger("JobApplicationAgent")

class LLMAgent:
    def __init__(self, phase:str,  provider: str = "ollama", model: str = "gemma3:1b") -> None:
        self.provider: str = provider
        self.model: str = model
        self.system_prompt: dict[str, str] = self._build_system_prompt(phase)
        # self.messages: list[dict[str, str]] = [self.system_prompt]
        self.messages: list[Any] = [self.system_prompt]
        if self.provider == "openai":
            self.api_key : str|None = os.getenv("OPENAI_API_KEY")
        elif self.provider == "anthropic":
            self.api_key : str|None = os.getenv("ANTHROPIC_API_KEY")

    def _build_system_prompt(self,phase:str)->dict[str,str]:
        json_response_format: str = (
            '{\n'
            '  "action": "click" | "fill" | "select" | "upload" | "submit" | "done" | "intervene",\n'
            '  "selector": "CSS_SELECTOR_HERE",\n'
            '  "text": "VALUE_TO_SELECT_OR_FILL_OR_UPLOAD_PATH or INSTRUCTION_REASON_FOR_INTERVENTION" '
            '}'
        )
        json_intervention_instruction_response_format: str = (
            '{\n'
            '  "action": "intervene",\n'
            '  "selector": "N/A",\n'
            '  "text": "Explain briefly why intervention is needed" '
            '}'
        )
        json_done_instruction_response_format: str = (
            '{\n'
            '  "action": "done",\n'
            '  "selector": "",\n'
            '  "text": "" '
            '}'
        )
        description_of_instruction : str = (
            "Each actionable instruction you generate is passed to an executor who will decipher the instruction and execute that instruction on the browser programatically using browser automation tool playwright.\n"
            "Each actionable instruction you generate is going to be an instruction specifying what type of action should be taken on a specific html dom element to interact and take the next step in the application process.\n"
            "Each actionable instruction you generate will use highly specific css selectors or identifiers to describe and narrow down the html dom element on which that specifc action is to be executed.\n "
            "Each actionable instruction you generate is to be a string representation of json object format.\n"
            "Each actionable instruction you generate will comprise of three key fields in it's string representation of json object format and they are:\n"
            "1. Action - This field will suggest what action needs to be taken next on an html dom element and it's value can only be one of the following pipe separated values:\n"
            """ "click" | "fill" | "select" | "upload" | "submit" | "done" | "intervene"\n """
            "2. Selector - This field is where you will specify the most specific css selector to narrow down the html dom element on which that action should be taken, making it as unambiguous as possible. This field's value will be left blank in the case when the action is either intervene or done.\n"
            "3. Text - This field's value is also optional depending on the action, for actions requiring setting form field values like fill and select it will specify the value to set that form field value with, for upload action type it will specify the file path of the file to be uploaded, for action type intervene it will briefly describe the reason why intervention is needed.\n"
        )
        system_prompt:dict[str,str]={}
        if phase =='application':
            system_prompt: dict[str, str] = {
                "role": "system",
                "content": (
                    "You are an intelligent job application agent, applying for jobs on a job posting site on behalf of an applicant.\n"
                    "Your task is to figure out the next action needed in the job application process from the HTML content of the current page of the job posting site and then generate instructions to interact with the website to execute those actions.\n"
                    "You will be provided with an html content of current state of a page of the job posting site, which will be under the label 'Current page HTML content:', which could either be just displaying job listings if application process for a job is yet to be initiated, or the html content could reflect the midway state of application process for a job listing, some point after initiation.\n"
                    "You will also be provided a json formatted string labeled 'Applicant Data' which will contain the applicant's data, which you will make use of while generating instructions for interacting with the application form fields encountered while progressing through application process, specifying values for fields in the forms.\n"
                    "You will parse the html content, infer and figure out how far has the application process progressed and generate instructions to interact with the website to take the immediate next steps inorder to progress through the application process for a job listing further. You will also make use of the applicant data for specifying the form field values when generating instructions pertaining to application form fields.\n"
                    f"{description_of_instruction}"
                    "Here is the complete instruction response format for one instruction:\n"
                    f"{json_response_format}\n"
                    "You will strictly adhere to that instruction format when generating each instructions."
                    "You will always respond in that instruction format and only in that format.\n"
                    "Your task finishes successfully once you realize from the html content of current page of the job posting website, that you successfully completed the application process and submitted the application for a job listing. Upon which you will generate one final instruction of action type 'done'.\n"
                    "Following are some constraints to keep in mind while generating instructions:\n"
                    # "- When referencing fields like first_name, email, phone, degree, etc., that are available in the Applicant Data section, you MUST use a placeholder like '$first_name', '$email', '$resume_path'. These will be fetched from the applicant_data.json file and get replaced later before execution. Only use plain values (e.g. 'John Doe' for full name which is not a field in applicant_data.json) for things that must be derived contextually and are not directly mentioned in the Applicant Data section.\n" 
                    "- When specifying application form field values in the text field of string formatted json instructions that you generate, if info or value for that field is available in the Applicant Data section, you MUST use a placeholder in the instruction specifying the value for those field's like 'text':'$first_name', 'text':'$email', 'text':'$resume_path' for fields asking about First Name, Email, etc. These will be fetched from the applicant_data.json file and get replaced later before execution. Use plain text as value for application form field value in text field of instruction when (e.g. 'text':'John Doe' for full name which is not a field in applicant_data.json) values must be derived contextually and are not directly mentioned in the Applicant Data section.\n" 
                    "- Do NOT generate multiple instructions for the same selector. Each instruction corresponds to one action on one selector.\n"
                    "- If the action is select, only choose from the provided list of values for the selector field.\n"
                    "- If the action is upload, use the field from Applicant Data such as 'resume_file' or 'cover_letter_file' for file path.\n"
                    "- Target only required fields. Keep responses tight and actionable.\n"
                    "- When you figure that a job application has been successfully completed, end your task by responding with:\n"
                    f"{json_done_instruction_response_format}\n"
                    "- If the DOM appears to be stuck (e.g., same HTML shown repeatedly after several steps), or the next action is ambiguous or risky, emit a single instruction with:\n"
                    f"{json_intervention_instruction_response_format}\n"
                    "This will trigger manual intervention mode where user will temporarily takeover and complete the next step and then let the agent resume control back again over the application process."
                    
                )
            }
        elif phase == 'search':
            system_prompt: dict[str, str] = {
                "role": "system",
                "content": (
                    "You are a job search assistant searching jobs on a jobs posting website on behalf of a job seeker, by interacting with the jobs posting website to search for jobs as per the job seeker's preferences.\n"
                    "Your task is to generate instructions to interact with the jobs posting website firstly to have it's search/filter jobs interface open,visible and interactable if it is not already, then further to help find relevant job listings based on job seeker's preferences.\n"
                    "You will be provided with an html content of current state of a page of the job posting site, which will be under the label 'Current page HTML content:', which could either be just displaying job posting site's home page with or without the search/filter interface open, visible and interactable or it could be displaying midway state of search process with the search/filter interface open, visible, interactable and showing where the agent last left off in the search phase, which would be reflected by some of the fields in the search form filled or selected. In the case where search/filter interface is not open, visible and interactable, you will first generate instructions to get search/filter interface open, visible and interactable, then move on to generate instructions to interact with it and carry out the searching of jobs as per job seeker's preferences.\n"
                    "You will also be provided a json formatted string labelled 'Job Seeker Preferences' which will contain the job seekers's job related preferences, which you will make use of while generating specific instructions for interacting with the website to proceed with search process.\n"
                    "You will parse the html content and generate instructions to interact with the website to take the immediate next steps inorder to succeed in searching and yielding job listings as per job seeker's preferences.\n"
                    "Your task finishes successfully once you realize from the html content of current page of the job posting website, that job listings are visible as per job seeker's preferences.\n"
                    f"{description_of_instruction}"
                    "Here is the complete instruction response format for one instruction:\n"
                    f"{json_response_format}\n"
                    "You will strictly adhere to that instruction format when generating each instructions."
                    "You will always respond in that instruction format and only in that format.\n"
                    "Your task finishes successfully once you realize from the html content of current page of the job posting website, that you successfully completed searching and yielding job listings as per job seeker's preferences. Upon which you will generate one final instruction of action type 'done'.\n"
                    "Following are some constraints to keep in mind while generating instructions:\n"
                    "- When you realize that info or value for a particular form field can be directly found in the Job Seeker Preferences Json Formatted string section, use placeholder values of format `$field_name_in_Job_Seeker_Preferences` while generating instruction for interacting with those fields, eg. 'text':'$preferred_role','text':'$location, 'text':'$job_type', etc. \n"
                    "- When you realize that info or value for a particular form field cannot be directly found in the Job Seeker Preferences Section rather needs to be derived contextually, you can specify the contextually derived value for that field plainly without any placeholders like 'text':'value' \n"
                    "- When job listings are visible , end your task by responding with:\n"
                    f"{json_done_instruction_response_format}\n"
                    "- NEVER attempt to apply for a job or interact with job listings. Only carry out the search.\n"
                    "- Do not issue redundant actions for the same selector."
                    "- If the DOM appears to be stuck (e.g., same HTML shown repeatedly after several steps), or the next action is ambiguous or risky, emit a single instruction with:\n"
                    f"{json_intervention_instruction_response_format}\n"
                    "This will trigger manual intervention mode where user will temporarily takeover and complete the next step and then let the agent resume control back again over the search process."
                )
            }
        elif phase == 'login':
            system_prompt: dict[str, str] = {
                "role": "system",
                "content": (
                    "You are an intelligent automation agent helping a job seeker log into a job posting website.\n"
                    "Your task is to generate instructions to interact with the jobs posting website to log into the website on behalf of the job seeker.\n"
                    "You will be provided with the html content of current state of a page of the job posting website, which will be under the label 'Current page HTML content:'.\n"
                    "You will also be provided a json formatted string labelled 'Job Seeker Credentials', which contains the job seeker's login credentials and other info to log into different websites.\n"
                    "You will parse the HTML content of the page and figure out it's logged in status, if no user is logged into that page, you will use the Job seeker's credentials for that job posting website and generate appropriate instructions to take the next steps towards logging the Job Seeker in.\n"
                    "Your task finishes when you infer and realize from the provided HTML content of the page that a user has successfully logged into that website.\n"
                    f"{description_of_instruction}"
                    "Here is the complete instruction response format for one instruction:\n"
                    f"{json_response_format}\n"
                    "You will strictly adhere to that instruction format when generating each instructions."
                    "You will always respond in that instruction format and only in that format.\n"
                    "Your task finishes successfully once you realize from the html content of the current page of the job posting website, that a user has successfully logged into the website. Upon which you will generate one final instruction of action type 'done'.\n"
                    "Following are some constraints to keep in mind while generating instructions:\n"
                    "- Use placeholders of format '$field_name_in_job_seeker_credentials_json' such as '$email', '$username', '$password' for text field values in instructions when referencing directly available fields from Job Seeker credentials, they will be replaced before execution. You can specify values direclty without any place holders for text field of instruction when the value is not directly from job seeker credential but contextually derived from html content of the page, such as CAPTCHA field values.\n"
                    "- Only act on fields necessary for the login process (e.g., username, email, password, login buttons, CAPTCHA).\n"
                    "- For each job board website mentioned in the Job Seeker Credentials json, it also mentions the 'login_type' used to login in to that site by the Job Seeker, for 'login_type':'Google', you are gonna have to generate instructions to do the sign in with google sign in. Trigger a Google OAuth flow (e.g. click 'Sign in with Google').\n"
                    "- For 'login_type':'Custom', you will generate instructions specifying to fill in the login form by picking values from the job seeker credentials for that site, such as email, password etc.\n"
                    "- Do NOT generate multiple instructions for the same selector.\n"
                    "- Each instruction corresponds to one action on one element.\n"
                    "- Keep instructions minimal, safe, and focused on progressing the login process.\n"
                    "- When you infer from the html content that a user has successfully logged in or that a user has already logged in, end your task with the following response:\n"
                    f"{json_done_instruction_response_format}\n"
                    "- Do not issue redundant actions for the same selector."
                    "- If the DOM appears to be stuck (e.g., same HTML shown repeatedly after several steps), or the next action is ambiguous or risky, emit a single instruction with:\n"
                    f"{json_intervention_instruction_response_format}\n"
                    "This will trigger manual intervention mode where user will temporarily takeover and complete the next step and then let the agent resume control back again over the login process."
                )
            }
        else :
            logger.error("[LLM Agent]Invalid phase")
        return system_prompt
        
    def _interpolate(self, instructions: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Replace $variables in instructions with real values."""
        flat_context = self._flatten(context.get("applicant_data", {}))

        def resolve(val : Union[str , Any]) -> str: 
            if isinstance(val, str) and val.startswith("$"):
                return flat_context.get(val[1:], val)
            return val

        for instr in instructions:
            if "text" in instr:
                instr["text"] = resolve(instr["text"])
        return instructions

    def _flatten(self, d: dict[str, Any], parent_key: str = '', sep: str = '_') -> dict[str, Any]:
        """Flatten nested dict into a single level with joined keys."""
        items : dict[str,Any]= {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten(cast(dict[str, Any], v), new_key, sep=sep))
            elif isinstance(v, list):
                items[new_key] = ", ".join(map(str, cast(list[Any], v) ))
            else:
                items[new_key] = v
        return items
    
    @staticmethod
    def format_dict(name: str, data: dict[str, Any], indent: int = 0) -> str:
        lines = [f"{'  ' * indent}{name}:"]
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(LLMAgent.format_dict(key, cast(dict[str, Any], value), indent + 1))
            elif isinstance(value, list):
                list_values = ", ".join(map(str, cast(list[Any], value) ))
                lines.append(f"{'  ' * (indent + 1)}{key}: {list_values}")
            else:
                lines.append(f"{'  ' * (indent + 1)}{key}: {value}")
        return "\n".join(lines)
    
    def ask(self, html_content: str, context:  dict[str, Any]) -> Optional[list[dict[str, Any]]]:
        phase : str = context["phase"]
        context_str : str = ""
        if phase == 'login':
            site : str = context["site"]
            applicant_credentials = self.format_dict("Job Seeker Credentials",context["job_seeker_credentials"])
            context_str = f"You are to log into the following website : {site} on behalf of the applicant, and you the applicant's credentials can be looked up from the following"+applicant_credentials
        elif phase == 'application':
            applicant_preferences = self.format_dict("Applicant Preferences",context["applicant_preferences"])
            applicant_data = self.format_dict("Applicant Data",context["applicant_data"])
            context_str = applicant_preferences + '\n' + applicant_data
        elif phase == 'search':
            applicant_preferences = self.format_dict("Job Seeker Preferences",context["job_seeker_preferences"])
            context_str =  applicant_preferences
        else:
            logger.error(f"⚠️ [LLMAgent] Invalid Phase: {phase}")
            return None
        
        prompt: dict[str, str] = {
            "role": "applicant",
            "content": f"Current page HTML content:\n{html_content[:5000]}\nContext: {context_str}"
        }

        # self.messages.append(prompt) # accumulate all messages ,Preserves memory of prior actions (can be useful in multi-turn tasks). Quickly grows beyond model token limits .
        self.messages = [self.system_prompt, prompt]  # reset every time, should be better suited as previous prompt history, instructions generated and actions taken is not necessary for generating next Instruction, at least for this application, current html context and system prompt should be fine. Although if included, would yield better context awareness and guidance, aiding precise instruction generation.

        result : str
        if self.provider == "ollama":
            result = self._ask_ollama()
        elif self.provider == "openai":
            result = self._ask_openai()
        elif self.provider == "anthropic":
            result = self._ask_anthropic()
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
        
        try:
            clean_result = extract_json_block(result)
            raw_instructions = json.loads(clean_result)
            instructions : list[dict[str,Any]] = []
            if isinstance(raw_instructions, dict):
                instructions : list[dict[str,Any]] = [raw_instructions]
            elif isinstance(raw_instructions, list): 
                instructions = cast(list[dict[str, Any]], raw_instructions)
            else : 
                logger.warning(f"[LLM Agent] ⚠️ Unexpected instruction format:{result}")
                return None
            return self._interpolate(instructions, context)
        
        except json.JSONDecodeError:
            logger.warning(f"[LLM Agent] ⚠️ Could not parse LLM response:{result}")
            return None
        
    def _ask_ollama(self) -> str:
        
        try:
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": cast(list[dict[str,str]], self.messages),
                "stream": False
            }
            res = requests.post(
                "http://localhost:11434/api/chat",
                json=payload
            )
            res.raise_for_status()
            return res.json()["message"]["content"]
        except Exception as e:
            logger.error(f"[LLMAgent] Ollama request failed: {e}")
            return ""
    
    def _ask_openai(self) -> str:
        try:
            openai_client = OpenAI(api_key=self.api_key)
            response = openai_client.chat.completions.create(
                model=self.model,
                messages=cast(list[ChatCompletionMessageParam], self.messages),
                temperature=0.2
            )
            res = response.choices[0].message.content
            if res is None:
                raise ValueError("[LLM Agent] ⚠️ LLM returned no content.")
            return res
        except Exception as e:
            logger.error(f"[LLMAgent] OpenAI request failed: {e}")
            return ""

    def _ask_anthropic(self) -> str:
        try:
            res = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "messages": self.messages
                }
            )
            res.raise_for_status()
            return res.json()["content"]
        except Exception as e:
            logger.error(f"[LLMAgent] Anthropic request failed: {e}")
            return ""
        
