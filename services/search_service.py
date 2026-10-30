import shlex
from datetime import datetime, time, timedelta


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"Data non valida: {value}. Usa il formato YYYY-MM-DD.")


def parse_query(q):
    parsed = {
        "from": None,
        "to": None,
        "subject": None,
        "after": None,
        "before": None,
        "has_attachment": False,
        "free": [],
    }

    if not q:
        return parsed

    try:
        tokens = shlex.split(q)
    except ValueError:
        tokens = q.split()

    for token in tokens:
        if ":" in token:
            key, value = token.split(":", 1)
            key = key.lower().strip()
            value = value.strip()

            if key == "from":
                parsed["from"] = value
                continue
            if key == "to":
                parsed["to"] = value
                continue
            if key == "subject":
                parsed["subject"] = value
                continue
            if key == "after":
                parsed["after"] = value
                continue
            if key == "before":
                parsed["before"] = value
                continue
            if key == "has" and value.lower() == "attachment":
                parsed["has_attachment"] = True
                continue

        if token.strip():
            parsed["free"].append(token.strip())

    return parsed


def build_where(
    archive=None,
    q="",
    from_addr=None,
    to_addr=None,
    subject=None,
    body=None,
    after=None,
    before=None,
    has_attachment=False,
):
    parsed = parse_query(q)

    from_addr = from_addr or parsed["from"]
    to_addr = to_addr or parsed["to"]
    subject = subject or parsed["subject"]
    after = after or parsed["after"]
    before = before or parsed["before"]
    has_attachment = bool(has_attachment or parsed["has_attachment"])

    clauses = []
    params = []

    if archive:
        clauses.append("archive = ?")
        params.append(archive)

    if from_addr:
        clauses.append("(from_addr LIKE ? OR from_name LIKE ?)")
        like = f"%{from_addr}%"
        params.extend([like, like])

    if to_addr:
        clauses.append("to_addrs LIKE ?")
        params.append(f"%{to_addr}%")

    if subject:
        clauses.append("subject LIKE ?")
        params.append(f"%{subject}%")

    if body:
        clauses.append("(body_text LIKE ? OR subject LIKE ?)")
        like = f"%{body}%"
        params.extend([like, like])

    if after:
        date_after = parse_date(after)
        ts_after = datetime.combine(date_after, time.min).timestamp()
        clauses.append("date_ts >= ?")
        params.append(int(ts_after))

    if before:
        date_before = parse_date(before)
        ts_before = datetime.combine(
            date_before + timedelta(days=1), time.min
        ).timestamp()
        clauses.append("date_ts < ?")
        params.append(int(ts_before))

    if has_attachment:
        clauses.append("has_attachments = 1")

    for term in parsed["free"]:
        like = f"%{term}%"
        clauses.append(
            "(subject LIKE ? OR body_text LIKE ? OR from_addr LIKE ? "
            "OR from_name LIKE ? OR to_addrs LIKE ?)"
        )
        params.extend([like, like, like, like, like])

    return clauses, params
