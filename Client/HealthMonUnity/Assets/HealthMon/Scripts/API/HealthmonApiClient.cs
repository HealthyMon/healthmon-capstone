using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace Healthmon.Beta
{
    public sealed class HealthmonApiClient : MonoBehaviour
    {
        [SerializeField] private string baseUrl = "http://127.0.0.1:8000";
        [SerializeField, Min(1)] private int timeoutSeconds = 240;
        private string bearerToken; // Runtime only: never store a real token in scenes or source.
        private UnityWebRequest activeRequest;
        private Coroutine activeCoroutine;
        private Action<ApiFailure> activeFailure;
        private ChatRequest pendingChat;
        private string pendingPetId;
        private string conversationId;
        private Coroutine heartbeatCoroutine;
        public bool ConversationReady { get; private set; }
        public bool ConversationLoading { get; private set; }
        public event Action<bool> ConversationChanged;
        public event Action ConversationFailed;

        public string PetId { get; private set; }
        public long StateVersion { get; private set; }
        public bool HasStateVersion { get; private set; }
        public bool IsBusy { get; private set; }
        public bool HasPendingChat { get { return pendingChat != null; } }
        public string PendingRequestId { get { return pendingChat == null ? null : pendingChat.request_id; } }
        public event Action<ChatResult> ChatReceived;
        public event Action<FoodConfirmationResult> FoodConfirmed;
        public event Action<string> SpeechReceived, EmotionReceived, AnimationReceived;
        public event Action<ServerExecution> ExecutionReceived;
        public event Action<ApiFailure> Failed;

        private void Awake()
        {
            Application.runInBackground = true;
        }

        public void Configure(string url, string token)
        {
            if (IsBusy || HasPendingChat) throw new InvalidOperationException("Resolve pending chat before changing connection.");
            Uri address;
            if (!Uri.TryCreate(url, UriKind.Absolute, out address) ||
                (address.Scheme != "http" && address.Scheme != "https") ||
                !string.IsNullOrEmpty(address.Query) || !string.IsNullOrEmpty(address.Fragment) ||
                !string.IsNullOrEmpty(address.UserInfo))
                throw new ArgumentException("Use an HTTP(S) base URL without credentials, query or fragment.");
            CloseConversation();
            baseUrl = url.TrimEnd('/');
            bearerToken = NormalizeToken(token);
            PetId = null;
            HasStateVersion = false;
        }

        public void SetBearerToken(string token)
        {
            if (IsBusy) throw new InvalidOperationException("Wait for the current request before refreshing authentication.");
            bearerToken = NormalizeToken(token);
        }

        public void SelectPet(string petId)
        {
            if (IsBusy || HasPendingChat) throw new InvalidOperationException("Resolve pending chat before switching pets.");
            if (string.IsNullOrWhiteSpace(petId)) throw new ArgumentException("petId is required.");
            CloseConversation();
            PetId = petId;
            HasStateVersion = false;
        }

        public void ListPets(Action<PetList> success, Action<ApiFailure> failure = null)
        { Begin("GET", "/pets", null, success, failure); }

        public void OpenConversation()
        {
            if (ConversationReady || ConversationLoading || !RequirePet(null)) return;
            CloseConversation();
            conversationId = Guid.NewGuid().ToString("N");
            ConversationLoading = true;
            StartCoroutine(ConversationControl(conversationId, false));
            heartbeatCoroutine = StartCoroutine(ConversationHeartbeat(conversationId));
        }

        public void CloseConversation()
        {
            string previous = conversationId;
            conversationId = null;
            ConversationReady = false;
            ConversationLoading = false;
            if (heartbeatCoroutine != null) StopCoroutine(heartbeatCoroutine);
            heartbeatCoroutine = null;
            if (previous == null || string.IsNullOrEmpty(PetId) || string.IsNullOrEmpty(bearerToken)) return;
            // Begin immediately, even when this component is being disabled. The server's
            // heartbeat deadline is the backup if the app exits before delivery.
            var request = SessionRequest(previous, false, false);
            request.timeout = 10;
            var operation = request.SendWebRequest();
            operation.completed += _ => request.Dispose();
        }

        private UnityWebRequest SessionRequest(string id, bool active, bool heartbeat)
        {
            var request = new UnityWebRequest(baseUrl + PetPath(heartbeat ? "/chat-session/heartbeat" : "/chat-session"), "POST");
            request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(
                JsonUtility.ToJson(new ConversationIntent { session_id = id, active = active })));
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Authorization", "Bearer " + bearerToken);
            request.SetRequestHeader("Content-Type", "application/json");
            request.redirectLimit = 0;
            request.timeout = 160;
            return request;
        }

        private IEnumerator ConversationControl(string id, bool heartbeat)
        {
            using (var request = SessionRequest(id, true, heartbeat))
            {
                yield return request.SendWebRequest();
                if (conversationId != id) yield break; // Ignore an old tab's delayed callback.
                ConversationStatus result = null;
                if (request.result == UnityWebRequest.Result.Success)
                    try { result = JsonUtility.FromJson<ConversationStatus>(request.downloadHandler.text); }
                    catch (Exception) { }
                if (result == null || !result.active)
                {
                    bool wasLoading = ConversationLoading;
                    ConversationLoading = false;
                    ConversationReady = false;
                    ConversationFailed?.Invoke();
                    Debug.LogWarning("[HealthMon LLM] Conversation session unavailable status=" + request.responseCode);
                    if (wasLoading) CloseConversation();
                    yield break;
                }
                // A heartbeat can arrive while the open request is still loading weights.
                if (heartbeat && ConversationLoading) yield break;
                bool readinessChanged = ConversationReady != result.ready;
                ConversationLoading = false;
                ConversationReady = result.ready;
                if (readinessChanged || !heartbeat) ConversationChanged?.Invoke(ConversationReady);
            }
        }

        private IEnumerator ConversationHeartbeat(string id)
        {
            while (conversationId == id)
            {
                yield return new WaitForSecondsRealtime(20);
                if (conversationId != id) yield break;
                yield return ConversationControl(id, true);
            }
        }

        public void CreatePet(PetSettings settings, Action<CreatedPet> success, Action<ApiFailure> failure = null)
        {
            if (HasPendingChat) { Fail(0, "Resolve pending chat before creating a pet.", failure); return; }
            Begin<CreatedPet>("POST", "/pets", JsonUtility.ToJson(settings), result =>
            {
                PetId = result.pet_id;
                StateVersion = result.state_version;
                HasStateVersion = true;
                success?.Invoke(result);
            }, failure);
        }

        public void GetState(Action<PetState> success, Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            Begin<PetState>("GET", PetPath("/state"), null, result =>
            {
                StateVersion = result.state_version;
                HasStateVersion = true;
                success?.Invoke(result);
            }, failure);
        }

        public void GetHistory(Action<MessageHistory> success, int limit = 50, Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            Begin<MessageHistory>("GET", PetPath("/messages?limit=" + Mathf.Clamp(limit, 1, 100)), null, result =>
            {
                StateVersion = result.state_version;
                HasStateVersion = true;
                success?.Invoke(result);
            }, failure);
        }

        public void GetQuests(Action<QuestList> success, Action<ApiFailure> failure = null)
        {
            if (RequirePet(failure)) Begin("GET", PetPath("/quests"), null, success, failure);
        }

        public void AnalyzeFood(byte[] image, Action<FoodAnalysis> success, Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            if (HasPendingChat) { Fail(0, "Resolve pending chat before food analysis.", failure); return; }
            if (image == null || image.Length == 0 || image.Length > 12 * 1024 * 1024)
            { Fail(0, "Use an image up to 12 MiB.", failure); return; }
            Begin<FoodAnalysis>("POST", PetPath("/food/analyze"), null, result =>
            {
                if (result.schema_version != "healthmon.food.v1") { Fail(0, "Unexpected food contract.", failure); return; }
                success?.Invoke(result);
            }, failure, image);
        }

        public void ConfirmFood(string analysisId, int candidateId, float? grams,
            Action<FoodConfirmationResult> success, Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            if (HasPendingChat) { Fail(0, "Resolve pending chat before confirming food.", failure); return; }
            string body = grams.HasValue
                ? JsonUtility.ToJson(new FoodConfirmation { analysis_id = analysisId, candidate_id = candidateId, grams = grams.Value })
                : JsonUtility.ToJson(new FoodConfirmationWithoutQuantity { analysis_id = analysisId, candidate_id = candidateId });
            Begin<FoodConfirmationResult>("POST", PetPath("/food/confirm"), body, result =>
            {
                StateVersion = result.state_version;
                HasStateVersion = true;
                success?.Invoke(result);
                if (!result.duplicate) FoodConfirmed?.Invoke(result);
            }, failure);
        }

        public void SendChat(string text, Action<ChatResult> success = null, Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            if (IsBusy || HasPendingChat) { Fail(0, "Retry or resolve the pending request first.", failure); return; }
            if (!HasStateVersion) { Fail(0, "GetState before sending chat.", failure); return; }
            if (string.IsNullOrWhiteSpace(text) || text.Length > 1500)
            { Fail(0, "Enter 1 to 1500 characters.", failure); return; }
            pendingPetId = PetId;
            pendingChat = new ChatRequest { request_id = Guid.NewGuid().ToString("N"), text = text, state_version = StateVersion };
            RetryPendingChat(success, failure);
        }

        // Retries keep the same ID, text and original version. No automatic repeat generation.
        public void RetryPendingChat(Action<ChatResult> success = null, Action<ApiFailure> failure = null)
        {
            if (pendingChat == null) { Fail(0, "No pending chat.", failure); return; }
            if (pendingPetId != PetId) { Fail(0, "Pending chat belongs to another pet.", failure); return; }
            Begin<ChatResult>("POST", PetPath("/chat"), JsonUtility.ToJson(pendingChat), result =>
            {
                if (result.schema_version != "healthmon.v1" || result.response == null ||
                    result.request_id != pendingChat.request_id)
                { Fail(0, "Unexpected response contract; pending request retained.", failure); return; }
                pendingChat = null;
                pendingPetId = null;
                StateVersion = result.state_version;
                HasStateVersion = true;
                ChatReceived?.Invoke(result);
                SpeechReceived?.Invoke(result.response.speech);
                EmotionReceived?.Invoke(result.response.emotion);
                AnimationReceived?.Invoke(result.response.animation);
                ExecutionReceived?.Invoke(result.execution);
                success?.Invoke(result);
            }, failure);
        }

        // Use after an explicit state-version 409 and a successful GetState, not for timeouts.
        public void RebasePendingChatToLatestState()
        {
            if (IsBusy || pendingChat == null || !HasStateVersion)
                throw new InvalidOperationException("Refresh state with the pending request idle first.");
            pendingChat.state_version = StateVersion; // ID and text stay fixed.
        }

        // Does not undo work on the server. Reconcile history/state before intentionally abandoning.
        public void DiscardPendingChat()
        {
            if (IsBusy) throw new InvalidOperationException("Cancel the current transport first.");
            pendingChat = null;
            pendingPetId = null;
        }

        // Contains user text, but no credentials. Persist securely if app restarts must survive retries.
        public string ExportPendingChat()
        {
            return pendingChat == null ? null : JsonUtility.ToJson(
                new PendingChatSnapshot { pet_id = pendingPetId, request = pendingChat });
        }

        public void RestorePendingChat(string json)
        {
            if (IsBusy || HasPendingChat) throw new InvalidOperationException("Pending chat already exists.");
            var snapshot = JsonUtility.FromJson<PendingChatSnapshot>(json);
            if (snapshot == null || snapshot.request == null || snapshot.pet_id != PetId ||
                string.IsNullOrWhiteSpace(snapshot.request.request_id) || snapshot.request.request_id.Length < 8 ||
                snapshot.request.request_id.Length > 100 || string.IsNullOrWhiteSpace(snapshot.request.text) ||
                snapshot.request.text.Length > 1500 || snapshot.request.state_version < 0)
                throw new ArgumentException("Invalid pending chat snapshot or pet mismatch.");
            pendingPetId = snapshot.pet_id;
            pendingChat = snapshot.request;
        }

        public void DecideQuest(string offerId, bool accept, Action<QuestDecisionResult> success,
            Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            if (HasPendingChat) { Fail(0, "Resolve pending chat before deciding a quest.", failure); return; }
            if (string.IsNullOrWhiteSpace(offerId)) { Fail(0, "Use execution.offer_id, not action.target_id.", failure); return; }
            Begin<QuestDecisionResult>("POST", PetPath("/quests/" + Escape(offerId) + "/decision"),
                JsonUtility.ToJson(new QuestDecision { decision = accept ? "accept" : "reject" }), result =>
                {
                    HasStateVersion = false;
                    success?.Invoke(result); // Caller refreshes state and quests; duplicate response has no version.
                }, failure);
        }

        public void CancelCurrent(bool notify = true)
        {
            if (!IsBusy) return;
            var callback = activeFailure;
            if (activeRequest != null) activeRequest.Abort();
            if (activeCoroutine != null) StopCoroutine(activeCoroutine);
            Cleanup();
            if (notify) Report(new ApiFailure(0, "Request cancelled locally; server work may continue.", true), callback);
        }

        private void OnDisable() { CloseConversation(); CancelCurrent(false); }
        private void OnApplicationQuit() { CloseConversation(); }
        private static string NormalizeToken(string token)
        {
            if (token != null && (token.IndexOf('\r') >= 0 || token.IndexOf('\n') >= 0))
                throw new ArgumentException("Bearer token must be one line.");
            return token == null ? "" : token.Trim();
        }
        private string PetPath(string suffix) { return "/pets/" + Escape(PetId) + suffix; }
        private static string Escape(string value) { return Uri.EscapeDataString(value); }
        private bool RequirePet(Action<ApiFailure> failure)
        {
            if (!string.IsNullOrEmpty(PetId)) return true;
            Fail(0, "Select or create a pet first.", failure);
            return false;
        }
        private void Fail(long code, string message, Action<ApiFailure> callback)
        { Report(new ApiFailure(code, message), callback); }
        private void Report(ApiFailure error, Action<ApiFailure> callback)
        { Failed?.Invoke(error); callback?.Invoke(error); }

        private void Begin<T>(string method, string path, string json, Action<T> success, Action<ApiFailure> failure, byte[] image = null) where T : class
        {
            if (!isActiveAndEnabled) { Fail(0, "Client component is disabled.", failure); return; }
            if (IsBusy) { Fail(0, "A request is already running.", failure); return; }
            if (string.IsNullOrWhiteSpace(bearerToken)) { Fail(401, "Configure a bearer token at runtime.", failure); return; }
            IsBusy = true;
            activeFailure = failure;
            activeCoroutine = StartCoroutine(Request(method, path, json, success, failure, image));
        }

        private IEnumerator Request<T>(string method, string path, string json,
            Action<T> success, Action<ApiFailure> failure, byte[] image = null) where T : class
        {
            // Yield once so cancellation has the Coroutine handle before the request starts.
            yield return null;
            activeRequest = new UnityWebRequest(baseUrl + path, method);
            activeRequest.downloadHandler = new DownloadHandlerBuffer();
            activeRequest.timeout = Mathf.Max(1, timeoutSeconds);
            activeRequest.redirectLimit = 0; // Avoid forwarding authorization to redirected hosts.
            activeRequest.SetRequestHeader("Authorization", "Bearer " + bearerToken);
            activeRequest.SetRequestHeader("Accept", "application/json");
            if (json != null)
            {
                activeRequest.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
                activeRequest.SetRequestHeader("Content-Type", "application/json");
            }
            else if (image != null)
            {
                activeRequest.uploadHandler = new UploadHandlerRaw(image);
                activeRequest.SetRequestHeader("Content-Type", "application/octet-stream");
            }
            var operation = activeRequest.SendWebRequest();
            float started = Time.realtimeSinceStartup;
            while (!operation.isDone)
            {
                if (Time.realtimeSinceStartup - started >= Mathf.Max(1, timeoutSeconds))
                {
                    activeRequest.Abort();
                    Cleanup();
                    Report(new ApiFailure(0, "Response timed out; retry the same request ID."), failure);
                    yield break;
                }
                yield return null;
            }
            var status = activeRequest.responseCode;
            var body = activeRequest.downloadHandler.text;
            var transportError = activeRequest.error;
            var ok = activeRequest.result == UnityWebRequest.Result.Success;
            Cleanup(); // Callbacks may safely start the next request.
            if (!ok)
            {
                // Server detail is retained for diagnostics, never inject it into character speech.
                Report(new ApiFailure(status, string.IsNullOrEmpty(body) ? transportError : body), failure);
                yield break;
            }
            T parsed = null;
            string parseError = null;
            try { parsed = JsonUtility.FromJson<T>(body); }
            catch (Exception error) { parseError = error.Message; }
            if (parsed == null) { Fail(status, "Invalid JSON response: " + parseError, failure); yield break; }
            success?.Invoke(parsed);
        }

        private void Cleanup()
        {
            if (activeRequest != null) activeRequest.Dispose();
            activeRequest = null;
            activeCoroutine = null;
            activeFailure = null;
            IsBusy = false;
        }
    }
}
