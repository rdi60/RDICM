import React,{useEffect,useRef,useState} from 'react';
import {AlertTriangle,CheckCircle2,Info,X} from 'lucide-react';

let dispatcher=null;
const pending=[];
function ask(config){return new Promise(resolve=>{const task={...config,resolve};if(dispatcher)dispatcher(task);else pending.push(task)})}
export const confirmAction=(message,destructive=false)=>ask({type:'confirm',message,destructive});
export const promptAction=(message,minLength=1)=>ask({type:'prompt',message,minLength});
export const notifyAction=(message)=>ask({type:'notice',message});

export function AppDialogs(){
 const [dialog,setDialog]=useState(null),[answer,setAnswer]=useState('');
 const current=useRef(null);const confirmButton=useRef(null);
 useEffect(()=>{
  const open=d=>{setAnswer('');setDialog(d)};
  dispatcher=open;
  if(pending.length)open(pending.shift());
  return()=>{dispatcher=null; if(current.current)current.current.resolve(current.current.type==='prompt'?null:false);while(pending.length){const d=pending.shift();d.resolve(d.type==='prompt'?null:false)}};
 },[]);
 useEffect(()=>{current.current=dialog},[dialog]);
 useEffect(()=>{if(dialog)confirmButton.current?.focus()},[dialog]);
 const finish=value=>{if(!dialog)return;dialog.resolve(value);setDialog(null);if(pending.length){const next=pending.shift();setAnswer('');setDialog(next)}};
 useEffect(()=>{if(!dialog)return;const key=e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();finish(dialog.type==='prompt'?null:false)}};document.addEventListener('keydown',key,true);return()=>document.removeEventListener('keydown',key,true)},[dialog]);
 if(!dialog)return null;
 const destructive=dialog.destructive;
 return <div className="rd-dialog-backdrop" onPointerDown={e=>{if(e.target===e.currentTarget)finish(dialog.type==='prompt'?null:false)}}>
  <section className="rd-dialog" role="alertdialog" aria-modal="true" aria-labelledby="rd-dialog-title" aria-describedby="rd-dialog-desc">
   <div className="rd-dialog-heading"><span className={'rd-dialog-icon '+(destructive?'danger':'')}>
    {destructive?<AlertTriangle size={21}/>:dialog.type==='notice'?<CheckCircle2 size={21}/>:<Info size={21}/>}
   </span><h2 id="rd-dialog-title">{dialog.type==='prompt'?'Reason Required':dialog.type==='notice'?'Notification':destructive?'Confirm Important Action':'Please Confirm'}</h2>
   <button type="button" className="rd-dialog-close" aria-label="Close dialog" onClick={()=>finish(dialog.type==='prompt'?null:false)}><X size={19}/></button></div>
   <p id="rd-dialog-desc" className="rd-dialog-message">{dialog.message}</p>
   {dialog.type==='prompt'&&<label className="rd-dialog-reason">Reason<textarea value={answer} autoFocus rows={3} onChange={e=>setAnswer(e.target.value)} placeholder="Enter a reason"/></label>}
   <div className="rd-dialog-actions">
    {dialog.type!=='notice'&&<button type="button" className="outline" onClick={()=>finish(dialog.type==='prompt'?null:false)}>Cancel</button>}
    <button ref={confirmButton} type="button" className={destructive?'rd-dialog-danger':'primary'} disabled={dialog.type==='prompt'&&answer.trim().length<dialog.minLength} onClick={()=>finish(dialog.type==='prompt'?answer.trim():true)}>{dialog.type==='notice'?'OK':dialog.type==='prompt'?'Continue':destructive?'Confirm Action':'Confirm'}</button>
   </div>
  </section>
 </div>
}

