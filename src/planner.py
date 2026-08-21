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

def generate_plan(intent_data):
    """
    Reads planner_prompt.txt, passes the intent to call_llm(),
    and returns the actions array.
    """
    prompt_template = load_prompt("prompts/planner_prompt.txt")
    intent_json = json.dumps(intent_data, indent=4)
    system_prompt = f"{prompt_template}\n\nInput Intent:\n{intent_json}"
    
    response = call_llm(system_prompt, expect_json=True)
    
    try:
        plan_data = json.loads(response)
        return plan_data.get("actions", [])
    except json.JSONDecodeError:
        print("Error: Planner failed to return valid JSON.")
        return []
