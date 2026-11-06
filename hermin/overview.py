"""Read-only local usage and daily USD/IDR reference rates; no prompts leave this host."""
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
import urllib.request
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

FX_URL = 'https://api.frankfurter.dev/v2/rate/usd/idr?providers=bi'
FX_SOURCE = 'https://frankfurter.dev/'
FX_LOCK = threading.Lock()


def local_router(url):
    try:
        parsed=urlparse(url or '')
        return parsed.hostname in ('localhost','127.0.0.1','::1') and parsed.port==20128
    except ValueError:return False


def connect(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=2)


def empty(name, error=''):
    return dict(name=name,available=not bool(error),prompt_tokens=0,completion_tokens=0,
                requests=0,estimated_cost_usd=0.0,unknown_routes=0,error=error,top_model='')


def add(result, incoming, outgoing, cost, requests=1):
    result['prompt_tokens']+=max(0,int(incoming or 0));result['completion_tokens']+=max(0,int(outgoing or 0))
    result['requests']+=max(0,int(requests or 0))
    if cost is not None and math.isfinite(float(cost)) and float(cost)>=0:result['estimated_cost_usd']+=float(cost)


class Overview:
    def __init__(self, root, home, router_db=None):
        self.root=Path(root);self.home=Path(home)
        self.router_db=Path(router_db) if router_db else self.root/'9router/data/db/data.sqlite'
        self.fx_file=self.root/'hermin/state/usd-idr.json';self.fx_retry=0

    def exchange(self):
        today=datetime.now(ZoneInfo('Asia/Jakarta')).date().isoformat()
        with FX_LOCK:
            cached={}
            try:cached=json.loads(self.fx_file.read_text())
            except (OSError,ValueError):pass
            if not isinstance(cached,dict):cached={}
            if time.time()-cached.get('fetched_at',0)>3600 and time.time()>=self.fx_retry:
                try:
                    with urllib.request.urlopen(urllib.request.Request(FX_URL,headers={'User-Agent':'HERMIN/0.0.1-beta'}),timeout=5) as response: data=json.load(response)
                    rate=float(data['rate']); date=datetime.fromisoformat(data['date']).date().isoformat()
                    if data['base']!='USD' or data['quote']!='IDR' or not math.isfinite(rate) or not 1000<rate<1000000 or date>today:raise ValueError('Invalid reference rate')
                    cached={'rate':rate,'date':date,'fetched_at':time.time()}
                    self.fx_file.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    temporary=self.fx_file.with_suffix('.tmp');temporary.write_text(json.dumps(cached));temporary.chmod(0o600);temporary.replace(self.fx_file)
                except (OSError,ValueError,KeyError,TypeError):self.fx_retry=time.time()+300
            available=isinstance(cached.get('rate'),(int,float)) and math.isfinite(cached['rate']) and 1000<cached['rate']<1000000
            return {**cached,'available':available,'source':'Bank Indonesia via Frankfurter','url':FX_SOURCE,
                    'stale':cached.get('date')!=today or time.time()-cached.get('fetched_at',0)>3600,
                    'error':'' if available else 'Kurs belum tersedia; estimasi rupiah belum dihitung.'}

    def router(self, cutoff):
        result=empty('9Router')
        with closing(connect(self.router_db)) as db:
            where=' WHERE timestamp >= ?' if cutoff else '';args=(datetime.fromtimestamp(cutoff,timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z'),) if cutoff else ()
            row=db.execute('SELECT SUM(promptTokens),SUM(completionTokens),SUM(cost),COUNT(*) FROM usageHistory'+where,args).fetchone()
            add(result,*row)
            top=db.execute('SELECT model,SUM(COALESCE(promptTokens,0)+COALESCE(completionTokens,0)) FROM usageHistory'+where+' GROUP BY model ORDER BY 2 DESC LIMIT 1',args).fetchone()
            latest=db.execute('SELECT model FROM usageHistory ORDER BY timestamp DESC LIMIT 1').fetchone()
            result['top_model']=top[0] if top else '';result['latest_model']=latest[0] if latest else ''
        return result

    def hermes(self, cutoff):
        # shortcut: Hermes persists cumulative route buckets; use event-level usage if upstream adds a ledger.
        result=empty('Hermes langsung');result['window_note']='Akumulasi per model/sesi yang terakhir aktif pada periode; dapat mencakup penggunaan lebih awal.'
        with closing(connect(self.root/'hermes/data/state.db')) as db:
            where=' WHERE last_seen >= ?' if cutoff else '';args=(cutoff,) if cutoff else ()
            for provider,url,model,incoming,outgoing,cost,calls in db.execute('SELECT billing_provider,billing_base_url,model,input_tokens,output_tokens,estimated_cost_usd,api_call_count FROM session_model_usage'+where,args):
                if local_router(url):continue
                if not url and provider in ('','custom','openai','unknown'):
                    result['unknown_routes']+=1;continue
                add(result,incoming,outgoing,cost,calls)
            latest=db.execute('SELECT model FROM sessions WHERE model IS NOT NULL ORDER BY COALESCE(last_activity_at,started_at) DESC LIMIT 1').fetchone()
            result['latest_model']=latest[0] if latest else ''
        return result

    def opencode(self, cutoff):
        result=empty('OpenCode langsung')
        config={}
        try:config=json.loads((self.home/'.config/opencode/opencode.json').read_text())
        except (OSError,ValueError):pass
        providers=config.get('provider',{}) if isinstance(config,dict) else {}
        with closing(connect(self.home/'.local/share/opencode/opencode.db')) as db:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            table='session_message' if 'session_message' in tables else 'message'
            role="type='assistant'" if table=='session_message' else "json_extract(data,'$.role')='assistant'"
            where=f" WHERE json_valid(data) AND {role}"+(' AND time_created >= ?' if cutoff else '')
            args=(int(cutoff*1000),) if cutoff else ()
            fields=["COALESCE(json_extract(data,'$.model.providerID'),json_extract(data,'$.providerID'))", "json_extract(data,'$.tokens.input')", "json_extract(data,'$.tokens.output')", "json_extract(data,'$.cost')"]
            for provider,incoming,outgoing,cost in db.execute('SELECT '+','.join(fields)+' FROM '+table+where,args):
                detail=providers.get(provider,{}) if isinstance(providers,dict) else {}
                url=(detail.get('options') or {}).get('baseURL','') if isinstance(detail,dict) else ''
                if provider=='9router' or local_router(url):continue
                if not provider:result['unknown_routes']+=1;continue
                add(result,incoming,outgoing,cost)
            latest=db.execute("SELECT COALESCE(json_extract(data,'$.model.id'),json_extract(data,'$.modelID')) FROM "+table+f" WHERE json_valid(data) AND {role} ORDER BY time_created DESC LIMIT 1").fetchone()
            result['latest_model']=latest[0] if latest else ''
        return result

    def usage(self, period='24h'):
        windows={'24h':86400,'7d':7*86400,'30d':30*86400,'all':None}
        if period not in windows:raise ValueError('Periode statistik tidak valid.')
        cutoff=time.time()-windows[period] if windows[period] else None
        sources=[]
        for name, reader in [('9Router',self.router),('Hermes langsung',self.hermes),('OpenCode langsung',self.opencode)]:
            try:sources.append(reader(cutoff))
            except (OSError,sqlite3.Error,ValueError,TypeError,AttributeError):sources.append(empty(name,'Catatan lokal belum tersedia atau schema belum didukung.'))
        result=empty('Total terdeteksi');result['available']=any(s['available'] for s in sources)
        for source in sources:
            if source['available']:add(result,source['prompt_tokens'],source['completion_tokens'],source['estimated_cost_usd'],source['requests'])
            source['total_tokens']=source['prompt_tokens']+source['completion_tokens']
        result.update(period=period,sources=sources,total_tokens=result['prompt_tokens']+result['completion_tokens'],fx=self.exchange(),
                      top_model=sources[0]['top_model'],partial=any(not s['available'] or s['unknown_routes'] for s in sources),
                      note='9Router + pemakaian langsung agent; rute 9Router tidak dijumlah dua kali. Biaya mengikuti catatan lokal, bukan tagihan provider. Nol bisa berarti harga belum dicatat. Angka Hermes berdasarkan akumulasi sesi aktif.')
        return result
