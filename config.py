# ─────────────────────────────────────────
#  WakyWaky – Configuration
# ─────────────────────────────────────────

# Ollama settings
MODEL_NAME: str = "llama3.2:3b"
OLLAMA_URL: str = "http://localhost:11434/api/generate"

# Behaviour
AUTO_SEND: bool = False          # False → prompt user Y/N before sending
CONTEXT_MESSAGES: int = 10      # how many past messages to load as context

# Paths (relative to project root)
DB_PATH: str = "database/messages.db"
LOGS_DIR: str = "logs"
ASSETS_DIR: str = "assets"
BANNER_FILE: str = "assets/banner.txt"

# Playwright browser profile (persistent session)
BROWSER_PROFILE_DIR: str = "browser_profile"

# WhatsApp Web URL
WHATSAPP_URL: str = "https://web.whatsapp.com"

# Polling interval (seconds) between new-message checks
POLL_INTERVAL: float = 2.0

# Request timeout for Ollama (seconds)
OLLAMA_TIMEOUT: int = 60
