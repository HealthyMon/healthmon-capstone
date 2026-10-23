using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;
using Healthmon.Common;

namespace Healthmon.Evolution
{
    public sealed class EvolutionClient : MonoBehaviour
    {
        public static EvolutionClient Instance { get; private set; }
        public ModelManifest Current { get; private set; }
        public string LastError { get; private set; }
        public string Phase { get; private set; }
        public string ActiveRequestId => CommonServerConnection.UsesServerAuthority ? commonPending?.request_id : pending?.request_id;
        public EvolutionSettings Settings { get; private set; } = new EvolutionSettings();
        public event Action<ModelManifest> ModelChanged;
        public event Action<string> StatusChanged;
        private readonly CancellationTokenSource lifetime = new CancellationTokenSource();
        private PetStateManager petState;
        private GrowthStats growthStats;
        private string scoreSource;
        [NonSerialized] private string bearerToken;
        private EvolutionRequest pending;
        private bool submitting;
        [Serializable] private sealed class CommonPending { public string request_id, job_id; }
        private CommonPending commonPending;
        private string commonScope, commonPendingKey;
        private bool commonTerminal, commonRetryRequested;
        private string PendingKey => "HealthMon.Evolution.Pending." + Settings.pet_id;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Bootstrap()
        {
            if (Instance == null) new GameObject("HealthMon Evolution").AddComponent<EvolutionClient>();
        }

        private void Awake()
        {
            if (Instance != null && Instance != this) { Destroy(gameObject); return; }
            Instance = this;
            DontDestroyOnLoad(gameObject);
            if (CommonServerConnection.UsesServerAuthority) return;
            var settingsAsset = Resources.Load<TextAsset>("HealthMonEvolution");
            if (settingsAsset != null) Settings = JsonUtility.FromJson<EvolutionSettings>(settingsAsset.text);
            Settings.base_url = Environment.GetEnvironmentVariable("HEALTHMON_EVOLUTION_URL") ?? Settings.base_url;
            Settings.pet_id = Environment.GetEnvironmentVariable("HEALTHMON_EVOLUTION_PET") ?? Settings.pet_id;
            Settings.certificate_sha256 = Environment.GetEnvironmentVariable("HEALTHMON_EVOLUTION_CERT_SHA256") ?? Settings.certificate_sha256;
            bearerToken = Environment.GetEnvironmentVariable("HEALTHMON_EVOLUTION_TOKEN");
            if (PlayerPrefs.HasKey(PendingKey)) pending = JsonUtility.FromJson<EvolutionRequest>(PlayerPrefs.GetString(PendingKey));
        }

        private async void Start()
        {
            if (CommonServerConnection.UsesServerAuthority) { await RunCommonServer(); return; }
            while (!lifetime.IsCancellationRequested)
            {
                BindGrowth();
                try
                {
                    var manifest = JsonUtility.FromJson<ModelManifest>(await Json("GET", "/v1/pets/" + Uri.EscapeDataString(Settings.pet_id) + "/current"));
                    LastError = null;
                    if (Current == null || Current.revision != manifest.revision)
                    {
                        Current = manifest;
                        if (petState != null) petState.ApplyEvolutionStage(manifest.stage);
                        ModelChanged?.Invoke(manifest);
                    }
                    if (pending != null) await SubmitPending();
                    else if (Settings.auto_level_evolution && petState != null) OnLevelChanged(petState.Level);
                }
                catch (OperationCanceledException) { break; }
                catch (Exception error) { LastError = error.Message; }
                try { await Task.Delay(3000, lifetime.Token); }
                catch (OperationCanceledException) { break; }
            }
        }

        private void BindGrowth()
        {
            if (petState != null) return;
            petState = FindAnyObjectByType<PetStateManager>(FindObjectsInactive.Include);
            if (petState != null) petState.LevelChanged += OnLevelChanged;
        }

        // Call this from the growth-stat producer. Dialogue personality is a separate channel.
        public void SetGrowthStats(GrowthStats stats, string source)
        {
            if (CommonServerConnection.UsesServerAuthority)
                throw new InvalidOperationException("Common server snapshots determine evolution; client scores are not accepted.");
            if (stats == null || !stats.IsValid() || string.IsNullOrWhiteSpace(source))
                throw new ArgumentException("Supply all eight valid growth stats and their source.");
            growthStats = JsonUtility.FromJson<GrowthStats>(JsonUtility.ToJson(stats));
            scoreSource = source;
        }

        private void OnLevelChanged(int level)
        {
            if (!Settings.auto_level_evolution || Current == null || Current.stage >= 3 || pending != null || submitting) return;
            int[] milestones = { 15, 30, 50 };
            if (level < milestones[Current.stage]) return;
            if (growthStats == null) { Phase = "waiting_for_growth_stats"; return; }
            RequestEvolution(level, growthStats, scoreSource);
        }

        // Also supports an explicit backend/game evolution signal without a level-up UI event.
        public void RequestEvolution(int level, GrowthStats stats, string source)
        {
            if (CommonServerConnection.UsesServerAuthority) { RequestCommonEvolution(); return; }
            if (pending != null || submitting) throw new InvalidOperationException("Resolve the pending evolution first.");
            if (level < 15 || level > 100) throw new ArgumentOutOfRangeException(nameof(level));
            SetGrowthStats(stats, source);
            pending = new EvolutionRequest { request_id = Guid.NewGuid().ToString("N"), level = level,
                stats = JsonUtility.FromJson<GrowthStats>(JsonUtility.ToJson(stats)), score_source = source };
            PlayerPrefs.SetString(PendingKey, JsonUtility.ToJson(pending));
            PlayerPrefs.Save();
            Phase = "queued";
        }

        public void RequestCommonEvolution()
        {
            var common = CommonServerConnection.Instance;
            if (common == null || !common.IsConnected || common.LatestState == null)
            { LastError = "Connect to the common server first."; return; }
            PrepareCommonScope(common);
            if (common.LatestState.evolution_target_stage <= common.LatestState.published_model_stage)
            { LastError = "No pending server-authorized evolution stage."; return; }
            if (commonPending == null)
                commonPending = new CommonPending { request_id = Guid.NewGuid().ToString("N") };
            // Explicit retry preserves request_id/job_id. A network failure cannot create a paid job twice.
            commonRetryRequested = true; commonTerminal = false;
            PlayerPrefs.SetString(commonPendingKey, JsonUtility.ToJson(commonPending)); PlayerPrefs.Save();
            Phase = "queued";
        }

        private void PrepareCommonScope(CommonServerConnection common)
        {
            string scope = common.ServerInstanceId + "\n" + common.OwnerId + "\n" + common.Api.PetId;
            if (scope == commonScope) return;
            commonScope = scope;
            commonPendingKey = "HealthMon.CommonEvolution." + Hash(Encoding.UTF8.GetBytes(scope));
            commonPending = PlayerPrefs.HasKey(commonPendingKey)
                ? JsonUtility.FromJson<CommonPending>(PlayerPrefs.GetString(commonPendingKey)) : null;
            commonTerminal = false; commonRetryRequested = commonPending != null;
            Current = null; ModelChanged?.Invoke(null);
            Settings.base_url = common.BaseUrl; Settings.pet_id = common.Api.PetId;
        }

        private async Task RunCommonServer()
        {
            while (!lifetime.IsCancellationRequested)
            {
                var common = CommonServerConnection.Instance;
                try
                {
                    if (common != null && common.IsConnected)
                    {
                        PrepareCommonScope(common);
                        string capturedScope = commonScope;
                        string root = "/pets/" + Uri.EscapeDataString(common.Api.PetId) + "/evolutions";
                        // A pending generation survives an app restart. Restore the already
                        // published visual independently so polling that job cannot hide the pet.
                        if (commonPending != null && common.LatestState != null &&
                            !string.IsNullOrEmpty(common.LatestState.model_reference) &&
                            (Current == null || Current.model_url != common.LatestState.model_reference))
                        {
                            string reference = common.LatestState.model_reference;
                            string publishedId = reference.Substring(reference.LastIndexOf('/') + 1);
                            var published = JsonUtility.FromJson<CommonEvolutionJob>(await Json("GET", root + "/" + Uri.EscapeDataString(publishedId)));
                            if (capturedScope != CurrentCommonScope()) continue;
                            if (published == null || published.status != "succeeded" || published.job_id != publishedId ||
                                !System.Text.RegularExpressions.Regex.IsMatch(published.model_sha256 ?? "", "^[a-f0-9]{64}$"))
                                throw new IOException("Published model recovery has no verified asset.");
                            string model = published.model_reference ?? published.model_url;
                            ResolveUrl(model);
                            if (model == reference && common.LatestState.model_reference == reference &&
                                common.LatestState.published_model_stage == published.stage &&
                                common.LatestState.state_version >= published.state_version)
                            {
                                Current = new ModelManifest { pet_id = common.Api.PetId, revision = published.job_id,
                                    stage = published.stage, model_url = model, model_sha256 = published.model_sha256 };
                                ModelChanged?.Invoke(Current);
                            }
                        }
                        CommonEvolutionJob job = null;
                        if (commonPending != null && !commonTerminal)
                        {
                            bool firstSubmission = string.IsNullOrEmpty(commonPending.job_id);
                            string json;
                            if (commonRetryRequested || string.IsNullOrEmpty(commonPending.job_id))
                            {
                                commonRetryRequested = false;
                                json = await Json("POST", root, JsonUtility.ToJson(new CommonEvolutionRequest { request_id = commonPending.request_id }));
                            }
                            else json = await Json("GET", root + "/" + Uri.EscapeDataString(commonPending.job_id));
                            if (capturedScope != CurrentCommonScope()) continue;
                            job = JsonUtility.FromJson<CommonEvolutionJob>(json);
                            if (job == null || string.IsNullOrWhiteSpace(job.request_id) ||
                                (!firstSubmission && job.request_id != commonPending.request_id) || string.IsNullOrEmpty(job.job_id))
                                throw new IOException("Invalid common evolution job contract.");
                            // Another device may already own this stage's one durable job.
                            // Adopt that authenticated same-pet job's original request identity once.
                            if (firstSubmission) commonPending.request_id = job.request_id;
                            commonPending.job_id = job.job_id;
                            PlayerPrefs.SetString(commonPendingKey, JsonUtility.ToJson(commonPending)); PlayerPrefs.Save();
                            Phase = job.status; StatusChanged?.Invoke(Phase);
                            if (job.status == "failed" || job.status == "unsupported")
                            { commonTerminal = true; LastError = "Evolution unavailable or failed; previous model retained."; }
                        }
                        else if (common.LatestState != null && common.LatestState.model_reference != null &&
                            (Current == null || Current.model_url != common.LatestState.model_reference))
                        {
                            string model = common.LatestState.model_reference;
                            string id = model.Substring(model.LastIndexOf('/') + 1);
                            job = JsonUtility.FromJson<CommonEvolutionJob>(await Json("GET", root + "/" + Uri.EscapeDataString(id)));
                            if (capturedScope != CurrentCommonScope()) continue;
                        }
                        if (job != null && job.status == "succeeded")
                        {
                            string model = job.model_reference ?? job.model_url;
                            if (job.stage < 0 || job.stage > 3 || string.IsNullOrEmpty(model) ||
                                !System.Text.RegularExpressions.Regex.IsMatch(job.model_sha256 ?? "", "^[a-f0-9]{64}$"))
                                throw new IOException("Successful job has no verified model asset.");
                            ResolveUrl(model); // Refuse cross-origin references before publication.
                            // A completed older job may be retained in the database without being
                            // the currently published model. The authoritative state decides this.
                            if (common.LatestState == null || common.LatestState.state_version < job.state_version)
                            {
                                common.RefreshState();
                                await Task.Delay(500, lifetime.Token);
                                continue;
                            }
                            if (common.LatestState.published_model_stage != job.stage || common.LatestState.model_reference != model)
                            {
                                if (commonPending != null && commonPending.job_id == job.job_id)
                                {
                                    commonPending = null; PlayerPrefs.DeleteKey(commonPendingKey); PlayerPrefs.Save();
                                }
                                Phase = "superseded";
                                await Task.Delay(3000, lifetime.Token);
                                continue;
                            }
                            var manifest = new ModelManifest { pet_id = common.Api.PetId, revision = job.job_id,
                                stage = job.stage, model_url = model, model_sha256 = job.model_sha256 };
                            if (Current == null || Current.revision != manifest.revision)
                            { Current = manifest; ModelChanged?.Invoke(manifest); }
                            commonPending = null; commonTerminal = false;
                            PlayerPrefs.DeleteKey(commonPendingKey); PlayerPrefs.Save();
                            Phase = "complete"; LastError = null; common.RefreshState();
                        }
                    }
                }
                catch (OperationCanceledException) { break; }
                catch (Exception)
                {
                    LastError = "Common evolution request failed. Retry retains the same request ID.";
                    // Do not automatically repeat failed generation submissions.
                    if (commonPending != null && string.IsNullOrEmpty(commonPending.job_id)) commonTerminal = true;
                }
                try { await Task.Delay(3000, lifetime.Token); }
                catch (OperationCanceledException) { break; }
            }
        }
        private static string CurrentCommonScope()
        {
            var c = CommonServerConnection.Instance;
            return c == null || !c.IsConnected ? null : c.ServerInstanceId + "\n" + c.OwnerId + "\n" + c.Api.PetId;
        }

        private async Task SubmitPending()
        {
            if (submitting) return;
            submitting = true;
            try
            {
                string path = "/v1/pets/" + Uri.EscapeDataString(Settings.pet_id) + "/evolutions";
                var job = JsonUtility.FromJson<EvolutionJob>(await Json("POST", path, JsonUtility.ToJson(pending)));
                LastError = null;
                Phase = job.phase;
                StatusChanged?.Invoke(Phase);
                if (job.status == "FAILED")
                {
                    // A failed model never replaces Current; retry requires a new explicit request.
                    LastError = job.error;
                    ClearPending();
                    growthStats = null;
                    StatusChanged?.Invoke("failed: " + job.error);
                }
                else if (job.status == "READY")
                {
                    Current = job.result;
                    if (petState != null) petState.ApplyEvolutionStage(Current.stage);
                    ModelChanged?.Invoke(Current);
                    ClearPending();
                }
            }
            finally { submitting = false; }
        }

        private void ClearPending()
        {
            pending = null;
            PlayerPrefs.DeleteKey(PendingKey);
            PlayerPrefs.Save();
        }

        public string ResolveUrl(string path)
        {
            if (CommonServerConnection.UsesServerAuthority)
                return CommonServerContract.ResolveApiUrl(Settings.base_url, path);
            var origin = new Uri(Settings.base_url.TrimEnd('/') + "/");
            var address = new Uri(origin, path);
            if (address.Scheme != origin.Scheme || address.Host != origin.Host || address.Port != origin.Port)
                throw new InvalidOperationException("Artifact must come from the configured evolution server.");
            return address.AbsoluteUri;
        }

        private async Task<string> Json(string method, string path, string body = null)
        {
            using (var request = new UnityWebRequest(ResolveUrl(path), method))
            {
                request.downloadHandler = new DownloadHandlerBuffer();
                if (body != null) { request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body)); request.SetRequestHeader("Content-Type", "application/json"); }
                await Send(request, 30);
                return request.downloadHandler.text;
            }
        }

        public async Task<byte[]> DownloadModel(ModelManifest manifest)
        {
            // Content-addressed cache survives reconnects. Never consume a half-written file.
            if (manifest.model_sha256 == null || manifest.model_sha256.Length != 64 ||
                !System.Text.RegularExpressions.Regex.IsMatch(manifest.model_sha256, "^[a-f0-9]{64}$"))
                throw new InvalidOperationException("Invalid model hash.");
            string directory = Path.Combine(Application.persistentDataPath, "HealthMonModels");
            Directory.CreateDirectory(directory);
            string path = Path.Combine(directory, manifest.model_sha256 + ".glb");
            if (File.Exists(path))
            {
                byte[] cached = File.ReadAllBytes(path);
                if (Hash(cached) == manifest.model_sha256) return cached;
            }
            using (var request = UnityWebRequest.Get(ResolveUrl(manifest.model_url)))
            {
                await Send(request, 120);
                byte[] data = request.downloadHandler.data;
                if (Hash(data) != manifest.model_sha256) throw new IOException("Downloaded GLB hash mismatch.");
                File.WriteAllBytes(path + ".part", data);
                if (File.Exists(path)) File.Delete(path);
                File.Move(path + ".part", path);
                return data;
            }
        }

        private async Task Send(UnityWebRequest request, int timeout)
        {
            lifetime.Token.ThrowIfCancellationRequested();
            request.timeout = timeout;
            if (CommonServerConnection.UsesServerAuthority)
                CommonServerConnection.Instance.Authorize(request);
            else if (!string.IsNullOrEmpty(Settings.certificate_sha256))
                request.certificateHandler = new PinnedCertificate(Settings.certificate_sha256);
            if (!CommonServerConnection.UsesServerAuthority && !string.IsNullOrEmpty(bearerToken)) request.SetRequestHeader("Authorization", "Bearer " + bearerToken);
            var operation = request.SendWebRequest();
            using (lifetime.Token.Register(request.Abort))
                while (!operation.isDone) { lifetime.Token.ThrowIfCancellationRequested(); await Task.Yield(); }
            lifetime.Token.ThrowIfCancellationRequested();
            if (request.result != UnityWebRequest.Result.Success)
                throw new IOException("Evolution HTTP " + request.responseCode + ": " + request.error);
        }

        private static string Hash(byte[] data)
        { using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(data)).Replace("-", "").ToLowerInvariant(); }

        private sealed class PinnedCertificate : CertificateHandler
        {
            private readonly string expected;
            public PinnedCertificate(string sha256) { expected = sha256; }
            protected override bool ValidateCertificate(byte[] data) => Hash(data) == expected;
        }

        private void OnDestroy()
        {
            if (Instance != this) return;
            if (petState != null) petState.LevelChanged -= OnLevelChanged;
            lifetime.Cancel();
            Instance = null;
        }
    }
}
