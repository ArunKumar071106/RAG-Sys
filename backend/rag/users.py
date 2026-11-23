"""Who is chatting: the name and phone number asked before the first question.

* A visitor gives a name and a mobile number; the chat page keeps the returned token and sends it
  with every question (header X-Arivazhai-User). With LOGIN_REQUIRED=true (the default) /api/chat
  answers only with a valid token.
* Every visitor is one row of DATA_DIR/admin/users.xlsx (Excel): name, phone, first and last visit,
  visits, questions asked. The folder is not served by the website: only the admin downloads it,
  through the admin panel (Bearer ADMIN_TOKEN).
* The token is signed with a secret kept in DATA_DIR/admin/secret.key, so it cannot be made up.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

COLUMNS = ["Name", "Phone", "First visit", "Last visit", "Visits", "Questions asked", "User ID"]


class InvalidUser(ValueError):
    pass


def clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "")).strip()
    # letters of any script, with their vowel signs (Tamil included), and spaces, dots, apostrophes or hyphens
    letters = sum(unicodedata.category(ch).startswith("L") for ch in name)
    allowed = all(unicodedata.category(ch)[0] in "LM" or ch in " .'-" for ch in name)
    if not 2 <= len(name) <= 60 or letters < 2 or not allowed or not unicodedata.category(name[0]).startswith("L"):
        raise InvalidUser("Please enter your name (letters only).")
    return name


def clean_phone(phone: str) -> str:
    """An Indian mobile number as 10 digits: +91 / 0 prefixes, spaces and dashes allowed."""
    digits = re.sub(r"[\s()-]", "", phone or "")
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise InvalidUser("Please enter a valid 10-digit mobile number.")
    return digits


def _now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


class UserStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.path = self.folder / "users.xlsx"
        self._lock = threading.Lock()
        self._secret: bytes | None = None

    # ------------------------------------------------------------ tokens
    @property
    def secret(self) -> bytes:
        if self._secret is None:
            key = self.folder / "secret.key"
            self.folder.mkdir(parents=True, exist_ok=True)
            if not key.exists():
                key.write_text(secrets.token_hex(32), encoding="utf-8")
            self._secret = key.read_text(encoding="utf-8").strip().encode()
        return self._secret

    def user_id(self, phone: str) -> str:
        return hmac.new(self.secret, b"user:" + phone.encode(), hashlib.sha256).hexdigest()[:16]

    def token_for(self, user_id: str) -> str:
        return user_id + "." + hmac.new(self.secret, b"token:" + user_id.encode(), hashlib.sha256).hexdigest()[:32]

    def verify(self, token: str) -> str | None:
        """The user id in a token this server issued, or None."""
        user_id, _, _sig = (token or "").partition(".")
        if not user_id or not re.fullmatch(r"[0-9a-f]{16}", user_id):
            return None
        return user_id if hmac.compare_digest(self.token_for(user_id), token) else None

    # ------------------------------------------------------------ the Excel file
    def _open(self):
        from openpyxl import Workbook, load_workbook
        from openpyxl.styles import Font

        if self.path.exists():
            book = load_workbook(self.path)
            return book, book.active
        book = Workbook()
        sheet = book.active
        sheet.title = "Users"
        sheet.append(COLUMNS)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column, width in zip("ABCDEFG", (24, 14, 18, 18, 8, 16, 18)):
            sheet.column_dimensions[column].width = width
        sheet.freeze_panes = "A2"
        return book, sheet

    def _save(self, book) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp.xlsx")
        book.save(tmp)
        tmp.replace(self.path)  # never a half-written file, even if the server stops mid-save

    @staticmethod
    def _row_of(sheet, user_id: str):
        for row in sheet.iter_rows(min_row=2):
            if row[6].value == user_id:
                return row
        return None

    def register(self, name: str, phone: str) -> dict:
        """Add the visitor (or update their name and visit) and return {user_id, token, name}."""
        name, phone = clean_name(name), clean_phone(phone)
        user_id = self.user_id(phone)
        with self._lock:
            book, sheet = self._open()
            row = self._row_of(sheet, user_id)
            if row is None:
                sheet.append([name, phone, _now(), _now(), 1, 0, user_id])
            else:
                row[0].value, row[3].value, row[4].value = name, _now(), int(row[4].value or 0) + 1
            self._save(book)
        return {"user_id": user_id, "token": self.token_for(user_id), "name": name}

    def asked(self, user_id: str) -> None:
        """One more question by this visitor (best effort: an open Excel file must not stop an answer)."""
        try:
            with self._lock:
                book, sheet = self._open()
                row = self._row_of(sheet, user_id)
                if row is None:
                    return
                row[5].value, row[3].value = int(row[5].value or 0) + 1, _now()
                self._save(book)
        except Exception as exc:
            log.warning("Could not update users.xlsx: %s", exc)

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self._lock:
            _, sheet = self._open()
            return max(0, sheet.max_row - 1)
