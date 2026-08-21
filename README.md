# Enterprise Conversational AI Agent

Production-style Enterprise Conversational AI Agent project for Text-to-SQL analysis on `AdventureWorks2022`.

## Project Structure

```text
enterprise-ai-agent/
├── backend/                  # FastAPI backend application
│   ├── app/                  # Application code
│   │   ├── api/             # API routers & endpoints
│   │   ├── core/            # App configuration & logging
│   │   ├── db/              # Database connections & execution
│   │   ├── llm/             # LLM client integrations (Ollama)
│   │   └── sales/           # Sales domain (schema, rules, text-to-sql)
│   ├── scripts/             # Utility scripts (schema extraction)
│   └── tests/               # Unit & integration tests
├── frontend/                 # React + TypeScript frontend
│   └── src/                 # UI components and API client
├── docker-compose.yml        # Docker compose configuration
├── .env.example              # Environment variables template
└── README.md                 # Project documentation
```

## Getting Started

### 1. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```
