from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict
from .parser import parse_config

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


class ParseRequest(BaseModel):
    content: str


@app.post("/parse")
async def parse_config_content(request: ParseRequest):
    """
    Parse a custom INI-like configuration format.
    
    This format supports:
    - Key-value pairs: key = value
    - Line continuation: indented lines continue the previous value
    - Special keys starting with /
    - Empty values
    """
    try:
        parsed = parse_config(request.content)
        return parsed
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")


@app.get("/format-info")
async def get_format_info():
    """
    Get information about the supported format.
    """
    return {
        "format": "Custom INI-like format without sections",
        "features": [
            "Key-value pairs: key = value",
            "Line continuation: indented lines continue the previous value",
            "Special keys starting with /",
            "Empty values supported"
        ],
        "example": {
            "content": "/title = My Title\n    with continuation\nkey = value",
            "parsed": {
                "/title": "My Title with continuation",
                "key": "value"
            }
        }
    }
