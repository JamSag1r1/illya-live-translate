import json, time, os, re, urllib.request

ENV = os.environ.get("ENV_FILE")          # 指向一个含 DEEPSEEK_API_KEY=... 的文件
key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip() or None
if not key and ENV and os.path.isfile(ENV):
    for line in open(ENV, encoding="utf-8", errors="ignore"):
        m = re.match(r'\s*DEEPSEEK_API_KEY\s*=\s*(.+?)\s*$', line)
        if m:
            key = m.group(1).strip().strip('"').strip("'")
            break
assert key, "没找到 key：设环境变量 DEEPSEEK_API_KEY，或用 ENV_FILE=<含 key 的文件> 运行"

BASE = "https://api.deepseek.com"
SYS = "你是同声传译。把用户给的话翻成自然的口语中文，只输出译文，不要解释。"

def call(model, payload_extra, text, timeout=60):
    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": text}],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    body.update(payload_extra)
    req = urllib.request.Request(BASE + "/chat/completions",
        data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key,
                                                "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
    except Exception as e:
        return None, time.time() - t0, f"{type(e).__name__}: {e}"
    dt = time.time() - t0
    ch = d["choices"][0]["message"]
    return ch.get("content", ""), dt, ch.get("reasoning_content", "")[:60]

# list models
req = urllib.request.Request(BASE + "/models", headers={"Authorization": "Bearer " + key})
with urllib.request.urlopen(req, timeout=30) as r:
    ids = [m["id"] for m in json.loads(r.read())["data"]]
print("MODELS:", ids)

TXT = "So the key insight is that the radical carries the spin density, and the lanthanide provides the anisotropy."
for model in ids:
    for label, extra in [("default", {}), ("effort=low", {"reasoning_effort": "low"}),
                         ("thinking=disabled", {"thinking": {"type": "disabled"}})]:
        out, dt, dbg = call(model, extra, TXT)
        print(f"[{model}] {label}: {dt:.2f}s | out={out!r} | {dbg[:50]}")
