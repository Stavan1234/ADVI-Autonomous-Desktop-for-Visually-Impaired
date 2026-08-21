import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def call_llm(prompt: str, expect_json: bool = True) -> str:
    """
    Calls the Gemini API and strictly returns the response text (typically a JSON string).
    
    Args:
        prompt: The text prompt (system prompt + user input context).
        expect_json: If True, forces the response to be a JSON string.
        
    Returns:
        A string containing the model's response.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set or is empty.")

    # Using gemini-3.6-flash since gemini-2.5-flash is no longer available
    model = "gemini-3.6-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    if expect_json:
        payload["generationConfig"] = {
            "responseMimeType": "application/json"
        }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Gemini API call failed with status code {response.status_code}: {response.text}")

    res_json = response.json()
    try:
        text_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
        return text_content.strip()
    except (KeyError, IndexError) as e:
        raise Exception(f"Failed to parse Gemini API response: {e}. Full response: {res_json}")
