#!/usr/bin/env python3
"""
agent.py — Ikirōne RAG Agent (fixed FAISS save/load signature)
"""

import os
import requests
import openai
import msal
import faiss

from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

from langchain.schema import Document
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter

# ─── CONFIG ───────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
STORE_DIR  = BASE_DIR / "faiss_store"
DATA_DIR.mkdir(exist_ok=True)
STORE_DIR.mkdir(exist_ok=True)

# Load .env
load_dotenv(BASE_DIR / ".env")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
IKIRONE_API_KEY  = os.getenv("IKIRONE_API_KEY")
MS_CLIENT_ID     = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_TENANT_ID     = os.getenv("MS_TENANT_ID")
GRAPH_USER_UPN   = os.getenv("GRAPH_USER_UPN")

# Ensure all required variables are present
missing = [
    k for k in (
        "OPENAI_API_KEY","IKIRONE_API_KEY",
        "MS_CLIENT_ID","MS_CLIENT_SECRET",
        "MS_TENANT_ID","GRAPH_USER_UPN"
    ) if not os.getenv(k)
]
if missing:
    raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

openai.api_key = OPENAI_API_KEY

# ─── FASTAPI SETUP ────────────────────────────────────────────────

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

# ─── MS GRAPH HELPERS ─────────────────────────────────────────────

def get_graph_token() -> str:
    client = msal.ConfidentialClientApplication(
        MS_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{MS_TENANT_ID}",
        client_credential=MS_CLIENT_SECRET
    )
    scopes = ["https://graph.microsoft.com/.default"]
    result = client.acquire_token_silent(scopes, account=None)
    if not result:
        result = client.acquire_token_for_client(scopes)
    if "access_token" in result:
        return result["access_token"]
    err  = result.get("error", "unknown_error")
    desc = result.get("error_description", "")
    raise RuntimeError(f"MSAL token error: {err} – {desc}")

def fetch_emails(token: str, top: int = 20) -> List[Dict[str, Any]]:
    url = (
        f"https://graph.microsoft.com/v1.0/users/{GRAPH_USER_UPN}"
        "/mailFolders/Inbox/messages"
        f"?$top={top}&$select=subject,bodyPreview,body"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json().get("value", [])

def fetch_onedrive_items(token: str, top: int = 20) -> List[Dict[str, Any]]:
    url = (
        f"https://graph.microsoft.com/v1.0/users/{GRAPH_USER_UPN}"
        "/drive/root/children"
        f"?$top={top}"
        "&$select=id,name,folder,file,@microsoft.graph.downloadUrl"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json().get("value", [])

def download_onedrive_text(item: Dict[str, Any], token: str) -> str:
    dl = item.get("@microsoft.graph.downloadUrl")
    if dl:
        r = requests.get(dl); r.raise_for_status(); return r.text
    url = (
        f"https://graph.microsoft.com/v1.0/users/{GRAPH_USER_UPN}"
        f"/drive/items/{item['id']}/content"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status(); return r.text

# ─── INDEX BUILDING / LOADING ─────────────────────────────────────

def build_or_load_index() -> FAISS:
    # Token-based splitter (~1 000 tokens/chunk)
    embedder = OpenAIEmbeddings()
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=1000, chunk_overlap=200
    )

    # If we’ve already saved to STORE_DIR, just load it
    if (STORE_DIR / "index").exists():
        vs = FAISS.load_local(str(STORE_DIR), embedder)  # no meta arg :contentReference[oaicite:5]{index=5}
    else:
        token = get_graph_token()
        raw_docs: List[Document] = []

        # Ingest emails
        for m in fetch_emails(token):
            txt = m["body"].get("content", m["bodyPreview"])
            raw_docs.append(Document(
                page_content=txt,
                metadata={"source":"email","subject":m["subject"]}
            ))

        # Ingest OneDrive files, skip folders
        for itm in fetch_onedrive_items(token):
            if "file" not in itm:
                continue
            txt = download_onedrive_text(itm, token)
            raw_docs.append(Document(
                page_content=txt,
                metadata={"source":"onedrive","name":itm["name"]}
            ))

        # Split into token-bounded chunks :contentReference[oaicite:6]{index=6}
        texts     = [d.page_content for d in raw_docs]
        metadatas = [d.metadata     for d in raw_docs]
        chunked   = splitter.create_documents(texts, metadatas)

        # Batch‐embed to avoid total‐tokens cap
        vs = None
        batch_size = 200
        for i in range(0, len(chunked), batch_size):
            batch = chunked[i : i + batch_size]
            if vs is None:
                vs = FAISS.from_documents(batch, embedder)
            else:
                vs.add_documents(batch)

        # Save WITHOUT the old `meta` arg :contentReference[oaicite:7]{index=7}
        vs.save_local(str(STORE_DIR))

    # GPU-accelerate the index
    cpu_ix = vs.index
    res    = faiss.StandardGpuResources()
    vs.index = faiss.index_cpu_to_gpu(res, 0, cpu_ix)  # GPU offload :contentReference[oaicite:8]{index=8}

    return vs

vectordb = build_or_load_index()

# ─── RAG + CHATGPT ───────────────────────────────────────────────

def run_rag(query: str) -> str:
    retriever = vectordb.as_retriever(search_kwargs={"k": 5})
    docs = retriever.get_relevant_documents(query)
    context = "\n\n---\n\n".join(
        f"[{d.metadata['source'].upper()}] "
        f"{d.metadata.get('subject', d.metadata.get('name'))}:\n"
        f"{d.page_content[:500]}"
        for d in docs
    )
    system = (
        "You are Ikirōne, a sharp, pragmatic agent. "
        "Answer based on the context; if unsure, say so.\n\n" + context
    )
    resp = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=[
            {"role":"system","content":system},
            {"role":"user",  "content":query}
        ],
        temperature=0.2,
        max_tokens=512
    )
    return resp.choices[0].message.content

# ─── ENDPOINTS ───────────────────────────────────────────────────

@app.post("/chat")
async def chat(req: ChatRequest, x_api_key: str = Header(...)):
    if x_api_key != IKIRONE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return {"response": run_rag(req.message)}

@app.get("/health")
async def health():
    return {"status":"ok"}

# ─── RUNNER ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent:app", host="0.0.0.0", port=8000)
