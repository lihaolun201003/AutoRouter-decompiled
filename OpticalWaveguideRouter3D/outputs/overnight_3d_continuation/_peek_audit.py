
import json,sys
p=r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\outputs\3d_strategy_v4\512_full_layout\audit'
cls=json.load(open(p+r'\classification_summary.json',encoding='utf-8'))
print('CLASSIFICATION SUMMARY:'); print(json.dumps(cls,ensure_ascii=False)[:3000])
led=json.load(open(p+r'\audit_ledger.json',encoding='utf-8')); print('LEDGER:',json.dumps(led,ensure_ascii=False)[:1500])
sa=json.load(open(p+r'\side_audit.json',encoding='utf-8'))
print('side_audit type',type(sa).__name__, (list(sa.keys())[:10] if isinstance(sa,dict) else len(sa)))
if isinstance(sa,dict):
    for k in list(sa.keys())[:5]: print(k,'->',json.dumps(sa[k],ensure_ascii=False)[:600])
else:
    print(json.dumps(sa[0],ensure_ascii=False)[:900])
tl=json.load(open(p+r'\target_list.json',encoding='utf-8'))
print('target_list type',type(tl).__name__, list(tl.keys())[:10] if isinstance(tl,dict) else len(tl))
print(json.dumps(tl,ensure_ascii=False)[:800])
