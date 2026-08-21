import os
import json
from services.llm_service import call_llm

def load_prompt(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    # Fallback to path relative to workspace root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fallback_path = os.path.join(base_dir, file_path)
    with open(fallback_path, 'r', encoding='utf-8') as file:
        return file.read()

def extract_intent(user_input):
    prompt_template = load_prompt("prompts/intent_prompt.txt")
    system_prompt = f"{prompt_template}\n\nUser Input: {user_input}"
    
    # Call your LLM (ensure it returns valid JSON)
    response = call_llm(system_prompt, expect_json=True)
    
    try:
        intent_data = json.loads(response)
        return intent_data
    except json.JSONDecodeError:
        print("Error: Intent parser failed to return valid JSON.")
        return None