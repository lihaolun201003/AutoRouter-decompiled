# -*- coding: utf-8 -*-
"""Wait until the target PDF exists and its (size, mtime, sha256, page_count) are unchanged twice in a row."""
import sys, os, time, hashlib, json
p = sys.argv[1]
budget = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
GAP = 15.0
t0 = time.time()
last = None
history = []
while time.time() - t0 < budget:
    if os.path.exists(p):
        try:
            raw = open(p, "rb").read()
            h = hashlib.sha256(raw).hexdigest()
            st = os.stat(p)
            sig = (st.st_size, int(st.st_mtime), h)
        except Exception as e:
            sig = ("ERR", str(e))
    else:
        sig = ("MISSING",)
    hh = sig[2][:16] if len(sig) > 2 and isinstance(sig[2], str) else str(sig)
    history.append({"t": round(time.time() - t0, 1), "sig": str(sig[0]), "sha16": hh})
    print("t=%6.1fs  %s" % (time.time() - t0, json.dumps(history[-1], ensure_ascii=False)))
    if last is not None and sig == last and sig[0] != "MISSING":
        print("STABLE after %.1fs: size=%s sha256=%s" % (time.time() - t0, sig[0], sig[2]))
        sys.exit(0)
    last = sig
    time.sleep(GAP)
print("NOT STABLE within %.0fs" % budget)
sys.exit(2)
