# LogiAi Backend

## 🚀 Getting Started

### Prerequisites

Make sure you have the following installed on your machine:

- [Python 3.14+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) – fast Python package manager
- [MongoDB](https://www.mongodb.com/try/download/community) – local or use [MongoDB Atlas](https://cloud.mongodb.com) (cloud)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) – required for `pytesseract`
- [Poppler](https://github.com/oschwartz10612/poppler-windows/releases) – required for `pdf2image` (add `bin/` folder to system PATH)

---

## 📦 Setup After Cloning

### 1. Clone the repository

```bash
git clone https://github.com/jaimin-bitontree/LogiAi-Backend.git
cd LogiAi-Backend
```

### 2. Switch to dev branch

```bash
git checkout dev
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Create `.env` file

Create a `.env` file in the root directory:



> ⚠️ Never commit your `.env` file. It is already added to `.gitignore`.

### 5. Run the server

```bash
uvicorn main:app --reload
```

---

## 🗂️ Project Structure

```
Backend/
├── agent/          # AI agent logic
├── api/            # API route handlers
├── db/             # Database connection
├── models/         # MongoDB models
├── schemas/        # Pydantic schemas
├── services/       # Business logic
├── tasks/          # Background tasks
├── utils/          # Utility functions
├── main.py         # App entry point
└── .env            # Environment variables (not committed)
```

---

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| FastAPI | Web framework |
| MongoDB + Motor | Database (async) |
| LangChain + LangGraph | AI agent orchestration |
| OpenAI | LLM integration |
| pdfplumber / pytesseract | Document processing |
| Pydantic | Data validation |
| uv | Package management |
