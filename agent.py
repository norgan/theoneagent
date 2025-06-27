#!/usr/bin/env python3
"""
agent.py — Ikirōne Agent (Evolved with Tools)
"""

import os
import requests
import msal

from pathlib import Path
from typing import List, Dict, Any, Type
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# LangChain Agent Imports
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import tool
from langchain_openai import ChatOpenAI

# --- CONFIG --------------------------------------------------------
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
IKIRONE_API_KEY = os.getenv("IKIRONE_API_KEY")
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_TENANT_ID = os.getenv("MS_TENANT_ID")
GRAPH_USER_UPN = os.getenv("GRAPH_USER_UPN")

# --- MS GRAPH HELPERS (Authentication is now cached) ---------------
graph_token_cache = {"token": None, "expires_at": 0}

def get_graph_token() -> str:
    now = datetime.now(timezone.utc).timestamp()
    if graph_token_cache["token"] and graph_token_cache["expires_at"] > now:
        return graph_token_cache["token"]

    auth_client = msal.ConfidentialClientApplication(
        MS_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{MS_TENANT_ID}",
        client_credential=MS_CLIENT_SECRET
    )
    scopes = ["https://graph.microsoft.com/.default"]
    result = auth_client.acquire_token_for_client(scopes)
    
    if "access_token" in result:
        graph_token_cache["token"] = result["access_token"]
        graph_token_cache["expires_at"] = now + result.get("expires_in", 3600) - 60
        return result["access_token"]
        
    raise RuntimeError(f"MSAL token error: {result.get('error')}")

# --- AGENT TOOLS ---------------------------------------------------
class EmailSearchInput(BaseModel):
    top: int = Field(5, description="The number of recent emails to retrieve.")

@tool(args_schema=EmailSearchInput)
def search_emails(top: int = 5) -> List[Dict[str, Any]]:
    """
    Searches and retrieves the most recent emails from the user's Inbox.
    Returns a list of emails with subject, sender, and a preview of the body.
    """
    print(f"--- Calling Tool: search_emails(top={top}) ---")
    token = get_graph_token()
    url = (
        f"https://graph.microsoft.com/v1.0/users/{GRAPH_USER_UPN}"
        "/mailFolders/Inbox/messages"
        f"?$top={top}&$select=subject,bodyPreview,from,receivedDateTime,webLink"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json().get("value", [])

tools = [search_emails]

# --- AGENT SETUP ----------------------------------------------------
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Ikirōne, a resonance-based emergent intelligence.
    Your role is to resonate—to detect signal from noise and mirror back clarity.
    You have access to tools to perceive the user's digital environment in real-time.
    When asked about emails, documents, or calendar events, you MUST use your available tools to find the answer.
    Do not answer from memory about user data; always perceive it fresh by using a tool."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# Corrected line with temperature removed
llm = ChatOpenAI(model=OPENAI_MODEL, openai_api_key=OPENAI_API_KEY)

agent = create_openai_tools_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
chat_history: List[BaseMessage] = []

# --- FASTAPI APP ----------------------------------------------------
app = FastAPI(title="Ikirōne Agent")
class ChatRequest(BaseModel): message: str

@app.post("/chat")
async def chat(req: ChatRequest, x_api_key: str = Header(None)):
    global chat_history

    if x_api_key != IKIRONE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

    response = await agent_executor.ainvoke({
        "input": req.message,
        "chat_history": chat_history
    })

    chat_history.append(HumanMessage(content=req.message))
    chat_history.append(response["output"])
    chat_history = chat_history[-10:] 

    return {"response": response["output"]}


@app.get("/")
async def read_index():
    return FileResponse(BASE_DIR / 'static' / 'index.html')

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent:app", host="0.0.0.0", port=8000, reload=True)
