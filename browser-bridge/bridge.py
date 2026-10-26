"""MCP 2025-06-18 stdio + loopback-only extension relay. Standard library only."""
import argparse
import glob
import hashlib
import hmac
import json
import queue
import re
import secrets
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

MAX_BODY=4*1024*1024
HOST='xcnmfu3da215.feishu.cn'


def equal(left,right):return hmac.compare_digest(left.encode('utf-8'),right.encode('utf-8'))


class Bridge:
    def __init__(self,catalog_path,downloads=None):
        raw=Path(catalog_path).read_bytes()
        self.catalog=json.loads(raw)
        self.digest=hashlib.sha256(raw).hexdigest()
        self.resources=self.catalog['resources']
        self.ids={str(r[k]) for r in self.resources if r.get('public_verified') or r.get('navigation_only') for k in ('id','obj_token') if r.get(k)}
        self.observed={}
        self.secret=secrets.token_urlsafe(32)
        self.origin=None;self.last_seen=0;self.last_download=None
        self.jobs=queue.Queue();self.pending={};self.lock=threading.Lock()
        self.downloads=Path(downloads or Path.home()/'Downloads').resolve()
        self.port=0

    def resource_id(self,value):
        if not isinstance(value,str):raise ValueError('url must be a string')
        u=urlsplit(value)
        if u.scheme!='https' or u.hostname!=HOST or u.port not in (None,443) or u.username or u.password or u.query:raise ValueError('Only approved public knowledge-base URLs are supported')
        match=re.fullmatch(r'/(wiki|file|docx)/([A-Za-z0-9]+)/?',u.path)
        if not match:raise ValueError('Unsupported resource path')
        return match[2]

    def allowed_url(self,value):
        ident=self.resource_id(value)
        if ident not in self.ids and ident not in self.observed:raise ValueError('Resource is outside the catalog and observed page links')
        return value

    def connection(self):
        connected=time.time()-self.last_seen<30
        result={'connected':connected,'loopback_port':self.port,'snapshot_at':self.catalog.get('snapshot_at'),'catalog_sha256':self.digest,'scope':'kb-seeded-visible-links-readonly'}
        if not connected:result['pairing_code']=self.secret
        return result

    def request(self,operation,args,timeout=55):
        if time.time()-self.last_seen>30:raise ValueError('Browser bridge not connected; call kb_connection and pair the extension')
        ident=uuid.uuid4().hex
        pending={'queue':queue.Queue(maxsize=1),'operation':operation,'created':time.time(),'arguments':args}
        with self.lock:self.pending[ident]=pending
        self.jobs.put({'id':ident,'operation':operation,'arguments':args})
        try:
            reply=pending['queue'].get(timeout=timeout)
            if reply.get('error'):raise ValueError(reply['error'])
            return reply.get('result',{})
        except queue.Empty:
            raise ValueError('Browser reply not confirmed; do not automatically repeat a download') from None
        finally:
            with self.lock:
                # Keep a short-lived late receipt, so a timed-out click is never blindly repeated.
                pending['finished_wait']=True

    def accept(self,payload):
        if not isinstance(payload,dict) or not isinstance(payload.get('id'),str):raise ValueError('Invalid result')
        with self.lock:
            pending=self.pending.get(payload['id'])
            if not pending or time.time()-pending['created']>120:raise ValueError('Unknown or expired request')
            if pending.get('received'):raise ValueError('Duplicate result')
            if isinstance(payload.get('result'),dict) and payload['result'].get('url'):self.allowed_url(payload['result']['url'])
            if pending['operation']=='read' and isinstance(payload.get('result'),dict):
                for link in payload['result'].get('links',[])[:150]:
                    try:
                        ident=self.resource_id(link.get('url',''))
                        if len(self.observed)<2000:self.observed[ident]=payload['result'].get('url')
                    except (ValueError,AttributeError):pass
            pending['received']=True
            if pending['operation']=='download' and isinstance(payload.get('result'),dict):
                self.last_download={**payload['result'],'started':pending['created']}
            pending['queue'].put_nowait(payload)
            expired=[key for key,value in self.pending.items() if time.time()-value['created']>120]
            for key in expired:self.pending.pop(key,None)

    def download_status(self):
        info=self.last_download
        if not info:return {'completion':'not_verified','notice':'No download receipt; do not claim a file was saved'}
        name=info.get('expected_name','')
        if not name or re.search(r'[\\/:\x00]',name) or name in ('.','..'):return {'completion':'not_verified','notice':'Unexpected filename'}
        try:self.allowed_url(info.get('url',''))
        except ValueError:return {'completion':'not_verified','notice':'Download page outside approved catalog'}
        ident=urlsplit(info['url']).path.rstrip('/').split('/')[-1]
        resource=next((r for r in self.resources if r.get('id')==ident or r.get('obj_token')==ident),{})
        expected=resource.get('sha256')
        if not expected:return {'completion':'not_verified','expected_name':name,'notice':'No published source hash; verify the browser download receipt with the Agent’s file tools'}
        candidates=list(self.downloads.glob(glob.escape(name)))+list(self.downloads.glob(glob.escape(Path(name).stem)+' (*)'+glob.escape(Path(name).suffix)))
        candidates=[p for p in candidates if not p.is_symlink() and p.is_file() and p.resolve().parent==self.downloads]
        for path in sorted(candidates,key=lambda p:p.stat().st_mtime,reverse=True):
            if path.is_symlink() or not path.is_file() or path.resolve().parent!=self.downloads:continue
            if path.stat().st_mtime<info['started']-3:continue
            digest=hashlib.sha256()
            with path.open('rb') as stream:
                while block:=stream.read(1024*1024):digest.update(block)
            if hmac.compare_digest(digest.hexdigest(),expected):return {'completion':'verified','path':str(path.resolve()),'sha256':expected,'url':info['url']}
        return {'completion':'not_verified','expected_name':name,'notice':'Matching new file not verified yet; use kb_download_status without clicking download again'}


class Server(ThreadingHTTPServer):
    daemon_threads=True


def make_server(bridge,port=38473):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass

        def origin_allowed(self):
            origin=self.headers.get('Origin','')
            return bool(re.fullmatch(r'chrome-extension://[a-p]{32}',origin)) and (bridge.origin is None or equal(origin,bridge.origin))

        def host_allowed(self):return self.headers.get('Host')==f'127.0.0.1:{bridge.port}'

        def reply(self,status,value):
            raw=json.dumps(value,ensure_ascii=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
            if self.origin_allowed():
                self.send_header('Access-Control-Allow-Origin',self.headers['Origin']);self.send_header('Vary','Origin')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

        def authorized(self):
            if not self.host_allowed() or not self.origin_allowed():self.reply(403,{'error':'Origin or Host rejected'});return False
            if not equal(self.headers.get('Authorization',''),'Bearer '+bridge.secret):self.reply(403,{'error':'Pairing rejected'});return False
            if not equal(self.headers.get('X-Astro-Catalog',''),bridge.digest):self.reply(409,{'error':'Catalog mismatch; use matching Skill and extension versions'});return False
            bridge.origin=self.headers['Origin'];bridge.last_seen=time.time();return True

        def do_OPTIONS(self):
            if not self.host_allowed() or not self.origin_allowed():self.reply(403,{'error':'Origin rejected'});return
            self.send_response(204);self.send_header('Access-Control-Allow-Origin',self.headers['Origin']);self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type, X-Astro-Catalog');self.send_header('Access-Control-Allow-Methods','GET, POST');self.send_header('Vary','Origin');self.end_headers()

        def do_GET(self):
            if not self.authorized():return
            if self.path=='/poll':
                try:job=bridge.jobs.get(timeout=20)
                except queue.Empty:job={'idle':True}
                if job.get('id'):
                    with bridge.lock:pending=bridge.pending.get(job['id'])
                    if not pending or pending.get('finished_wait') or time.time()-pending['created']>55:job={'idle':True}
                self.reply(200,job)
            elif self.path=='/health':self.reply(200,{'connected':True})
            else:self.reply(404,{'error':'Unknown route'})

        def do_POST(self):
            if not self.authorized():return
            if self.path!='/result':self.reply(404,{'error':'Unknown route'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=MAX_BODY:raise ValueError('Invalid body length')
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
                payload=json.loads(self.rfile.read(length).decode('utf-8'));bridge.accept(payload)
            except (ValueError,TypeError,AttributeError,UnicodeError,queue.Full):self.reply(400,{'error':'Invalid or unknown result'});return
            self.reply(200,{'accepted':True})
    server=Server(('127.0.0.1',port),Handler);bridge.port=server.server_port;return server


def tool(name,description,properties=None,required=None,read_only=True):
    return {'name':name,'description':description,'inputSchema':{'type':'object','properties':properties or {},'required':required or [],'additionalProperties':False},'annotations':{'readOnlyHint':read_only,'destructiveHint':False,'openWorldHint':False}}


TOOLS=[
    tool('kb_connection','查看本机浏览器桥状态；未连接时取得本次配对码，仅交给自己的插件，勿发布。'),
    tool('kb_open','在专用阅读页打开目录节点，或已读取页面实际可见的同域Wiki/文件链接；网站按读者本人权限判断访问。',{'url':{'type':'string'}},['url']),
    tool('kb_read','读取当前已加载正文、可见链接及图片信息；不是全文完成证明。',{'max_chars':{'type':'integer','minimum':300,'maximum':60000}}),
    tool('kb_scroll','滚动正文后需重新读取；到达当前底部不证明全部懒加载完成。',{'direction':{'type':'string','enum':['up','down']},'pages':{'type':'integer','minimum':1,'maximum':3}},['direction','pages']),
    tool('kb_page','请求跳到PDF页序；重新读取并核对显示页码后再引用。',{'page':{'type':'integer','minimum':1,'maximum':10000}},['page']),
    tool('kb_screenshot','截图用户共享的当前公开阅读页，需要本页activeTab授权。'),
    tool('kb_download','仅用户明确要原文件时，点击当前公开页面的实际下载按钮；回执不明时不自动重发。',read_only=False),
    tool('kb_download_status','不重复点击，只核验本次下载的新文件是否与目录中的源哈希一致。'),
]


def validate(name,args,bridge):
    spec=next((t for t in TOOLS if t['name']==name),None)
    if not spec or not isinstance(args,dict):raise ValueError('Unknown tool or arguments')
    schema=spec['inputSchema'];props=schema['properties']
    if set(args)-set(props) or any(k not in args for k in schema['required']):raise ValueError('Missing or unexpected arguments')
    for key,value in args.items():
        definition=props[key]
        if definition['type']=='integer' and (type(value) is not int or not definition['minimum']<=value<=definition['maximum']):raise ValueError('Invalid integer argument')
        if definition['type']=='string' and not isinstance(value,str):raise ValueError('String argument required')
        if 'enum' in definition and value not in definition['enum']:raise ValueError('Invalid enum argument')
    if name=='kb_open':bridge.allowed_url(args['url'])


def call_tool(name,args,bridge):
    validate(name,args,bridge)
    if name=='kb_connection':result=bridge.connection()
    elif name=='kb_download_status':result=bridge.download_status()
    else:
        result=bridge.request(name.removeprefix('kb_'),args)
        if name=='kb_download':
            result={**result,'local_check':bridge.download_status()}
        if name=='kb_screenshot':
            if not isinstance(result.get('image'),str) or len(result['image'])>MAX_BODY or result.get('mimeType')!='image/jpeg':raise ValueError('Invalid screenshot result')
            return {'content':[{'type':'image','data':result['image'],'mimeType':'image/jpeg'}]}
    return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}]}


def serve_stdio(bridge,input_stream=None,output_stream=None):
    incoming=input_stream or sys.stdin;outgoing=output_stream or sys.stdout;initialized=False
    for line in incoming:
        ident=None
        try:
            if len(line)>MAX_BODY:raise ValueError('Input too large')
            request=json.loads(line)
            if not isinstance(request,dict) or request.get('jsonrpc')!='2.0' or not isinstance(request.get('method'),str):raise ValueError('Invalid JSON-RPC request')
            if 'id' not in request:continue
            ident=request['id']
            if type(ident) not in (str,int):raise ValueError('Invalid request id')
            method=request['method'];params=request.get('params',{})
            if method=='initialize':
                initialized=True
                result={'protocolVersion':'2025-06-18','capabilities':{'tools':{}},'serverInfo':{'name':'astro-kb-browser-bridge','version':'0.1.1'}}
            elif method=='ping':result={}
            elif method not in ('tools/list','tools/call'):
                outgoing.write(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Method not found'}})+'\n');outgoing.flush();continue
            elif not initialized:
                outgoing.write(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32002,'message':'Initialize required'}})+'\n');outgoing.flush();continue
            elif method=='tools/list':result={'tools':TOOLS}
            elif method=='tools/call':
                try:result=call_tool(params.get('name'),params.get('arguments',{}),bridge)
                except (ValueError,TimeoutError,OSError) as exc:result={'content':[{'type':'text','text':str(exc)}],'isError':True}
            else:
                outgoing.write(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'Method not found'}})+'\n');outgoing.flush();continue
            reply={'jsonrpc':'2.0','id':ident,'result':result}
        except (ValueError,TypeError,AttributeError):reply={'jsonrpc':'2.0','id':ident,'error':{'code':-32600,'message':'Invalid request'}}
        outgoing.write(json.dumps(reply,ensure_ascii=False)+'\n');outgoing.flush()


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8',newline='\n')
    sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=38473)
    parser.add_argument('--catalog',type=Path,default=Path(__file__).resolve().parent/'extension'/'catalog.json')
    parser.add_argument('--downloads',type=Path)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('port must be 1024..65535')
    bridge=Bridge(args.catalog,args.downloads);server=make_server(bridge,args.port)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:serve_stdio(bridge)
    finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
