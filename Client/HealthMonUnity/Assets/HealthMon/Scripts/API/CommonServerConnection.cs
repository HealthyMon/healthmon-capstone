using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Healthmon.Beta;
using UnityEngine;
using UnityEngine.Networking;

namespace Healthmon.Common
{
    // Development connection surface deliberately created at runtime: team scene layouts/GUIDs
    // remain untouched. Credentials live only in this component or Android Keystore storage.
    [DefaultExecutionOrder(-10000)]
    public sealed class CommonServerConnection : MonoBehaviour
    {
        public static CommonServerConnection Instance { get; private set; }
        public static bool LocalDemoEnabled { get; private set; }
        public static bool UsesServerAuthority { get { return !LocalDemoEnabled; } }
        public HealthmonApiClient Api { get; private set; }
        public PetState LatestState { get; private set; }
        public string ServerInstanceId { get; private set; }
        public string OwnerId { get; private set; }
        public string EnvironmentName { get; private set; }
        public bool IsConnected { get; private set; }
        public string BaseUrl { get; private set; }
        public string Status { get; private set; } = "Configure the common server and a development user token.";
        public PhoneSyncStatus PhoneStatus { get; private set; }
        public string NextFoodMealType { get; private set; } = "snack";
        public bool NextFoodKcalReconfirmed { get; private set; }
        public event Action<PetState> StateChanged;
        private string urlInput, petInput = "";
        [NonSerialized] private string tokenInput = "", runtimeToken;
        private bool expanded, connecting, phoneBusy;
        private float nextRefresh;
        private int configGeneration;
        private Vector2 scroll;
        private QuestList quests;
        public QuestList LatestQuests => quests;
        private readonly ProposalDisplayGate proposalDisplays = new ProposalDisplayGate();
        private readonly PhoneSyncConfigurationQueue phoneConfigurations = new PhoneSyncConfigurationQueue();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void Bootstrap()
        {
            LocalDemoEnabled = System.Environment.GetEnvironmentVariable("HEALTHMON_LOCAL_DEMO") == "1";
            if (Instance == null) new GameObject("HealthMon Common Server").AddComponent<CommonServerConnection>();
        }
        private void Awake()
        {
            if (Instance != null && Instance != this) { Destroy(gameObject); return; }
            Instance = this;
            DontDestroyOnLoad(gameObject);
            Api = gameObject.AddComponent<HealthmonApiClient>();
            Api.StateReceived += Received;
            HealthMonAndroidBridge.Initialize();
            urlInput = System.Environment.GetEnvironmentVariable("API_BASE_URL") ??
                System.Environment.GetEnvironmentVariable("HEALTHMON_SERVER_URL") ?? "http://127.0.0.1:8000";
            tokenInput = System.Environment.GetEnvironmentVariable("HEALTHMON_USER_TOKEN") ?? "";
            petInput = System.Environment.GetEnvironmentVariable("HEALTHMON_PET_ID") ?? "";
            expanded = false;
        }
        private void Start()
        {
            if (!UsesServerAuthority) { Status = "LOCAL DEMO — synthetic local rewards; no server sync."; return; }
            if (!string.IsNullOrEmpty(tokenInput)) Connect(urlInput, tokenInput, petInput);
        }
        private void OnEnable()
        {
            if (Instance != null && Instance != this) return;
            Instance = this;
            if (Api == null) Api = GetComponent<HealthmonApiClient>();
            if (Api == null) return;
            Api.StateReceived -= Received; Api.StateReceived += Received;
            if (string.IsNullOrEmpty(runtimeToken) || !Api.IsConfigured)
            {
                IsConnected = false; connecting = false;
                Status = Api.HasPendingChat ? "Re-enter the same account token to recover the retained chat." : "Open developer settings and enter a user token.";
            }
        }
        public void Connect(string url, string token, string petId = null)
        {
            if (connecting || Api.IsBusy || Api.HasPendingChat)
            { Status = "Resolve the pending request before changing server/account/pet."; return; }
            if (string.IsNullOrWhiteSpace(token)) { Status = "Enter a user token."; return; }
            try
            {
                url = CommonServerContract.NormalizeBaseUrl(url);
                token = CommonServerContract.NormalizeBearerToken(token);
                Api.Configure(url, token);
            }
            catch (ArgumentException) { Status = "Invalid URL or token format."; return; }
            configGeneration++;
            quests = null; proposalDisplays.Reset(null, null, null);
            IsConnected = false; connecting = true; LatestState = null;
            ServerInstanceId = OwnerId = EnvironmentName = null;
            BaseUrl = url; runtimeToken = token; tokenInput = "";
            foreach (var state in FindObjectsByType<PetStateManager>(FindObjectsInactive.Include)) state.ClearServerState();
            // Clear old Android destination before any uploads can be enabled for a new login.
            HealthMonAndroidBridge.ClearServerSync();
            Status = "Checking server identity…";
            Api.GetServerInfo(info =>
            {
                if (string.IsNullOrWhiteSpace(info.server_instance_id) || string.IsNullOrWhiteSpace(info.environment))
                { Failed(new ApiFailure(0, "Invalid server identity.")); return; }
                ServerInstanceId = info.server_instance_id; EnvironmentName = info.environment;
                Api.GetIdentity(identity =>
                {
                    if (string.IsNullOrWhiteSpace(identity.owner_id)) { Failed(new ApiFailure(0, "Invalid account identity.")); return; }
                    OwnerId = identity.owner_id;
                    Api.BindIdentity(ServerInstanceId, OwnerId);
                    if (!string.IsNullOrWhiteSpace(petId)) SelectPet(petId);
                    else Api.ListPets(list =>
                    {
                        if (list.pets != null && list.pets.Length > 0)
                        {
                            string saved = PlayerPrefs.GetString(SelectedPetKey, "");
                            var previous = Array.Find(list.pets, candidate => candidate.pet_id == saved);
                            SelectPet(previous != null ? previous.pet_id : list.pets[0].pet_id);
                        }
                        else { connecting = false; Status = "Verified account. Create a pet to continue."; }
                    }, Failed);
                }, Failed);
            }, Failed);
        }
        private void SelectPet(string pet)
        {
            Api.SelectPet(pet); petInput = pet;
            proposalDisplays.Reset(ServerInstanceId, OwnerId, pet);
            Api.GetState(_ =>
            {
                connecting = false; IsConnected = true;
                urlInput = BaseUrl;
                Status = "Connected — " + EnvironmentName + " / " + CommonServerContract.RuleVersion;
                PlayerPrefs.SetString(SelectedPetKey, Api.PetId); PlayerPrefs.Save();
                ConfigurePhone(configGeneration);
                RefreshQuests();
            }, Failed);
        }
        private string SelectedPetKey
        {
            get
            {
                using (var hash = System.Security.Cryptography.SHA256.Create())
                    return "HealthMon.Common.SelectedPet." + BitConverter.ToString(hash.ComputeHash(
                        System.Text.Encoding.UTF8.GetBytes(ServerInstanceId + "\n" + OwnerId))).Replace("-", "");
            }
        }
        private void CreatePet()
        {
            if (Api.IsBusy || string.IsNullOrEmpty(OwnerId)) return;
            connecting = true;
            IsConnected = false; LatestState = null;
            Status = "Creating a new pet; previous pets are retained…";
            foreach (var state in FindObjectsByType<PetStateManager>(FindObjectsInactive.Include)) state.ClearServerState();
            Api.CreatePet(new PetSettings { name = "헬스몬", profanity = "none" }, result => SelectPet(result.pet_id), Failed);
        }
        public void CreateFreshTestPet()
        {
            if (EnvironmentName != "test" || !IsConnected || connecting || Api.IsBusy || Api.HasPendingChat)
            { Status = "A connected idle test account is required to start a fresh test pet."; return; }
            CreatePet();
        }
        public void RefreshState()
        { if (IsConnected && !Api.IsStateBusy && !Api.IsReauthenticating) Api.GetState(null, Failed); }
        private void ReauthenticatePendingToken()
        { ReauthenticatePendingToken(tokenInput); }
        public void ReauthenticatePendingToken(string token, Action<PetState> success = null, Action<ApiFailure> failure = null)
        {
            if (Api.IsBusy || connecting || !Api.HasPendingChat)
            { failure?.Invoke(new ApiFailure(0, "An idle retained chat is required for token recovery.")); return; }
            string candidate;
            try { candidate = CommonServerContract.NormalizeBearerToken(token); }
            catch (ArgumentException)
            {
                Status = "Invalid token format. Previous authentication and pending request retained.";
                failure?.Invoke(new ApiFailure(0, "Invalid token format; pending request retained.")); return;
            }
            int generation = configGeneration;
            connecting = true; Status = "Verifying the retained server/account/pet; the pending request is unchanged…";
            Api.ReauthenticatePendingChat(urlInput, candidate, petInput, state =>
            {
                if (generation != configGeneration) return;
                configGeneration++; // Invalidate earlier phone setup/status completions, even within the same identity.
                runtimeToken = candidate; tokenInput = "";
                BaseUrl = Api.BaseUrl; urlInput = BaseUrl; petInput = Api.PetId;
                ServerInstanceId = Api.VerifiedServerInstanceId; OwnerId = Api.VerifiedOwnerId;
                IsConnected = true; connecting = false;
                Status = "Same connection verified. Retry the retained chat with its original request ID.";
                ConfigurePhone(configGeneration);
                success?.Invoke(state);
            }, error =>
            {
                if (generation != configGeneration) return;
                connecting = false;
                Status = "Token verification failed (HTTP " + error.StatusCode + "). Previous authentication and pending request retained.";
                failure?.Invoke(error);
            });
        }
        public void ClearFoodCalorieConfirmation() { NextFoodKcalReconfirmed = false; }
        public void RefreshQuests()
        {
            if (!IsConnected || Api.IsBusy) return;
            int generation = configGeneration; string pet = Api.PetId;
            Api.GetQuests(result => { if (generation == configGeneration && pet == Api.PetId) quests = result; }, Failed);
        }
        public bool QuestDisplayAcknowledged(QuestOffer offer)
        {
            return offer != null && offer.pet_id == Api.PetId &&
                (!string.IsNullOrEmpty(offer.shown_at) || proposalDisplays.Acknowledged(offer.id));
        }
        // Called only by a visible, rendered quest row, never merely by fetching the list.
        public void ObserveDisplayedQuest(QuestOffer offer)
        {
            if (IsConnected && offer != null && offer.pet_id == Api.PetId && offer.IsPendingProposal)
                proposalDisplays.Observe(offer.id, !string.IsNullOrEmpty(offer.shown_at));
        }
        public void RetryQuestDisplay(QuestOffer offer)
        {
            if (offer != null && offer.pet_id == Api.PetId) proposalDisplays.Retry(offer.id);
        }
        public bool QuestDisplayFailed(QuestOffer offer)
        { return offer != null && offer.pet_id == Api.PetId && proposalDisplays.Failed(offer.id); }
        public void DecideDisplayedQuest(QuestOffer offer, bool accept, Action<ApiFailure> failure)
        {
            if (!IsConnected || offer == null || offer.pet_id != Api.PetId || Api.IsBusy || Api.HasPendingChat ||
                (offer.IsPendingProposal && !QuestDisplayAcknowledged(offer))) return;
            int generation = configGeneration;
            Api.DecideQuest(offer.id, accept, _ =>
            {
                if (generation != configGeneration) return;
                RefreshState(); RefreshQuests();
            }, failure);
        }
        private void SendObservedProposalAcknowledgement()
        {
            if (!IsConnected || Api.IsBusy || Api.HasPendingChat) return;
            string id = proposalDisplays.NextToAcknowledge();
            if (id == null || !proposalDisplays.TryBegin(id)) return;
            int generation = proposalDisplays.Generation;
            Api.MarkProposalShown(id, acknowledged =>
            {
                if (!proposalDisplays.Complete(generation, id, true)) return;
                if (quests?.offers != null)
                    for (int i = 0; i < quests.offers.Length; i++)
                        if (quests.offers[i].id == id) quests.offers[i] = acknowledged;
            }, error =>
            {
                if (!proposalDisplays.Complete(generation, id, false)) return;
                if (error.StatusCode == 401 || error.StatusCode == 403) Failed(error);
                else Status = "Proposal display was not confirmed (HTTP " + error.StatusCode + "). Retry before accepting or rejecting.";
            });
        }
        private void Received(PetState state)
        {
            LatestState = state;
            foreach (var view in FindObjectsByType<PetStateManager>(FindObjectsInactive.Include)) view.ApplyServerState(state);
            StateChanged?.Invoke(state);
        }
        private void Failed(ApiFailure error)
        {
            connecting = false;
            if (error.StatusCode == 401 || error.StatusCode == 403)
            {
                IsConnected = false;
                HealthMonAndroidBridge.ClearServerSync();
            }
            Status = "Common server request failed (HTTP " + error.StatusCode + "). Previous verified display retained.";
        }
        public void Authorize(UnityWebRequest request)
        {
            if (!IsConnected || string.IsNullOrEmpty(runtimeToken)) throw new InvalidOperationException("Connect first.");
            var origin = new Uri(BaseUrl + "/"); var target = new Uri(request.url);
            if (origin.Scheme != target.Scheme || origin.Host != target.Host || origin.Port != target.Port)
                throw new InvalidOperationException("Authorization is restricted to the configured common server.");
            if (!target.AbsolutePath.StartsWith(origin.AbsolutePath, StringComparison.Ordinal))
                throw new InvalidOperationException("Authorization is restricted to the configured API prefix.");
            request.SetRequestHeader("Authorization", "Bearer " + runtimeToken);
            request.redirectLimit = 0;
        }
        private void ConfigurePhone(int generation)
        {
            if (!HealthMonAndroidBridge.IsAndroidDevice) return;
            string url = BaseUrl, token = runtimeToken, pet = Api.PetId;
            _ = phoneConfigurations.Enqueue(() => generation == configGeneration && IsConnected,
                () => ConfigurePhoneInOrder(generation, url, token, pet));
        }
        private async Task ConfigurePhoneInOrder(int generation, string url, string token, string pet)
        {
            try
            {
                string result = await Task.Run(() => HealthMonAndroidBridge.ConfigureServerSync(url, token, pet));
                if (generation != configGeneration || !IsConnected) return;
                PhoneStatus = JsonUtility.FromJson<PhoneSyncStatus>(result);
            }
            catch (Exception)
            { if (generation == configGeneration && IsConnected) Status = "Connected; Android sync setup failed. Retry sync after checking the plugin."; }
        }
        public async void RefreshPhoneStatus()
        {
            if (phoneBusy || !HealthMonAndroidBridge.IsAndroidDevice || !IsConnected) return;
            phoneBusy = true; int generation = configGeneration;
            try
            {
                string result = await Task.Run(HealthMonAndroidBridge.GetServerSyncStatus);
                if (generation != configGeneration) return;
                var status = JsonUtility.FromJson<PhoneSyncStatus>(result);
                if (status != null && status.server_instance_id == ServerInstanceId && status.owner_id == OwnerId && status.pet_id == Api.PetId)
                    PhoneStatus = status;
                RefreshState();
            }
            catch (Exception) { Status = "Android sync status unavailable."; }
            finally { phoneBusy = false; }
        }
        private void Update()
        {
            SendObservedProposalAcknowledgement();
            if (!IsConnected || Time.unscaledTime < nextRefresh) return;
            nextRefresh = Time.unscaledTime + 15;
            RefreshState(); RefreshPhoneStatus();
        }
        private void OnApplicationFocus(bool focused) { if (focused) { RefreshState(); RefreshPhoneStatus(); } }
        private void OnGUI()
        {
            GUI.depth = -100;
            if (!expanded)
            {
                Rect safe = Screen.safeArea;
                var toggle = new Rect(Mathf.Max(8, safe.xMax - 40), Mathf.Max(8, Screen.height - safe.yMax + 8), 32, 32);
                string connectionLabel = connecting ? "연결 중" : IsConnected ? "연결됨" : "미연결";
                if (GUI.Button(toggle, new GUIContent("⚙", "COMMON SERVER · 개발용 · " + connectionLabel + " · 설정 열기"))) expanded = true;
                return; // A collapsed panel paints no proposal rows and cannot generate a display ACK.
            }
            float width = Mathf.Min(Screen.width - 16, 560);
            GUILayout.BeginArea(new Rect(8, 8, width, expanded ? Mathf.Min(Screen.height - 16, 740) : 46), GUI.skin.box);
            string stateLabel = connecting ? "연결 중" : IsConnected ? "연결됨" : "미연결";
            string header = (UsesServerAuthority ? "COMMON SERVER · 개발용 · " + stateLabel : "LOCAL DEMO / SYNTHETIC · 개발용") +
                (Api.HasPendingChat ? " · 대기 대화 보존" : "") + (expanded ? " · 접기 ▴" : " · 설정 열기 ▾");
            if (GUILayout.Button(header)) expanded = !expanded;
            if (expanded)
            {
                // GUI clip transforms are resolved while drawing each row, then
                // compared with this scroll viewport after EndScrollView. Merely
                // iterating offscreen rows cannot acknowledge an unseen proposal.
                var paintedProposals = new List<KeyValuePair<QuestOffer, Rect>>();
                scroll = GUILayout.BeginScrollView(scroll);
                GUILayout.Label(Status);
                GUILayout.Label("API_BASE_URL (Android: use explicit LAN host / emulator 10.0.2.2)");
                urlInput = GUILayout.TextField(urlInput ?? "");
                GUILayout.Label("User bearer token (runtime only)");
                tokenInput = GUILayout.PasswordField(tokenInput, '*');
                GUILayout.Label("Pet ID (empty: first owned pet)"); petInput = GUILayout.TextField(petInput);
                if (Api.HasPendingChat)
                {
                    GUILayout.Label("Pending chat retained. Status refresh does not discard it. Server work may still complete.");
                    GUI.enabled = !Api.IsBusy && !connecting;
                    if (GUILayout.Button("Re-authenticate token for the same server/account/pet")) ReauthenticatePendingToken();
                    GUI.enabled = !Api.IsBusy;
                    if (GUILayout.Button("Reconcile old history and clear this pending chat"))
                        Api.GetHistory(_ => { Api.DiscardPendingChat(); RefreshState(); }, failure: Failed);
                    if (GUILayout.Button("Explicitly abandon local chat for connection change (check history later)"))
                        Api.DiscardPendingChat();
                    GUI.enabled = true;
                }
                GUI.enabled = !connecting && !Api.IsBusy && !Api.HasPendingChat && UsesServerAuthority;
                if (GUILayout.Button("Connect / change connection")) Connect(urlInput, tokenInput, petInput);
                if (!IsConnected && !string.IsNullOrEmpty(OwnerId) && GUILayout.Button("Create pet for this account")) CreatePet();
                GUI.enabled = true; // Local Room history remains usable while the API is offline.
                if (GUILayout.Button("Open team WearableScene")) UnityEngine.SceneManagement.SceneManager.LoadScene("WearableScene");
                if (GUILayout.Button("Open MainARScene")) UnityEngine.SceneManagement.SceneManager.LoadScene("MainARScene");
                GUI.enabled = IsConnected;
                if (GUILayout.Button("Refresh authoritative state")) RefreshState();
                if (LatestState != null)
                {
                    var s = LatestState;
                    GUILayout.Label("server " + ServerInstanceId + " / owner " + OwnerId + " / pet " + s.pet_id);
                    GUILayout.Label("v" + s.state_version + "  Lv " + s.level + "  EXP " + s.current_exp + "/" + s.required_exp + " total " + s.total_exp + "  Coin " + s.coin);
                    GUILayout.Label("Upper " + s.upper_body + "  Lower " + s.lower_body + "  Nutrition " + s.nutrition + "  Energy " + s.energy_balance);
                    GUILayout.Label("Activity " + s.activity + "  Affinity " + s.affinity + "  Initiative " + s.initiative);
                    GUILayout.Label("Evolution target " + s.evolution_target_stage + " / published " + s.published_model_stage + " / " + s.asset_status);
                    if (GUILayout.Button("Request / retry evolution (same job ID retained)"))
                        Healthmon.Evolution.EvolutionClient.Instance?.RequestCommonEvolution();
                }
                if (GUILayout.Button("Load server quests")) RefreshQuests();
                GUILayout.Label("Next food confirmation: select the actual meal.");
                GUILayout.BeginHorizontal();
                foreach (var meal in new[] { "breakfast", "lunch", "dinner", "snack" })
                    if (GUILayout.Toggle(NextFoodMealType == meal, meal, GUI.skin.button)) NextFoodMealType = meal;
                GUILayout.EndHorizontal();
                NextFoodKcalReconfirmed = GUILayout.Toggle(NextFoodKcalReconfirmed, "I reconfirm the displayed calories for my actual consumed quantity");
                GUILayout.Label("Leave calorie confirmation off if unknown. Photo estimates alone do not confirm energy intake.");
                foreach (var offer in quests?.offers ?? new QuestOffer[0])
                {
                    if (offer == null || offer.pet_id != Api.PetId) continue;
                    GUILayout.Label((offer.template?.candidate ?? offer.template?.kind ?? "Quest") + " " + offer.progress + "/" + offer.template?.target + " " + offer.status);
                    if (offer.IsPendingProposal)
                    {
                        if (Event.current.type == EventType.Repaint)
                            paintedProposals.Add(new KeyValuePair<QuestOffer, Rect>(offer, ScreenRect(GUILayoutUtility.GetLastRect())));
                        bool acknowledged = !string.IsNullOrWhiteSpace(offer.shown_at) || proposalDisplays.Acknowledged(offer.id);
                        bool previousEnabled = GUI.enabled;
                        if (!acknowledged)
                        {
                            if (proposalDisplays.Failed(offer.id))
                            {
                                GUI.enabled = previousEnabled && !Api.IsBusy && !Api.HasPendingChat;
                                if (GUILayout.Button("Retry confirming displayed proposal " + offer.id)) proposalDisplays.Retry(offer.id);
                            }
                            else GUILayout.Label("Confirming displayed proposal before a decision…");
                        }
                        GUI.enabled = previousEnabled && acknowledged && !Api.IsBusy && !Api.HasPendingChat;
                        if (GUILayout.Button("Accept " + offer.id)) Api.DecideQuest(offer.id, true, _ => RefreshQuests(), Failed);
                        if (GUILayout.Button("Reject " + offer.id)) Api.DecideQuest(offer.id, false, _ => RefreshQuests(), Failed);
                        GUI.enabled = previousEnabled;
                    }
                    else if (!offer.is_proposal && offer.status == "offered")
                    {
                        bool previousEnabled = GUI.enabled;
                        GUI.enabled = previousEnabled && !Api.IsBusy && !Api.HasPendingChat;
                        if (GUILayout.Button("Accept " + offer.id)) Api.DecideQuest(offer.id, true, _ => RefreshQuests(), Failed);
                        if (GUILayout.Button("Reject " + offer.id)) Api.DecideQuest(offer.id, false, _ => RefreshQuests(), Failed);
                        GUI.enabled = previousEnabled;
                    }
                }
                if (HealthMonAndroidBridge.IsAndroidDevice)
                {
                    if (GUILayout.Button("Sync phone records and refresh")) { HealthMonAndroidBridge.RequestServerSync(); RefreshPhoneStatus(); }
                    if (PhoneStatus != null)
                    {
                        GUILayout.Label("Phone sync " + PhoneStatus.status + "; unbound " + PhoneStatus.unbound_count);
                        GUILayout.Label("Confirm only your own workouts for this server/account/pet:");
                        foreach (var workout in PhoneStatus.unbound ?? new UnboundWorkout[0])
                            if (GUILayout.Button("Confirm my workout: " + workout.exercise + " " + DateTimeOffset.FromUnixTimeMilliseconds(workout.start_time).ToString("u")))
                            { HealthMonAndroidBridge.ConfirmWorkoutUpload(workout.id); RefreshPhoneStatus(); }
                    }
                }
                GUI.enabled = true;
                GUILayout.EndScrollView();
                if (Event.current.type == EventType.Repaint && IsConnected)
                {
                    Rect viewport = ScreenRect(GUILayoutUtility.GetLastRect());
                    foreach (var painted in paintedProposals)
                        if (viewport.Contains(painted.Value.min) && viewport.Contains(painted.Value.max - Vector2.one * .5f))
                            proposalDisplays.Observe(painted.Key.id, !string.IsNullOrWhiteSpace(painted.Key.shown_at));
                }
            }
            GUILayout.EndArea();
        }
        private static Rect ScreenRect(Rect rectangle)
        {
            Vector2 min = GUIUtility.GUIToScreenPoint(rectangle.min), max = GUIUtility.GUIToScreenPoint(rectangle.max);
            return Rect.MinMaxRect(min.x, min.y, max.x, max.y);
        }
        private void OnDestroy()
        {
            if (Instance != this) return;
            Api.StateReceived -= Received;
            runtimeToken = tokenInput = null; Instance = null;
        }
    }
}
