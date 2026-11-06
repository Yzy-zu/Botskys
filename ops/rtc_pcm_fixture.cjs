'use strict';
// Synthetic PCM passed through Botsky's owned queue, never a provider or microphone.
const {PcmQueue}=require('../calls/pcm-queue.cjs');
const q=new PcmQueue('rtc-lab','session-lab');
for(let n=0;n<5;n++){
 const pcm=Buffer.alloc(24000);for(let i=0;i<12000;i++)pcm.writeInt16LE(Math.round(Math.sin((n*12000+i)*2*Math.PI*440/24000)*10000),i*2);
 q.push({callId:'rtc-lab',sessionId:'session-lab',epoch:0,sequence:n,pcm});
}
for(let p;(p=q.take(240));)process.stdout.write(p.pcm);
q.close();
