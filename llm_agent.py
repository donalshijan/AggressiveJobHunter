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
        system_prompt:dict[str,str]={}
        if phase =='application':
            system_prompt: dict[str, str] = {
                "role": "system",
                "content": (
                    "You are an intelligent job application agent. Your job is to infer the next action "
                    "needed in the job application process from HTML content. You always respond in the following JSON format:\n"
                    f"{json_response_format}"
                    '''You respond ONLY in JSON format. When referencing fields like first_name, email, phone, degree, etc., that are available in the applicant data, you MUST use a placeholder like "$first_name", "$email", "$resume_path". These will be replaced later before execution. Only use plain values (e.g. "John Doe" for full name which is not a field in applicant_data.json) for things that must be derived contextually and are not directly labeled in the applicant data. Do NOT generate multiple instructions for the same selector. Each instruction corresponds to one action on one field.'''
                    "\nIf the action is select, only choose from the provided list of values for the selector field."
                    "\nIf uploading, use the field from applicant data such as 'resume_file' or 'cover_letter_file'. for file path"
                    "\nTarget only required fields. Keep responses tight and actionable."
                    """
                    If the DOM appears to be stuck (e.g., same HTML shown repeatedly after several steps), or the next action is ambiguous or risky, emit a single instruction with:
                    - "action": "intervene"
                    - "selector": "N/A"
                    - "text": "Explain briefly why intervention is needed"

                    This will trigger manual intervention mode.
                    """
                )
            }
        elif phase == 'search':
            system_prompt: dict[str, str] = {
                "role": "system",
                "content": (
                    "You are a job search assistant. Your task is to interact with the job board's search/filter interface "
                    "to help find relevant job listings based on applicant's preferences.\n"
                    "You MUST only return valid instructions in the following JSON format:\n"
                    f"{json_response_format}\n"
                    "Respond ONLY in this JSON format. Your job is to:\n"
                    "- Identify and interact with search filters such as keywords, location, category, etc.\n"
                    "- Use placeholder fields like `$preferred_role`, `$location`, `$job_type`, etc., from applicant_preferences.\n"
                    "- Use 'submit' action when ready to execute the search.\n"
                    "- When job listings are visible , end your task by responding with:\n"
                    '{ "action": "done", "selector": "", "text": "" }\n'
                    "NEVER attempt to apply for a job or interact with job listings. Only configure the search.\n"
                    "Do not issue redundant actions for the same selector."
                    """
                    If the DOM appears to be stuck (e.g., same HTML shown repeatedly after several steps), or the next action is ambiguous or risky, emit a single instruction with:
                    - "action": "intervene"
                    - "selector": "N/A"
                    - "text": "Explain briefly why intervention is needed"

                    This will trigger manual intervention mode.
                    """
                )
            }
        elif phase == 'login':
            system_prompt: dict[str, str] = {
                "role": "system",
                "content": (
                    "You are an intelligent automation agent helping an applicant log into a job portal or website. "
                    "Your task is to infer the next step required in the login process based on the HTML content of the page. "
                    "You always respond in the following JSON format:\n"
                    f"{json_response_format}"
                    '''You respond ONLY in the above mentioned JSON format. Use placeholders such as "$email", "$username", "$password" for text field values when referencing applicant credentials that will be replaced before execution. Do not use actual credentials in the response.'''
                    "\nOnly act on fields necessary for the login process (e.g., username, email, password, login buttons)."
                    "\nFor each job board site mentioned in the applicant_credentials json, it also mentions the 'login_type' used to login in to that site by the applicant, for 'login_type':'Google', you are gonna have to generate instructions to do the sign in with google sign in. Trigger a Google OAuth flow (e.g. click 'Sign in with Google')."
                    "\nFor 'login_type':'Custom', you will generate instructions specifying to fill in the login form by picking values from the credentials json for that site, such as email, password etc."
                    "\nDo NOT generate multiple instructions for the same selector."
                    "\nEach instruction corresponds to one action on one element."
                    "\nUse `click` only when interacting with buttons or checkboxes."
                    "\nUse `fill` when entering text into input fields like email or password."
                    "\nUse `submit` if there's a form element to be submitted."
                    "\nKeep instructions minimal, safe, and focused on progressing the login process."
                    "\nIf you infer successful login from html or detect already logged in, then respond with the" + '{ "action": "done", "selector": "", "text": "" }\n' + "instruction"
                    """
                    If the DOM appears to be stuck (e.g., same HTML shown repeatedly after several steps), or the next action is ambiguous or risky, emit a single instruction with:
                    - "action": "intervene"
                    - "selector": "N/A"
                    - "text": "Explain briefly why intervention is needed"

                    This will trigger manual intervention mode.
                    """
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
            applicant_credentials = self.format_dict("Applicant Credentials",context["applicant_credentials"])
            context_str = f"You are to log into the following website : {site} on behalf of the applicant, and you the applicant's credentials can be looked up from the following"+applicant_credentials
        elif phase == 'application':
            applicant_preferences = self.format_dict("Applicant preferences",context["applicant_preferences"])
            applicant_data = self.format_dict("Applicant data",context["applicant_data"])
            context_str = applicant_preferences + '\n' + applicant_data
        elif phase == 'search':
            applicant_preferences = self.format_dict("Applicant preferences",context["applicant_preferences"])
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
        
