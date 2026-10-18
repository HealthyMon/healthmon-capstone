using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace Healthmon.Evolution
{
    public sealed class EvolutionClient : MonoBehaviour
    {
        public static EvolutionClient Instance { get; private set; }
        public ModelManifest Current { get; private set; }
        public string LastError { get; private set; }
        public string Phase { get; private set; }
        public string ActiveRequestId => pending == null ? null : pending.request_id;
        public EvolutionSettings Settings { get; private set; } = new EvolutionSettings();
        public event Action<ModelManifest> ModelChanged;
        public event Action<string> StatusChanged;
        private readonly CancellationTokenSource lifetime = new CancellationTokenSource();
        private PetStateManager petState;
        private GrowthStats growthStats;
        private string scoreSource, bearerToken;
        private EvolutionRequest pending;
        private bool submitting;
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
            if (pending != null || submitting) throw new InvalidOperationException("Resolve the pending evolution first.");
            if (level < 15 || level > 100) throw new ArgumentOutOfRangeException(nameof(level));
            SetGrowthStats(stats, source);
            pending = new EvolutionRequest { request_id = Guid.NewGuid().ToString("N"), level = level,
                stats = JsonUtility.FromJson<GrowthStats>(JsonUtility.ToJson(stats)), score_source = source };
            PlayerPrefs.SetString(PendingKey, JsonUtility.ToJson(pending));
            PlayerPrefs.Save();
            Phase = "queued";
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
            if (!string.IsNullOrEmpty(Settings.certificate_sha256))
                request.certificateHandler = new PinnedCertificate(Settings.certificate_sha256);
            if (!string.IsNullOrEmpty(bearerToken)) request.SetRequestHeader("Authorization", "Bearer " + bearerToken);
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
