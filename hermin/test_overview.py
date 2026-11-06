from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
from overview import Overview, local_router


class OverviewTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'stack';self.home=Path(self.temp.name)/'home'
        self.overview=Overview(self.root,self.home)
        for path in [self.overview.router_db,self.root/'hermes/data/state.db',self.home/'.local/share/opencode/opencode.db']:
            path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.overview.router_db)) as db, db:
            db.execute('create table usageHistory(timestamp text,model text,promptTokens integer,completionTokens integer,cost real)')
            db.execute("insert into usageHistory values('2026-11-06T00:00:00Z','combo/test',100,20,1)")
        with closing(sqlite3.connect(self.root/'hermes/data/state.db')) as db, db:
            db.execute('create table session_model_usage(billing_provider text,billing_base_url text,model text,input_tokens integer,output_tokens integer,estimated_cost_usd real,api_call_count integer,last_seen real)')
            db.executemany('insert into session_model_usage values(?,?,?,?,?,?,?,?)',[
                ('custom','http://localhost:20128/v1','routed',100,20,1,1,time.time()),
                ('nous','https://inference-api.nousresearch.com/v1','direct',50,10,2,1,time.time()),
                ('custom','','unknown',500,500,90,1,time.time())])
            db.execute('create table sessions(model text,last_activity_at real,started_at real)')
        with closing(sqlite3.connect(self.home/'.local/share/opencode/opencode.db')) as db, db:
            db.execute('create table session_message(type text,time_created integer,data text)')
            for provider in ['9router','opencode']:
                db.execute('insert into session_message values(?,?,?)',('assistant',int(time.time()*1000),json.dumps({'model':{'providerID':provider,'id':'test'},'tokens':{'input':10,'output':5},'cost':3})))

    def test_does_not_count_router_usage_twice_or_unknown_routes(self):
        with patch.object(self.overview,'exchange',return_value={'available':False}): result=self.overview.usage('all')
        self.assertEqual(result['total_tokens'],195)
        self.assertEqual(result['estimated_cost_usd'],6)
        self.assertEqual(result['sources'][1]['unknown_routes'],1)
        self.assertTrue(result['partial'])

    def test_custom_opencode_alias_for_router_is_excluded(self):
        folder=self.home/'.config/opencode';folder.mkdir(parents=True)
        (folder/'opencode.json').write_text(json.dumps({'provider':{'opencode':{'options':{'baseURL':'http://127.0.0.1:20128/v1'}}}}))
        self.assertEqual(self.overview.opencode(None)['prompt_tokens'],0)

    def test_missing_database_is_unavailable_not_zero_and_not_created(self):
        path=self.root/'missing.db';self.overview.router_db=path
        with patch.object(self.overview,'exchange',return_value={'available':False}): result=self.overview.usage('all')
        self.assertFalse(result['sources'][0]['available']);self.assertFalse(path.exists())

    def test_invalid_period_and_router_host_are_rejected(self):
        with self.assertRaises(ValueError):self.overview.usage('arbitrary')
        self.assertTrue(local_router('http://localhost:20128/v1'))
        self.assertFalse(local_router('http://127.0.0.1.evil:20128/v1'))

    def test_exchange_cache_survives_network_outage_and_marks_stale(self):
        self.overview.fx_file.parent.mkdir(parents=True)
        self.overview.fx_file.write_text(json.dumps({'rate':18000,'date':'2020-01-01','fetched_at':0}))
        with patch('overview.urllib.request.urlopen',side_effect=OSError('offline')):
            result=self.overview.exchange()
        self.assertTrue(result['available']);self.assertTrue(result['stale']);self.assertEqual(result['rate'],18000)

    def test_bad_network_rate_is_not_used(self):
        response=MagicMock();response.read.return_value=json.dumps({'base':'USD','quote':'IDR','rate':-1,'date':'2020-01-01'}).encode()
        with patch('overview.urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value=response
            self.assertFalse(self.overview.exchange()['available'])
