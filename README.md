# WakyWaky 

A terminal-based **WhatsApp Web AI auto-reply assistant** powered by [Ollama](https://ollama.ai) and [Playwright](https://playwright.dev/python/).

---

## Project Structure

```
WakyWaky/
├── main.py            ← orchestrator (everything except AI generation)
├── service.py         ← AI-only: prompt building + Ollama communication
├── config.py          ← all configuration constants
├── requirements.txt
├── README.md
├── assets/
│   └── banner.txt     ← ASCII art banner
├── logs/              ← per-contact daily log files (auto-created)
│   └── John/
│       └── 2026-06-05.log
└── database/
    └── messages.db    ← SQLite conversation history (auto-created)
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | `python --version` |
| [Ollama](https://ollama.ai) | Must be running locally |
| Chromium | Installed automatically by Playwright |
| WhatsApp account | For QR scan on first run |

---

## Setup

### 1. Clone / download the project

```bash
cd WakyWaky
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright's Chromium browser

```bash
playwright install chromium
```

### 5. Install and start Ollama

```bash
# Install Ollama from https://ollama.ai
# Then pull the model:
ollama pull llama3.2:3b

# Make sure Ollama is running:
ollama serve
```

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `MODEL_NAME` | `"llama3.2:3b"` | Ollama model to use |
| `OLLAMA_URL` | `"http://localhost:11434/api/generate"` | Ollama endpoint |
| `AUTO_SEND` | `False` | `True` → auto-send; `False` → ask Y/N |
| `CONTEXT_MESSAGES` | `10` | Messages loaded for AI context |
| `POLL_INTERVAL` | `2.0` | Seconds between message checks |
| `OLLAMA_TIMEOUT` | `60` | Request timeout in seconds |

---

## Running WakyWaky

```bash
python main.py
```

### First run (QR scan)

1. A Chromium window opens automatically.
2. WhatsApp Web shows the QR code.
3. Open WhatsApp on your phone → Linked Devices → Link a device → scan.
4. WakyWaky begins monitoring once connected.

### Subsequent runs

The browser profile is saved in `browser_profile/`. No QR scan needed.

---

## Runtime Terminal Output

```
[MSG]
  John (14:32:05)
  where u bro

[CTX]  Loaded 10 previous messages
[AI]   Generating response…

[REPLY]
  Me (14:32:07)
  outside rn gimme 10 mins

[LOG]  Conversation saved
```

### With `AUTO_SEND = False` (default)

```
[DRAFT]
  outside rn gimme 10 mins

  Send? [Y/N] y
[LOG]  Conversation saved
```

---

## Log Files

Logs are written to `logs/<ContactName>/<YYYY-MM-DD>.log`:

```
[14:32:05] John: where u bro
[14:32:07] AI: outside rn gimme 10 mins
```

---

## Database Schema

**File:** `database/messages.db`  
**Table:** `messages`

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `chat_name` | TEXT | Chat / contact name |
| `sender` | TEXT | Author or `"AI"` for replies |
| `message` | TEXT | Message body |
| `timestamp` | TEXT | `YYYY-MM-DD HH:MM:SS` |

---

## Architecture Notes

- **`main.py`** — owns everything: banner, startup, Ollama health check, Playwright browser, WhatsApp monitoring, database read/write, log writing, terminal UI, reply dispatch.
- **`service.py`** — pure AI layer: builds prompts, calls Ollama, returns a reply string. Zero WhatsApp, Playwright, DB, or logging code.
- **`config.py`** — single source of truth for all constants.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Ollama not reachable` | Run `ollama serve` in a separate terminal |
| `Model not found` | Run `ollama pull llama3.2:3b` |
| QR code not showing | Delete `browser_profile/` and rerun |
| Reply not sending | Check browser window; WhatsApp may have logged out |
| Blank message detected | WakyWaky skips empty texts automatically |

---

## Stopping

Press **Ctrl+C** in the terminal. WakyWaky exits cleanly.
