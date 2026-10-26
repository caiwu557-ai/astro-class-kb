document.querySelector('#connect').addEventListener('click',async()=>{
  const status=document.querySelector('#status');
  try {
    const result=await chrome.runtime.sendMessage({kind:'setup',port:Number(document.querySelector('#port').value),code:document.querySelector('#code').value.trim()});
    if (result.error) throw new Error(result.error);
    document.querySelector('#code').value='';
    status.textContent='桥接页已打开。保留“Astro 阅读桥”标签页，回到 Agent 调用连接状态工具。';
  } catch(error) {status.textContent=error.message;}
});
