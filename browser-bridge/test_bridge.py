import hashlib
import http.client
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from bridge import Bridge,call_tool,make_server,serve_stdio

TEST_ROOT=Path(__file__).resolve().parents[1]/'work'/'tests'
TEST_ROOT.mkdir(parents=True,exist_ok=True)
URL='https://xcnmfu3da215.feishu.cn/wiki/PublicNode123'


class BridgeChecks(unittest.TestCase):
    def setUp(self):
        self.folder=Path(tempfile.mkdtemp(prefix='bridge-',dir=TEST_ROOT))
        self.catalog=self.folder/'catalog.json'
        self.catalog.write_text(json.dumps({'snapshot_at':'fixture','resources':[{'id':'PublicNode123','obj_token':'PublicObject123','public_verified':True,'sha256':hashlib.sha256(b'fixture').hexdigest()}]}),encoding='utf-8')
        self.bridge=Bridge(self.catalog,self.folder)
        self.server=make_server(self.bridge,0)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join(2)

    def http(self,method,path,body=None,**headers):
        connection=http.client.HTTPConnection('127.0.0.1',self.bridge.port,timeout=5)
        fields={'Origin':'chrome-extension://'+'a'*32,'Authorization':'Bearer '+self.bridge.secret,'X-Astro-Catalog':self.bridge.digest}
        fields.update(headers)
        data=json.dumps(body).encode() if body is not None else None
        if data is not None:fields['Content-Type']='application/json'
        connection.request(method,path,body=data,headers=fields)
        response=connection.getresponse();result=(response.status,json.loads(response.read() or b'{}'));connection.close();return result

    def test_scope_rejects_private_other_sites_and_parameters(self):
        self.assertEqual(self.bridge.allowed_url(URL),URL)
        for url in ['http://xcnmfu3da215.feishu.cn/wiki/PublicNode123','https://evil.example/wiki/PublicNode123','https://xcnmfu3da215.feishu.cn/base/PublicNode123','https://xcnmfu3da215.feishu.cn/wiki/PrivateNode','https://xcnmfu3da215.feishu.cn/wiki/PublicNode123?redirect=https://evil.example','https://person@xcnmfu3da215.feishu.cn/wiki/PublicNode123']:
            with self.subTest(url=url),self.assertRaises(ValueError):self.bridge.allowed_url(url)

    def test_loopback_auth_origin_and_catalog_checks(self):
        self.assertEqual(self.server.server_address[0],'127.0.0.1')
        self.assertEqual(self.http('GET','/health',Authorization='Bearer wrong')[0],403)
        self.assertEqual(self.http('GET','/health',Origin='https://evil.example')[0],403)
        self.assertEqual(self.http('GET','/health',**{'X-Astro-Catalog':'0'*64})[0],409)
        self.assertEqual(self.http('GET','/health')[0],200)
        self.assertEqual(self.http('GET','/health',Origin='chrome-extension://'+'b'*32)[0],403)
        self.assertEqual(self.http('GET','/health',Host='evil.example')[0],403)

    def test_roundtrip_queue_and_read_receipt(self):
        self.http('GET','/health')
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.bridge.request,'read',{},3)
            status,job=self.http('GET','/poll')
            self.assertEqual(status,200);self.assertEqual(job['operation'],'read')
            payload={'id':job['id'],'result':{'url':URL,'text':'fixture page','coverage':'currently_loaded_dom','links':[{'url':'https://xcnmfu3da215.feishu.cn/wiki/NewLecture123'},{'url':'https://evil.example/private'},{'url':'https://xcnmfu3da215.feishu.cn/base/private'}]}}
            self.assertEqual(self.http('POST','/result',payload)[0],200)
            self.assertEqual(future.result(3)['text'],'fixture page')
            self.assertEqual(self.bridge.allowed_url('https://xcnmfu3da215.feishu.cn/wiki/NewLecture123'),'https://xcnmfu3da215.feishu.cn/wiki/NewLecture123')
            with self.assertRaises(ValueError):self.bridge.allowed_url('https://xcnmfu3da215.feishu.cn/base/private')
            self.assertEqual(self.http('POST','/result',payload)[0],400)

    def test_expired_operation_is_not_replayed(self):
        self.http('GET','/health')
        with self.assertRaises(ValueError):self.bridge.request('download',{},0.01)
        self.assertTrue(self.http('GET','/poll')[1].get('idle'))

    def test_download_only_reports_new_matching_public_hash(self):
        self.bridge.last_download={'url':URL,'expected_name':'fixture.pdf','started':__import__('time').time()}
        file=self.folder/'fixture.pdf';file.write_bytes(b'wrong')
        self.assertEqual(self.bridge.download_status()['completion'],'not_verified')
        file.write_bytes(b'fixture')
        self.assertEqual(self.bridge.download_status()['completion'],'verified')
        self.bridge.last_download['expected_name']='../private.txt'
        self.assertEqual(self.bridge.download_status()['completion'],'not_verified')

    def test_mcp_initialize_tools_and_scope_error(self):
        messages=[{'jsonrpc':'2.0','id':0,'method':'server/discover'},
                  {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'kb_open','arguments':{'url':'https://evil.example/'}}}]
        stream=io.StringIO('\n'.join(json.dumps(m) for m in messages)+'\n');output=io.StringIO()
        serve_stdio(self.bridge,stream,output)
        replies=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(replies[0]['error']['code'],-32601)
        self.assertEqual(replies[1]['result']['protocolVersion'],'2025-06-18')
        self.assertEqual(len(replies[2]['result']['tools']),8)
        self.assertTrue(replies[3]['result']['isError']);self.assertTrue(self.bridge.jobs.empty())

    def test_invalid_arguments_do_not_reach_browser(self):
        for name,args in [('kb_open',{'url':URL,'script':'alert(1)'}),('kb_page',{'page':True}),('kb_scroll',{'direction':'down','pages':99}),('kb_read',{'max_chars':1000000})]:
            with self.subTest(name=name),self.assertRaises(ValueError):call_tool(name,args,self.bridge)
        self.assertTrue(self.bridge.jobs.empty())


if __name__=='__main__':unittest.main()
