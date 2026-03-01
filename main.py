# main.py

import os
import sys
import traceback
from io import StringIO
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types

# --- App Setup ---
app = FastAPI()

# CORS: Allows browsers/testing tools to talk to your API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models (define request/response shapes) ---

class CodeRequest(BaseModel):
    code: str  # The Python code sent by the user

class CodeResponse(BaseModel):
    error: List[int]   # Line numbers with errors (empty if no error)
    result: str        # The actual output or traceback text

class ErrorAnalysis(BaseModel):
    error_lines: List[int]  # AI will fill this in

# --- Tool Function: Runs the code ---

def execute_python_code(code: str) -> dict:
    """
    Runs Python code using exec().
    Captures whatever it prints (stdout) or any crash message (traceback).
    Returns a dict with success=True/False and the output text.
    """
    # Temporarily replace the terminal output with a "fake" one we can read
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        exec(code, {})  # Run the code in a clean environment
        output = sys.stdout.getvalue()  # Grab whatever was printed
        return {"success": True, "output": output}

    except Exception:
        # If the code crashed, grab the full error message
        output = traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        # Always restore the real terminal output, no matter what
        sys.stdout = old_stdout

# --- AI Function: Analyzes the error ---

def analyze_error_with_ai(code: str, traceback_text: str) -> List[int]:
    from groq import Groq
    import json

    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    prompt = f"""Analyze this Python code and its error traceback.
Return ONLY a JSON object with the line numbers where the error occurred.
Format: {{"error_lines": [3]}}

CODE:
{code}

TRACEBACK:
{traceback_text}"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)
    return result.get("error_lines", [])
# --- The Main Endpoint ---

@app.post("/code-interpreter", response_model=CodeResponse)
def code_interpreter(request: CodeRequest):
    """
    1. Run the submitted code
    2. If it worked → return output with empty error list
    3. If it crashed → ask AI for the error line, return both
    """
    execution = execute_python_code(request.code)

    if execution["success"]:
        # Code ran fine — no AI needed
        return CodeResponse(error=[], result=execution["output"])
    else:
        # Code crashed — ask AI to find the broken line
        error_lines = analyze_error_with_ai(request.code, execution["output"])
        return CodeResponse(error=error_lines, result=execution["output"])