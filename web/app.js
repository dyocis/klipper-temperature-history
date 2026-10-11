"use strict";
const $ = id => document.getElementById(id);
const palette = ['#69dfb8','#62b8ff','#ffbf69','#dc8dff','#ff7c91','#d8e86b','#7bdbdf','#e7a580','#8ca8ff','#bddeab','#b9a194','#f4d3ec'];
const markers={print_started:['Start','#69dfb8'],print_finished:['Finish','#62b8ff'],print_cancelled:['Cancelled','#ffbf69'],print_error:['Error','#ff7c91'],print_paused:['Paused','#dc8dff'],print_resumed:['Resumed','#69dfb8'],printing_detected:['Printing detected','#8e9eaf']};
function eventLabel(event){
  if(markers[event.kind])return markers[event.kind][0];
  if(event.state==='complete')return 'Complete status observed — finish time unknown';
  if(event.state==='cancelled')return 'Cancelled status observed — cancellation time unknown';
  if(event.state==='error')return 'Error status observed — error time unknown';
  return `${event.state} status observed`;
}
let sensors = [], selected = new Set(), hours = 1, history = {series:{},events:[]}, status = {}, bounds = null, busy = false, initialized = false;
function group(sensor) {
  const name = sensor.name.split(' ').slice(1).join(' ').replace(/^_+/, '');
  if (/nevermore|stealthmax/i.test(sensor.name) || /^(?:SM_|BME_(?:IN|OUT)$|SGP_(?:IN|OUT)$)/i.test(name)) return 'nevermore';
  return sensor.kind === 'heater' ? 'heater' : /motor/i.test(sensor.name) ? 'motor' : 'electronics';
}
function visible() { return sensors.filter(s => $('group').value === 'all' || group(s) === $('group').value); }
function active() { return visible().filter(s => selected.has(s.name)); }
function color(sensor) { return palette[sensors.indexOf(sensor) % palette.length]; }
function format(value) { return value == null ? '—' : `${value.toFixed(1)}°`; }
function renderSensors() {
  $('sensors').replaceChildren();
  for (const sensor of visible()) {
    const label = document.createElement('label'); label.className = 'sensor'; label.style.setProperty('--color',color(sensor));
    const check = document.createElement('input'); check.type='checkbox'; check.checked=selected.has(sensor.name);
    check.addEventListener('change',()=>{check.checked?selected.add(sensor.name):selected.delete(sensor.name);draw();exportLink();});
    const name = document.createElement('span');name.textContent=sensor.label;name.style.color=color(sensor);
    const value = document.createElement('b');value.textContent=format(status.readings?.[sensor.name]?.value);
    label.append(check,name,value);$('sensors').append(label);
  }
}
function exportLink() {
  const q = new URLSearchParams({start:String(history.start || Date.now()/1000-hours*3600),end:String(history.end || Date.now()/1000)});
  for(const s of active())q.append('sensor',s.name);
  $('export').href='/api/export?'+q;
  $('export').hidden=active().length===0;
}
async function refresh() {
  if(busy)return;busy=true;
  try {
    const response=await fetch('/api/status');if(!response.ok)throw Error('Status unavailable');status=await response.json();
    const oldNames=new Set(sensors.map(s=>s.name));sensors=status.sensors;
    $('nevermoreGroup').hidden=!sensors.some(s=>group(s)==='nevermore');
    if(!initialized){selected=new Set(sensors.map(s=>s.name));initialized=true;}else for(const s of sensors)if(!oldNames.has(s.name))selected.add(s.name);
    $('connection').textContent=status.state==='recording'?'● Recording':status.state==='offline'?'● Printer offline':'● Starting';
    $('summary').textContent=`${sensors.length} sensors · every ${status.sample_seconds}s · ${status.retention_days} days retained · Last sample: ${status.last_sample?new Date(status.last_sample*1000).toLocaleString():'waiting'}`;
    $('excluded').textContent=status.excluded?.length?`Excluded non-temperature or configured channels: ${status.excluded.join(', ')}`:'';
    const end=Date.now()/1000,start=end-hours*3600;
    const h=await fetch('/api/history?'+new URLSearchParams({start:String(start),end:String(end)}));if(!h.ok)throw Error('History unavailable');
    history={...await h.json(),start,end};renderSensors();draw();exportLink();
    $('events').replaceChildren();for(const event of history.events.slice().reverse()){
      const p=document.createElement('p');p.textContent=`${new Date(event.ts*1000).toLocaleString()} · ${eventLabel(event)}${event.filename?' · '+event.filename:''}`;$('events').append(p);
    }
    if(!history.events.length)$('events').textContent='No print-state changes in this range.';
  } catch(error) { $('connection').textContent='● Monitor unavailable';$('summary').textContent='Unable to refresh. Retrying automatically.'; }
  finally{busy=false;}
}
function draw() {
  const canvas=$('chart'),rect=canvas.getBoundingClientRect(),ratio=devicePixelRatio||1;
  canvas.width=rect.width*ratio;canvas.height=rect.height*ratio;const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
  const w=rect.width,h=rect.height,pad={l:48,r:15,t:16,b:38};const list=active();
  const values=[];for(const s of list)for(const p of history.series[s.name]||[])if(p.value!=null){values.push(p.min,p.max);if($('targets').checked&&p.target!=null)values.push(p.target);}
  $('empty').hidden=values.length>0;if(!values.length){$('empty').textContent=list.length?'No readings in this range yet.':'Select a sensor to view history.';bounds=null;return;}
  let lo=Math.floor(values.reduce((a,b)=>Math.min(a,b),Infinity)/10)*10,hi=Math.ceil(values.reduce((a,b)=>Math.max(a,b),-Infinity)/10)*10;if(hi-lo<10)hi=lo+10;
  const start=history.start,end=history.end,x=t=>pad.l+(t-start)/(end-start)*(w-pad.l-pad.r),y=v=>h-pad.b-(v-lo)/(hi-lo)*(h-pad.t-pad.b);
  bounds={x,start,end,w,h,pad};ctx.font='11px system-ui';ctx.lineWidth=1;
  for(let i=0;i<=5;i++){const v=lo+(hi-lo)*i/5,yy=y(v);ctx.strokeStyle='#253243';ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.fillStyle='#8e9eaf';ctx.fillText(v.toFixed(0),8,yy+4);}
  for(let i=0;i<=4;i++){const t=start+(end-start)*i/4;ctx.fillStyle='#8e9eaf';ctx.textAlign=i===0?'left':i===4?'right':'center';ctx.fillText(new Date(t*1000).toLocaleString([],hours>24?{month:'short',day:'numeric',hour:'2-digit'}:{hour:'2-digit',minute:'2-digit'}),x(t),h-10);}ctx.textAlign='left';
  const gap=Math.max(status.sample_seconds*2.5,(history.bucket_seconds||1)*2.5);
  for(const sensor of list){const data=history.series[sensor.name]||[],segments=[];let segment=[],prev=null;
    for(const p of data){if(p.value==null||(prev!=null&&p.ts-prev>gap)){if(segment.length)segments.push(segment);segment=[];}if(p.value!=null)segment.push(p);prev=p.ts;}if(segment.length)segments.push(segment);
    for(const points of segments){ctx.fillStyle=color(sensor);ctx.globalAlpha=.12;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(x(p.ts),y(p.max)):ctx.moveTo(x(p.ts),y(p.max)));points.slice().reverse().forEach(p=>ctx.lineTo(x(p.ts),y(p.min)));ctx.closePath();ctx.fill();ctx.globalAlpha=1;
      ctx.strokeStyle=color(sensor);ctx.lineWidth=1.8;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(x(p.ts),y(p.value)):ctx.moveTo(x(p.ts),y(p.value)));ctx.stroke();
      if(points.length===1){ctx.beginPath();ctx.arc(x(points[0].ts),y(points[0].value),2.5,0,Math.PI*2);ctx.fill();}
      if($('targets').checked&&sensor.kind==='heater'){ctx.setLineDash([5,5]);ctx.lineWidth=1;ctx.beginPath();let pen=false;for(const p of points){if(p.target==null){pen=false;continue;}pen?ctx.lineTo(x(p.ts),y(p.target)):ctx.moveTo(x(p.ts),y(p.target));pen=true;}ctx.stroke();ctx.setLineDash([]);}
    }
  }
  let markerIndex=0;
  for(const event of history.events){const marker=markers[event.kind];if(!marker)continue;const xx=x(event.ts);ctx.strokeStyle=marker[1];ctx.globalAlpha=.75;ctx.lineWidth=1;ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(xx,pad.t);ctx.lineTo(xx,h-pad.b);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;ctx.fillStyle=marker[1];ctx.textAlign=xx>w-100?'right':'left';ctx.fillText(marker[0],xx+(xx>w-100?-4:4),pad.t+12+(markerIndex++%3)*14);}ctx.textAlign='left';
}
$('ranges').addEventListener('click',event=>{const button=event.target.closest('button');if(!button)return;hours=Number(button.dataset.hours);for(const b of $('ranges').children)b.classList.toggle('active',b===button);$('chartTitle').textContent=`Last ${button.textContent.toLowerCase()}`;refresh();});
$('group').addEventListener('change',()=>{renderSensors();draw();exportLink();});$('targets').addEventListener('change',draw);
$('selectAll').addEventListener('click',()=>{for(const s of visible())selected.add(s.name);renderSensors();draw();exportLink();});
$('chart').addEventListener('mousemove',event=>{if(!bounds)return;const pixel=event.offsetX,t=bounds.start+(pixel-bounds.pad.l)/(bounds.w-bounds.pad.l-bounds.pad.r)*(bounds.end-bounds.start);const readings=[];for(const s of active()){const data=history.series[s.name]||[];let closest=null;for(const p of data)if(!closest||Math.abs(p.ts-t)<Math.abs(closest.ts-t))closest=p;if(closest&&Math.abs(closest.ts-t)<Math.max(status.sample_seconds*3,history.bucket_seconds*1.5))readings.push(`${s.label}: ${format(closest.value)}`);}for(const e of history.events)if(markers[e.kind]&&Math.abs(bounds.x(e.ts)-pixel)<8)readings.unshift(`${markers[e.kind][0]}: ${e.filename||'unnamed print'}`);$('hover').textContent=`${new Date(t*1000).toLocaleString()} · ${readings.join(' · ')||'No readings'}`;});
new ResizeObserver(draw).observe($('chart'));refresh();setInterval(refresh,10000);
