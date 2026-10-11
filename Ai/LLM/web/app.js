import {HealthmonApi} from './api.js';

const $ = selector => document.querySelector(selector);
const api = new HealthmonApi();
const app = {pet:null,state:null,busy:false,mutating:false,ready:false,pending:null,activePanel:'chat',memory:null};
const EMOTIONS = {neutral:'편안하게 함께해요',happy:'기분이 좋아요',encouraging:'너를 응원하고 있어요',sad:'조용히 곁에 있을게요',tired:'잠깐 쉬어 가요',grumpy:'조금 새침해졌어요',playful:'장난기가 올라왔어요'};
const ANIMATIONS = new Set(['idle','wave','cheer','encourage','rest','pout','laugh']);
let thinkingTimer, toastTimer, reactionTimer;

function el(tag, className, text) {
  const node = document.createElement(tag); if (className) node.className = className;
  if (text !== undefined) node.textContent = text; return node;
}
function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('class','icon'); svg.setAttribute('aria-hidden','true');
  const use = document.createElementNS(svg.namespaceURI,'use');use.setAttribute('href',`#i-${name}`);svg.append(use);return svg;
}
function toast(text) { clearTimeout(toastTimer);$('#toast').textContent=text;$('#toast').hidden=false;toastTimer=setTimeout(()=>$('#toast').hidden=true,3500); }
function errorText(error) {
  if (error.status===401) return '연결 시간이 만료됐어요. 페이지를 새로고침해 주세요.';
  if (error.status===409) return '기록이 바뀌었거나 답변을 준비 중이에요. 잠시 뒤 다시 확인해 주세요.';
  if (error.status===410) return '기억이 정정되거나 삭제되어 이전 답변을 가져올 수 없어요. 새로 이야기해 주세요.';
  if (error.status===403) return '이 화면은 현재 서버 PC에서만 사용할 수 있어요.';
  if (error.status===503) return '기록을 보관하는 서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.';
  if (error.status===422) return '입력 내용을 확인해 주세요. 메시지는 1,500자까지 보낼 수 있어요.';
  return error.status ? '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.' : error.message;
}
function chatError(message, retry=false) { $('#chat-error').hidden=!message;$('#chat-error span').textContent=message;$('#retry-send').hidden=!retry; }
function scrollChat() { requestAnimationFrame(()=>{ const box=$('#chat-scroll');box.scrollTop=box.scrollHeight; }); }
function updateSend() { $('#send-button').disabled=!app.ready || app.busy || app.mutating || Boolean(app.pending) || !$('#message').value.trim(); }
function setMutating(value) {
  app.mutating=value;updateSend();$('#message').disabled=value || app.busy || !app.ready;
  document.querySelectorAll('[data-close],.sheet button,.sheet input,.sheet select,.sheet textarea').forEach(b=>b.disabled=value);
  if(!value && app.memory?.pendingRevision)$('#memory-edit').disabled=true;
}
function setBusy(value) {
  app.busy=value;$('#typing').hidden=!value;$('#message').disabled=!app.ready || value;
  $('#settings-button').disabled=value || Boolean(app.pending);
  document.querySelectorAll('[data-prompt]').forEach(b=>b.disabled=value || !app.ready || Boolean(app.pending));
  $('#retry-send').disabled=value;updateSend();clearTimeout(thinkingTimer);
  $('.composer-note').textContent=value?'천천히 답하고 있어요. 잠시만 기다려 주세요.':'소소한 이야기도 좋아요. 오늘을 들려주세요.';
  if (value) {
    $('#thinking-label').textContent='이야기를 생각하고 있어요';
    thinkingTimer=setTimeout(()=>$('#thinking-label').textContent='조금 더 생각하고 있어요. 잠시만요.',12000);
    scrollChat();
  }
}
function showEmotion(emotion='neutral',animation='idle') {
  const character=$('#character');character.dataset.emotion=Object.hasOwn(EMOTIONS,emotion)?emotion:'neutral';
  character.dataset.animation=ANIMATIONS.has(animation)?animation:'idle';
  $('#mood-label').textContent=EMOTIONS[character.dataset.emotion];
}
function applyState(state) {
  app.state=state;
  const name=state.settings.name;$('#pet-name').textContent=name;
  $('.app-header h1').replaceChildren(document.createTextNode(`${name}와 함께 `),el('span','beta-tag','beta'));
  $('#message').placeholder=`${name}에게 이야기해 주세요…`;
  $('#character').setAttribute('aria-label',`${name}에게 인사하기`);
  $('#setting-name').value=name;$('#setting-speech').value=state.settings.speech_level;$('#setting-profanity').value=state.settings.profanity;
  const bond=state.traits?.bond ?? 30;
  $('#bond-label').textContent=bond>=60?'조금 더 가까워진 우리':bond>30?'조금씩 알아가는 중':'천천히 알아가는 중';
}
function message(role,text,{time,response,metrics,requestId}={}) {
  $('#welcome')?.remove();
  const row=el('div',`message-row ${role}`);if(requestId)row.dataset.requestId=requestId;
  if (role==='assistant') {const avatar=el('img','avatar');avatar.src='/web/assets/mongle.svg';avatar.alt='';row.append(avatar);}
  const body=el('div','message-body');
  if(role==='assistant')body.append(el('div','message-name',app.state?.settings.name || '몽글이'));
  body.append(el('div','bubble',text));
  if(time){const date=new Date(time);if(!Number.isNaN(date.getTime()))body.append(el('div','message-time',date.toLocaleTimeString('ko-KR',{hour:'numeric',minute:'2-digit'})));}
  if(metrics?.fallback)body.append(el('span','fallback-tag','답변을 정리하지 못해 잠시 쉬어 가요'));
  row.append(body);$('#conversation').append(row);
  if(response)showEmotion(response.emotion,response.animation);
  return row;
}
async function loadHistory() {
  const history=await api.history(app.pet);
  $('#suggestions').hidden=history.messages.length>0;
  if(history.messages.length) {
    $('#conversation').replaceChildren();
    if(history.has_more)$('#conversation').append(el('p','section-description','최근 50번의 이야기를 보여드려요.'));
    for(const turn of history.messages) {
      if(turn.user)message('user',turn.user,{time:turn.created_at,requestId:turn.request_id});
      if(turn.assistant)message('assistant',turn.assistant,{time:turn.created_at,response:turn.response,metrics:turn.metrics});
    }
  } else if(!$('#welcome')) {
    $('#conversation').replaceChildren(el('div','welcome','새로운 이야기를 들려주세요.'));
  }
  scrollChat();
}
async function boot() {
  try {
    await api.session();
    try{app.pet=localStorage.getItem('healthmon.beta.petId');}catch{}
    if(app.pet) {try {applyState(await api.state(app.pet));}catch(error){if(error.status!==404)throw error;app.pet=null;}}
    if(!app.pet) {
      app.pet=(await api.createPet({name:'몽글이',profanity:'mild',speech_level:'casual',timezone:'Asia/Seoul'})).pet_id;
      try{localStorage.setItem('healthmon.beta.petId',app.pet);}catch{}
      applyState(await api.state(app.pet));
    }
    await loadHistory();
    app.ready=true;setBusy(false);$('#connection').className='connected';$('#connection').replaceChildren(el('span','status-dot'),document.createTextNode('함께 있는 중'));
    loadQuests();
  } catch(error) {
    chatError(errorText(error));$('#connection').className='offline';$('#connection').textContent='연결을 확인해 주세요';
  }
}
async function send(text, retry=false) {
  if(!app.ready || app.busy || app.mutating || (!retry && app.pending))return;
  text=text.trim();if(!text)return;
  chatError('');
  if(!retry) {
    const requestId=crypto.randomUUID();
    const row=message('user',text,{time:new Date().toISOString(),requestId});
    app.pending={text,requestId,row};$('#message').value='';$('#message').style.height='auto';
  }
  const pending=app.pending;
  setBusy(true);$('#suggestions').hidden=true;
  try {
    const result=await api.chat(app.pet,pending.text,pending.requestId);
    if(result.schema_version!=='healthmon.v1' || result.request_id!==pending.requestId || typeof result.response?.speech!=='string')
      throw new Error('답변 형식을 확인하지 못했어요. 같은 메시지를 다시 확인해 주세요.');
    pending.row.classList.remove('failed');
    app.pending=null; // The authoritative result is received; later view refreshes are not chat failures.
    if(result.execution?.deleted_memory_id) {
      $('#conversation').replaceChildren();$('#memories-content').replaceChildren();
      try{await loadHistory();}catch{chatError('기억은 지웠지만 대화 기록을 다시 불러오지 못했어요. 새로고침해 주세요.');}
      toast('말한 기억을 지웠어요.');
    } else message('assistant',result.response.speech,{time:new Date().toISOString(),response:result.response,metrics:result.metrics});
    showEmotion(result.response.emotion,result.response.animation);
    if(result.state_after)applyState({...result.state_after,settings:app.state.settings,state_version:result.state_version});
    await loadQuests();
  } catch(error) {
    pending.row.classList.add('failed');
    if(error.status===410) {app.pending=null;loadHistory().catch(()=>{});}
    chatError(errorText(error),Boolean(app.pending));
  } finally {setBusy(false);scrollChat();if(window.matchMedia('(min-width:701px)').matches)$('#message').focus();}
}
function switchPanel(name) {
  app.activePanel=name;
  document.querySelectorAll('.tab').forEach(b=>{const on=b.dataset.panel===name;b.classList.toggle('active',on);if(on)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  for(const p of ['chat','quests','memories'])$(`#${p}-panel`).hidden=p!==name;
  if(!app.ready)return;
  if(name==='quests')loadQuests();else if(name==='memories')loadMemories();else scrollChat();
}
function emptyCard(title,description,iconName='leaf',buttonText,action) {
  const node=el('div','empty-card');node.append(icon(iconName),el('h3','',title),el('p','',description));
  if(buttonText){const b=el('button','',buttonText);b.addEventListener('click',action);node.append(b);}return node;
}
async function loadQuests() {
  if(!app.pet)return;
  try {
    const data=await api.quests(app.pet);const box=$('#quests-content');box.replaceChildren();
    const active=data.offers.filter(q=>['offered','active','completed'].includes(q.status)).slice(0,8);
    $('#quest-dot').hidden=!active.some(q=>q.status==='offered' && new Date(q.expires_at)>new Date());
    if(!active.length)box.append(emptyCard('지금은 자유롭게 쉬어도 좋아요','가벼운 도전이 생각나면 몽글이에게 물어봐요.','leaf','몽글이에게 물어보기',()=>{switchPanel('chat');send('지금 할 수 있는 가벼운 걷기 퀘스트 추천해 줘.');}));
    for(const quest of active) {
      const card=el('article','quest-card');const top=el('div','card-top');
      const expired=quest.status!=='completed' && new Date(quest.expires_at)<=new Date();
      const stale=quest.status==='offered' && quest.state_version!==app.state?.state_version;
      const status=expired?'시간이 지났어요':stale?'다시 확인이 필요해요':({offered:'함께 해볼까요?',active:'함께하는 중',completed:'해냈어요!'})[quest.status];
      const title=quest.template.name || `${Number(quest.template.target).toLocaleString()}걸음 가볍게 걷기`;
      top.append(el('h3','',title),el('span','quest-status',status));card.append(top);
      if(quest.status==='offered') {
        card.append(el('p','',expired || stale?'몽글이에게 지금 할 수 있는 도전을 다시 물어봐 주세요.':'괜찮다면 시작해요. 오늘은 쉬어 가도 좋아요.'));
        if(!expired && !stale) {
          const buttons=el('div','quest-actions');
          for(const [decision,label] of [['accept','좋아, 시작할게'],['reject','다음에 할게']]) {
            const button=el('button',decision==='reject'?'secondary':'',label);
            button.addEventListener('click',async()=>{
              if(app.busy || app.mutating || app.pending){toast('진행 중인 이야기가 끝나면 선택해 주세요.');return;}
              setMutating(true);
              buttons.querySelectorAll('button').forEach(b=>b.disabled=true);
              try{await api.decide(app.pet,quest.id,decision);applyState(await api.state(app.pet));toast(decision==='accept'?'우리, 천천히 시작해요.':'오늘은 편하게 쉬어 가요.');await loadQuests();}
              catch(error){toast(errorText(error));try{applyState(await api.state(app.pet));await loadQuests();}catch{}}
              finally{setMutating(false);}
            });buttons.append(button);
          }card.append(buttons);
        }
      } else {
        const track=el('div','progress-track');const bar=el('div','progress-bar');bar.style.width=`${Math.min(100,Math.max(0,100*quest.progress/quest.template.target))}%`;track.append(bar);
        const label=el('div','progress-label');label.append(el('span','',`${Number(quest.progress).toLocaleString()}걸음`),el('span','',`목표 ${Number(quest.template.target).toLocaleString()}걸음`));card.append(track,label);
        card.append(el('p','',quest.status==='completed'?'작은 도전을 끝냈어요. 오늘도 잘했어요!':'확인된 운동 기록이 들어오면 진행 상황이 바뀌어요.'));
      }box.append(card);
    }
    if(data.reward_balance>0)box.append(el('div','quest-reward',`함께 모은 보상 ${data.reward_balance}`));
  } catch(error) {$('#quests-content').replaceChildren(el('p','panel-error',errorText(error)));}
}
async function loadMemories() {
  if(!app.ready)return;
  const query=$('#memory-query').value.trim();if(!query)return;
  const box=$('#memories-content');box.replaceChildren(el('p','section-description','우리의 기억을 찾아보고 있어요…'));
  try {
    const data=await api.memories(app.pet,query);box.replaceChildren();
    if(!data.memories.length)box.append(emptyCard('아직 적어 둔 기억이 없어요','“나는 달리기보다 걷는 게 좋아”처럼\n너의 이야기를 들려주세요.','heart','이야기하러 가기',()=>switchPanel('chat')));
    for(const memory of data.memories) {
      const card=el('article','memory-card');card.append(el('span','tag',({preference:'좋아하는 것',goal:'나의 목표',experience:'함께한 경험'})[memory.slot] || '우리의 기억'),el('p','',memory.content));
      const button=el('button');button.setAttribute('aria-label',`${memory.content} 기억 수정 또는 삭제`);button.append(icon('chevron'));
      button.addEventListener('click',()=>openMemory(memory));card.append(button);box.append(card);
    }
  } catch(error){box.replaceChildren(el('p','panel-error',errorText(error)));}
}
function openMemory(memory) {
  if(app.busy || app.mutating || app.pending){toast('진행 중인 이야기가 끝나면 기억을 바꿔 주세요.');return;}
  app.memory={...memory};$('#memory-edit').value=memory.content;$('#memory-edit').disabled=false;
  $('#memory-error').textContent='';$('#memory-delete').textContent='이 기억 지우기';$('#memory-delete').dataset.confirm='';$('#memory-save').textContent='이렇게 기억해 줘';$('#memory-dialog').showModal();
}
async function refreshAfterMemory() {
  applyState(await api.state(app.pet));await loadHistory();await loadMemories();await loadQuests();
}
$('#chat-form').addEventListener('submit',event=>{event.preventDefault();send($('#message').value);});
$('#message').addEventListener('input',()=>{$('#message').style.height='auto';$('#message').style.height=Math.min(96,$('#message').scrollHeight)+'px';updateSend();});
$('#message').addEventListener('keydown',event=>{if(event.key==='Enter' && !event.shiftKey && !event.isComposing){event.preventDefault();send($('#message').value);}});
$('#retry-send').addEventListener('click',()=>{if(app.pending)send(app.pending.text,true);});
document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>send(b.dataset.prompt)));
document.querySelectorAll('[data-panel]').forEach(b=>b.addEventListener('click',()=>switchPanel(b.dataset.panel)));
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>{if(!app.mutating)document.getElementById(b.dataset.close).close();}));
document.querySelectorAll('dialog').forEach(d=>d.addEventListener('cancel',event=>{if(app.mutating)event.preventDefault();}));
$('#character').addEventListener('click',()=>{clearTimeout(reactionTimer);$('#pet-reaction').textContent='여기 있어!';$('#pet-reaction').classList.add('visible');showEmotion('happy','wave');reactionTimer=setTimeout(()=>{$('#pet-reaction').classList.remove('visible');showEmotion();},2200);});
$('#settings-button').addEventListener('click',()=>{if(!app.ready || app.busy || app.mutating || app.pending){toast('진행 중인 연결을 기다려 주세요.');return;}$('#settings-error').textContent='';$('#settings-dialog').showModal();});
$('#settings-form').addEventListener('submit',async event=>{
  event.preventDefault();if(app.mutating || app.busy)return;setMutating(true);
  const settings={...app.state.settings,name:$('#setting-name').value.trim(),speech_level:$('#setting-speech').value,profanity:$('#setting-profanity').value};
  try{await api.settings(app.pet,settings);applyState(await api.state(app.pet));$('#settings-dialog').close();toast('우리의 대화 설정을 저장했어요.');loadQuests();}
  catch(error){$('#settings-error').textContent=errorText(error);}finally{setMutating(false);}
});
$('#refresh-quests').addEventListener('click',async()=>{try{applyState(await api.state(app.pet));await loadQuests();}catch(error){toast(errorText(error));}});
$('#memory-search').addEventListener('submit',event=>{event.preventDefault();loadMemories();});
document.querySelectorAll('[data-query]').forEach(button=>button.addEventListener('click',()=>{$('#memory-query').value=button.dataset.query;document.querySelectorAll('[data-query]').forEach(b=>b.classList.toggle('selected',b===button));loadMemories();}));
$('#memory-edit-form').addEventListener('submit',async event=>{
  event.preventDefault();if(app.mutating || app.busy)return;
  const button=$('#memory-save'),memory=app.memory;setMutating(true);$('#memory-error').textContent='';
  try {
    if(!memory.pendingRevision) {
      const edited=await api.editSource(app.pet,memory,$('#memory-edit').value.trim());
      memory.pendingRevision=edited.revision;memory.source_revision=edited.revision;
      // Old derived replies are invalid immediately after PATCH, even if indexing fails.
      $('#conversation').replaceChildren();$('#memories-content').replaceChildren();
      applyState(await api.state(app.pet));await loadHistory();
    }
    await api.registerMemory(app.pet,memory,memory.pendingRevision);
    $('#memory-dialog').close();await refreshAfterMemory();toast('새로운 내용으로 기억할게요.');
  }catch(error){$('#memory-error').textContent=memory.pendingRevision?'원본은 수정됐지만 기억 등록이 끝나지 않았어요. 다시 저장해 주세요.':errorText(error);if(memory.pendingRevision)button.textContent='기억 저장 다시 시도';}
  finally{setMutating(false);}
});
$('#memory-delete').addEventListener('click',async()=>{
  const button=$('#memory-delete');
  if(app.mutating || app.busy)return;
  if(!button.dataset.confirm){button.dataset.confirm='yes';button.textContent='원본과 기억을 지울까요? 한 번 더 눌러 주세요.';return;}
  const memory=app.memory;setMutating(true);
  try{await api.forget(app.pet,memory);$('#conversation').replaceChildren();$('#memories-content').replaceChildren();$('#memory-dialog').close();await refreshAfterMemory();toast('원본과 연결된 기억을 지웠어요.');}
  catch(error){$('#memory-error').textContent=errorText(error);}
  finally{setMutating(false);}
});
// Only our bundled, authored SVG is inserted; all user/model text uses textContent.
fetch('/web/assets/mongle.svg').then(r=>r.ok?r.text():Promise.reject()).then(svg=>{$('#character').innerHTML=svg;}).catch(()=>{});
boot();
