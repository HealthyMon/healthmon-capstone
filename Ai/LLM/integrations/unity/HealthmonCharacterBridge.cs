using System;
using UnityEngine;
using UnityEngine.Events;

namespace Healthmon.Beta
{
    // Attach next to HealthmonApiClient. Wire string events to your UI / character presenter.
    public sealed class HealthmonCharacterBridge : MonoBehaviour
    {
        [Serializable] public class TextEvent : UnityEvent<string> { }
        public HealthmonApiClient api;
        public TextEvent onSpeech = new TextEvent();
        public TextEvent onEmotion = new TextEvent();
        public TextEvent onAnimation = new TextEvent();
        public TextEvent onOffer = new TextEvent();
        public TextEvent onStatus = new TextEvent();
        public string LastOfferId { get; private set; }

        private void Awake() { if (api == null) api = GetComponent<HealthmonApiClient>(); }
        private void OnEnable()
        {
            if (api == null) return;
            api.ChatReceived += HandleChat;
            api.SpeechReceived += onSpeech.Invoke;
            api.EmotionReceived += onEmotion.Invoke;
            api.AnimationReceived += onAnimation.Invoke;
            api.Failed += HandleFailure;
        }
        private void OnDisable()
        {
            if (api == null) return;
            api.ChatReceived -= HandleChat;
            api.SpeechReceived -= onSpeech.Invoke;
            api.EmotionReceived -= onEmotion.Invoke;
            api.AnimationReceived -= onAnimation.Invoke;
            api.Failed -= HandleFailure;
        }

        // Call from your runtime login flow; never put a real token in an Inspector field.
        public void ConnectExisting(string url, string token, string petId)
        {
            api.Configure(url, token);
            api.SelectPet(petId);
            api.GetState(state => onStatus.Invoke("대화할 준비가 됐어요."));
        }
        public void ConnectNew(string url, string token, string characterName)
        {
            api.Configure(url, token);
            api.CreatePet(new PetSettings { name = characterName }, pet => onStatus.Invoke("대화할 준비가 됐어요."));
        }
        public void Send(string text)
        {
            if (api.IsBusy || api.HasPendingChat) { onStatus.Invoke("진행 중인 대화를 먼저 확인해 주세요."); return; }
            LastOfferId = null;
            onOffer.Invoke("");
            onStatus.Invoke("생각하고 있어요…");
            api.SendChat(text);
        }
        public void Retry() { onStatus.Invoke("이전 요청을 확인하고 있어요…"); api.RetryPendingChat(); }
        public void Cancel() { api.CancelCurrent(); }
        public void AcceptOffer() { Decide(true); }
        public void RejectOffer() { Decide(false); }
        private void Decide(bool accept)
        {
            if (string.IsNullOrEmpty(LastOfferId)) { onStatus.Invoke("먼저 유효한 퀘스트 제안을 받아 주세요."); return; }
            api.DecideQuest(LastOfferId, accept, result =>
            {
                LastOfferId = null;
                onOffer.Invoke("");
                api.GetState(state => api.GetQuests(quests =>
                    onStatus.Invoke(accept ? "퀘스트를 수락했어요." : "이번 제안은 쉬어 갈게요.")));
            });
        }
        private void HandleChat(ChatResult result)
        {
            LastOfferId = result.execution == null ? null : result.execution.offer_id;
            onOffer.Invoke(LastOfferId ?? "");
            onStatus.Invoke(result.metrics != null && result.metrics.fallback
                ? "답변을 마무리하지 못했어요. 잠시 뒤 다시 이야기해 주세요." : "");
        }
        private void HandleFailure(ApiFailure failure)
        {
            if (failure.Cancelled) onStatus.Invoke("연결 대기를 멈췄어요. 재시도로 이전 결과를 확인할 수 있어요.");
            else if (failure.StatusCode == 401) onStatus.Invoke("다시 로그인해 주세요.");
            else if (failure.StatusCode == 409) onStatus.Invoke("요청 진행 상황 또는 최신 상태를 확인해 주세요.");
            else if (failure.StatusCode == 410) onStatus.Invoke("기억 정정·삭제로 이전 답변이 무효화됐어요. 기록을 새로 불러와 주세요.");
            else onStatus.Invoke("연결을 확인하고 재시도해 주세요.");
        }
    }
}
