export interface Rect {left:number;top:number;right:number;bottom:number}
export function visibleRatio(bubble:Rect,viewport:Rect):number {
 const bw=Math.max(0,bubble.right-bubble.left),bh=Math.max(0,bubble.bottom-bubble.top),vw=Math.max(0,viewport.right-viewport.left),vh=Math.max(0,viewport.bottom-viewport.top);
 const maximum=Math.min(bw,vw)*Math.min(bh,vh);if(!maximum)return 0;
 return Math.max(0,Math.min(bubble.right,viewport.right)-Math.max(bubble.left,viewport.left))*Math.max(0,Math.min(bubble.bottom,viewport.bottom)-Math.max(bubble.top,viewport.top))/maximum;
}
export class VisibilityClock {
 private since:number|null=null;
 update(eligible:boolean,now:number):boolean {if(!eligible){this.since=null;return false;}if(this.since===null)this.since=now;return now-this.since>=500;}
}
export function shouldSubmitEnter(event:{key:string;isComposing:boolean;keyCode:number;shiftKey:boolean;ctrlKey:boolean;metaKey:boolean},hardware:boolean):boolean {
 if(event.key!=='Enter'||event.isComposing||event.keyCode===229||event.shiftKey)return false;
 return event.ctrlKey||event.metaKey||hardware;
}
export function hardwareKeyboardAvailable():boolean {
 const viewport=window.visualViewport;
 const keyboardShrunk=viewport!==null&&window.innerHeight-viewport.height>120;
 return !keyboardShrunk&&matchMedia('(any-pointer: fine)').matches&&matchMedia('(any-hover: hover)').matches&&!matchMedia('(any-pointer: coarse)').matches;
}
interface Observation {clock:VisibilityClock;pending:boolean;done:boolean}
export class ReadObserver {
 private frame:number|null=null;private observations=new Map<string,Observation>();private disposed=false;
 constructor(private readonly container:HTMLElement,private readonly current:()=>boolean,private readonly onRead:(id:string)=>Promise<void>){
  document.addEventListener('visibilitychange',this.reset);window.addEventListener('blur',this.reset);window.addEventListener('hine-overlay-change',this.reset);this.frame=requestAnimationFrame(this.measure);
 }
 private reset=():void=>{for(const item of this.observations.values())item.clock.update(false,performance.now());};
 private measure=():void=>{
  if(this.disposed)return;
  const now=performance.now();const modal=[...document.querySelectorAll<HTMLElement>('[aria-modal="true"],dialog[open]')].some(node=>node.getClientRects().length>0);
  const permitted=document.visibilityState==='visible'&&this.current()&&!modal&&this.container.getClientRects().length>0;
  const root=this.container.getBoundingClientRect(),vv=window.visualViewport;
  let visible:Rect={left:Math.max(root.left,vv?.offsetLeft??0),top:Math.max(root.top,vv?.offsetTop??0),right:Math.min(root.right,(vv?.offsetLeft??0)+(vv?.width??window.innerWidth)),bottom:Math.min(root.bottom,(vv?.offsetTop??0)+(vv?.height??window.innerHeight))};
  for(const node of document.querySelectorAll<HTMLElement>('[data-read-occlusion], .app-nav, .session-notice')){
   const r=node.getBoundingClientRect();if(r.right<=visible.left||r.left>=visible.right||r.bottom<=visible.top||r.top>=visible.bottom)continue;
   const candidates:Rect[]=[{...visible,bottom:Math.min(visible.bottom,r.top)},{...visible,top:Math.max(visible.top,r.bottom)},{...visible,right:Math.min(visible.right,r.left)},{...visible,left:Math.max(visible.left,r.right)}];
   candidates.sort((a,b)=>Math.max(0,b.right-b.left)*Math.max(0,b.bottom-b.top)-Math.max(0,a.right-a.left)*Math.max(0,a.bottom-a.top));visible=candidates[0];
  }
  const present=new Set<string>();
  for(const bubble of this.container.querySelectorAll<HTMLElement>('[data-message-id]')){
   const id=bubble.dataset.messageId;if(!id)continue;present.add(id);
   let observation=this.observations.get(id);if(!observation){observation={clock:new VisibilityClock(),pending:false,done:false};this.observations.set(id,observation);}
   const eligible=permitted&&bubble.dataset.readEligible==='true'&&visibleRatio(bubble.getBoundingClientRect(),visible)>=0.5;
   if(!observation.clock.update(eligible,now)||observation.pending||observation.done)continue;
   observation.pending=true;const item=observation;
   void this.onRead(id).then(()=>{item.done=true;},()=>{item.clock.update(false,performance.now());}).finally(()=>{item.pending=false;});
  }
  for(const [id,observation] of this.observations)if(!present.has(id))observation.clock.update(false,now);
  this.frame=requestAnimationFrame(this.measure);
 };
 dispose():void{this.disposed=true;if(this.frame!==null)cancelAnimationFrame(this.frame);document.removeEventListener('visibilitychange',this.reset);window.removeEventListener('blur',this.reset);window.removeEventListener('hine-overlay-change',this.reset);this.observations.clear();}
}
