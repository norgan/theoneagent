## Summary

This repository contains **Ikirōne**, a local Retrieval-Augmented Generation (RAG) chat agent built with FastAPI, LangChain, FAISS-GPU, and Microsoft Graph. It indexes your Office 365 emails and OneDrive files, bundles them into a GPU-accelerated FAISS index, and exposes a `/chat` endpoint for contextual LLM queries. A simple static React-style UI is served at `/` for interactive testing.

---

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Usage](#usage)
6. [Static UI](#static-ui)
7. [API Endpoints](#api-endpoints)
8. [Development](#development)
9. [Contributing](#contributing)
10. [License](#license)

---

## Features

* **Email & Document Ingestion** via Microsoft Graph (App-only flow) ([realpython.com][1])
* **Token-aware Chunking** using LangChain’s `RecursiveCharacterTextSplitter.from_tiktoken_encoder` ([thepythoncode.com][2])
* **GPU-accelerated Vector Index** with FAISS-GPU on your RTX 4080 ([docs.python-guide.org][3])
* **Retrieval-Augmented Chat** backed by OpenAI models (`gpt-4.1` by default) ([packaging.python.org][4])
* **Built-in Static UI** for local interactive testing (HTML/CSS/JS) ([github.com][5])

---

## Requirements

* **Hardware**: NVIDIA GPU (e.g. RTX 4080) with CUDA support for FAISS-GPU ([docs.python-guide.org][3])
* **OS**: Windows 11 (WSL Debian 12) or native Linux ([docs.python-guide.org][3])
* **Python** ≥ 3.11
* **Packages** (in `.venv` via `requirements.txt`):

  * fastapi, uvicorn, python-dotenv, openai, requests, msal
  * langchain, langchain-community, faiss-gpu-cu12
  * python-docx, pdfminer.six, tiktoken ([thepythoncode.com][2])

---

## Installation

1. **Clone** this repo:

   ````bash
   git clone https://github.com/norgan/ikirone-agent.git
   cd ikirone-agent
   ``` :contentReference[oaicite:8]{index=8}  
   ````
2. **Create & activate** a virtualenv:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install** dependencies:

   ````bash
   pip install -r requirements.txt
   ``` :contentReference[oaicite:9]{index=9}  
   ````

---

## Configuration

1. **Copy** `.env.example` to `.env` and fill in your secrets:

   ```dotenv
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4.1
   IKIRONE_API_KEY=your-agent-secret
   MS_CLIENT_ID=...
   MS_CLIENT_SECRET=...
   MS_TENANT_ID=...
   GRAPH_USER_UPN=norgan@norgan.net
   ```
2. **Ensure** no trailing spaces and Unix line endings. ([packaging.python.org][4])

---

## Usage

### Start the Agent

````bash
uvicorn agent:app --reload --host 0.0.0.0 --port 8000
``` :contentReference[oaicite:11]{index=11}  

### Health Check  
```bash
curl http://localhost:8000/health  
# {"status":"ok"}
````

### Chat via cURL

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your-agent-secret" \
  -d '{"message":"ping"}'
```

Expected response:

````json
{ "response": "Pong: ping" }
``` :contentReference[oaicite:12]{index=12}  

---

## Static UI  
A simple chat UI is served at the root (`/`). It supports:  
- **Text inputs**  
- **File & image uploads** via `/upload` (stubbed endpoint) :contentReference[oaicite:13]{index=13}  
- **Drag-and-drop** and multiple file selection  

Open your browser to [http://localhost:8000](http://localhost:8000).

---

## API Endpoints  
| Method | Path      | Description                                  |
|:-------|:----------|:---------------------------------------------|
| GET    | `/health` | Health check (returns `{"status":"ok"}`).    |
| POST   | `/chat`   | RAG chat; body `{"message": "..."}`.         |
| POST   | `/upload` | Upload files; header `X-API-KEY`; stubbed.   | :contentReference[oaicite:14]{index=14}  

---

## Development  
- **Code structure** follows the FastAPI example pattern:  
  - `agent.py` — main app  
  - `static/` — front-end assets :contentReference[oaicite:15]{index=15}  
  - `data/`, `faiss_store/` — persisted indexes & raw docs  
- **Project layout** inspired by The Hitchhiker’s Guide to Python :contentReference[oaicite:16]{index=16}.  
- **Testing**: use pytest to write unit tests under `tests/`.  

---

## Contributing  
1. **Fork** the repo and create a branch (`git checkout -b feat-xyz`).  
2. **Commit** your changes (`git commit -m "Add feature xyz"`).  
3. **Push** and open a Pull Request.  
4. **Review** will be done via GitHub’s PR UI.  

See [Contributing Guide](CONTRIBUTING.md) for details. :contentReference[oaicite:17]{index=17}  

---

## License  
This project is licensed under the MIT License. See [LICENSE](LICENSE) for details. :contentReference[oaicite:18]{index=18}  

---

**References & Further Reading**  
- Best practices for Python READMEs: Real Python :contentReference[oaicite:19]{index=19}  
- FastAPI official README example :contentReference[oaicite:20]{index=20}  
- Structuring Python projects: Hitchhiker’s Guide :contentReference[oaicite:21]{index=21}  
- Awesome README collection :contentReference[oaicite:22]{index=22}  
- LangChain text splitting docs :contentReference[oaicite:23]{index=23}  
::contentReference[oaicite:24]{index=24}
````

[1]: https://realpython.com/readme-python-project/?utm_source=chatgpt.com "Creating Great README Files for Your Python Projects"
[2]: https://thepythoncode.com/article/build-rag-chatbot-fastapi-openai-streamlit?utm_source=chatgpt.com "Building a Full-Stack RAG Chatbot with FastAPI, OpenAI, and Streamlit"
[3]: https://docs.python-guide.org/writing/structure/?utm_source=chatgpt.com "Structuring Your Project — The Hitchhiker's Guide to Python"
[4]: https://packaging.python.org/en/latest/guides/making-a-pypi-friendly-readme/?utm_source=chatgpt.com "Making a PyPI-friendly README - Python Packaging User Guide"
[5]: https://github.com/fastapi/fastapi/blob/master/README.md?utm_source=chatgpt.com "fastapi/README.md at master - GitHub"
