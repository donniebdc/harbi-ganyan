# -*- coding: utf-8 -*-
"""KARSILASTIRMALI ANALIZ — yeniden uretilen toplu tahmin vs CSV sonuclari vs Pegadrom akis.
Girdi: parse-edilebilir toplu tahmin dosyasi (KO:/5SATIR:/ATNO: formati).
Kullanim: python karsilastirmali_analiz.py [dosya.txt]   (varsayilan: en yeni v5_tahmin_*.txt)
Cikti: ekran + karsilastirmali_rapor.txt
"""
import sys, io, os, re, glob, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE="D:/Ganyan Gemini"
CSV_DIRS=[os.path.join(BASE,"CSV Sonuçlar/NİSAN"),os.path.join(BASE,"CSV Sonuçlar/MAYIS")]
RAPOR=os.path.join(BASE,"karsilastirmali_rapor.txt")
HIP_NORM={"İSTANBUL":"ISTANBUL","ISTANBUL":"ISTANBUL","İZMİR":"IZMIR","IZMIR":"IZMIR","BURSA":"BURSA","ADANA":"ADANA","ANTALYA":"ANTALYA","ELAZIĞ":"ELAZIG","ELAZIG":"ELAZIG","ŞANLIURFA":"SANLIURFA","SANLIURFA":"SANLIURFA","ANKARA":"ANKARA","KOCAELİ":"KOCAELI","KOCAELI":"KOCAELI","DİYARBAKIR":"DIYARBAKIR","DIYARBAKIR":"DIYARBAKIR","BALIKESİR":"BALIKESIR","BALIKESIR":"BALIKESIR","MUŞ":"MUS","MUS":"MUS"}
def norm_hip(s): return HIP_NORM.get(s.strip().upper(),s.strip().upper())
def norm_name(s):
    s=s.upper().strip(); s=re.sub(r'\s+(KG|DB|SK|K|G|D|B|S|AP|KD|SG)+$','',s); return s.strip()
def names_match(a,b):
    a,b=norm_name(a),norm_name(b)
    return bool(a) and bool(b) and (a==b or a.startswith(b) or b.startswith(a))
def derece_to_sec(d):
    m=re.match(r"(\d+):(\d+)\.(\d+)",d.strip())
    return int(m.group(1))*60+int(m.group(2))+float("0."+m.group(3)) if m else None

def parse_csv(dirpath):
    res={}
    if not os.path.isdir(dirpath): return res
    for fn in os.listdir(dirpath):
        if not fn.endswith(".csv"): continue
        m=re.match(r"(\d{2})\.(\d{2})\.(\d{4})-(.+?)-",fn)
        if not m: continue
        g,a,y,hip=m.groups(); tarih=f"{y}-{a}-{g}"; hn=norm_hip(hip)
        with open(os.path.join(dirpath,fn),encoding="utf-8-sig",errors="replace") as f: c=f.read()
        parts=re.split(r"\n(\d+)\. Kosu\s*:",c); i=1
        while i<len(parts):
            kno=int(parts[i]); blk=parts[i+1] if i+1<len(parts) else ""; i+=2
            am=re.search(r"At No;At İsmi;",blk)
            if not am: continue
            lines=blk[am.start():].strip().split("\n"); horses=[]
            for ln in lines[1:]:
                p=ln.strip().split(";")
                if len(p)<14: break
                try: int(p[0])
                except: break
                sec=derece_to_sec(p[12].strip())
                horses.append((p[1].strip(),sec))
            kosanlar=[h for h in horses if h[1] is not None]
            if not kosanlar: continue
            kosanlar.sort(key=lambda h:h[1])
            sira={norm_name(nm):pos for pos,(nm,_) in enumerate(kosanlar,1)}
            res[(tarih,hn,kno)]={"sira":sira,"wname":kosanlar[0][0],"nat":len(horses)}
    return res

def parse_bulk(path):
    """KO:/5SATIR:/ATNO: -> {(tarih_iso,hip,kno):{slots:{}, ats:[...]}}"""
    res={}
    with open(path,encoding="utf-8",errors="replace") as f: c=f.read()
    for blk in re.split(r"(?=^KO:\d+\|)",c,flags=re.MULTILINE):
        if not blk.startswith("KO:"): continue
        L=blk.strip().split("\n")
        km=re.match(r"KO:(\d+)\|(.+?)\|(\d{2})\.(\d{2})\.(\d{4})\|",L[0])
        if not km: continue
        kno=int(km.group(1)); hip=norm_hip(km.group(2)); tarih=f"{km.group(5)}-{km.group(4)}-{km.group(3)}"
        slots={}; ats=[]
        for ln in L[1:]:
            if ln.startswith("5SATIR:"):
                for part in ln[7:].split("|"):
                    if "=" in part:
                        sl,nm=part.split("=",1); slots[sl.strip()]=nm.strip()
            elif ln.startswith("ATNO:"):
                d={}; name=""
                for p in ln.split("|"):
                    if ":" not in p: continue
                    k,v=p.split(":",1); k=k.strip(); v=v.strip()
                    if k=="AT": name=v
                    else:
                        try: d[k]=float(v)
                        except: d[k]=v
                if name: d["NAME"]=name; ats.append(d)
        res[(tarih,hip,kno)]={"slots":slots,"ats":ats}
    return res

def main():
    args=[a for a in sys.argv[1:]]
    if args: path=args[0]
    else:
        cands=sorted(glob.glob(os.path.join(BASE,"Toplu Tahminler","v5_tahmin_*.txt")), key=os.path.getmtime)
        if not cands: print("Toplu tahmin dosyasi yok (v5_tahmin_*.txt)."); return
        path=cands[-1]
    print(f"Tahmin dosyasi: {os.path.basename(path)}")
    csv_data={}
    for d in CSV_DIRS: csv_data.update(parse_csv(d))
    bulk=parse_bulk(path)
    print(f"Tahmin kosusu: {len(bulk)}  |  CSV kosusu: {len(csv_data)}")

    SLOTS=["FAV","SUR","YAZ","BOM","HAR"]
    SLOTAD={"FAV":"Favori","SUR":"Sürpriz Olmaz","YAZ":"Yazılabilir","BOM":"Bomba","HAR":"Harbi mi?"}
    segs={"TUM":lambda n:True,"<=9":lambda n:n<=9,"10-13":lambda n:10<=n<=13,"14+":lambda n:n>=14}
    st={s:{"kosu":0,"bes_isabet":0,"ilk1":0,"ilk3":0,"ilk4":0,
           "slot":{sl:0 for sl in SLOTS},
           "har_evren":0,"har_yakalar":0,
           "w_flow_top5":0,"w_flow_yok":0} for s in segs}
    eslesmeyen=0
    iska=[]  # 5 satirda olmayan kazananlar
    for key,b in bulk.items():
        if key not in csv_data: eslesmeyen+=1; continue
        c=csv_data[key]; sira=c["sira"]; wname=c["wname"]; n=c["nat"]
        slots=b["slots"]; ats=b["ats"]
        # ana sirali (ATNO zaten ana desc geliyor ama garanti)
        srt=sorted(ats,key=lambda x:-x.get("ANA",0)) if ats else []
        # ana ilk1/3/4
        def winpos_in(names_list):
            return any(names_match(nm,wname) for nm in names_list)
        ana_names=[a["NAME"] for a in srt]
        # 5 satir picks (slot sirasiyla)
        picks=[(sl,slots.get(sl,"-")) for sl in SLOTS]
        # flow rank pos
        flow=[a for a in ats if isinstance(a.get("AKIS"),float) and a["AKIS"]>0]
        flow.sort(key=lambda x:x["AKIS"])
        wflow=None
        for i,a in enumerate(flow,1):
            if names_match(a["NAME"],wname): wflow=i; break
        for s,f in segs.items():
            if not f(n): continue
            S=st[s]; S["kosu"]+=1
            if ana_names[:1] and winpos_in(ana_names[:1]): S["ilk1"]+=1
            if winpos_in(ana_names[:3]): S["ilk3"]+=1
            if winpos_in(ana_names[:4]): S["ilk4"]+=1
            # 5 satir
            kazanan_slot=None
            for sl,nm in picks:
                if nm!="-" and names_match(nm,wname):
                    kazanan_slot=sl; break
            if kazanan_slot:
                S["bes_isabet"]+=1; S["slot"][kazanan_slot]+=1
            # HAR evreni: kazanan ana top4 disinda
            if not winpos_in(ana_names[:4]):
                S["har_evren"]+=1
                if wflow is None: S["w_flow_yok"]+=1
                elif wflow<=5: S["w_flow_top5"]+=1
                harnm=slots.get("HAR","-")
                if harnm!="-" and names_match(harnm,wname): S["har_yakalar"]+=1
                elif s=="TUM": iska.append((key,wname,n,wflow))

    OUT=[]
    def yaz(x=""): OUT.append(x); print(x)
    yaz("="*80)
    yaz("KARSILASTIRMALI ANALIZ — yeniden uretim (yeni HAR) vs CSV vs Pegadrom akis")
    yaz("="*80)
    yaz(f"Tahmin dosyasi : {os.path.basename(path)}")
    yaz(f"Eslesen kosu   : {st['TUM']['kosu']}   (CSV karsiligi olmayan: {eslesmeyen})")
    for s in ["TUM","<=9","10-13","14+"]:
        S=st[s]; k=S["kosu"]
        if not k: continue
        yaz("")
        yaz(f"### {s}  (kosu={k})")
        yaz(f"  Ana Ilk1(Favori)  : {S['ilk1']:>4}  %{100*S['ilk1']/k:.1f}")
        yaz(f"  Ana Ilk3          : {S['ilk3']:>4}  %{100*S['ilk3']/k:.1f}")
        yaz(f"  Ana Ilk4          : {S['ilk4']:>4}  %{100*S['ilk4']/k:.1f}")
        yaz(f"  5 SATIR ISABET    : {S['bes_isabet']:>4}  %{100*S['bes_isabet']/k:.1f}")
        yaz(f"  Hangi satir kazandirdi:")
        for sl in SLOTS:
            h=S["slot"][sl]
            yaz(f"     {SLOTAD[sl]:<14}: {h:>3}  (%{100*h/k:.1f})")
        hu=S["har_evren"]
        if hu:
            yaz(f"  HAR evreni (kazanan ana-top4 disi): {hu}")
            yaz(f"     -> YENI HAR yakalar : {S['har_yakalar']}/{hu} = %{100*S['har_yakalar']/hu:.0f}")
            yaz(f"     -> kazanan akis ilk5: {S['w_flow_top5']}/{hu} = %{100*S['w_flow_top5']/hu:.0f}  (akis yok: {S['w_flow_yok']})")
    # iska profili
    yaz("")
    yaz("="*80)
    yaz(f"5 SATIRDA YAKALANAMAYAN KAZANANLAR: {len(iska)}")
    yaz("="*80)
    fd=collections.Counter()
    seg=collections.Counter()
    for key,w,n,wf in iska:
        seg["<=9" if n<=9 else "10-13" if n<=13 else "14+"]+=1
        if wf is None: fd["akis_yok"]+=1
        elif wf<=5: fd["akis_1-5"]+=1
        elif wf<=8: fd["akis_6-8"]+=1
        else: fd["akis_9+"]+=1
    yaz(f"Saha dagilimi : {dict(seg)}")
    yaz(f"Akis rank dag.: {dict(fd)}")
    yaz("Ornekler:")
    for key,w,n,wf in iska[:30]:
        yaz(f"  {key[0]} {key[1]:<10} {key[2]:>2}.k ({n:>2} at)  kazanan={w:<22} akisRank={wf}")
    with open(RAPOR,"w",encoding="utf-8") as f: f.write("\n".join(OUT))
    print(f"\nRapor: {RAPOR}")

if __name__=="__main__":
    main()
