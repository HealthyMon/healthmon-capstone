/** Transport only. A Unity presenter can use the same healthmon.v1 endpoints. */
export class ApiError extends Error {
  constructor(status, detail) { super(detail); this.status = status; }
}
export class HealthmonApi {
  constructor(baseUrl = '') { this.baseUrl = baseUrl.replace(/\/$/, ''); }
  async request(path, {method = 'GET', body, timeout = 20000} = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(this.baseUrl + path, {
        method, credentials: 'same-origin', signal: controller.signal,
        headers: body !== undefined ? {'Content-Type': 'application/json'} : {},
        ...(body !== undefined ? {body: JSON.stringify(body)} : {})
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : '요청을 처리하지 못했어요.');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new ApiError(0, '응답을 기다리는 시간이 길어졌어요. 같은 메시지를 다시 확인해 주세요.');
      if (error instanceof ApiError) throw error;
      throw new ApiError(0, '서버에 연결하지 못했어요. 서버가 켜져 있는지 확인해 주세요.');
    } finally { clearTimeout(timer); }
  }
  session() { return this.request('/beta/session', {method: 'POST', body: {}}); }
  health() { return this.request('/health'); }
  createPet(settings = {}) { return this.request('/pets', {method: 'POST', body: settings}); }
  state(pet) { return this.request(`/pets/${encodeURIComponent(pet)}/state`); }
  history(pet) { return this.request(`/pets/${encodeURIComponent(pet)}/messages?limit=50`); }
  quests(pet) { return this.request(`/pets/${encodeURIComponent(pet)}/quests`); }
  chat(pet, text, requestId) {
    return this.request(`/pets/${encodeURIComponent(pet)}/chat`, {method:'POST', body:{text,request_id:requestId}, timeout:240000});
  }
  decide(pet, offerId, decision) {
    return this.request(`/pets/${encodeURIComponent(pet)}/quests/${encodeURIComponent(offerId)}/decision`, {method:'POST',body:{decision}});
  }
  settings(pet, settings) { return this.request(`/pets/${encodeURIComponent(pet)}/settings`, {method:'PUT',body:settings}); }
  memories(pet, query) { return this.request(`/pets/${encodeURIComponent(pet)}/memories?${new URLSearchParams({query})}`); }
  editSource(pet, memory, text) {
    return this.request(`/pets/${encodeURIComponent(pet)}/sources/${encodeURIComponent(memory.source_id)}`, {method:'PATCH', body:{expected_revision:memory.source_revision,text}});
  }
  registerMemory(pet, memory, revision) {
    return this.request(`/pets/${encodeURIComponent(pet)}/memories`, {method:'POST',body:{source_id:memory.source_id,revision,slot:memory.slot}});
  }
  forget(pet, memory) {
    return this.request(`/pets/${encodeURIComponent(pet)}/memories/${encodeURIComponent(memory.id)}?${new URLSearchParams({expected_revision:memory.source_revision})}`, {method:'DELETE'});
  }
}
