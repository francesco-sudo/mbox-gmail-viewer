import os
from io import BytesIO

import mailbox
from flask import (
    Flask,
    abort,
    jsonify,
    render_template,
    request,
    send_file,
    Response,
)

from services import attachment_service, html_sanitizer, mbox_service


SAFE_PREVIEW_MIMES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/pdf",
}

DANGEROUS_PREVIEW_MIMES = {
    "text/html",
    "application/xhtml+xml",
    "image/svg+xml",
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object("config.Config")

    if test_config:
        app.config.update(test_config)
        if "DATA_DIR" in test_config and "DATABASE_PATH" not in test_config:
            app.config["DATABASE_PATH"] = os.path.join(
                app.config["DATA_DIR"], "index.sqlite3"
            )

    try:
        os.makedirs(app.config["ARCHIVES_DIR"], exist_ok=True)
    except OSError:
        pass

    os.makedirs(app.config["DATA_DIR"], exist_ok=True)

    with app.app_context():
        mbox_service.init_db()

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: http: https:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "form-action 'none'; "
            "frame-src 'self'"
        )
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/archives")
    def api_archives():
        return jsonify({"archives": mbox_service.list_archives()})

    @app.post("/api/index/rebuild")
    def api_rebuild_index():
        data = request.get_json(silent=True) or {}
        archive = data.get("archive") or None
        try:
            result = mbox_service.rebuild_index(archive)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result)

    def _int_arg(name, default, min_value, max_value):
        try:
            value = int(request.args.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(min_value, min(max_value, value))

    @app.get("/api/messages")
    @app.get("/api/search")
    def api_messages():
        archive = request.args.get("archive") or None
        q = request.args.get("q", "")
        page = _int_arg("page", 1, 1, 10_000_000)
        per_page = _int_arg(
            "per_page",
            app.config["PAGE_SIZE_DEFAULT"],
            1,
            app.config["PAGE_SIZE_MAX"],
        )
        sort = request.args.get("sort", "date_desc")

        has_attachment = request.args.get("has_attachment") in ("1", "true", "yes")

        try:
            result = mbox_service.get_messages(
                archive=archive,
                q=q,
                page=page,
                per_page=per_page,
                sort=sort,
                from_addr=request.args.get("from"),
                to_addr=request.args.get("to"),
                subject=request.args.get("subject"),
                body=request.args.get("body"),
                after=request.args.get("after"),
                before=request.args.get("before"),
                has_attachment=has_attachment,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(result)

    @app.get("/api/messages/<int:msg_id>")
    def api_message_detail(msg_id):
        try:
            detail = mbox_service.get_message_detail(msg_id, allow_remote=False)
        except LookupError:
            abort(404)
        return jsonify(detail)

    @app.get("/api/messages/<int:msg_id>/body")
    def api_message_body(msg_id):
        mode = request.args.get("mode", "html")
        if mode not in ("html", "text"):
            return jsonify({"error": "mode non valido"}), 400

        allow_remote = request.args.get("allow_remote") in ("1", "true", "yes")

        try:
            body = mbox_service.get_body(msg_id, mode=mode, allow_remote=allow_remote)
        except LookupError:
            abort(404)

        if mode == "html":
            return Response(body, mimetype="text/html; charset=utf-8")
        return Response(body, mimetype="text/plain; charset=utf-8")

    @app.get("/api/messages/<int:msg_id>/attachments")
    def api_message_attachments(msg_id):
        try:
            detail = mbox_service.get_message_detail(msg_id, allow_remote=False)
        except LookupError:
            abort(404)
        return jsonify({"attachments": detail["attachments"]})

    @app.get("/api/messages/<int:msg_id>/attachments/<int:att_id>")
    def api_attachment_download(msg_id, att_id):
        row = mbox_service.get_message_row(msg_id)
        if not row:
            abort(404)

        try:
            path = mbox_service.safe_archive_path(row["archive"])
            box = mailbox.mbox(path, create=False)
            try:
                message = box.get_message(row["msg_index"])
                attachment = attachment_service.get_attachment(message, att_id)
            finally:
                box.close()
        except Exception:
            abort(404)

        if not attachment:
            abort(404)

        payload = attachment["payload"]
        if len(payload) > app.config["ATTACHMENT_MAX_BYTES"]:
            return jsonify({"error": "Allegato troppo grande"}), 413

        mime = attachment["mime"] or "application/octet-stream"
        download = request.args.get("download") in ("1", "true", "yes")
        previewable = mime in SAFE_PREVIEW_MIMES
        as_attachment = download or not previewable or mime in DANGEROUS_PREVIEW_MIMES

        return send_file(
            BytesIO(payload),
            mimetype=mime,
            as_attachment=as_attachment,
            download_name=attachment["filename"] or f"attachment_{att_id}",
        )

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Risorsa non trovata"}), 404
        return "Risorsa non trovata", 404

    @app.errorhandler(500)
    def internal_error(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Errore interno del server"}), 500
        return "Errore interno del server", 500

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=8080, debug=False)
