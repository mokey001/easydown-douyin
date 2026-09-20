import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowDown, ArrowDownToLine, ArrowLeft, ArrowRight, Check, CheckCheck, ChevronRight, CircleHelp, Clipboard, Download, ExternalLink, FileDown, Film, Folder, FolderOpen, History, Image, Link2, ListVideo, LoaderCircle, Pause, Play, Plus, RefreshCw, Search, Settings2, ShieldCheck, SlidersHorizontal, UserRound, X, type LucideIcon } from 'lucide-react';
import { command, connect, desktop, native, subscribe, type Settings, type Snapshot, type Task, type TaskState } from './client';

const defaultSettings:Settings = {output_dir:'首次启动后自动选择下载文件夹',quality:'highest',max_items:50,concurrency:3,start_date:'',end_date:'',filename_template:'{date}_{title}_{id}',save_cover:false,save_metadata:false,proxy:''};
const qualityNames:Record<string,string> = {highest:'最高画质','1080p':'1080P 优先','720p':'720P 优先',lowest:'节省空间'};
const stateNames:Record<TaskState,string> = {queued:'排队中',resolving:'解析中',downloading:'下载中',waiting_login:'需要验证',paused:'已暂停',completed:'已完成',failed:'下载失败',cancelled:'已取消'};
const running = (t:Task) => ['queued','resolving','downloading'].includes(t.state);
function bytes(n:number) { if (!n) return '0 B'; const i=Math.min(3,Math.floor(Math.log(n)/Math.log(1024))); return `${(n/1024**i).toFixed(i ? 1 : 0)} ${['B','KB','MB','GB'][i]}`; }
function IconButton({icon:Icon,label,onClick,disabled=false}:{icon:LucideIcon;label:string;onClick:()=>void;disabled?:boolean}) { return <button className="icon-button" title={label} aria-label={label} onClick={onClick} disabled={disabled}><Icon size={17}/></button>; }

export default function App() {
  const [tasks,setTasks] = useState<Task[]>([]);
  const [settings,setSettings] = useState<Settings>(defaultSettings);
  const [view,setView] = useState<'downloads'|'history'|'settings'>('downloads');
  const [filter,setFilter] = useState('all');
  const [query,setQuery] = useState('');
  const [text,setText] = useState('');
  const [ready,setReady] = useState(false);
  const [pageReady,setPageReady] = useState(false);
  const [loginOpening,setLoginOpening] = useState(false);
  const loginInFlight = useRef(false);
  const [busy,setBusy] = useState(false);
  const [toast,setToast] = useState('');
  const [error,setError] = useState('');
  const [confirmClear,setConfirmClear] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const notify = (value:string) => setToast(value);
  const safe = async (fn:()=>Promise<unknown>) => { try { await fn(); } catch(e) {notify(e instanceof Error ? e.message : String(e));} };
  async function openLogin() {
    if(loginInFlight.current)return;
    loginInFlight.current=true;
    setLoginOpening(true);
    try { await safe(()=>native('open_login')); }
    finally { loginInFlight.current=false;setLoginOpening(false); }
  }
  useEffect(()=>{if(toast){const t=setTimeout(()=>setToast(''),5500);return ()=>clearTimeout(t)}},[toast]);
  useEffect(()=>{
    let stopped=false;
    const off=subscribe(event=>{
      if(event.type==='task' && event.task) setTasks(old=>[event.task!,...old.filter(t=>t.id!==event.task!.id)].sort((a,b)=>b.created_at-a.created_at));
      if(event.type==='settings' && event.settings) setSettings(event.settings);
      if(event.type==='ready') {setReady(true);setError('');if(event.tasks)setTasks(event.tasks);if(event.settings)setSettings(event.settings);}
      if(event.type==='page-status') setPageReady(event.status==='connected');
      if(event.type==='engine_error') {setReady(false);setError(event.error || '下载引擎已停止');}
    });
    void (async()=>{
      if(!desktop)return;
      await connect();
      for(let i=0;i<30&&!stopped;i++) {
        try { const data=await command<Snapshot>('snapshot'); if(!stopped){setTasks(data.tasks);setSettings(data.settings);setReady(true);setError('');} return; }
        catch { await new Promise(r=>setTimeout(r,500)); }
      }
      if(!stopped)setError('下载引擎未能启动，请关闭后重新打开应用');
    })();
    return ()=>{stopped=true;off()};
  },[]);
  async function add(event?:FormEvent) {
    event?.preventDefault();
    if(!text.trim() || busy)return;
    setBusy(true);
    await safe(async()=>{
      const result=await command<{added:string[];duplicate:number}>('enqueue',{text});
      setText('');setView('downloads');setFilter('all');
      notify(`已添加 ${result.added.length} 个任务${result.duplicate ? `，跳过 ${result.duplicate} 个重复链接` : ''}`);
    });
    setBusy(false);
  }
  const completed=tasks.filter(t=>t.state==='completed').length;
  const pendingCount=tasks.filter(t=>t.state!=='completed'&&t.state!=='cancelled').length;
  const activeCount=tasks.filter(running).length;
  const problems=tasks.filter(t=>['waiting_login','failed','paused'].includes(t.state)).length;
  const list=tasks.filter(t=>(view==='history' ? t.state==='completed' : true) && (filter==='active' ? running(t) : filter==='attention' ? ['waiting_login','failed','paused'].includes(t.state) : true) && `${t.title} ${t.author} ${t.url}`.toLowerCase().includes(query.toLowerCase()));
  const totalSpeed=tasks.reduce((sum,t)=>sum+(t.state==='downloading'?t.speed:0),0);
  async function chooseFolder() { const path=await native<string|null>('choose_folder');if(path)await command('settings',{settings:{output_dir:path}}); }
  const taskAction=(task:Task,action:string)=>safe(async()=>{await command(action,{task_id:task.id});});

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><ArrowDownToLine size={24}/></div><div><strong>拾影</strong><span>SHIYING</span></div></div>
      <div className="workspace-label">我的工作台</div>
      <nav aria-label="主导航">
        <button className={view==='downloads'?'nav-item selected':'nav-item'} onClick={()=>{setView('downloads');setFilter('all');setQuery('')}}><Download size={19}/><span>下载队列</span>{pendingCount>0&&<b>{pendingCount}</b>}</button>
        <button className={view==='history'?'nav-item selected':'nav-item'} onClick={()=>{setView('history');setFilter('all');setQuery('')}}><History size={19}/><span>下载记录</span>{completed>0&&<b>{completed}</b>}</button>
        <button className={view==='settings'?'nav-item selected':'nav-item'} onClick={()=>setView('settings')}><Settings2 size={19}/><span>偏好设置</span></button>
      </nav>
      <div className="sidebar-bottom">
        <div className="connection-card"><div className="connection-title"><span className={`status-dot ${pageReady?'online':''}`}/>{pageReady?'抖音页面已连接':'连接你的抖音'}</div><p>{pageReady?'可在窗口中查看登录状态，处理验证码。':'在独立窗口登录，保存你的账号状态。'}</p><button disabled={loginOpening} onClick={()=>void openLogin()}>{loginOpening?'正在打开…':pageReady?'打开抖音窗口':'连接抖音'}{loginOpening?<LoaderCircle size={14} className="spin"/>:<ExternalLink size={14}/>}</button></div>
        <div className="version"><span>拾影桌面版</span><span>v0.1.1</span></div>
      </div>
    </aside>
    <main>
      <header className="topbar"><div className="breadcrumb">工作台<ChevronRight size={13}/><span>{view==='downloads'?'下载队列':view==='history'?'下载记录':'偏好设置'}</span></div><div className="engine-state"><span className={`status-dot ${ready?'online':''}`}/>{desktop ? ready?'下载引擎就绪':'正在连接引擎' : '界面预览'}</div></header>
      <div className="content">
        {error&&<div className="error-banner" role="alert"><CircleHelp size={18}/>{error}</div>}
        {!desktop&&<div className="preview-banner">这是界面预览；下载、账号连接和文件管理请使用桌面应用。</div>}
        {view==='settings' ? <SettingsPage settings={settings} save={async next=>{await command('settings',{settings:next});notify('设置已保存，新任务将使用这些设置')}} onBack={()=>setView('downloads')} onChoose={()=>safe(chooseFolder)} onClear={()=>setConfirmClear(true)} onExport={()=>safe(async()=>{const data=await command('diagnostics');const result=await native('export_diagnostics',{data});if(result)notify('脱敏诊断已导出')})} notify={notify}/> : <>
          <div className="page-heading"><div><h1>{view==='downloads'?'把喜欢的，留在本地。':'已经收好的片刻。'}</h1><p>{view==='downloads'?'粘贴抖音分享链接，视频、图集和主页作品都可以。':'下载记录保存在这台电脑，随时打开所在文件夹。'}</p></div><div className="heading-symbol"><ArrowDownToLine size={25}/></div></div>
          {view==='downloads'&&<form className="composer" onSubmit={add}>
            <div className="composer-input"><Link2 size={21}/><textarea ref={input} aria-label="抖音分享链接" placeholder="粘贴分享链接或整段分享文案…" value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();void add()}}}/><button type="button" className="paste-button" onClick={()=>safe(async()=>{setText(await navigator.clipboard.readText());input.current?.focus()})}><Clipboard size={16}/>粘贴</button></div>
            <div className="composer-footer"><div className="composer-options"><span><Film size={14}/>视频</span><span><Image size={14}/>图集</span><span><ListVideo size={14}/>主页 / 合集</span><span className="multi-hint">支持多链接</span></div><button className="primary" type="submit" disabled={!text.trim()||busy||!ready}>{busy?<LoaderCircle size={17} className="spin"/>:<Plus size={17}/>}添加下载<span className="shortcut">Ctrl ↵</span></button></div>
          </form>}
          <div className="download-preferences"><button className="folder-setting" title={settings.output_dir} onClick={()=>safe(chooseFolder)}><Folder size={16}/><span>{settings.output_dir}</span><ChevronRight size={14}/></button><button className="quality-setting" onClick={()=>setView('settings')}><SlidersHorizontal size={15}/>{qualityNames[settings.quality]}<span>·</span>{settings.concurrency} 路下载</button></div>
          <section className="queue-section" aria-label="下载任务">
            <div className="queue-toolbar"><div className="tabs">{view==='history'?<span className="history-count">下载记录 <b>{completed}</b></span>:<>{[['all','全部',tasks.length],['active','进行中',activeCount],['attention','待处理',problems]].map(([key,label,count])=><button key={key} className={filter===key?'tab active':'tab'} onClick={()=>setFilter(String(key))}>{label}<span>{count}</span></button>)}</>}</div><label className="search"><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索任务" aria-label="搜索任务"/></label></div>
            {list.length ? <div className="task-list">{list.map(task=><TaskRow key={task.id} task={task} action={action=>taskAction(task,action)} open={()=>safe(()=>native('open_folder',{path:task.output_dir}))} login={()=>void openLogin()}/>)}</div> : <div className="empty-state">
              <div className="empty-art" aria-hidden="true"><div className="film-back"/><div className="film-front"><span/><span/><span/><span/><ArrowDown size={32}/><span/><span/><span/><span/></div><div className="empty-check"><Check size={16}/></div></div>
              <h2>{query||filter!=='all'?'这里没有匹配的任务':view==='history'?'下载完成后，会出现在这里':'你的收藏，从一个链接开始'}</h2>
              <p>{query||filter!=='all'?'试试其他关键词，或切换任务分类。':view==='history'?'回到下载队列，添加想保存的作品。':'复制抖音里的分享链接，粘贴到上方即可添加。'}</p>
              {!query&&filter==='all'&&<button className="text-button" onClick={()=>{setView('downloads');setTimeout(()=>input.current?.focus(),0)}}>{view==='history'?'去添加下载':'添加第一个链接'}<ArrowRight size={15}/></button>}
            </div>}
          </section>
          <div className="bottom-note"><ShieldCheck size={15}/><span>账号数据保留在本机 · 下载完成的文件不会上传</span><span className="speed-total">{totalSpeed>0?`${bytes(totalSpeed)}/s`:'准备就绪'}</span></div>
        </>}
      </div>
    </main>
    {toast&&<div className="toast" role="status"><span>{toast}</span><button aria-label="关闭提示" onClick={()=>setToast('')}><X size={15}/></button></div>}
    {confirmClear&&<div className="modal-backdrop"><div className="modal" role="dialog" aria-modal="true" aria-labelledby="clear-title"><h2 id="clear-title">清除抖音登录数据？</h2><p>内置窗口的 Cookie 和网页缓存将被清除。下载文件和任务记录会保留，之后需要重新登录。</p><div><button className="secondary" onClick={()=>setConfirmClear(false)}>保留登录</button><button className="danger" onClick={()=>safe(async()=>{await native('clear_login');setConfirmClear(false);setPageReady(false);notify('已清除登录数据')})}>清除登录数据</button></div></div></div>}
  </div>;
}

function TaskRow({task:t,action,open,login}:{task:Task;action:(value:string)=>void;open:()=>void;login:()=>void}) {
  const Icon=t.kind==='gallery'?Image:t.kind==='user'?UserRound:t.kind==='collection'?ListVideo:Film;
  const active=running(t);
  const eta=t.speed>0&&t.bytes_total>t.bytes_read?Math.ceil((t.bytes_total-t.bytes_read)/t.speed):0;
  return <article className={`task-row ${t.state}`}><div className="task-art"><Icon size={24}/>{t.kind==='user'&&<span>批量</span>}</div><div className="task-body"><div className="task-title-row"><h3 title={t.title}>{t.title}</h3><span className={`state state-${t.state}`}>{t.state==='completed'?<CheckCheck size={13}/>:active?<LoaderCircle size={12} className={t.state==='queued'?'':'spin'}/>:null}{stateNames[t.state]}</span></div><div className="task-meta"><span>{t.author||'抖音分享'}</span><span>·</span><span>{new Date(t.created_at*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</span>{t.total>0&&<><span>·</span><span>{t.success+t.skipped} / {t.total} 个作品</span></>}</div><p className="task-detail" title={t.detail}>{t.detail}</p>{active&&<div className="progress-track"><div style={{width:`${t.progress}%`}}/></div>}<div className="task-bottom"><span className="task-url" title={t.url}>{t.url}</span>{t.state==='downloading'&&<span className="byte-progress">{bytes(t.bytes_read)}{t.bytes_total?` / ${bytes(t.bytes_total)}`:''} · {bytes(t.speed)}/s{eta>0?` · ${eta<60?`${eta}秒`:`${Math.ceil(eta/60)}分钟`}`:''}</span>}</div></div><div className="task-actions">{active?<><IconButton icon={Pause} label="暂停下载" onClick={()=>action('pause')}/><IconButton icon={X} label="取消下载" onClick={()=>action('cancel')}/></>:t.state==='completed'?<IconButton icon={FolderOpen} label="打开所在文件夹" onClick={open}/>:<>{t.state==='waiting_login'&&<IconButton icon={UserRound} label="打开登录窗口" onClick={login}/>}<IconButton icon={t.state==='paused'?Play:RefreshCw} label={t.state==='paused'?'继续下载':'重试下载'} onClick={()=>action(t.state==='paused'?'resume':'retry')}/>{t.success>0&&<IconButton icon={FolderOpen} label="打开已保存的文件" onClick={open}/>}</>}</div></article>;
}

function SettingsPage({settings,save,onBack,onChoose,onClear,onExport,notify}:{settings:Settings;save:(next:Settings)=>Promise<void>;onBack:()=>void;onChoose:()=>void;onClear:()=>void;onExport:()=>void;notify:(value:string)=>void}) {
  const [draft,setDraft]=useState(settings);
  const [saving,setSaving]=useState(false);
  useEffect(()=>setDraft(old=>({...old,output_dir:settings.output_dir})),[settings.output_dir]);
  const update=<K extends keyof Settings>(key:K,value:Settings[K])=>setDraft(old=>({...old,[key]:value}));
  async function submit(e:FormEvent){e.preventDefault();setSaving(true);try{await save(draft)}catch(e){notify(e instanceof Error?e.message:String(e))}finally{setSaving(false)}}
  return <><button className="text-button back-button" onClick={onBack}><ArrowLeft size={15}/>返回下载队列</button><div className="page-heading settings-heading"><div><h1>按你的习惯保存。</h1><p>设置对新添加的任务生效，正在下载的任务不受影响。</p></div></div><form className="settings-form" onSubmit={submit}>
    <section className="settings-section"><div className="section-heading"><Folder size={18}/><h2>文件保存</h2></div><label className="field"><span>保存位置</span><div className="path-control"><input readOnly value={draft.output_dir}/><button className="secondary" type="button" onClick={onChoose}>选择文件夹</button></div></label><label className="field"><span>文件名模板</span><input value={draft.filename_template} onChange={e=>update('filename_template',e.target.value)}/><small>可用字段：{'{date}'} 日期 · {'{title}'} 标题 · {'{id}'} 作品 ID · {'{author}'} 作者</small></label><div className="checkbox-row"><label><input type="checkbox" checked={draft.save_cover} onChange={e=>update('save_cover',e.target.checked)}/>同时保存封面</label><label><input type="checkbox" checked={draft.save_metadata} onChange={e=>update('save_metadata',e.target.checked)}/>同时保存作品信息 JSON</label></div></section>
    <section className="settings-section"><div className="section-heading"><SlidersHorizontal size={18}/><h2>下载选项</h2></div><div className="field-grid"><label className="field"><span>视频画质</span><select value={draft.quality} onChange={e=>update('quality',e.target.value)}>{Object.entries(qualityNames).map(([value,name])=><option value={value} key={value}>{name}</option>)}</select><small>指定画质不可用时，自动选择可用的档位。</small></label><label className="field"><span>同时下载的媒体数</span><select value={draft.concurrency} onChange={e=>update('concurrency',Number(e.target.value))}>{[1,2,3,4].map(n=><option value={n} key={n}>{n} 路下载</option>)}</select><small>链接任务按顺序处理，媒体文件可以并行。</small></label></div><label className="field compact-field"><span>每个主页 / 合集最多下载</span><div className="inline-field"><input type="number" min={1} max={10000} required value={draft.max_items} onChange={e=>update('max_items',Number(e.target.value))}/><span>个作品</span></div></label><div className="field-grid"><label className="field"><span>发布日期起点（可选）</span><input type="date" value={draft.start_date} onChange={e=>update('start_date',e.target.value)}/></label><label className="field"><span>发布日期终点（可选）</span><input type="date" value={draft.end_date} min={draft.start_date} onChange={e=>update('end_date',e.target.value)}/></label></div><label className="field"><span>媒体下载代理（可选）</span><input value={draft.proxy} onChange={e=>update('proxy',e.target.value)} placeholder="http://127.0.0.1:7897"/><small>只影响媒体与短链接请求。抖音登录窗口使用系统网络设置。</small></label></section>
    <div className="settings-save"><span>暂停后继续会跳过已完成作品；未完成文件可能重新下载。</span><button className="primary" disabled={saving}>{saving?<LoaderCircle size={16} className="spin"/>:<Check size={16}/>}保存设置</button></div>
  </form><section className="settings-section maintenance"><div><h2>账号与诊断</h2><p>诊断报告仅包含版本、任务状态和计数，不包含账号、作品链接或文件路径。</p></div><div className="maintenance-buttons"><button className="secondary" onClick={onExport}><FileDown size={15}/>导出诊断</button><button className="text-danger" onClick={onClear}>清除登录数据</button></div></section></>;
}
