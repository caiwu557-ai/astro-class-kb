"""Read-only offline locator. Python standard library; no network or credentials."""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ASSETS=Path(__file__).resolve().parents[1]/'assets'


def terms(query):
    query=unicodedata.normalize('NFKC',query).casefold()
    result=set(re.findall(r'[a-z0-9]{2,}|[\u4e00-\u9fff]{2,}',query))
    for word in list(result):
        if re.fullmatch(r'[\u4e00-\u9fff]{3,}',word):
            result.update(word[i:i+2] for i in range(len(word)-1))
    return sorted(result-{'什么','如何','怎么','课件','资料','介绍'})


def records():
    catalog=json.loads((ASSETS/'catalog.json').read_text(encoding='utf-8'))
    for item in catalog['resources']:
        yield {**item,'record_kind':'resource'}
    path=ASSETS/'content-index.jsonl'
    if path.exists():
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if line.strip():yield json.loads(line)


def search(query,course='',limit=8,offset=0):
    words=terms(query);hits=[]
    for item in records():
        if course and course.casefold() not in item.get('course','').casefold():continue
        title=(' '.join(item.get('trail',[]))+' '+item.get('title','')).casefold()
        body=(item.get('text','')+' '+' '.join(item.get('keywords',[]))).casefold()
        score=sum(12*int(word in title)+3*int(word in body) for word in words)
        if score:
            hits.append((score,item))
    hits.sort(key=lambda pair:(-pair[0],pair[1].get('title',''),str(pair[1].get('id',''))))
    out=[]
    for score,item in hits[offset:offset+limit]:
        out.append({k:item[k] for k in ['id','title','course','url','source_url','locator','record_kind','needs_visual','index_status'] if k in item}|{'score':score,'excerpt':item.get('text','')[:220],'keywords':item.get('keywords',[])[:24]})
    return {'query':query,'matches':len(hits),'offset':offset,'results':out,'next_offset':offset+limit if offset+limit<len(hits) else None,'notice':'关键词命中仅用于定位；回答前读取原文或页面。'}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    commands=parser.add_subparsers(dest='command',required=True)
    find=commands.add_parser('search');find.add_argument('query');find.add_argument('--course',default='');find.add_argument('--limit',type=int,default=8);find.add_argument('--offset',type=int,default=0)
    read=commands.add_parser('read');read.add_argument('id')
    commands.add_parser('coverage')
    args=parser.parse_args()
    if args.command=='search':
        if not 1<=args.limit<=50 or args.offset<0:parser.error('limit 1..50; offset >=0')
        result=search(args.query,args.course,args.limit,args.offset)
    elif args.command=='read':
        result=next((item for item in records() if item['id']==args.id),None)
        if result is None:parser.error('Unknown record id; use search first')
        if result.get('record_kind')=='page-keywords':result={**result,'notice':'本记录不是原文。用浏览器打开 url，核对相应页；不能把关键词拼成引文。'}
    else:result=json.loads((ASSETS/'coverage.json').read_text(encoding='utf-8'))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
