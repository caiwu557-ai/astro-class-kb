export const HOST = 'xcnmfu3da215.feishu.cn';

export function resourceId(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.hostname !== HOST || url.port || url.username || url.password || url.search) throw new Error('仅支持本知识库已核实的公开直链');
  const match = url.pathname.match(/^\/(wiki|file|docx)\/([a-zA-Z0-9]+)\/?$/);
  if (!match) throw new Error('不支持的页面类型');
  return match[2];
}

export function allowedUrl(value, catalog, observed = new Set()) {
  const id=resourceId(value);
  const ids = new Set(catalog.resources.filter(r => r.public_verified || r.navigation_only).flatMap(r => [r.id, r.obj_token]));
  if (!ids.has(id) && !observed.has(id)) throw new Error('资源不在目录中，也不是当前已读取页面实际可见的链接');
  return new URL(value).href;
}

// These functions are serialized by chrome.scripting; keep dependencies inside each function.
export function collectPage(maxChars = 50000,expectedUrl = null) {
  if (expectedUrl && location.href.split('#')[0]!==expectedUrl.split('#')[0]) throw new Error('页面已变化，取消读取');
  const root = document.querySelector('.docx') || document.querySelector('[class*="placeholder-wrapper"]') || document.querySelector('[class*="preview-main"]') || document.body;
  const text = root.innerText || '';
  const visible = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight; };
  const links = [...document.querySelectorAll('a[href]')].filter(visible).map(e => ({text:(e.innerText || e.getAttribute('aria-label') || '').trim(),url:e.href})).filter(e => /^https?:/.test(e.url)).slice(0,150);
  const images = [...root.querySelectorAll('img[src]')].filter(visible).map(e => ({alt:e.alt,url:e.src,width:e.naturalWidth,height:e.naturalHeight})).filter(e => e.width > 40 && /^https:/.test(e.url)).slice(0,24);
  const pageInput = document.querySelector('input[type="number"],input[role="spinbutton"],[role="spinbutton"] input');
  return {title:document.title.replace(/\p{Cf}/gu,''),url:location.href,text:text.slice(0,maxChars),truncated:text.length>maxChars,links,images,pdf_page:pageInput ? pageInput.value : null,coverage:'currently_loaded_dom',notice:'仅为当前已加载的页面内容；滚动、翻页或下载后再读取。'};
}

export function scrollPage(direction, pages,expectedUrl) {
  if (location.href.split('#')[0]!==expectedUrl.split('#')[0]) throw new Error('页面已变化');
  const candidates = [document.scrollingElement,...document.querySelectorAll('div')].filter(e => e && e.clientHeight>180 && e.scrollHeight>e.clientHeight+30);
  candidates.sort((a,b)=>b.clientWidth*Math.min(b.clientHeight,innerHeight)-a.clientWidth*Math.min(a.clientHeight,innerHeight));
  const element = candidates[0];
  if (!element) return {at_end:true,notice:'当前没有可滚动区域；这不证明全文件已读完。'};
  element.scrollBy({top:(direction==='up'?-1:1)*element.clientHeight*pages,behavior:'instant'});
  return {top:element.scrollTop,height:element.clientHeight,total:element.scrollHeight,at_end:element.scrollTop+element.clientHeight>=element.scrollHeight-3};
}

export function jumpPage(page,expectedUrl) {
  if (location.href.split('#')[0]!==expectedUrl.split('#')[0]) throw new Error('页面已变化');
  const inputs = [...document.querySelectorAll('input[type="number"],input[role="spinbutton"],[role="spinbutton"] input')];
  const input = inputs.find(e=>e.getBoundingClientRect().width>0);
  if (!input) throw new Error('没有找到可见页码输入框；请使用已有浏览器工具定位分页控件');
  if (input.max && page>Number(input.max)) throw new Error('页码超过文件范围');
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,String(page));
  input.dispatchEvent(new Event('input',{bubbles:true}));
  input.dispatchEvent(new Event('change',{bubbles:true}));
  input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true}));
  return {requested_page:page,notice:'请求已发出，重新读取并核对显示页码后再引用。'};
}

export function clickDownload(expectedUrl) {
  if (location.href.split('#')[0]!==expectedUrl.split('#')[0]) throw new Error('页面已变化，取消下载');
  const buttons = [...document.querySelectorAll('button,[role="button"]')];
  const button = buttons.find(e=>/^(下载|Download)$/i.test((e.innerText||e.getAttribute('aria-label')||'').trim()) && e.getBoundingClientRect().width>0);
  if (!button) throw new Error('当前页没有可见下载按钮，不能猜下载接口');
  const name = document.title.replace(/\p{Cf}/gu,'').replace(/\s*[-–]\s*(飞书云文档|Feishu Docs).*$/,'').trim();
  button.click();
  return {clicked:true,expected_name:name,url:location.href,completion:'not_verified'};
}
