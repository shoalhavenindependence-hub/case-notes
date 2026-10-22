    /* ---------- hands-free notes (for the car) ----------
       Open the app with "Hey Google, open Shift Case Notes" (or the Hands-free note shortcut).
       It asks who the note is for, takes the note down, and saves it when you say "save note". */
    const HF = window.Capacitor.Plugins.HandsFree;
    let hf=false, hfRun=0, hfAway=0, hfAsking=false, hfWait=0;
    const say=text=>HF ? HF.speak({text}).catch(()=>{}) : Promise.resolve();
    const norm=t=>' '+String(t).toLowerCase().replace(/[^a-z0-9' ]+/g,' ').replace(/\s+/g,' ').trim()+' ';
    const hfShow=msg=>{ $('hfBar').hidden=!hf; $('hfMsg').textContent=msg||''; $('hfBtn').hidden=hf; };
    async function hear(run){
      // One stretch of speech, up to the next pause. Empty string if nothing was heard.
      if(run!==hfRun) return null;
      try{ const r=await NSR.start({language:'en-AU', maxResults:1, partialResults:false, popup:false});
        return run===hfRun ? ((r && r.matches && r.matches[0]) || '') : null; }
      catch{ return run===hfRun ? '' : null; }
    }
    function findClient(said){
      // Full name beats first name; two people with the same first name means ask again.
      const t=norm(said), list=activeClients();
      const full=list.filter(c=>t.includes(norm(c.name)));
      if(full.length) return full.sort((a,b)=>b.name.length-a.name.length)[0];
      const first=list.filter(c=>t.includes(norm(c.name.split(/\s+/)[0])));
      return first.length===1 ? first[0] : null;
    }
    function afterName(said, c){
      // Anything said after the name ("Sarah, we went shopping...") is the start of the note.
      const words=said.split(/\s+/), keys=norm(c.name).trim().split(' ');
      const i=words.findIndex(w=>keys.includes(norm(w).trim()));
      const rest=words.slice(i+1).join(' ').replace(/^[\s,.:-]+/,'');
      return rest.split(/\s+/).filter(Boolean).length>=3 ? rest : '';
    }
    const SAVE=/\b(save|saved|finish|finished|end)( the| my| this)? (note|notes)[.!]?\s*$/i;
    const CANCEL=/^\s*(cancel|stop|never ?mind)( the| my| this)?( note)?[.!]?\s*$/i;
    function hfStop(msg){
      if(!hf) return;
      hf=false; hfRun++; NSR.stop().catch(()=>{}); if(HF) HF.stopSpeaking().catch(()=>{});
      saveDraft(); hfShow(); if(msg) toast(msg);
    }
    async function hfStart(){
      if(hf) return;
      if(!ready){ if(hfWait++<20) setTimeout(hfStart,500); return; }
      const run=++hfRun; hf=true; showTab('log'); hfShow('Starting…');
      const live=()=>run===hfRun;
      if(listening){ stopAll(); await new Promise(r=>setTimeout(r,500)); }
      try{
        if(typeof locked==='function' && locked()){ showPaywall(); await say('Your free month has ended. Unlock Shift Case Notes to keep adding notes.'); return hfStop(); }
        if(!activeClients().length){ await say('Add a client in the app first.'); return hfStop(); }
        let perm=await NSR.checkPermissions(); if(perm.speechRecognition!=='granted'){ hfAsking=true; try{ perm=await NSR.requestPermissions(); }finally{ hfAsking=false; } }
        if(perm.speechRecognition!=='granted'){ await say('Please allow the microphone for Shift Case Notes.'); return hfStop(); }
        if(!(await NSR.available()).available){ await say('Speech recognition is not available on this phone.'); return hfStop(); }
      }catch{ return hfStop('Hands-free could not start.'); }

      // 1. Who is it for?
      let c=null, start='';
      for(let tries=0; !c && tries<3; tries++){
        hfShow('Say the client’s name');
        await say(tries===0 ? 'Who is the note for?' : tries===1 ? 'Sorry, who is the note for?' : 'Your clients are '+activeClients().map(x=>x.name).join(', ')+'. Who is the note for?');
        if(!live()) return;
        const said=await hear(run); if(said===null) return;
        if(CANCEL.test(said)){ await say('Cancelled.'); return hfStop(); }
        c=findClient(said); if(c) start=afterName(said, c);
      }
      if(!c){ await say('I didn’t catch a client name. Stopping hands-free.'); return hfStop(); }
      if(!live()) return;
      saveDraft(); selected=c.id; ls.set('sel',selected); customWhen=null; $('timeRow').hidden=true; tick();
      $('noteText').value=ls.get('draft:'+selected,''); render();
      const add=t=>{ $('noteText').value=joinText($('noteText').value, tidy(t)); $('noteText').dispatchEvent(new Event('input')); };
      if(start) add(start);

      // 2. Take the note down until "save note".
      hfShow('Note for '+c.name+'. Say “save note” when you’re done.');
      await say('Note for '+c.name+'. Go ahead. Say save note when you’re finished.');
      let quiet=0;
      for(let rounds=0; rounds<60; rounds++){
        if(!live()) return;
        let said=await hear(run); if(said===null) return;
        if(!said.trim()){
          quiet++;
          if(quiet===3){ hfShow('Still listening. Say “save note” to save.'); await say('Still listening. Say save note to save, or keep talking.'); }
          if(quiet>=5){ await say('Stopping hands-free. Your note is kept as a draft.'); return hfStop(); }
          continue;
        }
        quiet=0;
        if(CANCEL.test(said)){ await say('Stopped. Your words are kept as a draft.'); return hfStop(); }
        const done=SAVE.test(said);
        said=said.replace(SAVE,'').trim();
        if(said) add(said);
        hfShow('Note for '+c.name+'. Say “save note” when you’re done.');
        if(done) break;
      }
      if(!live()) return;

      // 3. Save it.
      if(!$('noteText').value.trim()){ await say('There was nothing to save.'); return hfStop(); }
      $('saveNote').disabled=false; $('saveNote').click();
      for(let i=0; i<30 && $('noteText').value.trim(); i++) await new Promise(r=>setTimeout(r,100));
      if($('noteText').value.trim()){ await say('Sorry, the note did not save. It is kept as a draft.'); return hfStop(); }
      await say('Saved for '+c.name+'.');
      hfStop();
    }
    $('hfBtn').addEventListener('click', hfStart);
    $('hfStopBtn').addEventListener('click', ()=>hfStop('Hands-free stopped. Your words are kept as a draft.'));
    $('hfAuto').checked=ls.get('hfAuto',false);
    $('hfAuto').addEventListener('change',()=>ls.set('hfAuto',$('hfAuto').checked));
    btn.addEventListener('click',()=>hfStop(), true);
    if(HF){
      HF.addListener('shortcut', ()=>setTimeout(hfStart,1000));
      HF.addListener('pause', ()=>{ if(hfAsking) return; hfAway=Date.now(); hfStop(); });
      // Start by itself when the app comes back after a while (not after a quick look at another app or a pop-up).
      HF.addListener('resume', ()=>{ if(hfAway && Date.now()-hfAway>60000 && ls.get('hfAuto',false)) setTimeout(hfStart,1000); hfAway=0; });
      HF.takeLaunch().then(r=>{ if((r && r.handsFree) || ls.get('hfAuto',false)) setTimeout(hfStart,1200); }).catch(()=>{});
    }
