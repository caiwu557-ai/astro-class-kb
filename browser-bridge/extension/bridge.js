const status=document.querySelector('#status');
async function connect() {
  const config=await chrome.storage.session.get(['port','pairingCode']);
  if (!config.port || !config.pairingCode) {status.textContent='请在知识库页面点击插件图标完成配对。';return;}
  const base=`http://127.0.0.1:${config.port}`;
  const catalogText=await (await fetch(chrome.runtime.getURL('catalog.json'))).text();
  const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(catalogText)))].map(b=>b.toString(16).padStart(2,'0')).join('');
  const headers={Authorization:`Bearer ${config.pairingCode}`,'Content-Type':'application/json','X-Astro-Catalog':digest};
  while (true) {
    try {
      const response=await fetch(base+'/poll',{headers,credentials:'omit',signal:AbortSignal.timeout(25000)});
      if (!response.ok) throw new Error('连接被拒绝；检查本次配对码与本机 MCP 桥');
      const job=await response.json();
      status.textContent='已连接。仅响应当前公开知识库的阅读操作。';
      if (job.id) {
        const result=await chrome.runtime.sendMessage({kind:'run',job});
        const posted=await fetch(base+'/result',{method:'POST',headers,credentials:'omit',body:JSON.stringify({id:job.id,...result}),signal:AbortSignal.timeout(15000)});
        if (!posted.ok) throw new Error('结果回执未确认，不会自动重复下载操作');
      }
    } catch(error) {
      status.textContent=error.message+'\n请确认 Agent 桥仍在运行；如已重启桥，请重新配对。';
      await new Promise(resolve=>setTimeout(resolve,3000));
    }
  }
}
connect();
