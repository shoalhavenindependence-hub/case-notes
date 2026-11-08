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

# --- dictation: Android's own speech recognition when running as the Play Store app ---
tidy = re.search(r"    // Rambler-style clean-up.*?\n    function tidy\(t\)\{.*?\n    \}\n", s, re.S).group(0)
native = '''  const NSR = window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform() && window.Capacitor.Plugins.SpeechRecognition;
  if (NSR) {
    const btn=$('recBtn'); btn.hidden=false;
    let listening=false, base='', cur='', quiet=0, restarts=0, hooked=false;
    const setBtn=on=>{ btn.classList.toggle('on',on); btn.textContent=on?'■ Stop':'● Dictate'; };
    const joinText=(a,b)=>!a?b:(!b?a:a.replace(/\\s*$/,' ')+b.replace(/^\\s+/,''));
''' + tidy + '''    const show=()=>{ $('noteText').value=joinText(base,cur); $('noteText').dispatchEvent(new Event('input')); };
    const stopAll=msg=>{ listening=false; NSR.stop().catch(()=>{}); setBtn(false); if(msg) toast(msg); };
    async function hook(){
      if(hooked) return; hooked=true;
      await NSR.addListener('partialResults', d=>{ if(d && d.matches && d.matches[0]){ cur=d.matches[0]; quiet=0; show(); } });
      await NSR.addListener('listeningState', d=>{
        if(!d || d.status!=='stopped') return;
        if(cur){ base=joinText(base, tidy(cur)); cur=''; show(); } else quiet++;
        // Android stops after each pause; carry on until Stop, and give up after two quiet rounds.
        if(listening && quiet<2 && restarts<30){ restarts++; setTimeout(()=>{ if(listening) startOnce(); },300); }
        else if(listening){ listening=false; setBtn(false); }
      });
    }
    function startOnce(){ NSR.start({language:'en-AU', maxResults:1, partialResults:true, popup:false}).catch(()=>stopAll('Dictation stopped. Tap Dictate to carry on.')); }
    btn.addEventListener('click',async()=>{
      if(!selected){ toast('Pick a client first'); return; }
      if(listening){ stopAll(); return; }
      try{
        const ok=await NSR.available(); if(!ok.available){ toast('Speech recognition is not available on this phone. Use the keyboard microphone.'); return; }
        let perm=await NSR.checkPermissions(); if(perm.speechRecognition!=='granted') perm=await NSR.requestPermissions();
        if(perm.speechRecognition!=='granted'){ toast('Allow the microphone for Case Note Keeper in your phone settings to use Dictate.'); return; }
        await hook();
      }catch{ toast('Dictation could not start. Use the keyboard microphone.'); return; }
      base=$('noteText').value; cur=''; quiet=0; restarts=0; listening=true; setBtn(true); toast('Listening… speak now');
      startOnce();
    });
  } else '''
sub("  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;\n  if (SR) {",
    "  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;\n" + native + "if (SR) {")
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
  const TRIAL_DAYS = 30;
  const PRODUCT_ID = 'full_unlock';
  let firstOpen = ls.get('firstOpen', 0); if(!firstOpen){ firstOpen=Date.now(); ls.set('firstOpen', firstOpen); }
  let unlocked = ls.get('unlocked', false);
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
    if(!window.CdvPurchase) return;
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
