using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using Healthmon.Common;

namespace Healthmon.Beta
{
    public sealed class HealthmonApiClient : MonoBehaviour
    {
        [SerializeField] private string baseUrl = "http://127.0.0.1:8000";
        [SerializeField, Min(1)] private int timeoutSeconds = 240;
        [SerializeField, Min(1)] private int foodTimeoutSeconds = 300;
        [NonSerialized] private string bearerToken; // Exclude Editor hot-reload serialization too.
        private UnityWebRequest activeRequest;
        private Coroutine activeCoroutine;
        private Action<ApiFailure> activeFailure;
        [SerializeReference] private ChatRequest pendingChat;
        private string pendingPetId;
        [SerializeReference] private PendingChatSnapshot pendingScope; // Frozen identity only; no token or duplicate request text.
        private int emptyPlaceholderNormalizations;
        private string conversationId;
        private Coroutine heartbeatCoroutine;
        private UnityWebRequest stateRequest;
        private Coroutine stateCoroutine;
        private readonly StateVersionGate stateGate = new StateVersionGate();
        private string serverInstanceId = "unverified", ownerId = "unverified";
        public bool IsStateBusy { get { return stateCoroutine != null; } }
        public string BaseUrl { get { return baseUrl; } }
        public bool IsConfigured { get { return !string.IsNullOrEmpty(bearerToken); } }
        public string VerifiedServerInstanceId { get { return serverInstanceId; } }
        public string VerifiedOwnerId { get { return ownerId; } }
        public event Action<PetState> StateReceived;
        public bool ConversationReady { get; private set; }
        public bool ConversationLoading { get; private set; }
        public event Action<bool> ConversationChanged;
        public event Action ConversationFailed;

        public string PetId { get; private set; }
        public long StateVersion { get; private set; }
        public bool HasStateVersion { get; private set; }
        public bool IsBusy { get; private set; }
        public bool HasPendingChat { get { NormalizeEmptyPendingPlaceholder(); return pendingChat != null; } }
        public bool IsReauthenticating { get; private set; }
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
        private void OnEnable()
        {
            NormalizeEmptyPendingPlaceholder();
            if (activeCoroutine == null && activeRequest == null) { IsBusy = false; IsReauthenticating = false; }
        }
        private void NormalizeEmptyPendingPlaceholder()
        {
            if (!CommonServerContract.IsEmptyPendingPlaceholder(pendingChat, pendingPetId, pendingScope)) return;
            pendingChat = null; pendingScope = null; emptyPlaceholderNormalizations++;
        }
        public PendingChatDiagnostics GetPendingDiagnostics()
        {
            return new PendingChatDiagnostics { has_pending_object = pendingChat != null,
                has_request_id = !string.IsNullOrEmpty(pendingChat?.request_id), has_text = !string.IsNullOrEmpty(pendingChat?.text),
                has_pending_pet = !string.IsNullOrEmpty(pendingPetId), has_frozen_scope = pendingScope != null &&
                    (!string.IsNullOrEmpty(pendingScope.base_url) || !string.IsNullOrEmpty(pendingScope.server_instance_id) ||
                     !string.IsNullOrEmpty(pendingScope.owner_id) || !string.IsNullOrEmpty(pendingScope.pet_id)),
                credential_available = IsConfigured, empty_placeholder_normalizations = emptyPlaceholderNormalizations };
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
            string safeToken = CommonServerContract.NormalizeBearerToken(token);
            CloseConversation();
            CancelStateRequest();
            baseUrl = url.TrimEnd('/');
            bearerToken = safeToken;
            PetId = null;
            HasStateVersion = false;
            serverInstanceId = ownerId = "unverified";
            stateGate.Reset(baseUrl, ownerId, "");
        }

        public void GetServerInfo(Action<ServerInfo> success, Action<ApiFailure> failure = null)
        { Begin("GET", "/server-info", null, success, failure); }
        public void GetIdentity(Action<ServerIdentity> success, Action<ApiFailure> failure = null)
        { Begin("GET", "/identity", null, success, failure); }
        public void BindIdentity(string server, string owner)
        {
            if (string.IsNullOrWhiteSpace(server) || string.IsNullOrWhiteSpace(owner))
                throw new ArgumentException("Verified server and identity are required.");
            serverInstanceId = server; ownerId = owner;
            ResetStateScope();
        }
        private void ResetStateScope()
        {
            CancelStateRequest();
            stateGate.Reset(serverInstanceId, ownerId, PetId ?? "");
            HasStateVersion = false;
            StateVersion = 0;
        }
        private void ObserveVersion(long version)
        {
            if (version < 0) return;
            StateVersion = HasStateVersion ? Math.Max(StateVersion, version) : version;
            HasStateVersion = true;
            stateGate.Accept(stateGate.Generation, StateVersion);
        }

        public void SetBearerToken(string token)
        {
            if (IsBusy || HasPendingChat) throw new InvalidOperationException("Resolve pending work before changing authentication.");
            CloseConversation();
            bearerToken = CommonServerContract.NormalizeBearerToken(token);
            // Authentication refresh can represent another account; never retain its snapshot.
            ownerId = "unverified"; PetId = null;
            ResetStateScope();
        }

        public void SelectPet(string petId)
        {
            if (IsBusy || HasPendingChat) throw new InvalidOperationException("Resolve pending chat before switching pets.");
            if (string.IsNullOrWhiteSpace(petId)) throw new ArgumentException("petId is required.");
            CloseConversation();
            PetId = petId;
            ResetStateScope();
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
                ResetStateScope();
                ObserveVersion(result.state_version);
                success?.Invoke(result);
            }, failure);
        }

        public void GetState(Action<PetState> success, Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            if (!IsConfigured) { Fail(401, "Configure authentication first.", failure); return; }
            if (IsStateBusy) { Fail(0, "A state refresh is already running.", failure); return; }
            stateCoroutine = StartCoroutine(RequestState(stateGate.Generation, PetId, success, failure));
        }

        private IEnumerator RequestState(int generation, string pet, Action<PetState> success, Action<ApiFailure> failure)
        {
            yield return null;
            using (var request = new UnityWebRequest(baseUrl + "/pets/" + Escape(pet) + "/state", "GET"))
            {
                stateRequest = request;
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Authorization", "Bearer " + bearerToken);
                request.SetRequestHeader("Accept", "application/json");
                request.timeout = 20; request.redirectLimit = 0;
                yield return request.SendWebRequest();
                stateRequest = null; stateCoroutine = null;
                if (generation != stateGate.Generation) yield break;
                if (request.result != UnityWebRequest.Result.Success)
                { Fail(request.responseCode, "State refresh failed; previous verified state retained.", failure); yield break; }
                string json = request.downloadHandler.text;
                PetState state = null;
                try { if (CommonServerContract.HasRequiredStateFields(json)) state = JsonUtility.FromJson<PetState>(json); }
                catch (Exception) { }
                if (state == null || !state.IsValidCommonState(pet))
                { Fail(request.responseCode, "Invalid healthmon.v2.2 state response.", failure); yield break; }
                if (!stateGate.Accept(generation, state.state_version)) yield break;
                ObserveVersion(state.state_version);
                StateReceived?.Invoke(state);
                success?.Invoke(state);
            }
        }
        private void CancelStateRequest()
        {
            if (stateRequest != null) { stateRequest.Abort(); stateRequest.Dispose(); }
            if (stateCoroutine != null) StopCoroutine(stateCoroutine);
            stateRequest = null; stateCoroutine = null;
        }

        public void GetHistory(Action<MessageHistory> success, int limit = 50, Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            Begin<MessageHistory>("GET", PetPath("/messages?limit=" + Mathf.Clamp(limit, 1, 100)), null, result =>
            {
                ObserveVersion(result.state_version);
                success?.Invoke(result);
            }, failure);
        }

        public void GetQuests(Action<QuestList> success, Action<ApiFailure> failure = null)
        {
            if (RequirePet(failure)) Begin("GET", PetPath("/quests"), null, success, failure);
        }

        public void MarkProposalShown(string offerId, Action<QuestOffer> success, Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            if (HasPendingChat) { Fail(0, "Resolve pending chat before acknowledging a proposal.", failure); return; }
            if (string.IsNullOrWhiteSpace(offerId)) { Fail(0, "An actual displayed proposal ID is required.", failure); return; }
            string pet = PetId;
            Begin<QuestOffer>("POST", PetPath("/proposals/" + Escape(offerId) + "/shown"), null, result =>
            {
                if (result.id != offerId || result.pet_id != pet || !result.is_proposal || result.excluded ||
                    !string.IsNullOrEmpty(result.cancelled_at) || string.IsNullOrWhiteSpace(result.shown_at))
                { Fail(0, "Invalid proposal display acknowledgement; retry after refreshing quests.", failure); return; }
                success?.Invoke(result);
            }, failure);
        }

        public void AnalyzeFood(byte[] image, Action<FoodAnalysis> success, Action<ApiFailure> failure = null)
        {
            if (!RequirePet(failure)) return;
            if (HasPendingChat) { Fail(0, "Resolve pending chat before food analysis.", failure); return; }
            if (image == null || image.Length == 0 || image.Length > 12 * 1024 * 1024)
            { Fail(0, "Use an image up to 12 MiB.", failure); return; }
            Begin<FoodAnalysis>("POST", PetPath("/food/analyze"), null, result =>
            {
                if (!CommonServerContract.ValidFoodAnalysis(result)) { Fail(0, "Unexpected or incomplete food contract.", failure); return; }
                success?.Invoke(result);
            }, failure, image);
        }

        public void ConfirmFood(string analysisId, int candidateId, float? grams,
            Action<FoodConfirmationResult> success, Action<ApiFailure> failure = null,
            string mealType = "snack", bool kcalReconfirmed = false, float? vegetableFruitGrams = null, bool syntheticFixture = false)
        {
            if (!RequirePet(failure)) return;
            if (HasPendingChat) { Fail(0, "Resolve pending chat before confirming food.", failure); return; }
            string body;
            try { body = JsonUtility.ToJson(CommonServerContract.FoodConfirmationPayload(analysisId, candidateId, grams, vegetableFruitGrams, mealType, kcalReconfirmed, syntheticFixture)); }
            catch (ArgumentException) { Fail(0, "Invalid explicitly confirmed food quantities.", failure); return; }
            Begin<FoodConfirmationResult>("POST", PetPath("/food/confirm"), body, result =>
            {
                if (!result.stored || string.IsNullOrWhiteSpace(result.source_id) || result.analysis_id != analysisId || result.state == null || !result.state.IsValidCommonState(PetId) || result.state.state_version != result.state_version)
                { Fail(0, "Invalid food confirmation state; refresh before retrying.", failure); return; }
                ObserveVersion(result.state_version);
                success?.Invoke(result);
                if (!result.duplicate && !syntheticFixture) FoodConfirmed?.Invoke(result);
                RefreshCommonState();
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
            pendingScope = CurrentPendingScope();
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
                pendingScope = null;
                ObserveVersion(result.state_version);
                ChatReceived?.Invoke(result);
                SpeechReceived?.Invoke(result.response.speech);
                EmotionReceived?.Invoke(result.response.emotion);
                AnimationReceived?.Invoke(result.response.animation);
                ExecutionReceived?.Invoke(result.execution);
                success?.Invoke(result);
                RefreshCommonState();
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
            pendingScope = null;
        }

        // Contains user text, but no credentials. Persist securely if app restarts must survive retries.
        public string ExportPendingChat()
        {
            var scope = EnsurePendingScope();
            return pendingChat == null ? null : JsonUtility.ToJson(
                new PendingChatSnapshot { pet_id = pendingPetId, request = pendingChat,
                    server_instance_id = scope?.server_instance_id, owner_id = scope?.owner_id, base_url = scope?.base_url });
        }

        public void RestorePendingChat(string json)
        {
            if (IsBusy || HasPendingChat) throw new InvalidOperationException("Pending chat already exists.");
            var snapshot = JsonUtility.FromJson<PendingChatSnapshot>(json);
            if (snapshot == null || snapshot.request == null || snapshot.pet_id != PetId ||
                (CommonServerConnection.UsesServerAuthority && (snapshot.server_instance_id != serverInstanceId ||
                 snapshot.owner_id != ownerId || snapshot.base_url != baseUrl || ownerId == "unverified")) ||
                string.IsNullOrWhiteSpace(snapshot.request.request_id) || snapshot.request.request_id.Length < 8 ||
                snapshot.request.request_id.Length > 100 || string.IsNullOrWhiteSpace(snapshot.request.text) ||
                snapshot.request.text.Length > 1500 || snapshot.request.state_version < 0)
                throw new ArgumentException("Invalid pending chat snapshot or pet mismatch.");
            pendingPetId = snapshot.pet_id;
            pendingChat = snapshot.request;
            pendingScope = CurrentPendingScope();
        }

        private PendingChatSnapshot CurrentPendingScope()
        { return new PendingChatSnapshot { base_url = baseUrl, server_instance_id = serverInstanceId, owner_id = ownerId, pet_id = pendingPetId }; }
        private PendingChatSnapshot EnsurePendingScope()
        {
            if (pendingChat == null) return null;
            // A request already in flight when this recovery code is hot-loaded
            // may predate pendingScope. Adopt only its still-known verified scope.
            if (pendingScope == null)
            {
                var legacy = CurrentPendingScope();
                if (CommonServerContract.MatchesPendingScope(legacy, baseUrl, serverInstanceId, ownerId, PetId)) pendingScope = legacy;
            }
            return pendingScope;
        }

        // Re-authentication is intentionally separate from Configure: pending work
        // never grants permission to switch its server, account or pet.
        public void ReauthenticatePendingChat(string url, string token, string pet, Action<PetState> success, Action<ApiFailure> failure = null)
        {
            if (!isActiveAndEnabled || IsBusy || !HasPendingChat)
            { Fail(0, "An idle pending chat is required for same-connection authentication.", failure); return; }
            var scope = EnsurePendingScope();
            string candidate;
            try { candidate = CommonServerContract.NormalizeBearerToken(token); }
            catch (ArgumentException) { Fail(0, "Bearer token must be one line.", failure); return; }
            if (string.IsNullOrWhiteSpace(candidate) || !CommonServerContract.MatchesPendingScope(scope, url, serverInstanceId, ownerId, pet) || pet != PetId)
            { Fail(403, "Only the frozen pending server, account and pet may be re-authenticated.", failure); return; }
            CloseConversation(); CancelStateRequest();
            IsBusy = true; IsReauthenticating = true; activeFailure = failure;
            activeCoroutine = StartCoroutine(RecoverPendingAuthentication(scope, candidate, success, failure));
        }

        private IEnumerator RecoverPendingAuthentication(PendingChatSnapshot scope, string candidate, Action<PetState> success, Action<ApiFailure> failure)
        {
            var original = pendingChat;
            int generation = stateGate.Generation;
            string body = null;
            ApiFailure error = null;
            yield return null; // Retain the coroutine handle for cancellation.
            // Do not send the candidate credential until the selected server ID matches.
            yield return RecoveryRequest(scope.base_url, "/server-info", null, value => body = value, value => error = value);
            var info = DecodeRecovery<ServerInfo>(body);
            if (error == null && (info == null || info.server_instance_id != scope.server_instance_id))
                error = new ApiFailure(403, "Server identity differs from the pending request.");
            if (error == null)
            {
                body = null;
                yield return RecoveryRequest(scope.base_url, "/identity", candidate, value => body = value, value => error = value);
                var identity = DecodeRecovery<ServerIdentity>(body);
                if (error == null && (identity == null || identity.owner_id != scope.owner_id))
                    error = new ApiFailure(403, "Token owner differs from the pending request.");
            }
            PetState verified = null;
            if (error == null)
            {
                body = null;
                yield return RecoveryRequest(scope.base_url, "/pets/" + Escape(scope.pet_id) + "/state", candidate,
                    value => body = value, value => error = value);
                if (CommonServerContract.HasRequiredStateFields(body)) verified = DecodeRecovery<PetState>(body);
                if (error == null && (verified == null || !verified.IsValidCommonState(scope.pet_id)))
                    error = new ApiFailure(403, "Pending pet ownership/state could not be verified.");
            }
            if (generation != stateGate.Generation || pendingChat != original ||
                !CommonServerContract.MatchesPendingScope(scope, baseUrl, serverInstanceId, ownerId, PetId))
                error = new ApiFailure(409, "Pending connection changed during authentication; request retained.");
            if (error != null)
            { Cleanup(); Report(error, failure); yield break; }
            // All three checks succeeded. Neither pending request nor its original
            // request ID, text, version and frozen scope is changed or retransmitted.
            bearerToken = candidate;
            ResetStateScope(); ObserveVersion(verified.state_version);
            Cleanup();
            StateReceived?.Invoke(verified);
            success?.Invoke(verified);
        }
        private static T DecodeRecovery<T>(string json) where T : class
        { try { return string.IsNullOrWhiteSpace(json) ? null : JsonUtility.FromJson<T>(json); } catch (Exception) { return null; } }
        private IEnumerator RecoveryRequest(string url, string path, string candidate, Action<string> success, Action<ApiFailure> failure)
        {
            activeRequest = UnityWebRequest.Get(CommonServerContract.ResolveApiUrl(url, path));
            activeRequest.timeout = Mathf.Max(1, timeoutSeconds); activeRequest.redirectLimit = 0;
            activeRequest.SetRequestHeader("Accept", "application/json");
            if (candidate != null) activeRequest.SetRequestHeader("Authorization", "Bearer " + candidate);
            var operation = activeRequest.SendWebRequest();
            float started = Time.realtimeSinceStartup;
            while (!operation.isDone)
            {
                if (Time.realtimeSinceStartup - started >= Mathf.Max(1, timeoutSeconds))
                { activeRequest.Abort(); failure(new ApiFailure(0, "Authentication verification timed out; pending request retained.")); break; }
                yield return null;
            }
            if (operation.isDone)
            {
                if (activeRequest.result == UnityWebRequest.Result.Success) success(activeRequest.downloadHandler.text);
                else failure(new ApiFailure(activeRequest.responseCode, "Authentication verification failed; pending request retained."));
            }
            activeRequest.Dispose(); activeRequest = null;
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
                    RefreshCommonState();
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

        public void RefreshCommonState()
        { if (!IsStateBusy && !string.IsNullOrEmpty(PetId)) GetState(null); }
        private void OnDisable() { CloseConversation(); CancelCurrent(false); CancelStateRequest(); }
        private void OnApplicationQuit() { CloseConversation(); }
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
            int generation = stateGate.Generation;
            // Yield once so cancellation has the Coroutine handle before the request starts.
            yield return null;
            activeRequest = new UnityWebRequest(baseUrl + path, method);
            activeRequest.downloadHandler = new DownloadHandlerBuffer();
            int requestTimeout = Mathf.Max(1, typeof(T) == typeof(FoodAnalysis) ? Mathf.Max(timeoutSeconds, foodTimeoutSeconds) : timeoutSeconds);
            activeRequest.timeout = requestTimeout;
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
                if (Time.realtimeSinceStartup - started >= requestTimeout)
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
            if (generation != stateGate.Generation) yield break;
            if (!ok)
            {
                // Server detail is retained for diagnostics, never inject it into character speech.
                // Do not expose response bodies containing user data in UI or logs.
                Report(new ApiFailure(status, status == 409 ? "State version conflict; refresh before retry." : "Request failed (HTTP " + status + ")."), failure);
                yield break;
            }
            T parsed = null;
            string parseError = null;
            if (typeof(T) == typeof(FoodConfirmationResult) && !CommonServerContract.HasRequiredStateFields(body))
            { Fail(status, "Food confirmation omitted required server state fields.", failure); yield break; }
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
            IsReauthenticating = false;
        }
    }
}
