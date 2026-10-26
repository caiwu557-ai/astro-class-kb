import {allowedUrl,resourceId,collectPage,scrollPage,jumpPage,clickDownload} from './core.mjs';
const catalog = fetch(chrome.runtime.getURL('catalog.json')).then(r=>{if(!r.ok)throw new Error('缺少公开目录');return r.json();});
const observed = new Set();

async function target() {
  const {targetTabId,observedIds=[]} = await chrome.storage.session.get(['targetTabId','observedIds']);
  for (const id of observedIds) observed.add(id);
  if (!Number.isInteger(targetTabId)) throw new Error('请在公开知识库页面点击插件，先共享一个专用阅读标签页');
  const tab = await chrome.tabs.get(targetTabId);
  allowedUrl(tab.url,await catalog,observed);
  return tab;
}

async function injected(tabId,func,args=[]) {
  const result=await chrome.scripting.executeScript({target:{tabId},func,args});
  if (!result.length || result[0].error) throw new Error('页面脚本读取失败');
  return result[0].result;
}

async function run(job) {
  const args=job.arguments || {};
  const tab=await target();
  switch(job.operation) {
    case 'open': {
      const url=allowedUrl(args.url,await catalog,observed);
      await chrome.tabs.update(tab.id,{url});
      return {url,notice:'已导航；页面可能仍在加载，请调用 read 检查。'};
    }
    case 'read': {
      const max=args.max_chars??50000;
      if (!Number.isInteger(max) || max<300 || max>60000) throw new Error('max_chars 范围 300..60000');
      const result=await injected(tab.id,collectPage,[max,tab.url]);
      allowedUrl(result.url,await catalog,observed);
      for (const link of result.links || []) {
        try {if(observed.size<2000)observed.add(resourceId(link.url));} catch (_) {}
      }
      await chrome.storage.session.set({observedIds:[...observed]});
      return result;
    }
    case 'scroll': {
      if (!['up','down'].includes(args.direction) || !Number.isInteger(args.pages) || args.pages<1 || args.pages>3) throw new Error('direction up/down，pages 1..3');
      return injected(tab.id,scrollPage,[args.direction,args.pages,tab.url]);
    }
    case 'page': {
      if (!Number.isInteger(args.page) || args.page<1 || args.page>10000) throw new Error('页码范围 1..10000');
      return injected(tab.id,jumpPage,[args.page,tab.url]);
    }
    case 'download': {
      const result=await injected(tab.id,clickDownload,[tab.url]);
      const id=resourceId(tab.url);
      const item=(await catalog).resources.find(r=>r.id===id || r.obj_token===id);
      if(item?.obj_type==='file')result.expected_name=item.title;
      return result;
    }
    case 'screenshot': {
      await chrome.tabs.update(tab.id,{active:true});
      const active=await chrome.tabs.query({active:true,windowId:tab.windowId});
      if (active[0]?.id!==tab.id || active[0].url!==tab.url) throw new Error('活动标签页变化，取消截图');
      const data=await chrome.tabs.captureVisibleTab(tab.windowId,{format:'jpeg',quality:75});
      const after=await chrome.tabs.query({active:true,windowId:tab.windowId});
      if (after[0]?.id!==tab.id || after[0].url!==tab.url || !data.startsWith('data:image/jpeg;base64,')) throw new Error('截图目标发生变化');
      return {image:data.slice('data:image/jpeg;base64,'.length),mimeType:'image/jpeg',url:tab.url};
    }
    default:throw new Error('不支持的操作；本插件不提供任意脚本、表单填写或编辑能力');
  }
}

chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if (sender.id!==chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL(''))) return false;
  const action=async()=>{
    if (message.kind==='setup') {
      if (!Number.isInteger(message.port) || message.port<1024 || message.port>65535 || !/^[a-zA-Z0-9_-]{24,100}$/.test(message.code)) throw new Error('本机端口或配对码无效');
      const tabs=await chrome.tabs.query({active:true,currentWindow:true});
      if (!tabs.length) throw new Error('请先打开一个公开知识库页面');
      allowedUrl(tabs[0].url,await catalog);
      await chrome.storage.session.set({port:message.port,pairingCode:message.code,targetTabId:tabs[0].id});
      const url=chrome.runtime.getURL('bridge.html');
      const {bridgeTabId}=await chrome.storage.session.get('bridgeTabId');
      if (Number.isInteger(bridgeTabId)) {
        try {await chrome.tabs.reload(bridgeTabId);return {connected_page:true};} catch (_) {}
      }
      const tab=await chrome.tabs.create({url,active:false});
      await chrome.storage.session.set({bridgeTabId:tab.id});
      return {connected_page:true};
    }
    if (message.kind==='run') return run(message.job);
    throw new Error('未知扩展消息');
  };
  action().then(result=>reply({result})).catch(error=>reply({error:error.message}));
  return true;
});
