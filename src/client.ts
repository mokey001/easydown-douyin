import { invoke, isTauri } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';

export type TaskState = 'queued' | 'resolving' | 'downloading' | 'waiting_login' | 'paused' | 'completed' | 'failed' | 'cancelled';
export type Settings = { output_dir:string; quality:string; max_items:number; concurrency:number; start_date:string; end_date:string; filename_template:string; save_cover:boolean; save_metadata:boolean; proxy:string };
export type Task = { id:string; url:string; state:TaskState; title:string; author:string; kind:string; detail:string; created_at:number; total:number; success:number; failed:number; skipped:number; bytes_read:number; bytes_total:number; speed:number; progress:number; output_dir:string };
export type Snapshot = { tasks:Task[]; settings:Settings; version:string; engine:string };
export type EngineEvent = {type:string; task?:Task; settings?:Settings; tasks?:Task[]; error?:string; status?:string};
type Reply = {type:string; request_id:string; ok:boolean; data:unknown; error?:string};
export const desktop = isTauri();
const pending = new Map<string, {resolve:(data:unknown)=>void; reject:(error:Error)=>void; timer:ReturnType<typeof setTimeout>}>();
const subscribers = new Set<(event:EngineEvent)=>void>();
let connection:Promise<void> | undefined;
export const subscribe = (fn:(event:EngineEvent)=>void) => { subscribers.add(fn); return () => {subscribers.delete(fn)}; };
export function connect() {
  if (!desktop) return Promise.resolve();
  connection ??= (async () => {
    await listen<Reply & EngineEvent>('engine-event', ({payload}) => {
      if (payload.type === 'response') {
        const item = pending.get(payload.request_id);
        if (item) { clearTimeout(item.timer); pending.delete(payload.request_id); payload.ok ? item.resolve(payload.data) : item.reject(new Error(payload.error || '操作失败')); }
      } else subscribers.forEach(fn=>fn(payload));
    });
    await listen<{status:string}>('page-status', ({payload}) => subscribers.forEach(fn=>fn({type:'page-status',status:payload.status})));
  })();
  return connection;
}
export async function command<T>(action:string, fields:Record<string,unknown> = {}):Promise<T> {
  if (!desktop) throw new Error('这是界面预览。请打开拾影桌面应用使用下载功能');
  await connect();
  const request_id = crypto.randomUUID();
  return new Promise<T>((resolve,reject) => {
    const timer = setTimeout(()=>{ pending.delete(request_id); reject(new Error('操作超时，请重新启动应用')); }, 15000);
    pending.set(request_id,{resolve:resolve as (value:unknown)=>void,reject,timer});
    invoke('engine_command',{message:{action,request_id,...fields}}).catch(error=>{
      clearTimeout(timer); pending.delete(request_id); reject(new Error(String(error)));
    });
  });
}
export const native = <T,>(action:string, fields:Record<string,unknown> = {}) => desktop ? invoke<T>(action,fields) : Promise.reject(new Error('请在桌面应用中使用此功能'));
