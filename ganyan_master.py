import requests
import glob
import os
import re
import json
import sys
from datetime import datetime
from pathlib import Path
# Algoritmik modüller 'motor' alt klasöründe.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "motor"))
from pegadrom_ai_features import load_ai_txt_root
from pegadrom_ai_txt_topla import DEFAULT_DELAY, DEFAULT_OUT, collect_range
from altili_uretim import altili_ayaklari, hipodrom_altili_bloku, analiz_dosyalari_yaz, bes_satir_ekuri_notu
from altili_lib import ekuri_gruplari
from tahmin_sonuc_karsilastir import uret_aralik as tahmin_sonuc_uret

# ── Türkiye hipodromları ──────────────────────────────────────────────────────
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


class GanyanMasterEngine:
    """
    Veri-kanitli Pegadrom ak?? mimarisi:
    - AGF varsa: AGF %40 + Pegadrom yar?? ak??? %50 + Pegadrom galop %10
    - AGF yoksa: G %30 + Pegadrom yar?? ak??? %70
    - Gn ve eski galop guven sistemi ana skordan cikarildi
    - Pegadrom galop yoksa at bazinda 50 notr kabul edilir
    """
    def __init__(self, data_path="."):
        self.data_path = data_path
        self.jockey_global = {}      # {JOKEY: win_rate}
        self.jockey_city = {}        # {JOKEY: {SEHİR: win_rate}}
        self.sire_stats = {}         # {BABA: {pist: win_count}}
        self.report_lines = []
        self.altili_lines = []
        self.pegadrom_data = self.load_pegadrom()
        self.peg_ai_data = load_ai_txt_root(os.path.join(self.data_path, DEFAULT_OUT))

    # ── yardımcılar ───────────────────────────────────────────────────────────
    def cel(self, t):
        if not t: return ""
        return str(t).upper().translate(str.maketrans("ĞÜŞİÖÇI","GUSIOCI")).lower()

    def norm(self, atlar, kriter):
        vals=[a.get(kriter,0) for a in atlar]
        mn,mx=min(vals),max(vals)
        if mx==mn: return {a['key']:100.0 for a in atlar}
        return {a['key']:(a.get(kriter,0)-mn)/(mx-mn)*100 for a in atlar}

    def load_pegadrom(self):
        for fp in [os.path.join(os.path.dirname(os.path.abspath(__file__)), "motor", "pegadrom_skorlar.json"),
                   os.path.join(self.data_path, "pegadrom_skorlar.json"), "pegadrom_skorlar.json"]:
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

    def pegadrom_ai_txt_guncelle(self, tarih_dt):
        out_dir = Path(self.data_path) / DEFAULT_OUT
        print(f"Pegadrom AI TXT toplanıyor: {tarih_dt:%d.%m.%Y}")
        collect_range(tarih_dt, tarih_dt, out_dir, DEFAULT_DELAY, force=False)
        self.peg_ai_data = load_ai_txt_root(str(out_dir))
        print(f"Pegadrom AI TXT yüklendi: {len(self.peg_ai_data)} koşu")

    # ── CSV indeksleri (jokey-şehir + baba orijin) ─────────────────────────────
    def build_intelligence(self):
        csv_files = glob.glob(os.path.join(self.data_path,"**/*.csv"), recursive=True)
        if not csv_files:
            csv_files = glob.glob(os.path.join(self.data_path,"*.csv"))
        if not csv_files:
            print("⚠️ CSV bulunamadı. Jokey/orijin indeksleri boş kalacak.")
            return

        print("🧠 Jokey-şehir ve orijin indeksleri inşa ediliyor...")
        jg = {}   # {jok:{total,wins}}
        jc = {}   # {jok:{sehir:{total,wins}}}

        for fp in csv_files:
            try:
                fname=os.path.basename(fp)
                sehir=normalize_sehir(
                    re.sub(r'#U([0-9A-Fa-f]{4})', lambda x: chr(int(x.group(1),16)),
                           fname.split("-")[1] if "-" in fname else ""))
                with open(fp,'r',encoding='utf-8-sig') as f:
                    lines=f.readlines()
                is_r=False; cp="Kum"
                for line in lines:
                    line=line.strip().replace('\r','')
                    if ". Kosu :" in line or "Kosu :" in line:
                        cp = "Çim" if "çim" in line.lower() else "Kum"
                        if "sentetik" in line.lower(): cp="Sentetik"
                        is_r=False; continue
                    if "At No;At İsmi" in line: is_r=True; continue
                    if "GANYAN(" in line or "İKİLİ(" in line: is_r=False; continue
                    if is_r:
                        p=line.split(";")
                        if len(p)>=14 and p[0].strip().isdigit():
                            s=int(p[0].strip())
                            baba=p[3].strip().upper()
                            jok=normalize_jokey(p[6])
                            jg.setdefault(jok,{"total":0,"wins":0})
                            jg[jok]["total"]+=1
                            jc.setdefault(jok,{}).setdefault(sehir,{"total":0,"wins":0})
                            jc[jok][sehir]["total"]+=1
                            if s==1:
                                jg[jok]["wins"]+=1
                                jc[jok][sehir]["wins"]+=1
                            if s==1 and baba:
                                self.sire_stats.setdefault(baba,{"Kum":0,"Çim":0,"Sentetik":0})
                                self.sire_stats[baba][cp]+=1
            except: continue

        for j,d in jg.items():
            self.jockey_global[j] = d["wins"]/d["total"] if d["total"]>=5 else 0.05
        for j,cities in jc.items():
            self.jockey_city[j]={}
            for c,d in cities.items():
                if d["total"]>=8:   # anlamlı örneklem
                    self.jockey_city[j][c] = d["wins"]/d["total"]
        print(f"✅ {len(self.jockey_global)} jokey, {len(self.sire_stats)} baba orijini işlendi.")

    def jokey_skoru(self, jok, sehir_norm):
        """Şehir bazlı varsa %60 şehir + %40 global, yoksa global."""
        g=self.jockey_global.get(jok,0.05)
        c=self.jockey_city.get(jok,{}).get(sehir_norm)
        return c*0.60+g*0.40 if c is not None else g

    # ── API: bülten puanları ────────────────────────────────────────────────────
    def fetch_analysis(self, pid, rno, headers):
        try:
            url=(f"https://tjkbulten.atyarisi.com/api/v1/"
                 f"GetHorseAnalysisByProgramAndRace?programId={pid}&raceNo={rno}")
            r=requests.get(url, headers=headers, timeout=10)
            if r.status_code!=200: return {}
            return {int(h['horseNo']):{
                        'genel':float(h.get('generalScore') or 0),
                        'guncel':float(h.get('currentScore') or 0),
                        'saatli':float(h.get('hourlyScore') or 0),
                        'not':h.get('analysisNote','')}
                    for h in r.json().get('d',{}).get('horses',[])
                    if h.get('horseNo') is not None}
        except: return {}

    # ── API: galop ──────────────────────────────────────────────────────────────
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

    # -- ANA SKOR (yeni Pegadrom ak?? d?zeni) -----------------------------------
    def hesapla(self, atlar, ana_grup, alt_grup, pist, mesafe):
        agf_var = max(a.get('agf',0) for a in atlar) > 0
        bul_var = max(a.get('bulten_skoru',0) for a in atlar) > 0

        nA=self.norm(atlar,'agf')
        nG=self.norm(atlar,'genel')
        nFlow=self.norm(atlar,'peg_flow_score')
        for a in atlar:
            a['peg_galop_nortr']=a.get('peg_galop_skor',0) or 50.0
        nPegGalop=self.norm(atlar,'peg_galop_nortr')

        # Jokey sinyali: SADECE 10-13 atli sahalarda devreye girer (holdout-dogrulamali, k=0.20).
        # 1010 kosu testinde 10-13'te +0.6/+1.5 (holdout) kazanc; <=9'da notr, 14+'da ZARARLI
        # cikti (holdout -2.2). O yuzden jokey yalnizca orta kalabalikta uygulanir.
        n_at=len(atlar)
        jok_ek=0.20 if 10<=n_at<=13 else 0.0

        # 12+ SEGMENT-KAPILI GALOP (seg12_g7, dogrulanmis):
        # Kalabalik kosularda Pegadrom galop alt-alanlari (en_iyi+istikrar) ana skora eklenir.
        # 1004 kosu / 212 altili evreninde: 14+ 5-satir %78.0->%79.8, 10-13 %89.7->%90.8,
        # HAR %40.5->%42.7, altili cipa %62.7->%64.2, 3-kupondan-biri 53->54. <=12'de baseline aynen.
        # Global uygulanirsa <=9 ve Ilk1 bozuluyor; o yuzden SADECE n_at>=12'de acilir.
        seg_galop = n_at >= 12
        if seg_galop:
            for a in atlar:
                a['_gal_ei_nm']=a.get('peg_gal_eniyi',0) or 50.0    # en_iyi, eksik=50
                a['_gal_is_nm']=a.get('peg_gal_istikrar',0) or 50.0 # istikrar, eksik=50
                a['_gal_ei_rz']=a.get('peg_gal_eniyi',0)            # en_iyi, eksik=0
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
            a['_kaynak']=kaynak
        return atlar

    # -- 5 SATIR SE??M? -----------------------------------------------------------
    def bes_satir(self, atlar):
        sirali=sorted(atlar, key=lambda x:x['ana_skor'], reverse=True)
        n=len(sirali)
        secimler={}
        secimler['favori']        = sirali[0] if n>0 else None
        secimler['surpriz_degil'] = sirali[1] if n>1 else None
        secimler['yazilabilir']   = sirali[2] if n>2 else None
        secimler['bomba']         = sirali[3] if n>3 else None

        secilen_keyler={s['key'] for s in [secimler['favori'],secimler['surpriz_degil'],
                                            secimler['yazilabilir'],secimler['bomba']] if s}
        # HAR (5. satir) — 1010 kosu simulasyonu ile secilmis kural:
        #   kalabalik kosu (14+ at) -> en iyi Pegadrom akis rank (en kucuk peg_flow_rank)
        #   diger kosular           -> ana skor 5. at
        # Eski galop-tabanli HAR top4-disi kazananin %19'unu yakaliyordu; bu kural %39.
        aday=[a for a in sirali[4:] if a['key'] not in secilen_keyler]
        harbi=None
        if aday:
            if n>=14:
                flowlu=[a for a in aday if a.get('peg_flow_rank',0)>0]
                harbi=min(flowlu, key=lambda x:x['peg_flow_rank']) if flowlu else aday[0]
            else:
                harbi=aday[0]
        secimler['harbi']=harbi
        return secimler

    def altili_ayaklari(self, bets_by_kosu, son_kosu):
        return altili_ayaklari(bets_by_kosu, son_kosu)

    # NOT: Eski iki-mod (BONKÖR/SİMİTÇİ) kupon kurucu (ayak_genisligi/kupon_uret)
    # kaldırıldı. Altılı kuponlar artık tek merkezden — altili_uretim.hipodrom_altili_bloku
    # → altili_kupon_v2.build_nested_tiers — koşullu banko (BANKO_ZORUNLU_ESIK) + iç içe
    # kademe (Simitçi⊆Harbi⊆Ortaklı) mantığıyla kuruluyor. toplu_tahmin.py ile senkron.

    def run(self, target_date):
        print("="*85)
        print(f"📡 GANYAN MASTER ENGINE | TARİH: {target_date}")
        print("="*85)
        try:
            target_dt=datetime.strptime(target_date,"%d.%m.%Y")
            fd=target_dt.strftime("%Y-%m-%d")
        except:
            print("❌ Tarih formatı hatalı. Örnek: 30.05.2026"); return

        self.pegadrom_ai_txt_guncelle(target_dt)
        self.build_intelligence()

        tjk_h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0',
               'Accept':'application/json, text/plain, */*',
               'Accept-Language':'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
               'X-Requested-With':'XMLHttpRequest','platformId':'1',
               'Origin':'https://www.atyarisi.com','Referer':'https://www.atyarisi.com/'}
        lider_h={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0',
                 'Accept':'application/json','X-Widget':'race-gallops-sprints',
                 'Authorization':'Bearer AlfIl7OPl8b10n9103Otlt0lMILI8U',
                 'Origin':'https://www.atyarisi.com','Referer':'https://www.atyarisi.com/'}

        try:
            r=requests.get(f"https://tjkbulten.atyarisi.com/api/v1/ProgramHippodromes?date={fd}",
                          headers=tjk_h, timeout=15)
            if r.status_code!=200:
                print(f"❌ Hipodrom API hatası. Kod: {r.status_code}"); return
            cj=r.json()
            hips=cj.get('d',cj) if isinstance(cj,dict) else cj
            if not isinstance(hips,list) or not hips:
                print("⚠️ Bu tarihe ait bülten bulunamadı."); return

            self.report_lines.append(f"🔮 HARBÎ GANYAN GÜNLÜK TAHMİNLER — {target_date}")
            self.report_lines.append("="*78)
            self.report_lines.append("")

            for hp in hips:
                pid=hp.get('id') or hp.get('programId')
                if not pid: continue
                hobj=hp.get('hippodrome',{})
                sad=(hobj.get('place') or hobj.get('name') or
                     hp.get('place') or hp.get('name') or 'Bilinmeyen')
                if not is_turkiye_hipodrom(sad):
                    print(f"⏭️  {sad.upper()} atlandı (yabancı/karma)."); continue

                sn=normalize_sehir(sad); su=sehir_to_url(sad)
                print(f"📍 {sad.upper()} indiriliyor (programId={pid})...")
                try:
                    rd=requests.get(f"https://tjkbulten.atyarisi.com/api/v2/ProgramDetails?programId={pid}",
                                   headers=tjk_h, timeout=15)
                    if rd.status_code!=200:
                        print(f"⚠️ {sad.upper()} çekilemedi ({rd.status_code})"); continue
                    dj=rd.json()
                except: continue

                inner=dj.get('d',dj)
                races=inner.get('races',[]) if isinstance(inner,dict) else []
                if not races: continue

                self.report_lines.append(f"\n{'━'*78}")
                self.report_lines.append(f"🏟️  {sad.upper()} HİPODROMU")
                self.report_lines.append(f"{'━'*78}")

                ks=0
                kosu_verileri={}   # {kosu_no: {atlar_sirali, n_at, fark, alt}}
                bets_by_kosu={}    # {kosu_no: bets metni}
                son_kosu=0
                for race in races:
                    if not isinstance(race,dict): continue
                    kno=race.get('number','?')
                    rtitle=(race.get('name') or race.get('typeDescription') or '').strip()
                    kcat=self.cel(rtitle)
                    saat=race.get('hour','') or ''
                    pr=race.get('raceCourseType','Kum') or 'Kum'
                    pist=('Çim' if 'çim' in pr.lower() or 'cim' in pr.lower()
                          else 'Sentetik' if any(s in pr.lower() for s in ['sentetik','awt'])
                          else 'Kum')
                    mesafe=int(race.get('distance') or 1400)
                    ag,alt=self.tespit_grup(kcat)
                    # Kupon için bets bilgisini sakla
                    if isinstance(kno,int):
                        bets_by_kosu[kno]=race.get('bets','') or ''
                        son_kosu=max(son_kosu, kno)

                    hl=race.get('horses',[])
                    if not hl or len(hl)<2: continue

                    analysis=self.fetch_analysis(pid,kno,tjk_h)
                    galop_var=False

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
                                f0=ar[0]
                                agf=float(f0.get('percentage',0) or 0) if isinstance(f0,dict) else (float(f0) if f0 else 0.0)
                            elif isinstance(ar,(int,float)): agf=float(ar)
                            else: agf=0.0

                            a=analysis.get(ano,{})
                            g_=a.get('genel',0.0); gn=a.get('guncel',0.0); s_=a.get('saatli',0.0)
                            # Gn artik ana skorda kullanilmiyor; bulten var/yok icin G/S yeterli.
                            if s_>0: bs=s_*0.70+g_*0.30
                            elif g_>0: bs=g_
                            else: bs=0.0

                            peg_ai=self.pegadrom_ai_ozellikleri(fd,sn,kno,ano)
                            peg_gal_row=self.pegadrom_galop_row(fd,sn,kno,ano)
                            peg_galop=float(peg_gal_row.get('skor') or 0)

                            owner=((h.get('owner') or {}).get('name') or '').strip().upper()
                            stablemate=h.get('stablemate') or 0
                            atlar.append({
                                "key":f"{ano}_{at}","at_no":ano,"at":at,"raw_at":raw,
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
                                "ana_not":a.get('not',''),
                            })
                        except: continue

                    if len(atlar)<2: continue

                    atlar=self.hesapla(atlar,ag,alt,pist,mesafe)
                    secim=self.bes_satir(atlar)
                    kaynak=atlar[0].get('_kaynak','?')
                    # Eküri grupları (stablemate+sahip) ve 5'li satır eküri notu/alternatifi
                    gruplar=ekuri_gruplari(atlar)
                    sirali_atlar=sorted(atlar,key=lambda x:x['ana_skor'],reverse=True)
                    bes_secim=[secim.get('favori'),secim.get('surpriz_degil'),
                               secim.get('yazilabilir'),secim.get('bomba'),secim.get('harbi')]
                    ekuri_notlar,ekuri_alt=bes_satir_ekuri_notu(
                        bes_secim,sirali_atlar,gruplar,no_key='at_no',isim_key='raw_at')

                    # ── ÇIKTI (sade şablon) ──
                    # bets alanı (Koşu Analizleri için) KO satırının SONUNA eklenir;
                    # mevcut parser'lar p[0..8] kullandığından geriye dönük güvenlidir.
                    _bets_raw = bets_by_kosu.get(kno, "") if isinstance(kno, int) else ""
                    _bets_clean = (_bets_raw or "").replace("|", " ").replace("\n", " ").strip()
                    self.report_lines.append(
                        f"KO:{kno}|{sad}|{target_date}|{ag}|{alt}|{pist}|{mesafe}|{saat}|{kaynak}|{_bets_clean}")
                    if gruplar:
                        from altili_lib import ekuri_serialize
                        self.report_lines.append("EKURI:" + ekuri_serialize(gruplar))
                    def _atad(x):
                        return x.get('at', '') if x else "-"
                    self.report_lines.append(
                        f"5SATIR:FAV={_atad(secim.get('favori'))}|SUR={_atad(secim.get('surpriz_degil'))}|"
                        f"YAZ={_atad(secim.get('yazilabilir'))}|BOM={_atad(secim.get('bomba'))}|"
                        f"HAR={_atad(secim.get('harbi'))}")
                    for a in sorted(atlar, key=lambda x:x['ana_skor'], reverse=True):
                        self.report_lines.append(
                            f"ATNO:{a['at_no']}|AT:{a['at']}|ANA:{a['ana_skor']:.1f}|"
                            f"PEGGLP:{a.get('peg_galop_skor',0):.0f}|PEGMOD:{a.get('peg_model',0):.0f}|"
                            f"AKIS:{a.get('peg_flow_rank',0)}|AKS:{a.get('peg_flow_score',0):.1f}|"
                            f"G:{a['genel']:.0f}|Gn:{a['guncel']:.0f}|S:{a['saatli']:.0f}|"
                            f"AGF:{a['agf']:.1f}|GSP:0.0|GGN:99|GEF:|GSY:0|"
                            f"JOK:{a['jokey_skoru']:.3f}")
                    self.report_lines.append("")

                    # 14+ atli sahalar yapisal olarak dusuk isabetli (5 satir ~%79 vs ~%95);
                    # kullaniciya guven uyarisi verilir, kupon o ayakta genisletilir.
                    dusuk_guven=" | ⚠️ DÜŞÜK GÜVEN (kalabalık saha)" if len(atlar)>=14 else ""
                    self.report_lines.append(
                        f"\n┌─ {kno}. KOŞU | {rtitle} | {pist} {mesafe}m | ⏰{saat}{dusuk_guven}")
                    self.report_lines.append("│")

                    etiketler=[
                        ('favori',        '🎯 Harbi Ganyan Favorisi'),
                        ('surpriz_degil', '🔒 Kazanırsa Sürpriz Olmaz'),
                        ('yazilabilir',   '✍️  Kupona Yazılabilir'),
                        ('bomba',         '💣 Bomba!'),
                        ('harbi',         '❓ Harbi mi?'),
                    ]
                    for anahtar,etiket in etiketler:
                        a=secim.get(anahtar)
                        if not a:
                            self.report_lines.append(f"│  {etiket:<26}: —")
                        else:
                            ek=ekuri_notlar.get(a['at_no'])
                            eknot=f"  (eküri: {ek})" if ek else ""
                            self.report_lines.append(
                                f"│  {etiket:<26}: No:{a['at_no']:<3} {a['raw_at']}{eknot}")
                        self.report_lines.append("│")
                    # Eküri varsa: eküri-dışı ek olasılık öner (kaybedilen distinct slot için)
                    if ekuri_alt:
                        self.report_lines.append(
                            f"│  {'➕ Eküri dışı olasılık':<26}: No:{ekuri_alt['at_no']:<3} {ekuri_alt['raw_at']}")
                        self.report_lines.append("│")

                    # Sade puan dökümü (şablon)
                    self.report_lines.append("│  📊 Analiz Puanları:")
                    self.report_lines.append("│")
                    for a in sorted(atlar, key=lambda x:x['ana_skor'], reverse=True):
                        self.report_lines.append(
                            f"│     {a['at_no']:>2}. {a['raw_at']:<24} Skor: {a['ana_skor']:>5.1f}")
                    ks+=1

                    # Kupon için bu koşunun verisini sakla
                    if isinstance(kno,int):
                        sirali=sorted(atlar, key=lambda x:x['ana_skor'], reverse=True)
                        fark=(sirali[0]['ana_skor']-sirali[1]['ana_skor']) if len(sirali)>=2 else 100
                        kosu_verileri[kno]={
                            'atlar_sirali':sirali,
                            'n_at':len(atlar),
                            'fark':fark,
                            'race_type':ag,
                            'race_subtype':alt,
                            'bes_nos':[x['at_no'] for x in bes_secim if x],
                            'alt':alt,
                            'ekuri':gruplar,
                        }

                # ── ŞEHİR BİTTİ: ALTILI KUPONLARI (ayrı Altili dosyasına) ──
                altililar=self.altili_ayaklari(bets_by_kosu, son_kosu)
                if altililar:
                    self.altili_lines.append("")
                    self.altili_lines.extend(
                        hipodrom_altili_bloku(sad, altililar, kosu_verileri))
                    self.altili_lines.append("")

                print(f"   ✅ {sad.upper()}: {ks} koşu analiz edildi.")

            if len(self.report_lines)<=3:
                print("⚠️ Hiçbir koşu analiz edilemedi."); return

            # Çıktı: Harbi_Ganyan_Analiz/<tarih>/<tarih>_Tahminler.txt + _Altili.txt
            tarih_dosya=target_date.replace('.','-')   # GG-AA-YYYY
            if not self.altili_lines:
                self.altili_lines=[f"🎰 {target_date} — Altılı ganyan bulunamadı."]
            tahmin_yol,altili_yol=analiz_dosyalari_yaz(
                tarih_dosya, self.report_lines, self.altili_lines)
            print("\n"+"═"*60)
            print(f"🏆 TAMAMLANDI | 📅 {target_date}")
            print(f"   💾 Tahminler: {tahmin_yol}")
            print(f"   💾 Altılı   : {altili_yol}")
            try:
                yazilan = tahmin_sonuc_uret(target_date, collect_results=True)
                if yazilan:
                    print(f"   📊 TahminSonuçları: {yazilan[0]}")
                else:
                    print("   📊 TahminSonuçları: sonuç bulunamadı/henüz oluşmadı.")
            except Exception as ex:
                print(f"   ⚠️ TahminSonuçları üretilemedi: {ex}")
            print("═"*60)
        except Exception as e:
            import traceback
            print("❌ Hata:", e); traceback.print_exc()


if __name__=="__main__":
    print("🚀 Ganyan Master Engine (v5 — 5 satır + veri-kanıtlı)")
    t=input("🔮 Tarih girin (Örn: 30.05.2026): ").strip()
    if not t: t=datetime.now().strftime("%d.%m.%Y")
    GanyanMasterEngine().run(t)
