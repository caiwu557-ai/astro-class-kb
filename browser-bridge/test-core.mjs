import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {allowedUrl} from './extension/core.mjs';
const catalog={resources:[{id:'PublicNode123',obj_token:'Object123',public_verified:true},{id:'PrivateNode123',public_verified:false}]};

test('only published public resource IDs and host are allowed',()=>{
  assert.equal(allowedUrl('https://xcnmfu3da215.feishu.cn/wiki/PublicNode123#heading',catalog),'https://xcnmfu3da215.feishu.cn/wiki/PublicNode123#heading');
  assert.equal(allowedUrl('https://xcnmfu3da215.feishu.cn/file/Object123',catalog),'https://xcnmfu3da215.feishu.cn/file/Object123');
  for(const url of ['https://evil.example/wiki/PublicNode123','https://xcnmfu3da215.feishu.cn/base/PublicNode123','https://xcnmfu3da215.feishu.cn/wiki/PrivateNode123','https://xcnmfu3da215.feishu.cn/wiki/PublicNode123?x=1','https://user@xcnmfu3da215.feishu.cn/wiki/PublicNode123','javascript:alert(1)'])assert.throws(()=>allowedUrl(url,catalog));
});

test('MV3 has narrow permissions and no remote executable code',()=>{
  const manifest=JSON.parse(fs.readFileSync(new URL('./extension/manifest.json',import.meta.url),'utf8'));
  assert.equal(manifest.manifest_version,3);
  assert.deepEqual(manifest.permissions,['activeTab','scripting','storage']);
  assert.ok(!manifest.host_permissions.includes('<all_urls>'));
  assert.ok(!manifest.content_security_policy.extension_pages.includes('unsafe-eval'));
});

test('an observed same-host resource can be followed without allowing Base or other sites',()=>{
  const observed=new Set(['NewLecture123']);
  assert.equal(allowedUrl('https://xcnmfu3da215.feishu.cn/wiki/NewLecture123',catalog,observed),'https://xcnmfu3da215.feishu.cn/wiki/NewLecture123');
  assert.throws(()=>allowedUrl('https://xcnmfu3da215.feishu.cn/base/NewLecture123',catalog,observed));
  assert.throws(()=>allowedUrl('https://evil.example/wiki/NewLecture123',catalog,observed));
});
