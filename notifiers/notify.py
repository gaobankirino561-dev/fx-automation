import os, json, urllib.request, urllib.parse, traceback


def _post_json(url, payload, timeout=10):
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode()
    except Exception as e:  # noqa: BLE001 - log and continue
        print(f"[notify] post_json failed: {e}")
        return None


def notify_discord(event, detail):
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        print("[notify] DISCORD_WEBHOOK_URL not set; skip")
        return False
    content = (
        f"[{event}] {detail.get('pair')} {detail.get('side', '-')} "
        f"price={detail.get('price', '-')} pnl_jpy={detail.get('pnl_jpy', '-')}\n"
        f"reason: {detail.get('reason', '-')}"
    )
    resp = _post_json(url, {"content": content})
    return resp is not None


def notify_line(event, detail):
    token = os.getenv("LINE_NOTIFY_TOKEN")
    if not token:
        print("[notify] LINE_NOTIFY_TOKEN not set; skip")
        return False
    msg = (
        f"[{event}] {detail.get('pair')} {detail.get('side', '-')} "
        f"price={detail.get('price', '-')} pnl_jpy={detail.get('pnl_jpy', '-')}\n"
        f"reason: {detail.get('reason', '-')}"
    )
    data = urllib.parse.urlencode({"message": msg}).encode("utf-8")
    try:
        req = urllib.request.Request(
            "https://notify-api.line.me/api/notify",
            data=data,
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        return True
    except Exception as e:  # noqa: BLE001 - log and continue
        print(f"[notify] LINE failed: {e}")
        return False


def notify(event, detail):
    ok1 = notify_discord(event, detail)
    ok2 = notify_line(event, detail)
    print(f"[notify] discord={ok1}, line={ok2}")

