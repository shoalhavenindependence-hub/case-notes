  /* ---------- Google Drive: the person's own account ---------- */
  // After a one-time Google sign-in, every change is copied to a "Case Note Keeper"
  // folder in their Drive: one spreadsheet per client plus "All case notes".
  // Each changed client's sheet is rewritten from the notes on this phone.
  const GD = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.GoogleDrive;
  const DRIVE = 'https://www.googleapis.com/drive/v3/files', SHEETS = 'https://sheets.googleapis.com/v4/spreadsheets';
  const FOLDER_MIME = 'application/vnd.google-apps.folder', SHEET_MIME = 'application/vnd.google-apps.spreadsheet';
  const FOLDER_NAME = 'Case Note Keeper';
  const CLIENT_COLS = {head:['Date','Time','Case note','Last edited'], widths:[100,80,520,140], wrap:2};
  const ALL_COLS = {head:['Date','Time','Client','Case note','Last edited'], widths:[100,80,140,520,140], wrap:3};
  const gDate = new Intl.DateTimeFormat(undefined,{day:'2-digit',month:'2-digit',year:'numeric'});
  let gOn = ls.get('gOn', false), gBusy = false, gAgain = false, gTok = null, gTokAt = 0, gTimer = null;
  const gIds = () => ls.get('gIds', {folder:null, all:null, clients:{}});
  const gSaveId = (key, id) => { const ids = gIds(); if(key==='folder'||key==='all') ids[key]=id; else ids.clients[key]=id; ls.set('gIds', ids); };

  function gDirty(cid){ if(!gOn || !cid) return; const d=ls.get('gDirty',[]); if(!d.includes(cid)){ d.push(cid); ls.set('gDirty',d); } gSoon(); }
  function gDirtyAll(){ if(!gOn) return; ls.set('gDirty', [...new Set(clients.map(c=>c.id).concat(notes.map(n=>n.clientId)))]); gSoon(); }
  function gSoon(){ clearTimeout(gTimer); gTimer=setTimeout(gSync, 1500); }

  function gStatus(msg){
    $('driveStatus').textContent = msg;
    $('gSyncNow').hidden = $('gOff').hidden = !gOn;
    const a = gOn && ls.get('gAccount', null);
    $('driveAccount').hidden = !gOn;
    $('driveAccount').innerHTML = !gOn ? '' : a && a.email
      ? `<span class="label">Backing up to this Google account</span>${a.name?`<span class="name">${esc(a.name)}</span>`:''}<span class="email">${esc(a.email)}</span>`
      : `<span class="label">Backing up to your Google Drive</span><span class="name">Connected</span>`;
  }
  function gIdle(){
    const waiting = ls.get('gDirty',[]).length, last = ls.get('gLast',0);
    $('gConnect').hidden = true;
    gStatus(waiting ? `${waiting} ${waiting===1?'client has':'clients have'} changes waiting to back up. They’ll send next time you have signal.`
      : `All notes backed up to the "${FOLDER_NAME}" folder in Google Drive${last?`. Last backup ${fmtTime.format(last)}, ${fmtDate.format(last)}`:''}.`);
  }
  async function gLoadAccount(){
    try{
      const r = await gApi('GET', 'https://www.googleapis.com/drive/v3/about?fields=user(displayName,emailAddress)');
      if(r.user && r.user.emailAddress){ ls.set('gAccount', {name:r.user.displayName||'', email:r.user.emailAddress}); if(!gBusy) gIdle(); }
    }catch(e){}
  }

  async function gToken(interactive){
    if(gTok && Date.now()-gTokAt < 45*60*1000) return gTok;
    const r = await GD.authorize({interactive});
    gTok = r.accessToken; gTokAt = Date.now();
    return gTok;
  }
  async function gApi(method, url, body, retried){
    const tok = await gToken(false);
    const headers = {Authorization:'Bearer '+tok};
    if(body) headers['Content-Type'] = 'application/json';
    const res = await fetch(url, {method, headers, body: body ? JSON.stringify(body) : undefined});
    if(res.status===401 && !retried){ gTok=null; await GD.clearToken({token:tok}).catch(()=>{}); return gApi(method, url, body, true); }
    if(!res.ok){ const e=new Error('http_'+res.status); e.status=res.status; throw e; }
    return res.status===204 ? {} : res.json();
  }
  async function gMeta(id){
    if(!id) return null;
    try{ const f=await gApi('GET', `${DRIVE}/${id}?fields=id,name,trashed`); return f.trashed ? null : f; }
    catch(e){ if(e.status===404) return null; throw e; }
  }
  async function gFind(name, mime, parent){
    const quoted = "'" + name.replace(/\\/g,'\\\\').replace(/'/g,"\\'") + "'";
    const q = [`name=${quoted}`, `mimeType='${mime}'`, 'trashed=false'].concat(parent?[`'${parent}' in parents`]:[]).join(' and ');
    const r = await gApi('GET', `${DRIVE}?fields=files(id)&q=${encodeURIComponent(q)}`);
    return r.files && r.files[0] ? r.files[0].id : null;
  }
  async function gFolder(){
    const known = gIds().folder;
    if(await gMeta(known)) return known;
    const id = await gFind(FOLDER_NAME, FOLDER_MIME) || (await gApi('POST', `${DRIVE}?fields=id`, {name:FOLDER_NAME, mimeType:FOLDER_MIME})).id;
    gSaveId('folder', id);
    return id;
  }
  async function gBook(key, name, folder, cols){
    const ids = gIds(), known = key==='all' ? ids.all : ids.clients[key];
    let id = null, fresh = false;
    const meta = await gMeta(known);
    if(meta){ id = meta.id; if(meta.name!==name) await gApi('PATCH', `${DRIVE}/${id}`, {name}); }
    else {
      id = await gFind(name, SHEET_MIME, folder);
      if(!id){ id = (await gApi('POST', `${DRIVE}?fields=id`, {name, mimeType:SHEET_MIME, parents:[folder]})).id; fresh = true; }
    }
    gSaveId(key, id);
    const sheet = (await gApi('GET', `${SHEETS}/${id}?fields=sheets.properties(sheetId,title)`)).sheets[0].properties;
    if(!fresh) return {id, title: sheet.title};
    const sheetId = sheet.sheetId;
    const requests = [
      {updateSheetProperties:{properties:{sheetId, title:'Notes', gridProperties:{frozenRowCount:1}}, fields:'title,gridProperties.frozenRowCount'}},
      {repeatCell:{range:{sheetId, startRowIndex:0, endRowIndex:1}, cell:{userEnteredFormat:{textFormat:{bold:true}}}, fields:'userEnteredFormat.textFormat.bold'}},
      {repeatCell:{range:{sheetId, startColumnIndex:cols.wrap, endColumnIndex:cols.wrap+1}, cell:{userEnteredFormat:{wrapStrategy:'WRAP', verticalAlignment:'TOP'}}, fields:'userEnteredFormat(wrapStrategy,verticalAlignment)'}}
    ].concat(cols.widths.map((w,i)=>({updateDimensionProperties:{range:{sheetId, dimension:'COLUMNS', startIndex:i, endIndex:i+1}, properties:{pixelSize:w}, fields:'pixelSize'}})));
    await gApi('POST', `${SHEETS}/${id}:batchUpdate`, {requests});
    return {id, title:'Notes'};
  }
  async function gWrite(book, rows){
    const tab = "'" + book.title.replace(/'/g,"''") + "'";
    await gApi('POST', `${SHEETS}/${book.id}/values/${encodeURIComponent(tab)}:clear`, {});
    await gApi('PUT', `${SHEETS}/${book.id}/values/${encodeURIComponent(tab+'!A1')}?valueInputOption=RAW`, {values:rows});
  }
  const gWhen = t => t ? gDate.format(t)+' '+fmtTime.format(t) : '';
  const gName = n => nameOf(n.clientId) || n.clientName || '';
  const oldestFirst = list => list.slice().sort((a,b)=>a.createdAt-b.createdAt);

  async function gSync(){
    if(!GD || !gOn) return;
    if(gBusy){ gAgain=true; return; }
    if(navigator.onLine===false){ gIdle(); return; }
    const dirty = ls.get('gDirty',[]);
    if(!dirty.length){ gIdle(); return; }
    gBusy = true; ls.set('gDirty', []);
    const done = new Set();
    let failed = null;
    gStatus('Backing up to Google Drive…');
    try{
      const folder = await gFolder();
      for(const cid of dirty){
        const list = notes.filter(n=>n.clientId===cid);
        const name = nameOf(cid) || (list[0] && list[0].clientName);
        if(name){
          const book = await gBook(cid, 'Case notes - '+name, folder, CLIENT_COLS);
          await gWrite(book, [CLIENT_COLS.head, ...oldestFirst(list).map(n=>[gDate.format(n.createdAt), fmtTime.format(n.createdAt), n.text, gWhen(n.editedAt)])]);
        }
        done.add(cid);
      }
      const all = await gBook('all', 'All case notes', folder, ALL_COLS);
      await gWrite(all, [ALL_COLS.head, ...oldestFirst(notes).map(n=>[gDate.format(n.createdAt), fmtTime.format(n.createdAt), gName(n), n.text, gWhen(n.editedAt)])]);
      ls.set('gLast', Date.now());
    }catch(e){
      failed = e;
      const back = ls.get('gDirty',[]);
      dirty.forEach(cid=>{ if(!done.has(cid) && !back.includes(cid)) back.push(cid); });
      if(!back.length && dirty.length) back.push(dirty[0]); // the All case notes file still needs writing
      ls.set('gDirty', back);
    }finally{
      gBusy = false;
      if(!failed) gIdle();
      else if(failed.code==='consent_required'){ $('gConnect').hidden=false; gStatus('Google needs you to sign in again. Tap Connect Google Drive. Your notes are safe on this phone in the meantime.'); }
      else gStatus(`Could not reach Google Drive${failed.status?` (error ${failed.status})`:''}. Notes will back up next time you open the app with signal.`);
      if(gAgain){ gAgain=false; gSoon(); }
    }
  }

  async function gConnect(){
    $('gConnect').disabled = true; $('gWelcome').hidden = true; ls.set('gAsked', true);
    gStatus('Opening Google sign-in…');
    try{
      gTok = null;
      await gToken(true);
      gOn = true; ls.set('gOn', true);
      ls.set('gAccount', null); gLoadAccount();
      toast('Connected to Google Drive'); $('storeBanner').hidden = true;
      gDirtyAll(); gSync();
    }catch(e){
      $('gConnect').hidden = false;
      gStatus(e && e.code==='cancelled' ? 'Not connected. Tap Connect Google Drive to try again.' : 'Google sign-in did not work. Check your connection and try again.');
    }finally{ $('gConnect').disabled = false; }
  }
  if(GD){
    $('gConnect').addEventListener('click', gConnect);
    $('gWelcomeYes').addEventListener('click', gConnect);
    $('gWelcomeNo').addEventListener('click', ()=>{ $('gWelcome').hidden=true; ls.set('gAsked', true); });
    $('gSyncNow').addEventListener('click', ()=>{ gDirtyAll(); gSync(); });
    $('gOff').addEventListener('click', ()=>{
      gOn=false; gTok=null; ls.set('gOn', false); ls.set('gDirty', []);
      $('gConnect').hidden=false; gStatus('Disconnected. Your notes are stored on this phone only. Notes already in Google Drive stay there.');
    });
    if(gOn){ gIdle(); if(!ls.get('gAccount', null)) setTimeout(gLoadAccount, 1500); } else { $('gConnect').hidden=false; gStatus($('driveStatus').textContent); if(!ls.get('gAsked', false)) $('gWelcome').hidden=false; }
    window.addEventListener('online', gSync);
    document.addEventListener('visibilitychange', ()=>{ if(document.visibilityState==='visible') gSync(); });
    setInterval(gSync, 5*60*1000);
  } else $('drivePanel').hidden = true;
