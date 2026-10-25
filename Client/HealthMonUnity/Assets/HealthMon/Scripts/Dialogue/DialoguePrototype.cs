using System;
using Healthmon.Beta;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class DialoguePrototype : MonoBehaviour
{
    [Header("UI")]
    [SerializeField] private TMP_InputField messageInput;
    [SerializeField] private TMP_Text userMessageText;
    [SerializeField] private TMP_Text characterResponseText;

    [Header("AR speech bubble (optional)")]
    [SerializeField] private TMP_Text floatingBubbleText;
    [SerializeField] private TMP_Text personalityText;
    [SerializeField]
    private QuestPrototype questPrototype;

    [Header("LLM Server")]
    [SerializeField] private string serverUrl = "http://127.0.0.1:8000";
    [NonSerialized] private string bearerToken;
    private string existingPetId;
    private HealthmonApiClient api;
    private Button sendButton;
    private bool connected;
    private bool waitingForReply;
    private float replyStarted;
    private TMP_Text sendLabel;
    private bool retryNeedsState;
    private bool conversationRequested, sessionStartPending;
    private bool sendWhenReady;
    private float preparationStarted;
    public string ServerUrl => serverUrl;
    public string RuntimeToken { get => bearerToken; set => bearerToken = value; }
    public string PetId => api == null ? null : api.PetId;
    public HealthmonApiClient Api => api;
    public bool IsConnected => connected;
    public string LastRequestId { get; private set; }
    public bool LastFallback { get; private set; }
    public string LastSpeech { get; private set; }

    private void Awake()
    {
        api = FindAnyObjectByType<HealthmonApiClient>();
        if (api == null) api = new GameObject("HealthMon Session").AddComponent<HealthmonApiClient>();
        bearerToken = Environment.GetEnvironmentVariable("HEALTHMON_USER_TOKEN") ?? "";
        existingPetId = Environment.GetEnvironmentVariable("HEALTHMON_PET_ID");
        serverUrl = Environment.GetEnvironmentVariable("HEALTHMON_SERVER_URL") ?? serverUrl;
        BindApiEvents();
        foreach (var button in FindObjectsByType<Button>(FindObjectsInactive.Include))
            for (int i = 0; i < button.onClick.GetPersistentEventCount(); i++)
                if (button.onClick.GetPersistentTarget(i) == this && button.onClick.GetPersistentMethodName(i) == nameof(SendMessage))
                    sendButton = button;
        SetCharacterSpeech("실제 LLM 서버에 Connect한 뒤 대화해 주세요.");
        if (sendButton != null) sendLabel = sendButton.GetComponentInChildren<TMP_Text>(true);
        ConfigureRuntimeLayout();
    }

    private void OnEnable()
    {
        if (api == null) api = Healthmon.Common.CommonServerConnection.Instance?.Api ?? FindAnyObjectByType<HealthmonApiClient>();
        if (api != null) BindApiEvents();
        if (sendButton != null) ConfigureRuntimeLayout();
        if (conversationRequested && api != null && !api.ConversationReady) sessionStartPending = true;
    }
    // Keep the original response field (used by DialogueRuntimeLayout) alive,
    // while mirroring all server states and LLM replies to the AR head bubble.
    private void SetCharacterSpeech(string message)
    {
        message = message ?? string.Empty;
        if (characterResponseText != null && characterResponseText.text != message)
            characterResponseText.text = message;
        if (floatingBubbleText != null && floatingBubbleText.text != message)
            floatingBubbleText.text = message;
    }

    private void ConfigureRuntimeLayout()
    {
        var layout = GetComponent<DialogueRuntimeLayout>() ?? gameObject.AddComponent<DialogueRuntimeLayout>();
        layout.Configure(messageInput, userMessageText, characterResponseText, sendButton);
    }
    private void BindApiEvents()
    {
        api.ChatReceived -= Receive; api.ChatReceived += Receive;
        api.FoodConfirmed -= ReactToFood; api.FoodConfirmed += ReactToFood;
        api.ConversationChanged -= ConversationChanged; api.ConversationChanged += ConversationChanged;
        api.ConversationFailed -= ConversationFailed; api.ConversationFailed += ConversationFailed;
    }

    private void Start()
    {
        if (Healthmon.Common.CommonServerConnection.UsesServerAuthority) return;
        if (!string.IsNullOrWhiteSpace(bearerToken)) Connect();
    }

    private void Update()
    {
        var common = Healthmon.Common.CommonServerConnection.Instance;
        if (Healthmon.Common.CommonServerConnection.UsesServerAuthority && common != null)
        {
            connected = common.IsConnected;
            serverUrl = common.BaseUrl ?? serverUrl;
        }
        if (sessionStartPending && connected && !api.IsBusy) PrepareConversation();
        if (sendButton != null) sendButton.interactable = connected && !api.IsBusy && !api.ConversationLoading;
        if (sendLabel != null) sendLabel.text = api.HasPendingChat && !api.IsBusy ? "다시 시도"
            : api.ConversationLoading ? "준비 중" : waitingForReply && api.IsBusy ? "답변 중" : "보내기";
        if (conversationRequested && api.ConversationLoading && !waitingForReply && string.IsNullOrEmpty(LastSpeech))
            SetCharacterSpeech($"대화 모델을 준비하고 있어… ({Mathf.FloorToInt(Time.realtimeSinceStartup - preparationStarted)}초)");
        if (waitingForReply && api.IsBusy)
        {
            int seconds = Mathf.FloorToInt(Time.realtimeSinceStartup - replyStarted);
            if (seconds >= 10) SetCharacterSpeech($"답변을 기다리고 있어… ({seconds}초)");
        }
    }

    public void EnterConversation()
    {
        if (conversationRequested) return;
        conversationRequested = true;
        sessionStartPending = true;
    }

    public void LeaveConversation()
    {
        conversationRequested = false;
        sessionStartPending = false;
        sendWhenReady = false;
        if (api != null) api.CloseConversation();
    }

    private void PrepareConversation()
    {
        sessionStartPending = false;
        preparationStarted = Time.realtimeSinceStartup;
        api.OpenConversation();
    }

    private void ConversationChanged(bool ready)
    {
        if (conversationRequested && ready && sendWhenReady)
        { sendWhenReady = false; SendMessage(); return; }
        if (conversationRequested && ready && !waitingForReply && string.IsNullOrEmpty(LastSpeech))
            SetCharacterSpeech("대화 준비됐어. 편하게 말해 줘.");
    }

    private void ConversationFailed()
    {
        if (conversationRequested && !waitingForReply)
            SetCharacterSpeech("대화 모델을 준비하지 못했어. ‘대화 준비’를 눌러 다시 시도해 줘.");
    }

    private void OnDisable() { LeaveConversation(); }
    private void OnApplicationPause(bool paused)
    {
        if (api == null) return;
        if (paused) api.CloseConversation();
        else if (conversationRequested) sessionStartPending = true;
    }

    public void Connect()
    {
        if (Healthmon.Common.CommonServerConnection.UsesServerAuthority)
        {
            Healthmon.Common.CommonServerConnection.Instance?.Connect(serverUrl, bearerToken, existingPetId);
            return;
        }
        if (!Application.isPlaying || connected || api.IsBusy) return;
        if (string.IsNullOrWhiteSpace(bearerToken)) { SetCharacterSpeech("사용자 토큰을 입력해 주세요."); return; }
        try
        {
            api.Configure(serverUrl, bearerToken);
            SetCharacterSpeech("서버 연결을 확인하고 있어요…");
            if (!string.IsNullOrWhiteSpace(existingPetId))
            {
                api.SelectPet(existingPetId);
                api.GetState(_ => Connected());
            }
            else api.ListPets(list =>
            {
                if (list.pets != null && list.pets.Length > 0)
                {
                    api.SelectPet(list.pets[0].pet_id);
                    api.GetState(_ => Connected());
                }
                else api.CreatePet(new PetSettings { name = "몽글이", profanity = "none" }, _ => Connected());
            });
        }
        catch (ArgumentException error) { SetCharacterSpeech(error.Message); }
    }

    private void Connected()
    {
        connected = true;
        SetCharacterSpeech("연결 완료. 대화와 음식 기록을 함께 기억할게.");
        Debug.Log($"[HealthMon LLM] Connected server={serverUrl} pet={api.PetId}");
    }

    public void SendMessage()
    {
        if (connected && api.HasPendingChat && !api.IsBusy) { RetryPendingChat(); return; }
        if (conversationRequested && !api.ConversationReady)
        {
            // The first send keeps the entered message and sends it once the
            // session opens, including after an editor reload or app resume.
            if (string.IsNullOrWhiteSpace(messageInput.text)) return;
            sendWhenReady = true;
            if (connected && !api.IsBusy && !api.ConversationLoading) PrepareConversation();
            return;
        }
        string message = messageInput.text.Trim();

        if (string.IsNullOrEmpty(message))
            return;

        if (!connected || api.IsBusy || api.HasPendingChat) return;
        userMessageText.text = message;
        BeginWaiting();
        messageInput.text = "";
        api.SendChat(message, failure: Failure);
    }

    public void RetryPendingChat()
    {
        if (!api.HasPendingChat || api.IsBusy) return;
        BeginWaiting();
        if (retryNeedsState)
            api.GetState(_ => { retryNeedsState = false; api.RebasePendingChatToLatestState(); api.RetryPendingChat(failure: Failure); }, Failure);
        else api.RetryPendingChat(failure: Failure);
    }

    private void BeginWaiting()
    {
        waitingForReply = true;
        replyStarted = Time.realtimeSinceStartup;
        SetCharacterSpeech("생각하고 있어…");
    }

    private void Receive(ChatResult result)
    {
        waitingForReply = false;
        retryNeedsState = false;
        LastRequestId = result.request_id;
        LastFallback = result.metrics != null && result.metrics.fallback;
        LastSpeech = result.response.speech;
        SetCharacterSpeech(result.response.speech);
        bool synthetic = result.provenance == "synthetic" || (result.metrics != null && result.metrics.synthetic) ||
            (result.metrics != null && result.metrics.backend == "mock") ||
            (result.metrics != null && result.metrics.handler != null &&
            (result.metrics.handler.IndexOf("mock", StringComparison.OrdinalIgnoreCase) >= 0 || result.metrics.handler.IndexOf("synthetic", StringComparison.OrdinalIgnoreCase) >= 0));
        if (personalityText != null) personalityText.text = synthetic ? "MOCK / SYNTHETIC — 개발용 합성 응답" : LastFallback ? "상태 : 답변 생성 실패" : "상태 : 대화 중";
        if (!LastFallback && questPrototype != null) questPrototype.AddDialogue();
        Debug.Log($"[HealthMon LLM] ChatDisplayed request_id={LastRequestId} fallback={LastFallback} attempts={result.metrics?.attempts} latency_seconds={result.metrics?.latency_seconds:F2}");
    }

    private void ReactToFood(FoodConfirmationResult result)
    {
        if (connected && api.ConversationReady && !api.IsBusy && !api.HasPendingChat)
        {
            BeginWaiting();
            SetCharacterSpeech("음식 기록을 보고 있어…");
            api.SendChat("방금 확정한 음식 기록을 보고 짧게 한마디 해줘.", failure: Failure);
        }
    }

    private void Failure(ApiFailure error)
    {
        waitingForReply = false;
        retryNeedsState = error.StatusCode == 409 && error.Message != null &&
            (error.Message.Contains("State version conflict") || error.Message.Contains("State changed"));
        SetCharacterSpeech(api.HasPendingChat
            ? "답변을 받지 못했어. ‘다시 시도’를 누르면 같은 요청을 확인할게."
            : $"서버 연결 오류 ({error.StatusCode}). 서버와 토큰을 확인해 주세요.");
        Debug.LogWarning($"[HealthMon LLM] request failed status={error.StatusCode}");
    }

    private void OnDestroy()
    {
        if (api == null) return;
        api.ChatReceived -= Receive;
        api.FoodConfirmed -= ReactToFood;
        api.ConversationChanged -= ConversationChanged;
        api.ConversationFailed -= ConversationFailed;
        api.CloseConversation();
    }
}
