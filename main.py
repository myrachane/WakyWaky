"""
main.py – WakyWaky Entry Point & Orchestrator
──────────────────────────────────────────────
Handles:
  • ASCII banner display
  • Startup status messages
  • Ollama health check
  • WhatsApp Web connection via Playwright
  • Incoming message detection
  • Sender name & message reading
  • SQLite storage (messages.db)
  • Context loading (last N messages)
  • Delegating AI generation to service.py
  • Terminal display of replies
  • Sending replies to WhatsApp
  • Per-contact log files
  • Error handling throughout
"""

from __future__ import annotations

import os
import sys
import sqlite3
import time
import logging
from datetime import datetime
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, Playwright

import config
import service


# ─────────────────────────────────────────
#  ANSI colour helpers
# ─────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    RED    = "\033[91m"
    DIM    = "\033[2m"
    MAGENTA= "\033[95m"


def _c(colour: str, text: str) -> str:
    return f"{colour}{text}{C.RESET}"


# ─────────────────────────────────────────
#  Banner
# ─────────────────────────────────────────

def display_banner() -> None:
    """Print the ASCII art banner from assets/banner.txt."""
    banner_path = Path(config.BANNER_FILE)
    if banner_path.exists():
        print(_c(C.CYAN, banner_path.read_text()))
    else:
        print(_c(C.CYAN + C.BOLD, "\n  ★  WakyWaky – WhatsApp AI Assistant  ★\n"))


# ─────────────────────────────────────────
#  Startup status printer
# ─────────────────────────────────────────

def _info(msg: str) -> None:
    print(f"{C.DIM}[INFO]{C.RESET} {msg}")

def _ok(msg: str) -> None:
    print(f"{C.GREEN}[ OK ]{C.RESET} {msg}")

def _err(msg: str) -> None:
    print(f"{C.RED}[ERR!]{C.RESET} {msg}")

def _section(tag: str, colour: str = C.YELLOW) -> None:
    print(f"\n{colour}[{tag}]{C.RESET}", end=" ")

def _line(text: str) -> None:
    print(text)


# ─────────────────────────────────────────
#  Ollama health checks
# ─────────────────────────────────────────

def check_ollama() -> None:
    """Verify Ollama is reachable and the configured model is available."""
    _info("Checking Ollama...")
    base_url = config.OLLAMA_URL.rsplit("/api/", 1)[0]

    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        _err(f"Ollama not reachable: {exc}")
        sys.exit(1)

    _ok("Ollama online")
    _info("Checking model...")

    models: list[dict] = resp.json().get("models", [])
    available = [m.get("name", "") for m in models]
    if not any(config.MODEL_NAME in name for name in available):
        _err(
            f"Model '{config.MODEL_NAME}' not found. "
            f"Run: ollama pull {config.MODEL_NAME}"
        )
        sys.exit(1)

    _ok(f"{config.MODEL_NAME} available")


# ─────────────────────────────────────────
#  Database
# ─────────────────────────────────────────

def init_db() -> sqlite3.Connection:
    """Create (or open) the SQLite database and ensure the messages table exists."""
    db_path = Path(config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_name TEXT    NOT NULL,
            sender    TEXT    NOT NULL,
            message   TEXT    NOT NULL,
            timestamp TEXT    NOT NULL
        )
    """)
    conn.commit()
    return conn


def save_message(
    conn: sqlite3.Connection,
    chat_name: str,
    sender: str,
    message: str,
) -> None:
    """Persist a single message (incoming or outgoing) to the database."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO messages (chat_name, sender, message, timestamp) VALUES (?, ?, ?, ?)",
        (chat_name, sender, message, ts),
    )
    conn.commit()


def load_context(
    conn: sqlite3.Connection,
    chat_name: str,
    limit: int = config.CONTEXT_MESSAGES,
) -> list[dict]:
    """
    Return the last ``limit`` messages for *chat_name*, ordered oldest→newest.
    Each row is a dict with keys: sender, message, timestamp.
    """
    cur = conn.execute(
        """
        SELECT sender, message, timestamp
        FROM   messages
        WHERE  chat_name = ?
        ORDER  BY id DESC
        LIMIT  ?
        """,
        (chat_name, limit),
    )
    rows = cur.fetchall()
    # rows are newest-first; reverse so history is oldest-first
    return [dict(row) for row in reversed(rows)]


# ─────────────────────────────────────────
#  Per-contact logging
# ─────────────────────────────────────────

def _get_contact_logger(contact: str) -> logging.Logger:
    """
    Return a Logger that writes to logs/<contact>/<YYYY-MM-DD>.log.
    A new file is created automatically each day.
    """
    log_name = f"wakywaky.{contact}"
    logger = logging.getLogger(log_name)

    if logger.handlers:          # already configured
        return logger

    logger.setLevel(logging.DEBUG)

    log_dir = Path(config.LOGS_DIR) / contact
    log_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"{date_str}.log"

    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(fh)

    return logger


def log_exchange(contact: str, sender: str, message: str) -> None:
    """Append one line to the contact's daily log file."""
    logger = _get_contact_logger(contact)
    logger.info("%s: %s", sender, message)


# ─────────────────────────────────────────
#  WhatsApp Web – Playwright helpers
# ─────────────────────────────────────────

def launch_browser(pw: Playwright) -> tuple[Browser, BrowserContext, Page]:
    """
    Launch Chromium with a persistent profile so WhatsApp session is reused.
    On first run the user must scan the QR code; subsequent runs reconnect
    automatically.
    """
    profile_dir = str(Path(config.BROWSER_PROFILE_DIR).resolve())

    context: BrowserContext = pw.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        args=["--no-sandbox", "--disable-setuid-sandbox"],
        viewport={"width": 1280, "height": 900},
    )

    page: Page = context.pages[0] if context.pages else context.new_page()
    return context, page  # type: ignore[return-value]


def connect_whatsapp(page: Page) -> None:
    """
    Navigate to WhatsApp Web and wait until the chat list is visible.
    If this is a fresh session the user will see (and must scan) the QR code.
    """
    _info("Connecting to WhatsApp...")
    page.goto(config.WHATSAPP_URL, wait_until="domcontentloaded")

    # Wait up to 90 s for either the QR canvas or the chat-list side panel
    try:
        page.wait_for_selector(
            'canvas[aria-label="Scan me!"], div[aria-label="Chat list"]',
            timeout=90_000,
        )
    except Exception:
        _err("WhatsApp Web did not load in time.")
        sys.exit(1)

    # If the QR code is shown, wait for the user to scan it (up to 5 min)
    if page.query_selector('canvas[aria-label="Scan me!"]'):
        print(_c(C.YELLOW, "\n  ▶  Please scan the QR code in the browser window…\n"))
        page.wait_for_selector('div[aria-label="Chat list"]', timeout=300_000)

    _ok("Connected")


def get_open_chat_name(page: Page) -> str | None:
    """Return the display name of the currently open chat, or None."""
    try:
        header = page.query_selector('header span[dir="auto"]')
        if header:
            return header.inner_text().strip() or None
    except Exception:
        pass
    return None


def get_last_incoming_message(page: Page) -> tuple[str, str] | None:
    """
    Scan the open chat for the most recent message NOT sent by us.

    Returns (sender_name, message_text) or None if none found.

    WhatsApp Web DOM note:
      • Outgoing messages:  .message-out
      • Incoming messages:  .message-in
    The sender name inside a group is in  span[aria-label] inside .message-in.
    For 1-to-1 chats we fall back to the chat header name.
    """
    try:
        # All incoming message bubbles
        incoming = page.query_selector_all("div.message-in")
        if not incoming:
            return None

        last = incoming[-1]

        # Message text
        text_el = last.query_selector("span.selectable-text")
        if not text_el:
            return None
        text = text_el.inner_text().strip()
        if not text:
            return None

        # Sender – try group author first, then fall back to header
        author_el = last.query_selector("span[aria-label][class*='copyable-text']")
        if author_el:
            author = author_el.inner_text().strip()
        else:
            author = get_open_chat_name(page) or "Unknown"

        return author, text

    except Exception:
        return None


def send_whatsapp_message(page: Page, text: str) -> bool:
    """
    Type and send *text* in the currently open WhatsApp chat.
    Returns True on success, False on failure.
    """
    try:
        box = page.query_selector('div[contenteditable="true"][data-tab="10"]')
        if not box:
            return False
        box.click()
        # Use clipboard paste to handle emoji / special chars safely
        page.evaluate(
            """(text) => {
                navigator.clipboard.writeText(text);
            }""",
            text,
        )
        box.press("Control+v")
        time.sleep(0.3)
        box.press("Enter")
        return True
    except Exception as exc:
        _err(f"Failed to send message: {exc}")
        return False


# ─────────────────────────────────────────
#  Terminal display helpers (runtime)
# ─────────────────────────────────────────

def print_incoming(author: str, text: str, ts: str) -> None:
    print(f"\n{C.CYAN}[MSG]{C.RESET}")
    print(f"  {C.BOLD}{author}{C.RESET} ({ts})")
    print(f"  {text}")


def print_context(count: int) -> None:
    print(f"{C.DIM}[CTX]{C.RESET}  Loaded {count} previous messages")


def print_generating() -> None:
    print(f"{C.YELLOW}[AI]{C.RESET}   Generating response…")


def print_reply(reply: str, ts: str) -> None:
    print(f"{C.GREEN}[REPLY]{C.RESET}")
    print(f"  {C.BOLD}Me{C.RESET} ({ts})")
    print(f"  {reply}")


def print_log_saved() -> None:
    print(f"{C.DIM}[LOG]{C.RESET}  Conversation saved")


def print_error(msg: str) -> None:
    print(f"{C.RED}[ERR!]{C.RESET} {msg}")


# ─────────────────────────────────────────
#  Auto-send prompt
# ─────────────────────────────────────────

def confirm_send(reply: str) -> bool:
    """
    When AUTO_SEND is False, show the draft and ask Y/N.
    Returns True if the user confirms.
    """
    print(f"\n{C.MAGENTA}[DRAFT]{C.RESET}")
    print(f"  {reply}")
    while True:
        choice = input(f"\n  {C.BOLD}Send? [Y/N]{C.RESET} ").strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False


# ─────────────────────────────────────────
#  Message monitor loop
# ─────────────────────────────────────────

def monitor_messages(page: Page, conn: sqlite3.Connection) -> None:
    """
    Poll the open WhatsApp chat for new incoming messages and orchestrate
    the full pipeline:
      1. Detect new message
      2. Save to DB
      3. Load context
      4. Generate AI reply via service.py
      5. Optionally confirm send
      6. Save reply to DB
      7. Send reply to WhatsApp
      8. Write log
    """
    _info("Starting message monitor…\n")

    last_seen_text: str = ""       # simple dedup: track last processed text
    last_seen_author: str = ""

    while True:
        try:
            result = get_last_incoming_message(page)

            if result is None:
                time.sleep(config.POLL_INTERVAL)
                continue

            author, text = result

            # Skip if we've already processed this exact message
            if text == last_seen_text and author == last_seen_author:
                time.sleep(config.POLL_INTERVAL)
                continue

            last_seen_text = text
            last_seen_author = author

            now = datetime.now()
            ts = now.strftime("%H:%M:%S")
            chat_name = get_open_chat_name(page) or author

            # ── 1. Display incoming ──────────────────────────────
            print_incoming(author, text, ts)

            # ── 2. Save incoming message ─────────────────────────
            save_message(conn, chat_name, author, text)
            log_exchange(chat_name, author, text)

            # ── 3. Load context ──────────────────────────────────
            history = load_context(conn, chat_name, config.CONTEXT_MESSAGES)
            print_context(len(history))

            # ── 4. Generate reply ────────────────────────────────
            print_generating()
            try:
                reply = service.generate_reply(author, text, history)
            except Exception as exc:
                print_error(f"AI generation failed: {exc}")
                time.sleep(config.POLL_INTERVAL)
                continue

            reply_ts = datetime.now().strftime("%H:%M:%S")
            print_reply(reply, reply_ts)

            # ── 5. Auto-send or confirm ──────────────────────────
            should_send: bool
            if config.AUTO_SEND:
                should_send = True
            else:
                should_send = confirm_send(reply)

            if should_send:
                # ── 6. Save reply to DB ──────────────────────────
                save_message(conn, chat_name, "AI", reply)
                log_exchange(chat_name, "AI", reply)

                # ── 7. Send to WhatsApp ──────────────────────────
                sent = send_whatsapp_message(page, reply)
                if not sent:
                    print_error("Could not send message – check browser window.")
                else:
                    print_log_saved()
            else:
                print(f"{C.DIM}  [skipped]{C.RESET}")

        except KeyboardInterrupt:
            print(f"\n{C.YELLOW}[INFO]{C.RESET} Shutting down WakyWaky. Bye!\n")
            sys.exit(0)
        except Exception as exc:
            print_error(f"Monitor loop error: {exc}")

        time.sleep(config.POLL_INTERVAL)


# ─────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────

def main() -> None:
    # ── Banner ────────────────────────────────────────────────────
    display_banner()

    # ── Startup sequence ──────────────────────────────────────────
    _info("Starting WakyWaky…")

    # ── Ollama checks ─────────────────────────────────────────────
    check_ollama()

    # ── Database ──────────────────────────────────────────────────
    conn = init_db()

    # ── WhatsApp Web ──────────────────────────────────────────────
    with sync_playwright() as pw:
        context, page = launch_browser(pw)
        try:
            connect_whatsapp(page)
            monitor_messages(page, conn)
        finally:
            context.close()
            conn.close()


if __name__ == "__main__":
    main()
