import { expect, test } from 'bun:test';
import { visibleRatio, shouldSubmitEnter, VisibilityClock } from './read-observer';
test('oversized bubble uses maximum possible intersection, not total bubble area',()=>{
 expect(visibleRatio({left:0,top:0,right:200,bottom:2000},{left:0,top:0,right:200,bottom:500})).toBe(1);
});
test('interrupted visibility starts a new continuous 500ms interval',()=>{
 const clock=new VisibilityClock(); expect(clock.update(true,0)).toBe(false); expect(clock.update(true,499)).toBe(false);
 expect(clock.update(false,499)).toBe(false); expect(clock.update(true,500)).toBe(false); expect(clock.update(true,999)).toBe(false); expect(clock.update(true,1000)).toBe(true);
});
test('IME always blocks send even with modifier and hardware signals',()=>{
 expect(shouldSubmitEnter({key:'Enter',isComposing:true,keyCode:229,shiftKey:false,ctrlKey:true,metaKey:false},true)).toBe(false);
});
test('unknown or software keyboard Enter is newline but modifier send remains available',()=>{
 const event={key:'Enter',isComposing:false,keyCode:13,shiftKey:false,ctrlKey:false,metaKey:false};
 expect(shouldSubmitEnter(event,false)).toBe(false); expect(shouldSubmitEnter({...event,ctrlKey:true},false)).toBe(true);
 expect(shouldSubmitEnter(event,true)).toBe(true); expect(shouldSubmitEnter({...event,shiftKey:true},true)).toBe(false);
});
