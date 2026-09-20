import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {version}=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
const output=[`Shiying Desktop ${version} — third-party notices\n\nThis distribution includes software under the licenses reproduced below. Build-only and other-platform dependencies may also be listed. Upstream core: jiji262/douyin-downloader commit f7ec48f9cfe1fc80b0093440c62c0c60425c31b2 (MIT).\n`];
function append(name, dir, recursive=false) {
  if(!fs.existsSync(dir)) return;
  for(const entry of fs.readdirSync(dir,{withFileTypes:true})) {
    const file=path.join(dir,entry.name);
    if(entry.isDirectory() && (recursive || /^(licenses?|notices?)$/i.test(entry.name))) append(name,file,true);
    else if(entry.isFile() && (recursive || /^(licen[cs]e|copying|copyright|notice|unlicense)/i.test(entry.name))) {
      if(fs.statSync(file).size<300000) output.push(`\n\n===== ${name} / ${entry.name} =====\n${fs.readFileSync(file,'utf8')}\n`);
    }
  }
}
output.push(fs.readFileSync(path.join(root,'sidecar/vendor/LICENSE-jiji.txt'),'utf8'));
for(const name of ['react','react-dom','scheduler','lucide-react','@tauri-apps/api']) append(name,path.join(root,'node_modules',name));
const rustRoot=path.join(process.env.CARGO_HOME||path.join(os.homedir(),'.cargo'),'registry/src');
const lock=fs.readFileSync(path.join(root,'src-tauri/Cargo.lock'),'utf8');
for(const block of lock.split('[[package]]')) {
  const name=block.match(/\nname = "([^"]+)"/)?.[1], version=block.match(/\nversion = "([^"]+)"/)?.[1];
  if(name&&version&&fs.existsSync(rustRoot)) for(const registry of fs.readdirSync(rustRoot)) append(`${name} ${version}`,path.join(rustRoot,registry,`${name}-${version}`));
}
const pyLib=path.join(root,'sidecar/.venv/Lib/site-packages');
for(const entry of fs.readdirSync(pyLib)) if(entry.endsWith('.dist-info')) append(entry, path.join(pyLib,entry));
const pycfg=fs.readFileSync(path.join(root,'sidecar/.venv/pyvenv.cfg'),'utf8');
const pyhome=pycfg.match(/^home = (.+)$/m)?.[1]?.trim();
if(pyhome) append('Python runtime',pyhome);
fs.writeFileSync(path.join(root,'THIRD_PARTY_NOTICES.txt'),output.join(''),'utf8');
console.log(`Collected ${output.length} license sections.`);
