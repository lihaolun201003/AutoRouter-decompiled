# -*- coding: utf-8 -*-
import sys, os, hashlib, time, fitz
p = sys.argv[1]
st = os.stat(p)
print("path      :", p)
print("size      :", st.st_size)
print("mtime     :", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)))
print("sha256    :", hashlib.sha256(open(p, "rb").read()).hexdigest())
d = fitz.open(p)
print("page_count:", d.page_count)
d.close()
