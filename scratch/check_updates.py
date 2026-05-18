import urllib.request
import urllib.error
import json

BOT_TOKEN = "8651526412:AAHUeHt9OXViecgi50ELgv8uOqk7bhF--ok"

def check_bot():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    results = {}
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode('utf-8'))
            results["getMe"] = res
    except Exception as e:
        results["getMe_error"] = str(e)

    url_updates = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        req = urllib.request.Request(url_updates)
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode('utf-8'))
            results["getUpdates"] = res
    except urllib.error.HTTPError as e:
        results["getUpdates_http_error"] = f"{e.code} {e.reason}"
        try:
            err_body = json.loads(e.read().decode('utf-8'))
            results["getUpdates_http_error_body"] = err_body
        except Exception:
            pass
    except Exception as e:
        results["getUpdates_error"] = str(e)

    with open("scratch/check_updates_output.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("Results written to scratch/check_updates_output.json")

if __name__ == '__main__':
    check_bot()
