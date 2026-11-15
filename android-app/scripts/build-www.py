#!/usr/bin/env python3
"""Builds android-app/www/index.html from the web app (../index.html).

The Play Store app shares the web app's screens and logic, with these changes:
- no web-install bits (manifest, service worker)
- Google Drive sync signs in with the person's Google account instead of an Apps Script link
- Dictate uses Android's own speech recognition
- a free trial, then a Google Play purchase to keep adding notes
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
src = (ROOT / 'index.html').read_text()
s = src
FOUNDER_URL = re.search(r"const AI_URL = '([^']+)'", src).group(1)

def cut(text, start, end, repl='', include_end=False):
    i = text.index(start)
    j = text.index(end, i)
    if include_end:
        j += len(end)
    return text[:i] + repl + text[j:]

def sub(old, new, count=1):
    global s
    if old not in s:
        sys.exit('build-www: expected text not found: ' + old[:70])
    s = s.replace(old, new, count)

# --- web-install bits ---
sub('<link rel="manifest" href="manifest.webmanifest">\n', '')
sub('<link rel="apple-touch-icon" href="icon-192.png">\n', '')
sub('<link rel="icon" href="icon-192.png">\n', '')
sub("  if('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(()=>{});\n", '')

# --- Google Drive: Apps Script sync -> sign in with Google (scripts/drive-sync.js) ---
s = cut(s, '    <!-- drive panel -->\n', '    <!-- /drive panel -->\n', """    <div class="pad" id="drivePanel">
      <h2>Back up notes to Google Drive</h2>
      <p class="hint">Your notes are stored on this phone. Back them up to Google Drive so they’re safe if your phone is lost, broken or replaced. Every note you save, edit or delete is backed up automatically, with a spreadsheet for each client.</p>
      <div class="account" id="driveAccount" hidden></div>
      <p class="hint" id="driveStatus">Not backed up yet. Tap Connect Google Drive and choose your Google account.</p>
      <div class="row">
        <button class="btn primary" id="gConnect">Connect Google Drive</button>
        <button class="btn small" id="gSyncNow" hidden>Back up everything again</button>
        <button class="btn small" id="gOff" hidden>Disconnect</button>
      </div>
    </div>
""")
s = cut(s, '  /* ---------- Google Drive sync ---------- */', '  store={', (ROOT / 'android-app' / 'scripts' / 'drive-sync.js').read_text())
sub(" if(drive){ queueUp(n.id); setTimeout(flushDrive,50); }", ' gDirty(n.clientId);')
sub(" if(drive){ queueDel(id); setTimeout(flushDrive,50); }", ' gDirty((notes.find(x=>x.id===id)||{}).clientId);')
sub("store.saveClients(clients).then(()=>toast('Renamed'));", "store.saveClients(clients).then(()=>toast('Renamed')); gDirty(viewClient);")
sub("  flushDrive();\n", '  if(typeof gSync==="function") gSync();\n')
sub('<div class="toast" id="toast" hidden></div>', """<div class="toast" id="toast" hidden></div>
<div class="paywall" id="gWelcome" hidden role="dialog" aria-modal="true" aria-labelledby="gWelcomeTitle">
  <div class="pad paycard">
    <h2 id="gWelcomeTitle">Sign in with Google</h2>
    <p class="hint">Sign in with Google to back up your notes to Drive. Every note is backed up automatically, with a spreadsheet for each client, so your notes are safe if your phone is lost or replaced. You can change this any time in the History tab.</p>
    <div class="row">
      <button class="btn primary" id="gWelcomeYes">Sign in with Google</button>
      <button class="btn small" id="gWelcomeNo">Not now</button>
    </div>
  </div>
</div>""")

# --- the reminder banner follows Google sign-in instead of the Apps Script link ---
sub("if(notes.length && !drive){", "if(notes.length && GD && !gOn){")

# --- dictation on Android (2026-11-15, version 52): the app's own Dictation plugin keeps listening
#     through pauses by itself; here it is dressed up as Chrome's speech recognition, so the Play app
#     runs exactly the same Dictate code (sentence breaks, beep, 30 s quiet stop) as the web app ---
sub("  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;\n",
"""  const DictationNative = window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()
    && window.Capacitor.getPlatform()==='android' && window.Capacitor.Plugins && window.Capacitor.Plugins.Dictation;
  let micAsked=false;
  // Behaves like Chrome's speech recognition on an Android phone: one long, growing result
  // (every finished phrase plus the words being spoken now) until Stop, or 30 seconds of quiet.
  class AndroidSR {
    constructor(){ this.lang='en-AU'; this.continuous=true; this.interimResults=true; this.maxAlternatives=1;
      this._fin=[]; this._part=''; this._h=null; this._done=false; this._quiet=null; this._heard=0; }
    _emit(){
      this._heard=Date.now();
      const text=this._fin.concat(this._part?[this._part]:[]).join(' ').replace(/\\s+/g,' ').trim();
      const r=Object.assign([{transcript:text}],{isFinal:false});
      if(this.onresult) this.onresult({resultIndex:0, results:[r]});
    }
    _end(){
      if(this._done) return; this._done=true; clearInterval(this._quiet);
      const h=this._h; this._h=null; if(h) Promise.resolve(h).then(x=>x.remove()).catch(()=>{});
      if(this.onend) this.onend();
    }
    async start(){
      const P=window.Capacitor.Plugins.SpeechRecognition;
      if(!micAsked && P){ try{ let p=await P.checkPermissions(); if(p.speechRecognition!=='granted') p=await P.requestPermissions(); micAsked=true;
        if(p.speechRecognition!=='granted'){ micAsked=false; if(this.onerror) this.onerror({error:'not-allowed'}); this._end(); return; } }catch{} }
      if(this._done) return;
      this._h=DictationNative.addListener('dictation', d=>{
        if(this._done||!d) return;
        if(d.type==='partial'){ this._part=d.text||''; this._emit(); }
        else if(d.type==='final'){ this._part=''; if(d.text) this._fin.push(d.text); this._emit(); }
        else if(d.type==='error'){
          const e={9:'not-allowed',3:'audio-capture',1:'network',2:'network'}[d.code]||'aborted';
          if(this.onerror) this.onerror({error:e});
        }
        else if(d.type==='end') this._end();
      });
      this._heard=Date.now();
      // The phone keeps listening by itself, so the 30 seconds of quiet are counted here.
      this._quiet=setInterval(()=>{ if(Date.now()-this._heard>=30000){ DictationNative.abort().catch(()=>{}); this._end(); } },1000);
      try{ await this._h; if(this._done) return; await DictationNative.start({lang:this.lang}); }
      catch{ if(this.onerror) this.onerror({error:'aborted'}); this._end(); }
    }
    stop(){ DictationNative.stop().catch(()=>{}); }
    abort(){ DictationNative.abort().catch(()=>{}); this._end(); }
  }
  // iPhone (2026-11-15): Apple's speech recognition (the SpeechRecognition plugin) dressed up the same way,
  // so the iPhone app runs exactly the same Dictate code as the web app and the Play app.
  const IosNSR = window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()
    && window.Capacitor.getPlatform()==='ios' && window.Capacitor.Plugins && window.Capacitor.Plugins.SpeechRecognition;
  class IosSR {
    constructor(){ this.lang='en-AU'; this.continuous=true; this.interimResults=true; this.maxAlternatives=1;
      this._text=''; this._hs=[]; this._done=false; this._quiet=null; this._heard=0; }
    _end(){
      if(this._done) return; this._done=true; clearInterval(this._quiet);
      const hs=this._hs; this._hs=[]; hs.forEach(h=>Promise.resolve(h).then(x=>x.remove()).catch(()=>{}));
      if(this.onend) this.onend();
    }
    async start(){
      if(!micAsked){ try{ let p=await IosNSR.checkPermissions(); if(p.speechRecognition!=='granted') p=await IosNSR.requestPermissions(); micAsked=true;
        if(p.speechRecognition!=='granted'){ micAsked=false; if(this.onerror) this.onerror({error:'not-allowed'}); this._end(); return; } }catch{} }
      if(this._done) return;
      this._hs.push(IosNSR.addListener('partialResults', d=>{
        if(this._done || !d || !d.matches || !d.matches[0]) return;
        this._text=d.matches[0]; this._heard=Date.now();
        const r=Object.assign([{transcript:this._text}],{isFinal:false});
        if(this.onresult) this.onresult({resultIndex:0, results:[r]});
      }));
      this._hs.push(IosNSR.addListener('listeningState', d=>{ if(d && d.status==='stopped') this._end(); }));
      this._heard=Date.now();
      // Count the 30 seconds of quiet here too, as the phone may keep listening by itself.
      this._quiet=setInterval(()=>{ if(Date.now()-this._heard>=30000){ IosNSR.stop().catch(()=>{}); this._end(); } },1000);
      try{ await Promise.all(this._hs); if(this._done) return;
        await IosNSR.start({language:this.lang, maxResults:1, partialResults:true, popup:false}); }
      catch{ if(this.onerror) this.onerror({error:'aborted'}); this._end(); }
    }
    stop(){ IosNSR.stop().catch(()=>{}); }
    abort(){ IosNSR.stop().catch(()=>{}); this._end(); }
  }
  const SR = DictationNative ? AndroidSR : IosNSR ? IosSR : (window.SpeechRecognition || window.webkitSpeechRecognition);
""")


# Keep the iPhone screen on while dictating, so the phone doesn't sleep and cut the recording off.
sub("    const setBtn=on=>{ btn.classList.toggle('on',on); btn.textContent=on?'■ Stop':'● Dictate'; };\n    const joinText=(a,b)=>!a?b:(!b?a:a.replace(/[ \\t]*$/",
    "    const setBtn=on=>{ btn.classList.toggle('on',on); btn.textContent=on?'■ Stop':'● Dictate';\n      try{ const C=window.Capacitor; if(C && C.getPlatform && C.getPlatform()==='ios'){ const L=(C.Plugins&&C.Plugins.AppLock)||C.registerPlugin('AppLock'); L.keepAwake({on}).catch(()=>{}); } }catch{} };\n    const joinText=(a,b)=>!a?b:(!b?a:a.replace(/[ \\t]*$/")
sub('Microphone is blocked. In Chrome, go to Settings, Site settings, Microphone and allow this app. Also check Chrome itself is allowed the microphone in your phone settings.',
    'Microphone is blocked. Allow the microphone for Case Note Keeper in your phone settings.')

# --- free trial, then a Google Play purchase ---
sub('<div class="toast" id="toast" hidden></div>', '''<div class="toast" id="toast" hidden></div>
<div class="paywall" id="paywall" hidden role="dialog" aria-modal="true" aria-labelledby="payTitle">
  <div class="pad paycard">
    <h2 id="payTitle">Your free month has ended</h2>
    <p class="hint" id="payText">Unlock Case Note Keeper to keep logging notes. Your saved notes stay on this phone and in your Google Drive, and you can still read them.</p>
    <div class="row">
      <button class="btn primary" id="buyBtn">Unlock</button>
      <button class="btn small" id="restoreBuy">I've already paid</button>
    </div>
    <button class="btn small" id="payLater">Not now</button>
  </div>
</div>''')
sub('</style>', '''.paywall{position:fixed;inset:0;z-index:30;background:color-mix(in srgb,var(--card-ink) 55%,transparent);display:flex;align-items:flex-end;justify-content:center;padding:16px;padding-bottom:calc(16px + env(safe-area-inset-bottom,0px))}
.paycard{max-width:560px;width:100%}
.trial{font-size:.85rem;color:var(--muted)}
</style>''')
sub('''  showTab(ls.get('tab','log'));
''', '''  showTab(ls.get('tab','log'));

  /* ---------- free trial and purchase (Google Play or the App Store) ---------- */
  // Launch is free (Mark's decision, 2026-11-08): no trial, no paywall.
  // The first 50 iPhones and first 50 Android phones become founding members, free for one year
  // from the day they joined (Mark changed this from free for life on 2026-11-15).
  // (numbered by the Carla script, debrief-ai/Code.gs, action 'founder'; testers count too).
  const FREE_LAUNCH = true;
  const FOUNDER_URL = '__FOUNDER_URL__';
  const founderUntil=()=>{ if(!ls.get('founder',null)) return 0; let s=ls.get('founderSince',0); if(!s){ s=Date.now(); ls.set('founderSince',s); } return s+365*864e5; };
  function showFounder(){ const f=ls.get('founder',null); if(!f) return; const el=$('founderNote'); el.hidden=false;
    const until=founderUntil(); el.textContent='\u2605 Founding member #'+f+(Date.now()<until ? ' \u00b7 free until '+new Date(until).toLocaleDateString('en-AU',{day:'numeric',month:'long',year:'numeric'}) : ''); }
  (async()=>{
    const C=window.Capacitor; if(!(C && C.isNativePlatform && C.isNativePlatform())) return;
    if(ls.get('founderAsked',false)){ showFounder(); return; }
    try{
      let d=ls.get('deviceId',null); if(!d){ d=(crypto.randomUUID ? crypto.randomUUID() : uidGen()+uidGen()); ls.set('deviceId',d); }
      const res=await fetch(FOUNDER_URL,{method:'POST',headers:{'Content-Type':'text/plain;charset=utf-8'},body:JSON.stringify({action:'founder',device:d,platform:C.getPlatform()})});
      const j=await res.json();
      if(j && typeof j.founder==='boolean'){
        ls.set('founderAsked',true);
        if(j.founder){ ls.set('founder',j.number); if(!ls.get('founderSince',0)) ls.set('founderSince',Date.now()); showFounder(); toast('Welcome, founding member #'+j.number+'! Case Note Keeper is free for you for a year.'); }
      }
    }catch{}
  })();
  const TRIAL_DAYS = 30;
  const PRODUCT_ID = 'full_unlock';
  let firstOpen = ls.get('firstOpen', 0); if(!firstOpen){ firstOpen=Date.now(); ls.set('firstOpen', firstOpen); }
  let unlocked = ls.get('unlocked', false) || Date.now() < founderUntil();
  const daysLeft = () => Math.max(0, Math.ceil(TRIAL_DAYS - (Date.now()-firstOpen)/864e5));
  const locked = () => !unlocked && daysLeft()===0 && !!window.CdvPurchase;
  function showPaywall(){ $('paywall').hidden=false; }
  $('payLater').addEventListener('click',()=>{ $('paywall').hidden=true; });
  // Block new notes (not reading or exporting) once the trial is over.
  $('saveNote').addEventListener('click', e=>{ if(locked()){ e.stopImmediatePropagation(); showPaywall(); } }, true);
  function trialNote(){
    const b=$('storeBanner');
    if(unlocked || !window.CdvPurchase) return;
    const d=daysLeft();
    if(d===0){ b.hidden=false; b.textContent='Your free month has ended. Tap here to unlock Case Note Keeper.'; b.onclick=showPaywall; }
    else if(d<=5){ b.hidden=false; b.textContent=d+(d===1?' day':' days')+' left in your free month. Tap here to unlock.'; b.onclick=showPaywall; }
  }
  document.addEventListener('deviceready', ()=>{
    if(!window.CdvPurchase || FREE_LAUNCH) return;
    const { store, ProductType, Platform } = CdvPurchase;
    // iPhone app buys through Apple's App Store, Android app through Google Play.
    const IOS = window.Capacitor && window.Capacitor.getPlatform && window.Capacitor.getPlatform()==='ios';
    const PF = IOS ? Platform.APPLE_APPSTORE : Platform.GOOGLE_PLAY, SHOP = IOS ? 'The App Store' : 'Google Play';
    store.register([{ id: PRODUCT_ID, type: ProductType.NON_CONSUMABLE, platform: PF }]);
    const refresh=()=>{
      const p=store.get(PRODUCT_ID, PF);
      if(p && p.owned){ unlocked=true; ls.set('unlocked',true); $('paywall').hidden=true; $('storeBanner').hidden=true; }
      const price=p && p.pricing && p.pricing.price;
      if(price){ $('buyBtn').textContent='Unlock for '+price; $('payText').textContent='Unlock Case Note Keeper for a one-off '+price+' to keep logging notes. Your saved notes stay on this phone'+(GD?' and in your Google Drive':'')+', and you can still read them.'; }
    };
    store.when().approved(t=>t.finish()).finished(()=>{ refresh(); toast('Thanks! Case Note Keeper is unlocked.'); }).productUpdated(refresh);
    store.initialize([PF]).then(()=>{ refresh(); trialNote(); });
    $('buyBtn').addEventListener('click',()=>{
      const offer=store.get(PRODUCT_ID, PF)?.getOffer();
      if(!offer){ toast(SHOP+' is not ready yet. Check your connection and try again.'); return; }
      offer.order().then(err=>{ if(err && err.code!==CdvPurchase.ErrorCode.PAYMENT_CANCELLED) toast('The purchase did not go through. Please try again.'); });
    });
    $('restoreBuy').addEventListener('click',()=>{ store.restorePurchases().then(()=>{ refresh(); if(!unlocked) toast(IOS?'No purchase found for this Apple ID.':'No purchase found for this Google account.'); }); });
  }, false);
''')

# --- founding members: badge under the tabs, and the Carla script's URL ---
s = s.replace("__FOUNDER_URL__", FOUNDER_URL)
sub('  <div id="storeBanner" class="banner" hidden></div>', '  <div id="storeBanner" class="banner" hidden></div>\n  <p class="trial founder" id="founderNote" hidden></p>')
sub('</style>', '.founder{text-align:center;margin:4px 0 0;font-weight:600}\n</style>')

# --- iPhone: Carla's listening ---
# iOS speech recognition never finishes by itself, so listen with live words
# and stop after a short pause (Android keeps its own behaviour).
sub("      if(NSR){ const r = await NSR.start({language:'en-AU', maxResults:1, partialResults:false, popup:false}); return (r && r.matches && r.matches[0]) || ''; }",
"""      if(NSR && window.Capacitor.getPlatform()==='ios') return new Promise(async res=>{
        let txt='', last=Date.now(), done=false, h=null;
        const finish=async()=>{ if(done) return; done=true; clearInterval(t); try{ await NSR.stop(); }catch{} try{ h && h.remove(); }catch{} res(txt); };
        const t=setInterval(()=>{ const idle=Date.now()-last; if(!on || (txt && idle>1500) || (!txt && idle>9000)) finish(); }, 250);
        try{ h=await NSR.addListener('partialResults', d=>{ const m=d && d.matches && d.matches[0]; if(m && m!==txt){ txt=m; last=Date.now(); status('“'+m+'”'); } });
             await NSR.start({language:'en-AU', maxResults:1, partialResults:true, popup:false}); }
        catch(e){ finish(); }
      });
      if(NSR){ const r = await NSR.start({language:'en-AU', maxResults:1, partialResults:false, popup:false}); return (r && r.matches && r.matches[0]) || ''; }""")

# --- iPhone: Face ID lock ---
# Find the app's own AppLock plugin even if it isn't pre-attached, let iOS itself
# decide (Face ID, or the passcode), and show iOS's reason if it says no.
sub("  const NativeLock = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.AppLock;",
    "  const IOS_APP = !!(window.Capacitor && window.Capacitor.getPlatform && window.Capacitor.getPlatform()==='ios');\n"
    "  const NativeLock = window.Capacitor && ((window.Capacitor.Plugins && window.Capacitor.Plugins.AppLock) || (IOS_APP && window.Capacitor.registerPlugin ? window.Capacitor.registerPlugin('AppLock') : null));")
sub("      if(NativeLock) return (await NativeLock.available()).available;",
    "      if(NativeLock && IOS_APP) return true;\n      if(NativeLock) return (await NativeLock.available()).available;")
sub("    }catch(e){ toast('The lock was not turned on. Try again.'); }",
    "    }catch(e){ toast(IOS_APP && e && e.message ? 'The lock was not turned on: '+e.message : 'The lock was not turned on. Try again.'); }")

# --- iPhone: say Face ID instead of fingerprint ---
sub('</body>', """<script>
(function(){
  if(!(window.Capacitor && window.Capacitor.getPlatform && window.Capacitor.getPlatform()==='ios')) return;
  const swaps=[[/your fingerprint \\(or your phone’s PIN\\)/g,'Face ID (or your passcode)'],[/your fingerprint or your phone’s PIN/g,'Face ID or your passcode'],
    [/a fingerprint or screen lock/g,'Face ID or a passcode'],[/with your fingerprint/g,'with Face ID'],[/your fingerprint/g,'Face ID'],[/Fingerprint/g,'Face ID'],[/fingerprint/g,'Face ID']];
  const fix=n=>{ if(n.nodeType===3){ let v=n.nodeValue, w=v; if(!/ingerprint/.test(v)) return; swaps.forEach(([a,b])=>{ w=w.replace(a,b); }); if(w!==v) n.nodeValue=w; } else if(n.childNodes) n.childNodes.forEach(fix); };
  fix(document.body);
  new MutationObserver(ms=>ms.forEach(m=>{ if(m.type==='characterData') fix(m.target); else m.addedNodes.forEach(fix); })).observe(document.body,{subtree:true,childList:true,characterData:true});
})();
</script>
</body>""")

out = ROOT / 'android-app' / 'www' / 'index.html'
out.write_text(s)
print('wrote', out.relative_to(ROOT), len(s), 'bytes')
