import requests
import glob
import os
import re
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
# Algoritmik modüller 'motor' alt klasöründe.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "motor"))
from pegadrom_ai_features import load_ai_txt_root
from pegadrom_ai_txt_topla import DEFAULT_DELAY, DEFAULT_OUT, collect_range
from altili_uretim import altili_ayaklari, hipodrom_altili_bloku, analiz_dosyalari_yaz
from altili_lib import ekuri_gruplari, ekuri_serialize
from tahmin_sonuc_karsilastir import uret_aralik as tahmin_sonuc_uret

TURKIYE_HIPODROMS = {
    "ANKARA","İSTANBUL","ISTANBUL","İZMİR","IZMIR","BURSA","ADANA",
    "ELAZIĞ","ELAZIG","DİYARBAKIR","DIYARBAKIR","KOCAELİ","KOCAELI",
    "ŞANLIURFA","SANLIURFA","BALIKESİR","BALIKESIR","ANTALYA",
}
SEHIR_URL_MAP = {
    "ANKARA":"ANKARA","ISTANBUL":"ISTANBUL","İSTANBUL":"ISTANBUL",
    "IZMIR":"IZMIR","İZMİR":"IZMIR","BURSA":"BURSA","ADANA":"ADANA",
    "ELAZIG":"ELAZIG","ELAZIĞ":"ELAZIG","DIYARBAKIR":"DIYARBAKIR",
    "DİYARBAKIR":"DIYARBAKIR","KOCAELI":"KOCAELI","KOCAELİ":"KOCAELI",
    "SANLIURFA":"SANLIURFA","ŞANLIURFA":"SANLIURFA",
    "BALIKESIR":"BALIKESIR","BALIKESİR":"BALIKESIR","ANTALYA":"ANTALYA",
}

def normalize_sehir(ad):
    if not ad: return ""
    return ad.upper().translate(str.maketrans("ğüşıöçĞÜŞİÖÇİ","gusiocGUSIOCI")).strip()
def is_turkiye_hipodrom(s):
    return normalize_sehir(s) in {normalize_sehir(h) for h in TURKIYE_HIPODROMS}
def sehir_to_url(s):
    return SEHIR_URL_MAP.get(normalize_sehir(s), normalize_sehir(s))

def normalize_jokey(jok):
    """Jokey adını CSV ve API arasında eşleşecek şekilde normalize et.
    'M.A.AKGÖBEK AP' → 'M.A.AKGÖBEK' (apprentice eki temizlenir)."""
    if not jok: return ""
    j = jok.upper().strip()
    # Sondaki yamak/apprentice eklerini temizle
    for ek in [" AP", " (AP)", " YMK", " Y."]:
        if j.endswith(ek):
            j = j[:-len(ek)].strip()
    return j


class TopluTahminV5:
    """Yeni mimari (v5) ile toplu tahmin — backtest için parse-edilebilir çıktı."""
    def __init__(self, data_path="."):
        self.data_path=data_path
        self.jockey_global={}
        self.jockey_city={}
        self.sire_stats={}
        self.rapor=[]
        self.pegadrom_data=self.load_pegadrom()
        self.peg_ai_data=load_ai_txt_root(os.path.join(self.data_path,DEFAULT_OUT))

    def load_pegadrom(self):
        for fp in [os.path.join(os.path.dirname(os.path.abspath(__file__)),"motor","pegadrom_skorlar.json"),
                   os.path.join(self.data_path,"pegadrom_skorlar.json"), "pegadrom_skorlar.json"]:
            try:
                if os.path.exists(fp):
                    with open(fp, encoding="utf-8") as f:
                        return json.load(f)
            except Exception:
                pass
        return {}

    def pegadrom_galop_row(self, tarih_iso, sehir, kosu_no, at_no):
        key=f"{tarih_iso}|{sehir_to_url(sehir)}|{kosu_no}"
        race=self.pegadrom_data.get(key) or {}
        return (race.get("galop") or {}).get(str(at_no)) or {}

    def pegadrom_galop_skoru(self, tarih_iso, sehir, kosu_no, at_no):
        return float(self.pegadrom_galop_row(tarih_iso, sehir, kosu_no, at_no).get("skor") or 0)

    def pegadrom_ai_ozellikleri(self, tarih_iso, sehir, kosu_no, at_no):
        key=f"{tarih_iso}|{sehir_to_url(sehir)}|{kosu_no}"
        return (self.peg_ai_data.get(key) or {}).get(int(at_no), {})

    def pegadrom_ai_txt_guncelle(self, bas_dt, bit_dt):
        out_dir = Path(self.data_path) / DEFAULT_OUT
        print(f"Pegadrom AI TXT toplanıyor: {bas_dt:%d.%m.%Y} - {bit_dt:%d.%m.%Y}")
        collect_range(bas_dt, bit_dt, out_dir, DEFAULT_DELAY, force=False)
        self.peg_ai_data = load_ai_txt_root(str(out_dir))
        print(f"Pegadrom AI TXT yüklendi: {len(self.peg_ai_data)} koşu")

    def cel(self, t):
        if not t: return ""
        return str(t).upper().translate(str.maketrans("ĞÜŞİÖÇI","GUSIOCI")).lower()

    def norm(self, atlar, kriter):
        vals=[a.get(kriter,0) for a in atlar]
        mn,mx=min(vals),max(vals)
        if mx==mn: return {a['key']:100.0 for a in atlar}
        return {a['key']:(a.get(kriter,0)-mn)/(mx-mn)*100 for a in atlar}

    def build_intelligence(self):
        csv_files=glob.glob(os.path.join(self.data_path,"**/*.csv"),recursive=True)
        if not csv_files:
            csv_files=glob.glob(os.path.join(self.data_path,"*.csv"))
        if not csv_files:
            print("⚠️ CSV bulunamadı. Jokey/orijin indeksleri boş."); return
        print("🧠 Jokey-şehir + orijin indeksleri inşa ediliyor...")
        jg={}; jc={}
        for fp in csv_files:
            try:
                fname=os.path.basename(fp)
                sehir=normalize_sehir(re.sub(r'#U([0-9A-Fa-f]{4})',
                    lambda x:chr(int(x.group(1),16)), fname.split("-")[1] if "-" in fname else ""))
                with open(fp,'r',encoding='utf-8-sig') as f: lines=f.readlines()
                is_r=False; cp="Kum"
                for line in lines:
                    line=line.strip().replace('\r','')
                    if ". Kosu :" in line or "Kosu :" in line:
                        cp="Çim" if "çim" in line.lower() else "Kum"
                        if "sentetik" in line.lower(): cp="Sentetik"
                        is_r=False; continue
                    if "At No;At İsmi" in line: is_r=True; continue
                    if "GANYAN(" in line or "İKİLİ(" in line: is_r=False; continue
                    if is_r:
                        p=line.split(";")
                        if len(p)>=14 and p[0].strip().isdigit():
                            s=int(p[0].strip()); baba=p[3].strip().upper(); jok=normalize_jokey(p[6])
                            jg.setdefault(jok,{"total":0,"wins":0}); jg[jok]["total"]+=1
                            jc.setdefault(jok,{}).setdefault(sehir,{"total":0,"wins":0})
                            jc[jok][sehir]["total"]+=1
                            if s==1:
                                jg[jok]["wins"]+=1; jc[jok][sehir]["wins"]+=1
                            if s==1 and baba:
                                self.sire_stats.setdefault(baba,{"Kum":0,"Çim":0,"Sentetik":0})
                                self.sire_stats[baba][cp]+=1
            except: continue
        for j,d in jg.items():
            self.jockey_global[j]=d["wins"]/d["total"] if d["total"]>=5 else 0.05
        for j,cities in jc.items():
            self.jockey_city[j]={c:d["wins"]/d["total"] for c,d in cities.items() if d["total"]>=8}
        print(f"✅ {len(self.jockey_global)} jokey, {len(self.sire_stats)} baba işlendi.")

    def jokey_skoru(self, jok, sehir):
        g=self.jockey_global.get(jok,0.05)
        c=self.jockey_city.get(jok,{}).get(sehir)
        return c*0.60+g*0.40 if c is not None else g

    def fetch_analysis(self, pid, rno, headers):
        try:
            url=(f"https://tjkbulten.atyarisi.com/api/v1/"
                 f"GetHorseAnalysisByProgramAndRace?programId={pid}&raceNo={rno}")
            r=requests.get(url,headers=headers,timeout=10)
            if r.status_code!=200: return {}
            return {int(h['horseNo']):{'genel':float(h.get('generalScore') or 0),
                                       'guncel':float(h.get('currentScore') or 0),
                                       'saatli':float(h.get('hourlyScore') or 0),
                                       'not':h.get('analysisNote','')}
                    for h in r.json().get('d',{}).get('horses',[])
                    if h.get('horseNo') is not None}
        except: return {}

    def tespit_grup(self, kat):
        if "maiden" in kat: return ("maiden","maiden")
        for kv,t in [("kv-6","kv6"),("kv 6","kv6"),("kv-7","kv7"),("kv 7","kv7"),
                      ("kv-8","kv8"),("kv 8","kv8")]:
            if kv in kat: return ("kv_grup",t)
        if any(k in kat for k in ["kisa vade","kv-","kv ","grup","g1","g2","g3","acik","açık"]):
            return ("kv_grup","kv_diger")
        if "handikap" in kat or "/h" in kat: return ("handikap","handikap")
        if "sartli 1" in kat or "şartlı 1" in kat: return ("sartli","s1")
        return ("sartli","sartli")

    def hesapla(self, atlar, ag, alt):
        agf_var=max(a.get('agf',0) for a in atlar)>0
        bul_var=max(a.get('bulten_skoru',0) for a in atlar)>0
        nA=self.norm(atlar,'agf'); nG=self.norm(atlar,'genel')
        nFlow=self.norm(atlar,'peg_flow_score')
        for a in atlar:
            a['peg_galop_nortr']=a.get('peg_galop_skor',0) or 50.0
        nPegGalop=self.norm(atlar,'peg_galop_nortr')
        kaynak="ZAYIF"
        # Jokey sinyali: SADECE 10-13 atli sahalarda (ganyan_master ile senkron, k=0.20).
        n_at=len(atlar)
        jok_ek=0.20 if 10<=n_at<=13 else 0.0
        # 12+ SEGMENT-KAPILI GALOP (seg12_g7, dogrulanmis) — ganyan_master ile senkron.
        seg_galop = n_at >= 12
        if seg_galop:
            for a in atlar:
                a['_gal_ei_nm']=a.get('peg_gal_eniyi',0) or 50.0
                a['_gal_is_nm']=a.get('peg_gal_istikrar',0) or 50.0
                a['_gal_ei_rz']=a.get('peg_gal_eniyi',0)
            nGalEiNM=self.norm(atlar,'_gal_ei_nm')
            nGalIsNM=self.norm(atlar,'_gal_is_nm')
            nGalEiRZ=self.norm(atlar,'_gal_ei_rz')
        for a in atlar:
            k=a['key']
            flow=nFlow.get(k,50.0)
            if seg_galop and (agf_var or bul_var):
                market=nA[k] if agf_var else nG[k]
                ana=(market*0.25+flow*0.45
                     +nGalEiNM[k]*0.10+nGalIsNM[k]*0.15+nGalEiRZ[k]*0.05)
                kaynak=("AGF" if agf_var else "G")+"+PEG_AKIS+GALOP12"
            elif agf_var:
                ana=nA[k]*0.40+flow*0.50+nPegGalop[k]*0.10
                kaynak="AGF+PEG_AKIS"
            elif bul_var:
                ana=nG[k]*0.30+flow*0.70
                kaynak="G+PEG_AKIS"
            else:
                ana=flow
                kaynak="PEG_AKIS"
            if jok_ek:
                ana+=jok_ek*a.get('jokey_skoru',0.0)*100
                kaynak+="+JOK"
            a['ana_skor']=ana
        return atlar, kaynak

    def bes_satir(self, atlar):
        sirali=sorted(atlar,key=lambda x:x['ana_skor'],reverse=True)
        n=len(sirali)
        sec={}
        sec['favori']=sirali[0] if n>0 else None
        sec['surpriz_degil']=sirali[1] if n>1 else None
        sec['yazilabilir']=sirali[2] if n>2 else None
        sec['bomba']=sirali[3] if n>3 else None
        secilen={s['key'] for s in sec.values() if s}
        # HAR (5. satir) — 1010 kosu simulasyonu ile secilmis kural:
        #   kalabalik kosu (14+ at) -> en iyi Pegadrom akis rank (en kucuk peg_flow_rank)
        #   diger kosular           -> ana skor 5. at
        # Eski galop-tabanli HAR top4-disi kazananin %19'unu yakaliyordu; bu kural %39.
        aday=[a for a in sirali[4:] if a['key'] not in secilen]
        harbi=None
        if aday:
            if n>=14:
                flowlu=[a for a in aday if a.get('peg_flow_rank',0)>0]
                harbi=min(flowlu,key=lambda x:x['peg_flow_rank']) if flowlu else aday[0]
            else:
                harbi=aday[0]
        sec['harbi']=harbi
        return sec

    def isle_tarih(self, td, tjk_h, lider_h):
        fd=datetime.strptime(td,"%d.%m.%Y").strftime("%Y-%m-%d")
        try:
            r=requests.get(f"https://tjkbulten.atyarisi.com/api/v1/ProgramHippodromes?date={fd}",
                          headers=tjk_h,timeout=15)
            if r.status_code!=200: print(f"  ❌ {td}: {r.status_code}"); return
            cj=r.json(); hips=cj.get('d',cj) if isinstance(cj,dict) else cj
            if not isinstance(hips,list) or not hips: print(f"  ⚠️ {td}: bülten yok"); return
        except Exception as e: print(f"  ❌ {td}: {e}"); return

        date_tahmin=[]   # bu tarihin parse-edilebilir tahmin satırları (Tahminler dosyası)
        date_altili=[]   # bu tarihin altılı kupon satırları (Altili dosyası)
        for hp in hips:
            pid=hp.get('id') or hp.get('programId')
            if not pid: continue
            hobj=hp.get('hippodrome',{})
            sad=(hobj.get('place') or hobj.get('name') or hp.get('place') or hp.get('name') or 'Bilinmeyen')
            if not is_turkiye_hipodrom(sad): continue
            sn=normalize_sehir(sad); su=sehir_to_url(sad)
            try:
                rd=requests.get(f"https://tjkbulten.atyarisi.com/api/v2/ProgramDetails?programId={pid}",
                               headers=tjk_h,timeout=15)
                if rd.status_code!=200: continue
                dj=rd.json()
            except: continue
            inner=dj.get('d',dj)
            races=inner.get('races',[]) if isinstance(inner,dict) else []
            if not races: continue

            kosu_verileri={}; bets_by_kosu={}; son_kosu=0
            for race in races:
                if not isinstance(race,dict): continue
                kno=race.get('number','?')
                rtitle=(race.get('name') or race.get('typeDescription') or '').strip()
                kcat=self.cel(rtitle); saat=race.get('hour','') or ''
                pr=race.get('raceCourseType','Kum') or 'Kum'
                pist=('Çim' if 'çim' in pr.lower() or 'cim' in pr.lower()
                      else 'Sentetik' if any(s in pr.lower() for s in ['sentetik','awt']) else 'Kum')
                mesafe=int(race.get('distance') or 1400)
                ag,alt=self.tespit_grup(kcat)
                if isinstance(kno,int):
                    bets_by_kosu[kno]=race.get('bets','') or ''
                    son_kosu=max(son_kosu,kno)
                hl=race.get('horses',[])
                if not hl or len(hl)<2: continue
                analysis=self.fetch_analysis(pid,kno,tjk_h)

                atlar=[]
                for h in hl:
                    try:
                        if h.get('status') is False: continue
                        raw=(h.get('name') or '').upper().strip()
                        if not raw: continue
                        at=re.split(r'\s(?:KG|DB|SK|K|SGK)\b',raw)[0].strip()
                        ano=int(h.get('number') or 0)
                        jobj=h.get('jockey',{}) or {}
                        jok=normalize_jokey(jobj.get('name') or jobj.get('jockeyLongName') or 'JOKEY')
                        ar=h.get('agf',[])
                        if isinstance(ar,list) and ar:
                            f0=ar[0]; agf=float(f0.get('percentage',0) or 0) if isinstance(f0,dict) else (float(f0) if f0 else 0.0)
                        elif isinstance(ar,(int,float)): agf=float(ar)
                        else: agf=0.0
                        a=analysis.get(ano,{})
                        g_=a.get('genel',0.0); gn=a.get('guncel',0.0); s_=a.get('saatli',0.0)
                        if s_>0: bs=s_*0.70+g_*0.30
                        elif g_>0: bs=g_
                        else: bs=0.0
                        peg_ai=self.pegadrom_ai_ozellikleri(fd,sn,kno,ano)
                        peg_gal_row=self.pegadrom_galop_row(fd,sn,kno,ano)
                        peg_galop=float(peg_gal_row.get('skor') or 0)
                        owner=((h.get('owner') or {}).get('name') or '').strip().upper()
                        stablemate=h.get('stablemate') or 0
                        atlar.append({"key":f"{ano}_{at}","at_no":ano,"at":at,"raw_at":raw,
                                      "jokey_adi":jok,"jokey_skoru":self.jokey_skoru(jok,sn),
                                      "agf":agf,"genel":g_,"guncel":gn,"saatli":s_,
                                      "bulten_skoru":bs,
                                      "peg_galop_skor":peg_galop,
                                      "peg_gal_eniyi":float(peg_gal_row.get('en_iyi') or 0),
                                      "peg_gal_istikrar":float(peg_gal_row.get('istikrar') or 0),
                                      "peg_model":peg_ai.get('peg_model',0),
                                      "peg_flow_rank":peg_ai.get('peg_flow_rank',0),
                                      "peg_flow_score":peg_ai.get('peg_flow_score',50),
                                      "peg_flow_type":peg_ai.get('peg_flow_type',''),
                                      "owner":owner,"stablemate":stablemate,
                                      "g_sprint":0,"g_gun":99,"g_efor":"","g_sayi":0})
                    except: continue

                if len(atlar)<2: continue
                atlar,kaynak=self.hesapla(atlar,ag,alt)
                sec=self.bes_satir(atlar)
                bes_secim=[sec.get('favori'),sec.get('surpriz_degil'),
                           sec.get('yazilabilir'),sec.get('bomba'),sec.get('harbi')]
                gruplar=ekuri_gruplari(atlar)   # eküri (stablemate+sahip)

                # Parse-edilebilir çıktı (Tahminler dosyası + bulk rapor)
                date_tahmin.append(
                    f"KO:{kno}|{sad.upper()}|{td}|{ag}|{alt}|{pist}|{mesafe}|{saat}|{kaynak}")
                if gruplar:
                    date_tahmin.append(f"EKURI:{ekuri_serialize(gruplar)}")
                def atad(s): return s['raw_at'] if s else "-"
                date_tahmin.append(
                    f"5SATIR:FAV={atad(sec['favori'])}|SUR={atad(sec['surpriz_degil'])}|"
                    f"YAZ={atad(sec['yazilabilir'])}|BOM={atad(sec['bomba'])}|HAR={atad(sec['harbi'])}")
                for a in sorted(atlar,key=lambda x:x['ana_skor'],reverse=True):
                    date_tahmin.append(
                        f"ATNO:{a['at_no']}|AT:{a['raw_at']}|ANA:{a['ana_skor']:.1f}|"
                        f"PEGGLP:{a.get('peg_galop_skor',0):.0f}|PEGMOD:{a.get('peg_model',0):.0f}|"
                        f"AKIS:{a.get('peg_flow_rank',0)}|AKS:{a.get('peg_flow_score',0):.1f}|"
                        f"G:{a['genel']:.0f}|Gn:{a['guncel']:.0f}|S:{a['saatli']:.0f}|"
                        f"AGF:{a['agf']:.1f}|"
                        f"GSP:0.0|GGN:99|GEF:|GSY:0|"
                        f"JOK:{a['jokey_skoru']:.3f}")
                date_tahmin.append("")

                # Kupon için koşu verisi
                if isinstance(kno,int):
                    sirali=sorted(atlar,key=lambda x:x['ana_skor'],reverse=True)
                    fark=(sirali[0]['ana_skor']-sirali[1]['ana_skor']) if len(sirali)>=2 else 100.0
                    kosu_verileri[kno]={'atlar_sirali':sirali,'n_at':len(atlar),'fark':fark,
                                        'race_type':ag,'race_subtype':alt,
                                        'bes_nos':[x['at_no'] for x in bes_secim if x],
                                        'ekuri':gruplar}

            # ── Hipodrom bitti: altılı kuponları ──
            altililar=altili_ayaklari(bets_by_kosu, son_kosu)
            if altililar:
                date_altili.append("")
                date_altili.extend(hipodrom_altili_bloku(sad, altililar, kosu_verileri))
                date_altili.append("")

        # ── Tarih bitti: bulk rapora ekle + Tahminler/Altili dosyalarını yaz ──
        self.rapor.extend(date_tahmin)
        if date_tahmin:
            tarih_dosya=td.replace('.','-')   # GG-AA-YYYY
            if not date_altili:
                date_altili=[f"🎰 {td} — altılı ganyan bulunamadı."]
            ty,ay=analiz_dosyalari_yaz(tarih_dosya, date_tahmin, date_altili)
            print(f"     💾 {os.path.basename(ty)} + {os.path.basename(ay)}")

    def calistir(self, bas, bit):
        try:
            b=datetime.strptime(bas,"%d.%m.%Y"); e=datetime.strptime(bit,"%d.%m.%Y")
        except: print("❌ Tarih formatı hatalı."); return
        print(f"\n{'='*60}\n🚀 TOPLU TAHMİN v5 — {bas} → {bit}\n{'='*60}")
        self.pegadrom_ai_txt_guncelle(b, e)
        self.build_intelligence()
        tjk_h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0',
               'Accept':'application/json, text/plain, */*','X-Requested-With':'XMLHttpRequest',
               'platformId':'1','Origin':'https://www.atyarisi.com','Referer':'https://www.atyarisi.com/'}
        lider_h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0',
                 'Accept':'application/json','X-Widget':'race-gallops-sprints',
                 'Authorization':'Bearer AlfIl7OPl8b10n9103Otlt0lMILI8U',
                 'Origin':'https://www.atyarisi.com','Referer':'https://www.atyarisi.com/'}
        gun=b
        while gun<=e:
            ts=gun.strftime("%d.%m.%Y")
            print(f"⏳ {ts}...")
            self.isle_tarih(ts,tjk_h,lider_h)
            gun+=timedelta(days=1)
        _tt=os.path.join(os.path.dirname(os.path.abspath(__file__)),"Toplu Tahminler")
        os.makedirs(_tt,exist_ok=True)
        dosya=os.path.join(_tt,f"v5_tahmin_{bas.replace('.','')}-{bit.replace('.','')}.txt")
        with open(dosya,"w",encoding="utf-8") as f: f.write("\n".join(self.rapor))
        print(f"\n✅ Tamamlandı. Rapor: '{dosya}'")
        try:
            yazilan = tahmin_sonuc_uret(bas, bit, collect_results=True)
            if yazilan:
                print(f"📊 TahminSonuçları üretildi: {len(yazilan)} gün")
                print(f"   Klasör: {os.path.join(os.path.dirname(os.path.abspath(__file__)), 'TahminSonuçları')}")
            else:
                print("📊 TahminSonuçları: aralıkta sonuç bulunamadı/henüz oluşmadı.")
        except Exception as ex:
            print(f"⚠️ TahminSonuçları üretilemedi: {ex}")


if __name__=="__main__":
    print("🏇 TOPLU TAHMİN MOTORU v5")
    print("─"*40)
    bas=input("Başlangıç tarihi (Örn: 01.04.2026): ").strip()
    bit=input("Bitiş tarihi     (Örn: 28.05.2026): ").strip()
    TopluTahminV5().calistir(bas,bit)
