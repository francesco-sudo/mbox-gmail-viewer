import base64
import re
from email.header import decode_header
from urllib.parse import unquote


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


def _is_attachment_part(part):
    if part.is_multipart():
        return False

    filename = part.get_filename()
    disposition = part.get_content_disposition()
    cid = part.get("Content-ID")

    if disposition == "attachment":
        return True
    if filename:
        return True
    if cid and part.get_content_maintype() == "image":
        return True
    return False


def extract_attachments(message):
    attachments = []

    for index, part in enumerate(message.walk()):
        if not _is_attachment_part(part):
            continue

        filename = part.get_filename()
        if filename:
            filename = decode_mime_header(filename)
        else:
            filename = f"attachment_{index}"

        payload = part.get_payload(decode=True) or b""
        cid = part.get("Content-ID")
        if cid:
            cid = cid.strip().strip("<>")

        disposition = part.get_content_disposition()
        attachments.append(
            {
                "id": index,
                "filename": filename,
                "mime": part.get_content_type() or "application/octet-stream",
                "size": len(payload),
                "inline": disposition == "inline" or bool(cid),
                "cid": cid,
            }
        )

    return attachments


def get_attachment(message, attachment_id):
    for index, part in enumerate(message.walk()):
        if index != attachment_id:
            continue
        if not _is_attachment_part(part):
            return None

        filename = part.get_filename()
        if filename:
            filename = decode_mime_header(filename)
        else:
            filename = f"attachment_{index}"

        payload = part.get_payload(decode=True) or b""

        return {
            "id": index,
            "filename": filename,
            "mime": part.get_content_type() or "application/octet-stream",
            "payload": payload,
            "size": len(payload),
        }

    return None


def cid_data_uri_map(message):
    result = {}

    for index, part in enumerate(message.walk()):
        if part.is_multipart():
            continue

        cid = part.get("Content-ID")
        if not cid:
            continue

        cid = cid.strip().strip("<>")
        mime = part.get_content_type()

        if not mime.startswith("image/"):
            continue

        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue

        encoded = base64.b64encode(payload).decode("ascii")
        result[cid] = f"data:{mime};base64,{encoded}"

    return result


def replace_cid_images(html, message):
    if not html:
        return html

    mapping = cid_data_uri_map(message)
    if not mapping:
        return html

    def repl(match):
        cid = unquote(match.group(1).strip().strip("<>"))
        return mapping.get(cid, match.group(0))

    return re.sub(r"cid:([^\"'\s>)]+)", repl, html, flags=re.IGNORECASE)
