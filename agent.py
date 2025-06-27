#!/usr/bin/env python3
"""
agent.py — Ikirōne Agent (Hybrid Model with Batched Indexing)
"""

import os
import requests
import msal
import json
import urllib.parse
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# LangChain Imports
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

# --- CONFIG & HELPERS (Same as before) ---
BASE_DIR = Path(__file__).parent
STORE_DIR = BASE_DIR / "faiss_store"
load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
IKIRONE_API_KEY = os.getenv("IKIRONE_API_KEY")
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_TENANT_ID = os.getenv("MS_TENANT_ID")
GRAPH_USER_UPN = os.getenv("GRAPH_USER_UPN")

graph_token_cache = {"token": None, "expires_at": 0}

def get_graph_token() -> str:
    # ... (function content is the same)
    now = datetime.now(timezone.utc).timestamp()
    if graph_token_cache["token"] and graph_token_cache["expires_at"] > now:
        return graph_token_cache["token"]
    auth_client = msal.ConfidentialClientApplication(
        MS_CLIENT_ID, authority=f"https://login.microsoftonline.com/{MS_TENANT_ID}",
        client_credential=MS_CLIENT_SECRET
    )
    result = auth_client.acquire_token_for_client(["https://graph.microsoft.com/.default"])
    if "access_token" in result:
        graph_token_cache["token"] = result["access_token"]
        graph_token_cache["expires_at"] = now + result.get("expires_in", 3600) - 60
        return result["access_token"]
    raise RuntimeError(f"MSAL token error: {result.get('error')}")

# --- AGENT TOOLS ---
# ... (get_current_time and search_recent_emails tools are the same)
@tool
def get_current_time() -> str:
    """Returns the current date and time in ISO 8601 format."""
    print("--- Calling Tool: get_current_time() ---")
    return datetime.now().isoformat()

@tool
def search_recent_emails(top: int = 10) -> List[Dict[str, Any]]:
    """
    Fetches the absolute most recent emails (up to 10).
    Useful for questions like "what just arrived?".
    """
    print(f"--- Calling Tool: search_recent_emails(top={top}) ---")
    token = get_graph_token()
    url = f"https://graph.microsoft.com/v1.0/users/{GRAPH_USER_UPN}/mailFolders/Inbox/messages"
    params = {
        "$select": "id,subject,bodyPreview,from,receivedDateTime,webLink",
        "$top": min(top, 10),
        "$orderby": "receivedDateTime desc"
    }
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
    r.raise_for_status()
    return r.json().get("value", [])

# ... (query_local_index tool is the same)
class LocalIndexSearchInput(BaseModel):
    query: str = Field(..., description="The user's question for semantic search against the local email index.")

@tool(args_schema=LocalIndexSearchInput)
def query_local_index(query: str) -> str:
    """
    Performs a deep, semantic search over a large historical index of emails.
    """
    print(f"--- Calling Tool: query_local_index(query='{query}') ---")
    if not STORE_DIR.exists() or not any(STORE_DIR.iterdir()):
        return "The local email index has not been built yet. Please ask the user for permission to build it."
    embedder = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    vector_store = FAISS.load_local(str(STORE_DIR), embedder, allow_dangerous_deserialization=True)
    retriever = vector_store.as_retriever(search_kwargs={"k": 20})
    docs = retriever.invoke(query)
    context = "\n\n---\n\n".join(
        f"FROM: {d.metadata.get('sender', 'N/A')}\nSUBJECT: {d.metadata.get('subject', 'N/A')}\n"
        f"DATE: {d.metadata.get('date', 'N/A')}\nPREVIEW: {d.page_content[:300]}"
        for d in docs
    )
    return f"Found {len(docs)} relevant documents in the local index. Summary:\n{context}"

# ** THE FIX IS HERE: build_local_email_index now processes in batches **
@tool
def build_local_email_index() -> str:
    """
    Performs a one-time, deep ingestion of the last 500 emails to build a local, searchable index.
    This process can take a few minutes. Should only be run once, or when a full refresh is needed.
    """
    print("--- Calling Tool: build_local_email_index() ---")
    if STORE_DIR.exists():
        shutil.rmtree(STORE_DIR)
    STORE_DIR.mkdir(exist_ok=True)
    
    token = get_graph_token()
    url = f"https://graph.microsoft.com/v1.0/users/{GRAPH_USER_UPN}/mailFolders/Inbox/messages"
    params = {"$select": "subject,body,from,receivedDateTime", "$top": 500, "$orderby": "receivedDateTime desc"}
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
    r.raise_for_status()
    emails = r.json().get("value", [])
    
    if not emails:
        return "Could not find any emails to index."

    docs = []
    for email in emails:
        docs.append(Document(
            page_content=email.get('body', {}).get('content', ''),
            metadata={
                "sender": email.get('from', {}).get('emailAddress', {}).get('name', 'Unknown'),
                "subject": email.get('subject', 'No Subject'),
                "date": email.get('receivedDateTime', '')
            }
        ))
    
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    
    embedder = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    
    # Process in batches to avoid API token limits
    batch_size = 200 # A safe number of documents per batch
    vector_store = None
    
    print(f"Embedding {len(splits)} document chunks in batches of {batch_size}...")
    for i in range(0, len(splits), batch_size):
        batch = splits[i:i + batch_size]
        if vector_store is None:
            # Create the store with the first batch
            vector_store = FAISS.from_documents(batch, embedder)
        else:
            # Add subsequent batches to the existing store
            vector_store.add_documents(batch)
        print(f"  ...processed batch {i//batch_size + 1}")

    vector_store.save_local(str(STORE_DIR))
    
    return f"Successfully built the local index with {len(emails)} emails ({len(splits)} chunks). It is now ready to be queried."

tools = [get_current_time, search_recent_emails, query_local_index, build_local_email_index]

# --- AGENT SETUP and FastAPI App (Same as before) ---
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Ikirōne... (Your full custom prompt here).

    **Core Directives & Tools:**
    You have two distinct ways of accessing email information. You must choose the correct one based on the user's need.

    1.  **For DEEP ANALYSIS & SUMMARIES (`query_local_index`):**
        * **Use Case:** When the user asks a broad, analytical, or historical question.
        * **Action:** Use the `query_local_index` tool.
        * **If the index doesn't exist:** The tool will inform you. You must then ask the user for permission to build it using `build_local_email_index`, warning them it may take a few minutes.

    2.  **For REAL-TIME & FRESHNESS (`search_recent_emails`):**
        * **Use Case:** When the user asks about something that just happened.
        * **Action:** Use the `search_recent_emails` tool.

    3.  **Time Awareness (`get_current_time`):** Use this to understand temporal queries.
    """),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

llm = ChatOpenAI(model=OPENAI_MODEL, openai_api_key=OPENAI_API_KEY)
agent = create_openai_tools_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
chat_history: List[BaseMessage] = []

app = FastAPI(title="Ikirōne Agent")
class ChatRequest(BaseModel): message: str

@app.post("/chat")
async def chat(req: ChatRequest, x_api_key: str = Header(None)):
    global chat_history
    if x_api_key != IKIRONE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    response = await agent_executor.ainvoke({
        "input": req.message, "chat_history": chat_history
    })
    chat_history.append(HumanMessage(content=req.message))
    chat_history.append(response["output"])
    chat_history = chat_history[-10:] 
    return {"response": response["output"]}

@app.get("/")
async def read_index(): return FileResponse(BASE_DIR / 'static' / 'index.html')
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent:app", host="0.0.0.0", port=8000, reload=True)
