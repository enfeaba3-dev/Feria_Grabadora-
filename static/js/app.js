'use strict';

const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

let config=structuredClone(window.FERIA_BOOTSTRAP||{});
let activeLog='app';
let hotkeyCapture=false;
let selectedFile=null;
let stream=null;
let recorder=null;
let audioContext=null;
let analyser=null;
let segmentTimer=null;
let clockTimer=null;
let recordingStartedAt=0;
let isRecording=false;
let liveQueue=[];
let queueRunning=false;
let currentSession=0;
let nextChunkIndex=1;
let captureEnded=true;

const elements={
  pageTitle:$('#pageTitle'),runtimePill:$('#runtimePill'),refreshButton:$('#refreshButton'),
  sidebarDot:$('#sidebarDot'),sidebarStatus:$('#sidebarStatus'),sidebarSubstatus:$('#sidebarSubstatus'),
  dictationEnabled:$('#dictationEnabled'),hotkeyInput:$('#hotkeyInput'),captureHotkeyButton:$('#captureHotkeyButton'),
  inputDeviceSelect:$('#inputDeviceSelect'),microphoneHint:$('#microphoneHint'),
  globalModelSelect:$('#globalModelSelect'),globalLanguageSelect:$('#globalLanguageSelect'),globalDeviceSelect:$('#globalDeviceSelect'),
  autoPasteToggle:$('#autoPasteToggle'),clipboardToggle:$('#clipboardToggle'),overlayToggle:$('#overlayToggle'),
  saveConfigButton:$('#saveConfigButton'),restartAgentButton:$('#restartAgentButton'),
  hotkeyDisplay:$('#hotkeyDisplay'),capsuleState:$('#capsuleState'),agentBadge:$('#agentBadge'),agentTitle:$('#agentTitle'),
  agentDescription:$('#agentDescription'),statusHotkey:$('#statusHotkey'),statusModel:$('#statusModel'),statusDevice:$('#statusDevice'),statusHeartbeat:$('#statusHeartbeat'),
  modelSelect:$('#modelSelect'),languageSelect:$('#languageSelect'),deviceSelect:$('#deviceSelect'),
  recordButton:$('#recordButton'),recordingLabel:$('#recordingLabel'),timer:$('#timer'),waveform:$('#waveform'),recordHint:$('#recordHint'),
  fileInput:$('#fileInput'),dropzone:$('#dropzone'),selectedFileBox:$('#selectedFile'),fileName:$('#fileName'),fileSize:$('#fileSize'),
  removeFile:$('#removeFile'),transcribeFileButton:$('#transcribeFileButton'),
  transcriptText:$('#transcriptText'),statusChip:$('#statusChip'),modelChip:$('#modelChip'),deviceChip:$('#deviceChip'),
  progressLine:$('#progressLine'),progressPercent:$('#progressPercent'),errorMessage:$('#errorMessage'),clearButton:$('#clearButton'),copyButton:$('#copyButton'),downloadTxtButton:$('#downloadTxtButton'),downloadPdfButton:$('#downloadPdfButton'),downloadDocxButton:$('#downloadDocxButton'),cancelButton:$('#cancelButton'),modelLoading:$('#modelLoading'),
  modelLoaderPanel:$('#modelLoaderPanel'),modelLoaderTitle:$('#modelLoaderTitle'),modelLoaderDetail:$('#modelLoaderDetail'),modelLoaderName:$('#modelLoaderName'),modelLoaderElapsed:$('#modelLoaderElapsed'),modelLoaderBar:$('#modelLoaderBar'),modelLoaderPercent:$('#modelLoaderPercent'),
  runDiagnosticsButton:$('#runDiagnosticsButton'),diagnosticList:$('#diagnosticList'),diagStatus:$('#diagStatus'),diagErrors:$('#diagErrors'),diagWarnings:$('#diagWarnings'),diagChecks:$('#diagChecks'),diagnosticBadge:$('#diagnosticBadge'),
  logViewer:$('#logViewer'),refreshLogsButton:$('#refreshLogsButton'),openLogsButton:$('#openLogsButton'),toastStack:$('#toastStack'),
  themeToggleButton:$('#themeToggleButton'),gpuPill:$('#gpuPill'),gpuName:$('#gpuName'),gpuStats:$('#gpuStats'),
  historyList:$('#historyList'),historySearch:$('#historySearch'),refreshHistoryButton:$('#refreshHistoryButton'),
  webMicSelect:$('#webMicSelect'),webMicHint:$('#webMicHint'),
};

function clientLog(level,message,context={}){
  try{
    const payload=JSON.stringify({level,message,context:{...context,url:location.href,userAgent:navigator.userAgent}});
    navigator.sendBeacon('/api/client-log',new Blob([payload],{type:'application/json'}));
  }catch{}
}

let abortController=null;
let transcribiendo=false;

function cancelTranscription(){
  if(abortController){abortController.abort();abortController=null;}
  transcribiendo=false;
  elements.cancelButton.classList.add('hidden');
  setTranscriptionStatus('Cancelado','idle');
  showTranscriptionError('');
  toast('Transcripción cancelada.','error');
}

window.addEventListener('error',event=>clientLog('error',event.message,{source:event.filename,line:event.lineno,column:event.colno,stack:event.error?.stack}));
window.addEventListener('unhandledrejection',event=>clientLog('error','Promise rechazada',{reason:String(event.reason),stack:event.reason?.stack}));

async function fetchJson(url,options={}){
  const response=await fetch(url,options);
  let data;
  try{data=await response.json();}
  catch{throw new Error(`Respuesta no válida del servidor (${response.status}).`);}
  if(!response.ok){
    const error=data.error;
    const message=typeof error==='object'?error.message:error;
    const code=typeof error==='object'?error.code:'HTTP_ERROR';
    const requestId=data.request_id||response.headers.get('X-Request-ID');
    const exception=new Error(`${message||`Error ${response.status}`}${requestId?` · ID ${requestId}`:''}`);
    exception.code=code;exception.requestId=requestId;throw exception;
  }
  return data;
}

function toast(message,type='info',duration=3600){
  const item=document.createElement('div');
  item.className=`toast ${type}`;item.textContent=message;
  elements.toastStack.appendChild(item);
  setTimeout(()=>item.remove(),duration);
}

function setView(name){
  $$('.nav-item').forEach(button=>button.classList.toggle('active',button.dataset.view===name));
  $$('.view').forEach(view=>view.classList.toggle('active',view.id===`${name}View`));
  const titles={dictation:'Dictado global',transcribe:'Transcribir',diagnostics:'Diagnóstico'};
  elements.pageTitle.textContent=titles[name]||'Feria Transcriber';
  if(name==='diagnostics')refreshLogs();
  history.replaceState(null,'',`#${name}`);
}

$$('.nav-item').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.view)));
const initialView=location.hash.replace('#','');
if(['dictation','transcribe','diagnostics'].includes(initialView))setView(initialView);

for(let i=0;i<28;i++){
  const bar=document.createElement('i');
  bar.style.animationDelay=`${i*0.035}s`;
  $('#miniWave').appendChild(bar);
}
for(let i=0;i<52;i++)elements.waveform.appendChild(document.createElement('i'));
const waveBars=[...elements.waveform.children];

function applyConfig(next){
  config=structuredClone(next);
  const d=config.dictation||{};
  elements.dictationEnabled.checked=Boolean(d.enabled);
  elements.hotkeyInput.value=d.hotkey||'f8';
  elements.hotkeyDisplay.textContent=(d.hotkey||'f8').toUpperCase();
  elements.globalModelSelect.value=config.model||'large-v3-turbo';
  elements.globalLanguageSelect.value=config.language||'';
  elements.globalDeviceSelect.value=config.device||'auto';
  elements.autoPasteToggle.checked=d.auto_paste!==false;
  elements.clipboardToggle.checked=d.copy_to_clipboard!==false;
  elements.overlayToggle.checked=d.show_overlay!==false;
  elements.inputDeviceSelect.value=d.input_device??'';
  elements.modelSelect.value=config.model||'large-v3-turbo';
  elements.languageSelect.value=config.language||'';
  elements.deviceSelect.value=config.device||'auto';
  elements.statusHotkey.textContent=(d.hotkey||'f8').toUpperCase();
  elements.statusModel.textContent=config.model||'large-v3-turbo';
  elements.statusDevice.textContent=deviceLabel(config.device);
  elements.modelChip.textContent=config.model||'large-v3-turbo';
  elements.deviceChip.textContent=deviceLabel(config.device);
}

function collectConfig(){
  const inputDevice=elements.inputDeviceSelect.value;
  return {
    ...config,
    model:elements.globalModelSelect.value,
    language:elements.globalLanguageSelect.value,
    device:elements.globalDeviceSelect.value,
    dictation:{
      ...(config.dictation||{}),
      enabled:elements.dictationEnabled.checked,
      hotkey:elements.hotkeyInput.value.trim().toLowerCase(),
      input_device:inputDevice===''?null:Number(inputDevice),
      auto_paste:elements.autoPasteToggle.checked,
      copy_to_clipboard:elements.clipboardToggle.checked,
      show_overlay:elements.overlayToggle.checked,
    },
  };
}

function deviceLabel(value){
  return value==='cuda'?'GPU NVIDIA':value==='cpu'?'CPU':'Automático';
}

async function loadAudioDevices(){
  try{
    const current=config.dictation?.input_device;
    const data=await fetchJson('/api/audio-devices');
    elements.inputDeviceSelect.innerHTML='<option value="">Predeterminado del sistema</option>';
    data.devices.forEach(device=>{
      const option=document.createElement('option');
      option.value=device.id;option.textContent=device.name;
      elements.inputDeviceSelect.appendChild(option);
    });
    elements.inputDeviceSelect.value=current??'';
    elements.microphoneHint.textContent=`${data.devices.length} entrada(s) detectada(s).`;
  }catch(error){
    elements.microphoneHint.textContent=error.message;
    clientLog('warning','No se pudieron cargar micrófonos',{error:error.message});
  }
}

function mapHotkeyEvent(event){
  const codeMap={
    Insert:'insert',Home:'home',End:'end',PageUp:'page up',PageDown:'page down',Pause:'pause',ScrollLock:'scroll lock',
    ControlRight:'right ctrl',AltRight:'right alt',
  };
  let trigger='';
  if(/^F([1-9]|1[0-2])$/.test(event.code))trigger=event.code.toLowerCase();
  else trigger=codeMap[event.code]||'';
  if(!trigger)return '';
  const parts=[];
  if(event.ctrlKey&&trigger!=='right ctrl')parts.push('ctrl');
  if(event.altKey&&trigger!=='right alt')parts.push('alt');
  if(event.shiftKey)parts.push('shift');
  if(event.metaKey)parts.push('windows');
  parts.push(trigger);
  return parts.join('+');
}

elements.captureHotkeyButton.addEventListener('click',()=>{
  hotkeyCapture=true;
  elements.captureHotkeyButton.classList.add('capturing');
  elements.captureHotkeyButton.textContent='Pulsa ahora…';
  toast('Pulsa F8, F9, F10 o una combinación con una tecla especial.');
});

document.addEventListener('keydown',event=>{
  if(!hotkeyCapture)return;
  event.preventDefault();event.stopPropagation();
  const hotkey=mapHotkeyEvent(event);
  if(!hotkey)return;
  elements.hotkeyInput.value=hotkey;
  elements.hotkeyDisplay.textContent=hotkey.toUpperCase();
  hotkeyCapture=false;
  elements.captureHotkeyButton.classList.remove('capturing');
  elements.captureHotkeyButton.textContent='Capturar';
  toast(`Tecla capturada: ${hotkey.toUpperCase()}`,'success');
},{capture:true});

async function saveConfig(){
  const original=elements.saveConfigButton.innerHTML;
  elements.saveConfigButton.disabled=true;elements.saveConfigButton.textContent='Guardando…';
  try{
    const data=await fetchJson('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(collectConfig())});
    applyConfig(data.config);
    (data.warnings||[]).forEach(message=>toast(message,'error',5500));
    toast('Configuración guardada y agente reiniciado.','success');
    await sleep(700);await refreshStatus();
  }catch(error){
    toast(error.message,'error',6500);clientLog('error','No se pudo guardar configuración',{error:error.message});
  }finally{
    elements.saveConfigButton.disabled=false;elements.saveConfigButton.innerHTML=original;
  }
}

elements.saveConfigButton.addEventListener('click',saveConfig);
elements.restartAgentButton.addEventListener('click',async()=>{
  elements.restartAgentButton.disabled=true;
  try{await fetchJson('/api/agent/restart',{method:'POST'});toast('Agente reiniciado.','success');await sleep(700);await refreshStatus();}
  catch(error){toast(error.message,'error');}
  finally{elements.restartAgentButton.disabled=false;}
});

function renderAgent(agent,model){
  const status=agent?.status||'starting';
  const titles={idle:'Dictado preparado',model_loading:'Preparando modelo',recording:'Escuchando tu voz',processing:'Transcribiendo',error:'Agente con error',crashed:'Agente detenido por error',stopped:'Agente detenido',unresponsive:'Agente sin respuesta',starting:'Iniciando agente',disabled:'Dictado desactivado',unsupported:'No compatible'};
  const descriptions={idle:'Mantén la tecla pulsada en cualquier aplicación.',model_loading:'El modelo se está descargando o cargando en memoria.',recording:'Suelta la tecla para copiar y pegar el resultado.',processing:'Procesando los últimos fragmentos de audio.',error:agent.last_error||'Consulta los logs del agente.',crashed:agent.last_error||'Reinicia el agente desde esta pantalla.',stopped:'Pulsa Reiniciar agente para volver a activarlo.',unresponsive:'El proceso existe, pero no actualiza su estado.',starting:'Registrando tecla, micrófono y cápsula.',disabled:'Activa el interruptor y guarda los cambios.',unsupported:'El dictado global solo funciona en Windows.'};
  const healthy=['idle','model_loading','recording','processing'].includes(status);
  const error=['error','crashed','unresponsive'].includes(status);
  elements.agentBadge.className=`live-badge ${healthy?'ready':error?'error':''}`;
  elements.agentBadge.innerHTML=`<i></i>${status}`;
  elements.agentTitle.textContent=titles[status]||status;
  elements.agentDescription.textContent=descriptions[status]||'Estado desconocido.';
  elements.capsuleState.textContent=status==='recording'?'Escuchando…':status==='processing'?'Transcribiendo…':status==='model_loading'?'Cargando modelo…':titles[status]||status;
  elements.statusHeartbeat.textContent=agent.heartbeat_age_seconds==null?'—':`${agent.heartbeat_age_seconds} s`;
  elements.statusHotkey.textContent=(agent.hotkey||config.dictation?.hotkey||'f8').toUpperCase();
  const warm=model?.warmup||{};
  if(warm.state==='working')elements.statusModel.textContent=`${warm.model||config.model} · preparando`;
  else if(warm.state==='error')elements.statusModel.textContent=`${warm.model||config.model} · error`;
  else elements.statusModel.textContent=model?.current?.model||config.model;
  elements.statusDevice.textContent=model?.current?.device==='cuda'?'GPU NVIDIA':model?.current?.device==='cpu'?'CPU':deviceLabel(config.device);
  elements.sidebarDot.className=`status-dot ${healthy?'ready':error?'error':''}`;
  elements.sidebarStatus.textContent=healthy?'Sistema operativo':error?'Revisar diagnóstico':'Iniciando sistema';
  elements.sidebarSubstatus.textContent=elements.agentTitle.textContent;
}

async function refreshStatus(){
  elements.refreshButton.classList.add('loading');
  try{
    const data=await fetchJson('/api/status');
    renderAgent(data.agent,data.model);
    renderModelLoader(data.model?.warmup||{});
    elements.runtimePill.className='runtime-pill ready';
    elements.runtimePill.querySelector('small').textContent='Online';
  }catch(error){
    elements.runtimePill.className='runtime-pill error';
    elements.runtimePill.querySelector('small').textContent='Sin conexión';
    elements.sidebarDot.className='status-dot error';
    elements.sidebarStatus.textContent='Servidor con error';
    elements.sidebarSubstatus.textContent=error.message;
  }finally{elements.refreshButton.classList.remove('loading');}
}

elements.refreshButton.addEventListener('click',refreshStatus);

function setTranscript(text,append=false){
  const clean=(text||'').trim();
  if(append&&clean){
    const current=elements.transcriptText.innerText.trim();
    elements.transcriptText.innerText=current?`${current} ${clean}`:clean;
  }else if(!append){elements.transcriptText.innerText=clean;}
  elements.transcriptText.classList.toggle('empty',!elements.transcriptText.innerText.trim());
  elements.transcriptText.scrollTop=elements.transcriptText.scrollHeight;
}


function appendTranscriptDistinct(text){
  const incoming=(text||'').trim();
  if(!incoming)return;
  const existing=elements.transcriptText.innerText.trim();
  if(!existing){setTranscript(incoming);return;}
  const oldWords=existing.split(/\s+/);
  const newWords=incoming.split(/\s+/);
  const normalize=word=>word.toLocaleLowerCase('es').replace(/[^a-záéíóúüñ0-9]/gi,'');
  let overlap=0;
  for(let size=Math.min(12,oldWords.length,newWords.length);size>0;size--){
    const left=oldWords.slice(-size).map(normalize);
    const right=newWords.slice(0,size).map(normalize);
    if(left.every((word,index)=>word&&word===right[index])){overlap=size;break;}
  }
  setTranscript(newWords.slice(overlap).join(' '),true);
}

function setTranscriptionStatus(text,type='idle',pct=0){
  elements.statusChip.className=type;
  elements.statusChip.innerHTML=`<i></i>${text}`;
  const numeric=Number.isFinite(Number(pct))?Math.max(0,Math.min(100,Number(pct))):null;
  const indeterminate=type==='working'&&(pct===null||pct===undefined||numeric===0);
  elements.progressLine.classList.toggle('indeterminate',indeterminate);
  if(indeterminate){elements.progressLine.style.width='35%';}
  else{elements.progressLine.style.width=(type==='done'?100:(numeric??0))+'%';}
  if(elements.progressPercent){elements.progressPercent.textContent=indeterminate?'…':`${type==='done'?100:(numeric??0)}%`;}
}

function showTranscriptionError(message=''){
  elements.errorMessage.textContent=message;
  elements.errorMessage.classList.toggle('hidden',!message);
}

function formatTime(ms){
  const total=Math.floor(ms/1000);
  return `${String(Math.floor(total/60)).padStart(2,'0')}:${String(total%60).padStart(2,'0')}`;
}

function formatBytes(bytes){
  if(!Number.isFinite(bytes))return '';
  const units=['B','KB','MB','GB'];let value=bytes;let index=0;
  while(value>=1024&&index<units.length-1){value/=1024;index++;}
  return `${value.toFixed(index?1:0)} ${units[index]}`;
}

function preferredMimeType(){
  return ['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus'].find(type=>MediaRecorder.isTypeSupported(type))||'';
}

function updateWaveform(){
  if(!isRecording||!analyser){
    waveBars.forEach((bar,index)=>bar.style.height=`${4+(index%4)}px`);return;
  }
  const values=new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(values);
  waveBars.forEach((bar,index)=>{
    const sourceIndex=Math.floor(index*values.length/waveBars.length);
    const value=values[sourceIndex]||0;
    bar.style.height=`${Math.max(5,Math.min(72,value*.29))}px`;
  });
  requestAnimationFrame(updateWaveform);
}

function beginSegment(sessionId){
  if(!isRecording||sessionId!==currentSession||!stream)return;
  const pieces=[];const mimeType=preferredMimeType();
  const active=mimeType?new MediaRecorder(stream,{mimeType}):new MediaRecorder(stream);
  recorder=active;
  active.addEventListener('dataavailable',event=>{if(event.data?.size)pieces.push(event.data);});
  active.addEventListener('stop',()=>{
    clearTimeout(segmentTimer);
    const blob=new Blob(pieces,{type:active.mimeType||mimeType||'audio/webm'});
    if(blob.size>900)enqueueChunk(blob,sessionId,nextChunkIndex++);
    if(isRecording&&sessionId===currentSession)beginSegment(sessionId);
    else{stopMediaStream();captureEnded=true;finishRecordingWhenReady(sessionId);}
  },{once:true});
  active.start();
  const chunkMs=Math.max(3000,Number(config.web?.live_chunk_seconds||6)*1000);
  segmentTimer=setTimeout(()=>{if(active.state==='recording')active.stop();},chunkMs);
}

async function startRecording(){
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){showTranscriptionError('Usa Chrome o Edge actualizado para grabar desde la web.');return;}
  try{
    showTranscriptionError();setTranscript('');
    currentSession++;nextChunkIndex=1;liveQueue=[];captureEnded=false;
    stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
    audioContext=new(window.AudioContext||window.webkitAudioContext)();
    const source=audioContext.createMediaStreamSource(stream);
    analyser=audioContext.createAnalyser();analyser.fftSize=128;analyser.smoothingTimeConstant=.7;source.connect(analyser);
    isRecording=true;recordingStartedAt=Date.now();elements.timer.textContent='00:00';
    clockTimer=setInterval(()=>elements.timer.textContent=formatTime(Date.now()-recordingStartedAt),250);
    elements.recordButton.classList.add('recording');elements.recordingLabel.classList.add('recording');
    elements.recordingLabel.innerHTML='<i></i>Grabando';elements.recordHint.textContent='La transcripción se actualiza por fragmentos mientras hablas.';
    setTranscriptionStatus('Escuchando y transcribiendo','working');
    elements.modelChip.textContent=elements.modelSelect.value;elements.deviceChip.textContent=deviceLabel(elements.deviceSelect.value);
    beginSegment(currentSession);updateWaveform();
  }catch(error){
    const message=error.name==='NotAllowedError'?'No se concedió permiso para usar el micrófono.':`No se pudo abrir el micrófono: ${error.message}`;
    showTranscriptionError(message);setTranscriptionStatus('Error de micrófono','failed');clientLog('error',message,{name:error.name});
  }
}

function stopRecording(){
  if(!isRecording)return;
  isRecording=false;clearTimeout(segmentTimer);clearInterval(clockTimer);
  elements.recordButton.classList.remove('recording');elements.recordingLabel.classList.remove('recording');
  elements.recordingLabel.innerHTML='<i></i>Finalizando';elements.recordHint.textContent='Procesando el último fragmento…';
  setTranscriptionStatus('Terminando transcripción','working');
  if(recorder?.state==='recording')recorder.stop();else{stopMediaStream();captureEnded=true;finishRecordingWhenReady(currentSession);}
}

function stopMediaStream(){
  if(stream){stream.getTracks().forEach(track=>track.stop());stream=null;}
  if(audioContext){audioContext.close().catch(()=>{});audioContext=null;}
  analyser=null;updateWaveform();
}

function enqueueChunk(blob,sessionId,index){liveQueue.push({blob,sessionId,index});processQueue();}

async function processQueue(){
  if(queueRunning)return;queueRunning=true;
  while(liveQueue.length){
    const item=liveQueue.shift();if(item.sessionId!==currentSession)continue;
    try{
      const data=await transcribeBlob(item.blob,'live',`fragmento-${item.index}.webm`);
      if(data.text)appendTranscriptDistinct(data.text);
      applyMetadata(data);
      if(data.warning)toast(data.warning,'error',7000);
      if(isRecording)setTranscriptionStatus(`Grabando · fragmento ${item.index}`,'working');
    }catch(error){showTranscriptionError(error.message);setTranscriptionStatus(`Falló fragmento ${item.index}`,'failed');clientLog('error','Falló fragmento web',{index:item.index,error:error.message});}
  }
  queueRunning=false;finishRecordingWhenReady(currentSession);
}

function finishRecordingWhenReady(sessionId){
  if(sessionId!==currentSession||isRecording||!captureEnded||queueRunning||liveQueue.length)return;
  elements.recordingLabel.innerHTML='<i></i>Preparado';elements.recordHint.textContent='Pulsa para iniciar una nueva grabación.';
  const hasText=elements.transcriptText.innerText.trim();
  setTranscriptionStatus(hasText?'Transcripción terminada':'No se detectó voz',hasText?'done':'idle');
}

async function transcribeBlob(blob,mode,filename,onProgress){
  transcribiendo=true;elements.cancelButton.classList.remove('hidden');
  const form=new FormData();
  form.append('audio',blob,filename);form.append('model',elements.modelSelect.value);form.append('language',elements.languageSelect.value);form.append('device',elements.deviceSelect.value);form.append('mode',mode);
  abortController=new AbortController();
  const signal=abortController.signal;
  try{
    const data=await new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();
      xhr.upload.onprogress=e=>{if(e.lengthComputable&&onProgress)onProgress(Math.round(e.loaded/e.total*80));};
      xhr.onloadend=()=>{
        if(xhr.status===0&&signal.aborted){reject(new DOMException('Abortado','AbortError'));return;}
        try{const d=JSON.parse(xhr.responseText);if(d.error){const e=d.error;reject(new Error(typeof e==='object'?(e.message||e.code||`Error ${xhr.status}`):(e||`Error ${xhr.status}`)));}else if(xhr.status<200||xhr.status>=300){reject(new Error(`Error ${xhr.status}`));}else resolve(d);}
        catch{reject(new Error('Respuesta no válida.'));}
      };
      xhr.onerror=()=>reject(new Error('Error de conexión.'));
      xhr.open('POST','/api/transcribe');
      signal.addEventListener('abort',()=>{xhr.abort();reject(new DOMException('Cancelado','AbortError'));});
      xhr.send(form);
    });
    if(onProgress)onProgress(100);
    return data;
  }catch(err){
    if(err.name==='AbortError')throw new Error('Cancelado por el usuario.');
    throw err;
  }finally{abortController=null;elements.cancelButton.classList.add('hidden');transcribiendo=false;}
}

function applyMetadata(data){
  elements.modelChip.textContent=data.model||elements.modelSelect.value;
  elements.deviceChip.textContent=data.device==='cuda'?'GPU NVIDIA · FP16':'CPU · INT8';
}

elements.recordButton.addEventListener('click',()=>isRecording?stopRecording():startRecording());

$$('.mode-tabs button').forEach(button=>button.addEventListener('click',()=>{
  if(isRecording)stopRecording();
  $$('.mode-tabs button').forEach(item=>item.classList.toggle('active',item===button));
  $('#recordMode').classList.toggle('active',button.dataset.mode==='record');
  $('#fileMode').classList.toggle('active',button.dataset.mode==='file');
}));

function chooseFile(file){
  if(!file)return;selectedFile=file;elements.fileName.textContent=file.name;elements.fileSize.textContent=formatBytes(file.size);
  elements.selectedFileBox.classList.remove('hidden');elements.transcribeFileButton.disabled=false;
}

elements.dropzone.addEventListener('click',()=>elements.fileInput.click());
elements.fileInput.addEventListener('change',()=>chooseFile(elements.fileInput.files[0]));
['dragenter','dragover'].forEach(type=>elements.dropzone.addEventListener(type,event=>{event.preventDefault();elements.dropzone.classList.add('dragging');}));
['dragleave','drop'].forEach(type=>elements.dropzone.addEventListener(type,event=>{event.preventDefault();elements.dropzone.classList.remove('dragging');}));
elements.dropzone.addEventListener('drop',event=>chooseFile(event.dataTransfer.files[0]));
elements.removeFile.addEventListener('click',()=>{selectedFile=null;elements.fileInput.value='';elements.selectedFileBox.classList.add('hidden');elements.transcribeFileButton.disabled=true;});

elements.transcribeFileButton.addEventListener('click',async()=>{
  if(!selectedFile)return;
  elements.transcribeFileButton.disabled=true;elements.cancelButton.classList.remove('hidden');showTranscriptionError();setTranscript('');setTranscriptionStatus('Subiendo archivo…','working',0);
  try{
    const data=await transcribeBlob(selectedFile,'file',selectedFile.name,(pct)=>{setTranscriptionStatus('Transcribiendo…','working',pct);});setTranscript(data.text||'');applyMetadata(data);
    if(data.warning)toast(data.warning,'error',7000);
    setTranscriptionStatus(data.text?`Completado en ${data.processing_seconds} s`:'No se detectó voz',data.text?'done':'idle');
    if(data.text){
      try{
        await fetchJson('/api/notify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'Feria Transcriber',message:`Transcripción lista (${data.text.length} chars)`})});
      }catch(e){}
    }
  }catch(error){
    if(error.message.includes('Cancelado')){setTranscriptionStatus('Cancelado','idle');showTranscriptionError('');}
    else{showTranscriptionError(error.message);setTranscriptionStatus('No se pudo transcribir','failed');clientLog('error','Falló archivo',{name:selectedFile.name,error:error.message});}
  }
  finally{elements.transcribeFileButton.disabled=false;elements.cancelButton.classList.add('hidden');}
});

elements.clearButton.addEventListener('click',()=>{setTranscript('');showTranscriptionError();setTranscriptionStatus('Esperando audio','idle');});
elements.copyButton.addEventListener('click',async()=>{
  const text=elements.transcriptText.innerText.trim();if(!text)return toast('No hay texto para copiar.','error');
  try{await navigator.clipboard.writeText(text);toast('Transcripción copiada.','success');}
  catch{toast('El navegador no permitió copiar automáticamente.','error');}
});
function downloadAs(format){
  const text=elements.transcriptText.innerText.trim();if(!text)return toast('No hay texto para descargar.','error');
  const ts=new Date().toISOString().slice(0,19).replaceAll(':','-');
  if(format==='txt'){
    const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));link.download=`feria-transcripcion-${ts}.txt`;link.click();URL.revokeObjectURL(link.href);return;
  }
  setTranscriptionStatus('Generando '+format.toUpperCase()+'...','working',50);
  fetch('/api/export/'+format,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text,filename:`feria-transcripcion-${ts}.${format}`})})
  .then(r=>{if(!r.ok)throw new Error('Error del servidor');return r.blob();})
  .then(blob=>{const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`feria-transcripcion-${ts}.${format}`;link.click();URL.revokeObjectURL(link.href);setTranscriptionStatus('Descargado','done');toast(format.toUpperCase()+' descargado.','success');})
  .catch(err=>{setTranscriptionStatus('Error al generar '+format.toUpperCase(),'failed');toast(err.message,'error');});
}
elements.downloadTxtButton.addEventListener('click',()=>downloadAs('txt'));
elements.downloadPdfButton.addEventListener('click',()=>downloadAs('pdf'));
elements.downloadDocxButton.addEventListener('click',()=>downloadAs('docx'));

async function runDiagnostics(){
  elements.runDiagnosticsButton.disabled=true;elements.runDiagnosticsButton.textContent='Comprobando…';
  elements.diagnosticList.innerHTML='<div class="empty-state">Ejecutando comprobaciones de sistema…</div>';
  try{
    const data=await fetchJson('/api/diagnostics');renderDiagnostics(data.report);toast('Diagnóstico completado.','success');
  }catch(error){elements.diagnosticList.innerHTML=`<div class="empty-state">${escapeHtml(error.message)}</div>`;toast(error.message,'error');}
  finally{elements.runDiagnosticsButton.disabled=false;elements.runDiagnosticsButton.textContent='Ejecutar diagnóstico';}
}

function renderDiagnostics(report){
  const summary=report.summary;
  elements.diagStatus.textContent=summary.ok?'Correcto':'Revisar';elements.diagErrors.textContent=summary.errors;elements.diagWarnings.textContent=summary.warnings;elements.diagChecks.textContent=summary.checks;
  elements.diagnosticBadge.classList.toggle('hidden',summary.errors===0);
  elements.diagnosticList.innerHTML='';
  report.checks.forEach(check=>{
    const item=document.createElement('div');
    const severity=check.ok?'ok':check.level==='warning'?'warning':'error';
    item.className=`check-item ${severity}`;
    const detail=typeof check.detail==='string'?check.detail:JSON.stringify(check.detail);
    item.innerHTML=`<div class="check-icon">${check.ok?'✓':check.level==='warning'?'!':'×'}</div><div><strong>${escapeHtml(check.name)}</strong><span>${escapeHtml(detail)}</span></div>`;
    elements.diagnosticList.appendChild(item);
  });
}

function escapeHtml(value){return String(value).replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[char]));}

elements.runDiagnosticsButton.addEventListener('click',runDiagnostics);

async function refreshLogs(){
  elements.logViewer.textContent='Cargando logs…';
  try{
    const data=await fetchJson(`/api/logs?name=${encodeURIComponent(activeLog)}&limit=500`);
    elements.logViewer.textContent=data.lines.length?data.lines.join('\n'):'Este log todavía está vacío.';
    elements.logViewer.scrollTop=elements.logViewer.scrollHeight;
  }catch(error){elements.logViewer.textContent=error.message;}
}

$$('.log-tabs button').forEach(button=>button.addEventListener('click',()=>{
  $$('.log-tabs button').forEach(item=>item.classList.toggle('active',item===button));activeLog=button.dataset.log;refreshLogs();
}));
elements.refreshLogsButton.addEventListener('click',refreshLogs);
elements.openLogsButton.addEventListener('click',async()=>{try{await fetchJson('/api/open-logs',{method:'POST'});}catch(error){toast(error.message,'error');}});

elements.cancelButton.addEventListener('click',cancelTranscription);

let modelLoaderHideTimer=null;
function renderModelLoader(w={}){
  const state=w.state||'idle';
  const working=state==='working';
  const failed=state==='error';
  const progress=Number.isFinite(Number(w.progress))?Math.max(0,Math.min(100,Number(w.progress))):null;
  if(modelLoaderHideTimer){clearTimeout(modelLoaderHideTimer);modelLoaderHideTimer=null;}
  elements.modelLoaderPanel.classList.toggle('error',failed);
  elements.modelLoaderPanel.classList.toggle('ready',state==='ready');
  if(working||failed){elements.modelLoaderPanel.classList.remove('hidden');}
  else if(state==='ready'){
    elements.modelLoaderPanel.classList.remove('hidden');
    modelLoaderHideTimer=setTimeout(()=>elements.modelLoaderPanel.classList.add('hidden'),1400);
  }else{elements.modelLoaderPanel.classList.add('hidden');}
  elements.modelLoaderTitle.textContent=w.message||(failed?'Error cargando el modelo':'Preparando modelo…');
  elements.modelLoaderDetail.textContent=w.detail||(working?'Descargando o cargando los archivos locales.':'');
  elements.modelLoaderName.textContent=w.model||config.model||'large-v3-turbo';
  elements.modelLoaderElapsed.textContent=`${Math.round(Number(w.elapsed_seconds)||0)} s`;
  elements.modelLoaderBar.classList.toggle('indeterminate',working&&(w.indeterminate||progress===null));
  if(working&&(w.indeterminate||progress===null)){
    elements.modelLoaderBar.style.width='28%';
    elements.modelLoaderPercent.textContent='Cargando';
  }else{
    const value=state==='ready'?100:(progress??0);
    elements.modelLoaderBar.style.width=`${value}%`;
    elements.modelLoaderPercent.textContent=`${Math.round(value)}%`;
  }
  if(elements.modelLoading){
    elements.modelLoading.classList.toggle('hidden',!working);
    if(working)elements.modelLoading.innerHTML=`<span class="loading-spinner"></span>${w.message||'Preparando modelo…'} ${w.model||''}`;
  }
}

async function checkModelWarmup(){
  try{const s=await fetchJson('/api/status');renderModelLoader(s.model?.warmup||{});renderAgent(s.agent,s.model);}catch(e){}
}
setInterval(checkModelWarmup,850);

applyConfig(config);
loadAudioDevices();
refreshStatus();
setInterval(refreshStatus,2500);
setInterval(()=>{if($('#diagnosticsView').classList.contains('active'))refreshLogs();},5000);

// ── Tema claro/oscuro ─────────────────────────────────────────────────────────
function applyTheme(theme){
  document.body.classList.toggle('light-theme',theme==='light');
  try{localStorage.setItem('feria-theme',theme);}catch{}
}
elements.themeToggleButton.addEventListener('click',()=>{
  const isLight=document.body.classList.contains('light-theme');
  applyTheme(isLight?'dark':'light');
});
try{
  const saved=localStorage.getItem('feria-theme');
  if(saved)applyTheme(saved);
}catch{}

// ── GPU stats ────────────────────────────────────────────────────────────────
async function refreshGpuStats(){
  try{
    const data=await fetchJson('/api/gpu-stats');
    const stats=data.stats;
    if(!stats.cuda_available||!stats.devices.length){
      elements.gpuPill.classList.add('hidden');
      return;
    }
    const d=stats.devices[0];
    elements.gpuPill.classList.remove('hidden');
    elements.gpuName.textContent=d.name||'GPU';
    if(d.memory_total_mb){
      const pct=Math.round(d.memory_used_mb/d.memory_total_mb*100);
      elements.gpuStats.textContent=`${d.gpu_util_pct||0}% · ${d.memory_used_mb}MB / ${d.memory_total_mb}MB${d.temperature_c?' · '+d.temperature_c+'°C':''}`;
    }else{
      elements.gpuStats.textContent='Activa';
    }
  }catch(e){
    elements.gpuPill.classList.add('hidden');
  }
}
setInterval(refreshGpuStats,3000);
refreshGpuStats();

// ── Historial ────────────────────────────────────────────────────────────────
let historyCache=[];
async function refreshHistory(){
  try{
    const data=await fetchJson('/api/history');
    historyCache=data.items||[];
    renderHistory(historyCache);
  }catch(e){
    elements.historyList.innerHTML=`<div class="empty-history">Error: ${e.message}</div>`;
  }
}
function renderHistory(items){
  const q=(elements.historySearch.value||'').toLowerCase().trim();
  const filtered=items.filter(it=>!q||(it.text||'').toLowerCase().includes(q)||(it.created_at_iso||'').includes(q));
  if(!filtered.length){
    elements.historyList.innerHTML=`<div class="empty-history">${q?'Sin resultados.':'No hay transcripciones aún.'}</div>`;
    return;
  }
  elements.historyList.innerHTML='';
  filtered.forEach(item=>{
    const el=document.createElement('div');
    el.className='history-item';
    const ago=timeAgo(item.created_at);
    el.innerHTML=`
      <div class="history-item-head">
        <div class="history-item-meta">
          <b>${escapeHtml(item.model||'?')}</b>
          <span>${escapeHtml((item.language||'auto').toUpperCase())}</span>
          <span>${escapeHtml(item.device||'auto')}</span>
          <span>${escapeHtml(ago)}</span>
          <span>${(item.char_count||0)} chars</span>
        </div>
        <div class="history-item-actions">
          <button data-action="open" data-id="${item.id}">Abrir</button>
          <button class="delete" data-action="delete" data-id="${item.id}">Eliminar</button>
        </div>
      </div>
      <div class="history-item-text">${escapeHtml(item.text||'')}</div>
    `;
    elements.historyList.appendChild(el);
  });
}
function timeAgo(ts){
  if(!ts)return'?';
  const seconds=Math.floor((Date.now()/1000)-ts);
  if(seconds<60)return'hace '+seconds+'s';
  const m=Math.floor(seconds/60);
  if(m<60)return'hace '+m+'m';
  const h=Math.floor(m/60);
  if(h<24)return'hace '+h+'h';
  const d=Math.floor(h/24);
  if(d<30)return'hace '+d+'d';
  return new Date(ts*1000).toLocaleDateString();
}
elements.historyList.addEventListener('click',async(e)=>{
  const btn=e.target.closest('button[data-action]');
  if(!btn)return;
  const id=btn.dataset.id;
  const item=historyCache.find(x=>x.id===id);
  if(!item)return;
  if(btn.dataset.action==='open'){
    elements.transcriptText.innerText=item.text||'';
    elements.transcriptText.classList.toggle('empty',!elements.transcriptText.innerText.trim());
    resultMeta.innerHTML=`
      <span id="statusChip" class="done"><i></i>Del historial</span>
      <span class="chip lang">Idioma: ${(item.language||'auto').toUpperCase()}</span>
      <span class="chip model">Modelo: ${item.model||'?'}</span>
      <span class="chip">${item.char_count||0} chars</span>
    `;
    setView('transcribe');
    toast('Transcripción cargada del historial.','success');
  }else if(btn.dataset.action==='delete'){
    if(!confirm('¿Eliminar esta transcripción?'))return;
    try{
      await fetchJson(`/api/history/${id}`,{method:'DELETE'});
      toast('Eliminado.','success');
      refreshHistory();
    }catch(err){toast(err.message,'error');}
  }
});
elements.historySearch.addEventListener('input',()=>renderHistory(historyCache));
elements.refreshHistoryButton.addEventListener('click',refreshHistory);

// ── Micrófonos web ────────────────────────────────────────────────────────────
async function loadWebMicrophones(){
  try{
    if(!navigator.mediaDevices?.enumerateDevices)return;
    const devices=await navigator.mediaDevices.enumerateDevices();
    const mics=devices.filter(d=>d.kind==='audioinput');
    elements.webMicSelect.innerHTML='<option value="">Predeterminado del sistema</option>';
    mics.forEach((m,i)=>{
      const opt=document.createElement('option');
      opt.value=m.deviceId;
      opt.textContent=m.label||`Micrófono ${i+1}`;
      elements.webMicSelect.appendChild(opt);
    });
    elements.webMicHint.textContent=`${mics.length} micrófono(s) disponible(s).`;
  }catch(e){
    elements.webMicHint.textContent='No se pudo enumerar los micrófonos.';
  }
}
elements.webMicSelect.addEventListener('change',()=>{
  toast('Cambia el micrófono para futuras grabaciones.','info');
});

// ── Atajos de teclado ────────────────────────────────────────────────────────
document.addEventListener('keydown',e=>{
  if(hotkeyCapture)return;
  // Ctrl+Enter = transcribir archivo
  if(e.ctrlKey&&e.key==='Enter'){
    e.preventDefault();
    if(elements.transcribeFileButton&&!elements.transcribeFileButton.disabled&&selectedFile){
      elements.transcribeFileButton.click();
    }else if(elements.recordButton&&!isRecording){
      elements.recordButton.click();
    }else if(isRecording){
      elements.recordButton.click();
    }else{
      toast('Carga un archivo o inicia una grabación.','info');
    }
    return;
  }
  // Esc = cancelar / parar grabación
  if(e.key==='Escape'){
    if(transcribiendo){
      e.preventDefault();
      cancelTranscription();
    }else if(isRecording){
      e.preventDefault();
      elements.recordButton.click();
    }
    return;
  }
  // Ctrl+L = limpiar transcripción
  if(e.ctrlKey&&e.key==='l'){
    e.preventDefault();
    if(elements.clearButton)elements.clearButton.click();
    return;
  }
  // Ctrl+B = historial
  if(e.ctrlKey&&e.key==='b'){
    e.preventDefault();
    setView('history');
    refreshHistory();
    return;
  }
  // Ctrl+T = toggle tema
  if(e.ctrlKey&&e.key==='t'){
    e.preventDefault();
    elements.themeToggleButton.click();
    return;
  }
});

// Cargar historial y mics al iniciar
loadWebMicrophones();
refreshHistory();
