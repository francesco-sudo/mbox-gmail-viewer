import html as html_module
import mailbox
import os
import re
import sqlite3
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime

from flask import current_app

from services import attachment_service, html_sanitizer


def get_db():
    db_path = current_app.config["DATABASE_PATH"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archive TEXT NOT NULL,
                msg_index INTEGER NOT NULL,
                message_id TEXT,
                subject TEXT,
                from_name TEXT,
                from_addr TEXT,
                to_addrs TEXT,
                cc_addrs TEXT,
                date_ts INTEGER,
                date_raw TEXT,
                has_attachments INTEGER NOT NULL DEFAULT 0,
                preview TEXT,
                body_text TEXT,
                UNIQUE(archive, msg_index)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_archive_date
                ON messages(archive, date_ts);

            CREATE INDEX IF NOT EXISTS idx_messages_from_addr
                ON messages(from_addr);

            CREATE INDEX IF NOT EXISTS idx_messages_subject
                ON messages(subject);

            CREATE INDEX IF NOT EXISTS idx_messages_has_attachments
                ON messages(has_attachments);
            """
        )
        conn.commit()
    finally:
        conn.close()


def decode_mime_header(value):
    if not value:
        return ""
    try:
        parts = decode_header(value)
        result = []
        for part, encoding in parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)
    except Exception:
        return str(value)


def strip_html(value):
    if not value:
        return ""
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html_module.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def extract_text_and_html(message):
    text_parts = []
    html_parts = []

    for part in message.walk():
        if part.is_multipart():
            continue

        if part.get_content_disposition() == "attachment":
            continue

        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        charset = part.get_content_charset() or "utf-8"
        try:
            content = payload.decode(charset, errors="replace")
        except LookupError:
            content = payload.decode("utf-8", errors="replace")

        if content_type == "text/plain":
            text_parts.append(content)
        else:
            html_parts.append(content)

    text = "\n\n".join(text_parts).strip()
    html = "\n\n".join(html_parts).strip()

    if not text and html:
        text = strip_html(html)

    return text, html


def message_has_attachments(message):
    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment":
            return True
        if part.get_filename():
            return True
        if part.get("Content-ID") and part.get_content_maintype() == "image":
            return True
    return False


def parse_date_header(raw_date):
    if not raw_date:
        return None, ""
    raw = decode_mime_header(raw_date)
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            return None, raw
        if dt.tzinfo is None:
            return int(dt.timestamp()), raw
        return int(dt.timestamp()), raw
    except Exception:
        return None, raw


def parse_message(message, archive, msg_index):
    subject = decode_mime_header(message.get("Subject", ""))
    from_raw = decode_mime_header(message.get("From", ""))
    from_name, from_addr = parseaddr(from_raw)
    to_addrs = decode_mime_header(message.get("To", ""))
    cc_addrs = decode_mime_header(message.get("Cc", ""))
    message_id = decode_mime_header(message.get("Message-ID", ""))
    date_ts, date_raw = parse_date_header(message.get("Date", ""))

    body_text, _body_html = extract_text_and_html(message)
    preview = re.sub(r"\s+", " ", body_text).strip()[:500]

    return {
        "archive": archive,
        "msg_index": msg_index,
        "message_id": message_id,
        "subject": subject,
        "from_name": from_name,
        "from_addr": from_addr,
        "to_addrs": to_addrs,
        "cc_addrs": cc_addrs,
        "date_ts": date_ts,
        "date_raw": date_raw,
        "has_attachments": 1 if message_has_attachments(message) else 0,
        "preview": preview,
        "body_text": body_text[:1_000_000],
    }


def list_archives():
    archives_dir = current_app.config["ARCHIVES_DIR"]
    if not os.path.isdir(archives_dir):
        return []

    counts = {}
    conn = get_db()
    try:
        for row in conn.execute(
            "SELECT archive, COUNT(*) AS count FROM messages GROUP BY archive"
        ):
            counts[row["archive"]] = row["count"]
    finally:
        conn.close()

    result = []
    for entry in os.scandir(archives_dir):
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue

        try:
            stat = entry.stat()
        except OSError:
            continue

        result.append(
            {
                "name": entry.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(
                    timespec="seconds"
                ),
                "messages": counts.get(entry.name, 0),
            }
        )

    result.sort(key=lambda item: item["name"].lower())
    return result


def safe_archive_path(name):
    if not name or os.path.basename(name) != name:
        raise ValueError("Nome archivio non valido")

    archives_dir = os.path.realpath(current_app.config["ARCHIVES_DIR"])
    path = os.path.realpath(os.path.join(archives_dir, name))

    if os.path.commonpath([archives_dir, path]) != archives_dir:
        raise ValueError("Percorso archivio non valido")

    if not os.path.isfile(path):
        raise ValueError("Archivio non trovato")

    return path


def rebuild_index(archive_name=None):
    if archive_name:
        safe_archive_path(archive_name)
        archive_names = [archive_name]
    else:
        archive_names = [item["name"] for item in list_archives()]

    result = {"archives": [], "messages": 0, "errors": []}

    for name in archive_names:
        path = safe_archive_path(name)
        count = 0

        try:
            box = mailbox.mbox(path, create=False)
        except Exception as exc:
            result["errors"].append(f"{name}: impossibile aprire l'archivio: {exc}")
            continue

        conn = get_db()
        try:
            conn.execute("DELETE FROM messages WHERE archive = ?", (name,))

            for key in box.iterkeys():
                try:
                    message = box.get_message(key)
                    data = parse_message(message, name, key)
                    conn.execute(
                        """
                        INSERT INTO messages (
                            archive, msg_index, message_id, subject,
                            from_name, from_addr, to_addrs, cc_addrs,
                            date_ts, date_raw, has_attachments, preview, body_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            data["archive"],
                            data["msg_index"],
                            data["message_id"],
                            data["subject"],
                            data["from_name"],
                            data["from_addr"],
                            data["to_addrs"],
                            data["cc_addrs"],
                            data["date_ts"],
                            data["date_raw"],
                            data["has_attachments"],
                            data["preview"],
                            data["body_text"],
                        ),
                    )
                    count += 1
                except Exception as exc:
                    result["errors"].append(f"{name}:{key}: {exc}")

            conn.commit()
        except Exception as exc:
            conn.rollback()
            result["errors"].append(f"{name}: errore indicizzazione: {exc}")
        finally:
            conn.close()
            box.close()

        result["archives"].append({"archive": name, "messages": count})
        result["messages"] += count

    return result


def get_messages(
    archive=None,
    q="",
    page=1,
    per_page=50,
    sort="date_desc",
    from_addr=None,
    to_addr=None,
    subject=None,
    body=None,
    after=None,
    before=None,
    has_attachment=False,
):
    from services.search_service import build_where

    clauses, params = build_where(
        archive=archive,
        q=q,
        from_addr=from_addr,
        to_addr=to_addr,
        subject=subject,
        body=body,
        after=after,
        before=before,
        has_attachment=has_attachment,
    )

    where_sql = ""
    if clauses:
        where_sql = " WHERE " + " AND ".join(clauses)

    order_map = {
        "date_desc": "date_ts DESC, id DESC",
        "date_asc": "date_ts ASC, id ASC",
        "subject_asc": "LOWER(subject) ASC, id ASC",
        "subject_desc": "LOWER(subject) DESC, id DESC",
        "from_asc": "LOWER(from_addr) ASC, id ASC",
    }
    order_sql = order_map.get(sort, order_map["date_desc"])

    conn = get_db()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) AS total FROM messages{where_sql}", params
        ).fetchone()["total"]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""
            SELECT id, archive, msg_index, subject, from_name, from_addr,
                   to_addrs, date_ts, date_raw, has_attachments, preview
            FROM messages
            {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

        messages = [dict(row) for row in rows]
        pages = (total + per_page - 1) // per_page if per_page else 0

        return {
            "messages": messages,
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
        }
    finally:
        conn.close()


def get_message_row(msg_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def load_message(row):
    path = safe_archive_path(row["archive"])
    box = mailbox.mbox(path, create=False)
    try:
        return box.get_message(row["msg_index"])
    finally:
        box.close()


def get_message_detail(msg_id, allow_remote=False):
    row = get_message_row(msg_id)
    if not row:
        raise LookupError("Messaggio non trovato")

    message = load_message(row)
    text, html = extract_text_and_html(message)

    if html:
        html = attachment_service.replace_cid_images(html, message)
        html = html_sanitizer.sanitize_html(
            html, allow_remote_images=allow_remote
        )

    attachments = attachment_service.extract_attachments(message)

    headers = {}
    for key, value in message.items():
        headers[decode_mime_header(key)] = decode_mime_header(value)

    return {
        "id": row["id"],
        "archive": row["archive"],
        "msg_index": row["msg_index"],
        "subject": row["subject"] or "(senza oggetto)",
        "from_name": row["from_name"],
        "from_addr": row["from_addr"],
        "to_addrs": row["to_addrs"],
        "cc_addrs": row["cc_addrs"],
        "date_ts": row["date_ts"],
        "date_raw": row["date_raw"],
        "has_attachments": bool(row["has_attachments"]),
        "body_text": text,
        "body_html": html,
        "attachments": attachments,
        "headers": headers,
    }


def get_body(msg_id, mode="html", allow_remote=False):
    detail = get_message_detail(msg_id, allow_remote=allow_remote)
    if mode == "text":
        return detail["body_text"] or ""
    return detail["body_html"] or ""
