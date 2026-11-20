#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Healthmon.Beta;
using Healthmon.Common;
using Healthmon.Evolution;
using TMPro;
using UnityEditor;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.UI;

[Serializable] public sealed class NativeE2EConfig
{
    public bool isolated_fixture;
    public string api_base_url, bearer_token, bearer_token_env = "HEALTHMON_NATIVE_E2E_TOKEN";
    public string expected_server_instance_id, expected_owner_id;
    public int timeout_seconds = 240;
    public bool require_real_llm = true, require_distinct_llm_responses = true, capture_screenshots = true;
    public NativeE2ECase[] cases;
}

[Serializable] public sealed class NativeE2ECase
{
    public string case_id, pet_id, prompt;
    public PetState expected_state;
    public NativeE2EEvolutionProfile expected_evolution_profile;
    public bool run_workout_smoke, run_chat = true, require_model_display;
    public bool run_auth_recovery_smoke;
    public bool run_dialogue_layout_smoke;
    public bool run_food_smoke, food_require_real_vision = true;
    public string food_image_path, food_fixture_meal_type = "breakfast";
    public int food_candidate_index;
    public float food_fixture_grams = 100, food_fixture_vegetable_fruit_g = 80;
    public bool food_fixture_kcal_reconfirmed;
    public bool simulate_ar_placement;
    public string expected_model_revision, expected_model_sha256;
    public float expected_lower_body_after_workout;
}

[Serializable] public sealed class NativeE2EEvolutionProfile
{
    public int stage;
    public float strength, difference;
    public string appearance, body_balance, nutrition_condition, energy_condition;
    public bool generation_required, recovery;
}

[Serializable] public sealed class NativeE2ECaseResult
{
    public string case_id, status, error_code, request_id, response_sha256, provenance, backend;
    public int response_characters, level, target_stage, published_stage, ui_assertions;
    public long state_version;
    public float upper_body, lower_body, nutrition, energy_balance, activity, affinity, initiative;
    public bool server_dto_valid, ui_matches_server, workout_idempotent, evolution_condition_matches, score_evolution_profile_matches;
    public string appearance, body_balance, nutrition_condition, energy_condition;
    public bool real_llm_contract, llm_context_matches_server, dialogue_text_matches, model_renderability_verified;
    public bool manual_visual_review_required;
    public string home_screenshot, dialogue_screenshot;
    public bool placement_is_simulated, physical_ar_tracking;
    public bool model_asset_sha256_verified, native_skin_verified, bones_verified, camera_frustum_verified;
    public bool native_camera_frame_seen, native_renderability_verified;
    public string model_revision, displayed_revision, model_sha256, model_job_status, model_screenshot, model_camera;
    public int native_skinned_renderer_count, native_bone_count, native_mesh_vertices, native_renderable_renderer_count;
    public float simulated_placement_distance_m;
    public Vector3 model_bounds_center, model_bounds_size;
    public int model_camera_frames_observed, model_stable_camera_frames, model_shader_pending_observations;
    public int model_shader_pending_camera_frames, model_render_wait_timeout_seconds;
    public float model_render_wait_seconds;
    public bool model_shader_compilation_observed, model_shader_pending_at_capture;
    public bool auth_recovery_smoke_verified, auth_initial_401_verified, auth_invalid_candidate_rejected;
    public bool auth_pending_preserved, auth_same_scope_reauthenticated, auth_same_id_retry_verified, auth_server_rule_response_verified;
    public bool auth_whitespace_candidate_verified, auth_connection_header_matches;
    public string auth_request_id, auth_pending_snapshot_sha256;
    public long auth_original_request_version;
    public int auth_expected_401_observations, auth_history_new_request_count;
    public bool dialogue_geometry_verified, dialogue_layout_smoke_verified, dialogue_layout_synthetic;
    public bool dialogue_user_scroll_reaches_end, dialogue_response_scroll_reaches_end, dialogue_layout_no_chat_sent;
    public int dialogue_overlap_count, dialogue_layout_user_characters, dialogue_layout_response_characters;
    public string dialogue_layout_start_screenshot, dialogue_layout_end_screenshot;
    public NativeDialogueViewportEvidence dialogue_user_viewport, dialogue_response_viewport;
    public bool dialogue_raycast_verified, dialogue_input_module_active, dialogue_application_focused;
    public string dialogue_input_module;
    public NativeDialogueRaycastProbe[] dialogue_raycast_probes;
    public NativeInputActionEvidence[] dialogue_input_actions;
    public string dialogue_input_update_mode, dialogue_editor_input_behavior, dialogue_background_behavior;
    public bool dialogue_event_system_focused, dialogue_run_in_background;
    public float dialogue_scroll_delta_per_tick;
    public bool food_smoke_verified, food_real_vision_contract, food_analysis_displayed, food_estimate_not_confirmed;
    public bool food_explicit_quantity_verified, food_synthetic_consumption, food_state_ui_verified, food_idempotent, food_no_chat_sent;
    public string food_image_sha256, food_analysis_id, food_backend, food_provenance, food_source_id, food_candidate_name;
    public string food_candidates_screenshot, food_confirmation_screenshot, food_quantities_screenshot, food_recorded_screenshot;
    public int food_candidate_id, food_candidate_count, food_record_count;
    public float food_confidence, food_confirmed_grams, food_confirmed_vegetable_fruit_g;
    public string food_meal_type;
    public bool food_analysis_synthetic, food_analysis_produce_available, food_kcal_reconfirmed;
}

[Serializable] public sealed class NativeInputActionEvidence
{
    public string slot, action_name, action_type;
    public bool reference_present, action_present, action_enabled;
    public string[] binding_paths, resolved_control_paths;
}

[Serializable] public sealed class NativeDialogueRaycastProbe
{
    public string viewport, sample, top_hit_path, top_hit_type, top_scroll_path;
    public Vector2 screen_position;
    public int hit_count;
    public bool top_hit_routes_to_expected_scroll;
}

[Serializable] public sealed class NativeDialogueViewportEvidence
{
    public float content_height, viewport_height, vertical_normalized_position;
    public bool fits_viewport, scroll_required, scroll_performed;
    public bool first_glyph_within_viewport, last_glyph_within_viewport, all_glyphs_within_viewport;
    public Vector2 viewport_min, viewport_max, first_glyph_min, first_glyph_max, last_glyph_min, last_glyph_max;
    public static bool RequiresScrolling(float contentHeight, float viewportHeight)
    {
        if (float.IsNaN(contentHeight) || float.IsInfinity(contentHeight) || float.IsNaN(viewportHeight) ||
            float.IsInfinity(viewportHeight) || contentHeight <= 0 || viewportHeight <= 0)
            throw new ArgumentException("A finite positive text viewport is required.");
        return contentHeight > viewportHeight + .5f;
    }
    public bool ReadabilityVerified()
    {
        if (scroll_required == fits_viewport || scroll_required != RequiresScrolling(content_height, viewport_height)) return false;
        return scroll_required ? scroll_performed && last_glyph_within_viewport && vertical_normalized_position <= .01f
            : !scroll_performed && first_glyph_within_viewport && last_glyph_within_viewport && all_glyphs_within_viewport;
    }
}

// Pure frame policy; observing one visible frame while shaders are compiling
// is insufficient evidence for a useful model screenshot.
public sealed class NativeRenderStabilityGate
{
    private int lastFrame = -1;
    public int CameraFrames { get; private set; }
    public int StableFrames { get; private set; }
    public int ShaderPendingObservations { get; private set; }
    public int ShaderPendingCameraFrames { get; private set; }
    public bool Ready { get { return StableFrames >= 3; } }
    public void ObserveShaderPending(bool pending)
    { if (pending) { ShaderPendingObservations++; StableFrames = 0; } }
    public void ObserveFrame(int frame, bool shaderPending, bool renderable)
    {
        ObserveShaderPending(shaderPending);
        if (frame == lastFrame) return;
        lastFrame = frame; CameraFrames++;
        if (shaderPending) { ShaderPendingCameraFrames++; StableFrames = 0; }
        else StableFrames = renderable ? StableFrames + 1 : 0;
    }
}

[Serializable] public sealed class NativeE2EReport
{
    public string status = "running", error_code, started_at_utc, completed_at_utc, unity_version, scene;
    public string server_instance_id, owner_id, main_scene_sha256;
    public int assertions, passed_cases, real_llm_cases, model_renderability_cases, runtime_error_count, distinct_llm_responses;
    public int auth_recovery_cases, expected_auth_401_observations;
    public int dialogue_layout_smoke_cases;
    public int food_smoke_cases, real_vision_cases;
    public bool native_play_mode, main_scene_unchanged, wearable_scene_unchanged, player_settings_unchanged;
    public bool real_model_execution_independently_proven;
    public bool placement_is_simulated, physical_ar_tracking;
    public bool manual_visual_review_required;
    public NativeE2ECaseResult[] cases;
    public string[] limits = {
        "Real LLM contract means remote/real/non-synthetic response metadata; correlate server/model execution evidence separately.",
        "model_renderability_verified validates asset identity, native loading and camera renderability; it does not verify screen-pixel visibility.",
        "Simulated placement calls the production prefab/GLB path at a fixed camera-relative pose; physical AR tracking is not verified.",
        "Native camera-frame/frustum/skin checks establish renderability; inspect the Game-view capture for visual appearance and UI occlusion.",
        "Dialogue geometry checks do not approve pixel readability; UI-only long-text smoke uses labelled synthetic text and sends no chat.",
        "Food smoke uses actual remote analysis of an existing fixture photo and explicitly synthetic tester-entered consumption; no actual meal or photo-ground-truth quantity is claimed.",
        "This fixture writes only explicitly selected isolated test pets; no physical Watch/Android pairing is exercised."
    };

    // Pure policy also exercised by the managed checks. Preserve the first
    // failure code and runtime count; runtime errors can never yield passed.
    public void ApplyRuntimeErrorPolicy()
    {
        assertions++;
        if (runtime_error_count <= 0) return;
        status = "failed";
        if (string.IsNullOrEmpty(error_code)) error_code = "native_runtime_errors_detected";
    }
}

// Root starts the native editor and invokes this menu/entrypoint. Nothing auto-runs on import.
[InitializeOnLoad]
public static class CommonServerNativeVerification
{
    private const string Armed = "HealthMon.NativeE2E.Armed";
    private const string ConfigPath = "HealthMon.NativeE2E.ConfigPath";
    static CommonServerNativeVerification()
    { EditorApplication.playModeStateChanged += PlayStateChanged; }

    [MenuItem("HealthMon/Verification/Run isolated native E2E")]
    public static void RunFromConfig()
    {
        if (EditorApplication.isCompiling) throw new InvalidOperationException("Wait for script compilation.");
        string path = Environment.GetEnvironmentVariable("HEALTHMON_NATIVE_E2E_CONFIG");
        if (string.IsNullOrWhiteSpace(path))
            path = Path.Combine(Directory.GetParent(Application.dataPath).Parent.Parent.FullName, ".runtime", "unity-native-e2e.json");
        path = Path.GetFullPath(path);
        ValidateConfig(JsonUtility.FromJson<NativeE2EConfig>(File.ReadAllText(path)));
        if (SceneManager.GetActiveScene().path != "Assets/HealthMon/Scenes/MainARScene.unity")
            throw new InvalidOperationException("Open MainARScene before running native E2E. No scene will be replaced by the verifier.");
        if (Application.isPlaying) { StartRunner(path); return; }
        SessionState.SetString(ConfigPath, path);
        SessionState.SetBool(Armed, true);
        EditorApplication.isPlaying = true;
    }

    private static void PlayStateChanged(PlayModeStateChange state)
    {
        if (state != PlayModeStateChange.EnteredPlayMode || !SessionState.GetBool(Armed, false)) return;
        SessionState.SetBool(Armed, false);
        string path = SessionState.GetString(ConfigPath, "");
        SessionState.EraseString(ConfigPath);
        StartRunner(path);
    }
    private static void StartRunner(string path)
    {
        if (UnityEngine.Object.FindAnyObjectByType<CommonServerNativeE2ERunner>() != null)
            throw new InvalidOperationException("A native E2E run is already active.");
        var runner = new GameObject("HealthMon isolated native verification").AddComponent<CommonServerNativeE2ERunner>();
        runner.ConfigPath = path;
    }
    public static void ValidateConfig(NativeE2EConfig config)
    {
        if (config == null || !config.isolated_fixture || config.cases == null || config.cases.Length == 0 ||
            string.IsNullOrWhiteSpace(config.expected_server_instance_id) || string.IsNullOrWhiteSpace(config.expected_owner_id))
            throw new InvalidOperationException("Explicit isolated fixture/server/owner/cases are required.");
        CommonServerContract.NormalizeBaseUrl(config.api_base_url);
        if (config.timeout_seconds < 10 || config.timeout_seconds > 900)
            throw new InvalidOperationException("Native E2E timeout must be 10..900 seconds.");
        var identities = new HashSet<string>();
        foreach (var item in config.cases)
        {
            if (item == null || string.IsNullOrWhiteSpace(item.case_id) ||
                !System.Text.RegularExpressions.Regex.IsMatch(item.case_id, "^[A-Za-z0-9_-]{1,64}$") ||
                string.IsNullOrWhiteSpace(item.pet_id) || item.expected_state == null ||
                !item.expected_state.IsValidCommonState(item.pet_id) ||
                (item.run_chat && (string.IsNullOrWhiteSpace(item.prompt) || item.prompt.Length > 1500)))
                throw new InvalidOperationException("Invalid isolated native case manifest.");
            if (!identities.Add(item.case_id)) throw new InvalidOperationException("Native case IDs must be unique.");
            if (item.run_dialogue_layout_smoke && item.run_chat)
                throw new InvalidOperationException("Synthetic UI layout smoke must be separate from actual LLM dialogue cases.");
            if (item.run_food_smoke && (item.run_chat || item.run_auth_recovery_smoke || item.run_dialogue_layout_smoke ||
                item.run_workout_smoke || item.require_model_display || string.IsNullOrWhiteSpace(item.food_image_path)))
                throw new InvalidOperationException("Food verification requires a separate isolated non-chat case and explicit fixture image.");
            if (item.run_food_smoke)
                CommonServerContract.FoodConfirmationPayload("fixture", item.food_candidate_index, item.food_fixture_grams,
                    item.food_fixture_vegetable_fruit_g, item.food_fixture_meal_type, item.food_fixture_kcal_reconfirmed, true);
            if (item.simulate_ar_placement && !item.require_model_display)
                throw new InvalidOperationException("Simulated placement requires an explicit model-display case.");
            if (item.require_model_display && (item.expected_state.published_model_stage < 0 ||
                string.IsNullOrWhiteSpace(item.expected_state.model_reference)))
                throw new InvalidOperationException("Model-display cases require an already published server model in the expected state.");
            if (!string.IsNullOrEmpty(item.expected_model_sha256) &&
                !System.Text.RegularExpressions.Regex.IsMatch(item.expected_model_sha256, "^[a-f0-9]{64}$"))
                throw new InvalidOperationException("Expected model SHA must be lowercase SHA-256.");
        }
    }
}

// Editor-only runtime component: observes the actual production connection/UI path.
// It neither edits scene assets nor replaces native Unity APIs with test doubles.
public sealed class CommonServerNativeE2ERunner : MonoBehaviour
{
    public string ConfigPath { private get; set; }
    [Serializable] private sealed class RawChat
    {
        public string schema_version, request_id, provenance;
        public CharacterResponse response;
        public ResponseMetrics metrics;
        public PetState state_used, state_after;
        public long state_version;
    }
    [Serializable] private sealed class WorkoutFixture
    {
        public string event_id, occurred_at, started_at;
        public string source = "user", workout_type = "running", unit = "minutes";
        public bool synthetic = true;
        public int revision = 1;
        public float actual = 30;
    }
    [Serializable] private sealed class WorkoutAck { public bool stored, duplicate; public long state_version; public PetState state; }
    [Serializable] private sealed class ProfileState { public NativeE2EEvolutionProfile evolution_profile; }
    [Serializable] private sealed class FoodSourceList { public FoodSource[] records; }
    [Serializable] private sealed class FoodSource { public string event_id; public int revision; public bool synthetic; public FoodSourceData record; }
    [Serializable] private sealed class FoodSourceData
    {
        public string food_name, meal_type;
        public float grams, vegetable_fruit_g;
        public bool confirmed, quantity_confirmed, kcal_reconfirmed, synthetic;
    }
    private sealed class CheckFailure : Exception { public CheckFailure(string code) : base(code) { } }
    private readonly CancellationTokenSource lifetime = new CancellationTokenSource();
    private readonly List<NativeE2ECaseResult> results = new List<NativeE2ECaseResult>();
    private readonly HashSet<string> responseHashes = new HashSet<string>();
    private readonly Dictionary<string, string> protectedHashes = new Dictionary<string, string>();
    private NativeE2EConfig config;
    private NativeE2EReport report;
    private NativeE2ECaseResult current;
    private CommonServerConnection connection;
    private ApiFailure productionFailure;
    private string expectedAuth401Phase;
    [NonSerialized] private string token;
    private string outputDirectory, runId;
    private bool finished;

    private async void Start()
    {
        report = new NativeE2EReport { started_at_utc = DateTime.UtcNow.ToString("o"), unity_version = Application.unityVersion,
            native_play_mode = Application.isPlaying, scene = SceneManager.GetActiveScene().path };
        runId = DateTime.UtcNow.ToString("yyyyMMddTHHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8);
        outputDirectory = Path.Combine(Directory.GetParent(Application.dataPath).FullName, "Temp", "NativeE2E", runId);
        Directory.CreateDirectory(outputDirectory);
        Application.logMessageReceived += CountRuntimeError;
        try
        {
            config = JsonUtility.FromJson<NativeE2EConfig>(File.ReadAllText(ConfigPath));
            CommonServerNativeVerification.ValidateConfig(config);
            token = !string.IsNullOrWhiteSpace(config.bearer_token) ? config.bearer_token : Environment.GetEnvironmentVariable(config.bearer_token_env);
            Check(!string.IsNullOrWhiteSpace(token) && token.IndexOf('\r') < 0 && token.IndexOf('\n') < 0, "runtime_token_required");
            config.bearer_token = null; // Never serialize a credential into the result report.
            Check(Application.isPlaying && CommonServerConnection.UsesServerAuthority, "native_play_server_authority_required");
            Protect("Assets/HealthMon/Scenes/MainARScene.unity");
            Protect("Assets/HealthMon/Scenes/WearableScene.unity");
            Protect("ProjectSettings/ProjectSettings.asset");
            var info = JsonUtility.FromJson<ServerInfo>(await Http("GET", "/server-info", null, false));
            Check(info != null && info.environment == "test" && info.server_instance_id == config.expected_server_instance_id, "isolated_test_server_mismatch");
            var identity = JsonUtility.FromJson<ServerIdentity>(await Http("GET", "/identity"));
            Check(identity != null && identity.owner_id == config.expected_owner_id, "isolated_test_owner_mismatch");
            report.server_instance_id = info.server_instance_id; report.owner_id = identity.owner_id;
            await WaitFor(() => CommonServerConnection.Instance != null, 20, "common_connection_not_bootstrapped");
            connection = CommonServerConnection.Instance;
            Check(!connection.Api.IsBusy && !connection.Api.HasPendingChat, "existing_pending_work_must_be_resolved_by_operator");
            connection.Api.Failed += ProductionApiFailed;
            foreach (var item in config.cases) await RunCase(item);
            report.distinct_llm_responses = responseHashes.Count;
            int chatCases = 0; foreach (var item in config.cases) if (item.run_chat) chatCases++;
            if (config.require_distinct_llm_responses && chatCases > 1)
                Check(responseHashes.Count > 1, "different_stat_cases_received_identical_llm_speech");
            report.status = "passed";
        }
        catch (Exception error)
        {
            report.status = "failed";
            report.error_code = error is CheckFailure ? error.Message : "unexpected_" + error.GetType().Name;
            if (current != null && current.status != "passed") { current.status = "failed"; current.error_code = report.error_code; }
            if (current != null && connection != null && connection.Api.HasPendingChat) current.request_id = connection.Api.PendingRequestId;
        }
        finally
        {
            report.main_scene_unchanged = ProtectedUnchanged("Assets/HealthMon/Scenes/MainARScene.unity");
            report.wearable_scene_unchanged = ProtectedUnchanged("Assets/HealthMon/Scenes/WearableScene.unity");
            report.player_settings_unchanged = ProtectedUnchanged("ProjectSettings/ProjectSettings.asset");
            report.main_scene_sha256 = protectedHashes.ContainsKey("Assets/HealthMon/Scenes/MainARScene.unity") ? protectedHashes["Assets/HealthMon/Scenes/MainARScene.unity"] : null;
            if (protectedHashes.Count == 3 && (!report.main_scene_unchanged || !report.wearable_scene_unchanged || !report.player_settings_unchanged))
            { report.status = "failed"; report.error_code = "protected_asset_changed"; }
            report.ApplyRuntimeErrorPolicy();
            report.completed_at_utc = DateTime.UtcNow.ToString("o"); report.cases = results.ToArray();
            Application.logMessageReceived -= CountRuntimeError;
            if (connection != null && connection.Api != null) connection.Api.Failed -= ProductionApiFailed;
            token = null; finished = true;
            File.WriteAllText(Path.Combine(outputDirectory, "result.json"), JsonUtility.ToJson(report, true));
            Debug.Log("HEALTHMON_NATIVE_E2E_" + report.status.ToUpperInvariant() + " cases=" + report.passed_cases + "/" + results.Count +
                " assertions=" + report.assertions + " result=" + Path.Combine(outputDirectory, "result.json") +
                (report.error_code == null ? "" : " error_code=" + report.error_code));
            // Keep Play running for root's real UI inspection. Do not close editor or alter settings.
            Destroy(gameObject);
        }
    }

    private async Task RunCase(NativeE2ECase item)
    {
        current = new NativeE2ECaseResult { case_id = item.case_id, status = "running",
            manual_visual_review_required = item.require_model_display }; results.Add(current);
        if (item.require_model_display) report.manual_visual_review_required = true;
        productionFailure = null;
        Check(!connection.Api.IsBusy && !connection.Api.HasPendingChat, "pending_work_before_case");
        connection.Connect(config.api_base_url, token, item.pet_id);
        await WaitFor(() => connection.IsConnected && connection.Api.PetId == item.pet_id && connection.LatestState != null &&
            connection.LatestState.pet_id == item.pet_id && !connection.Api.IsBusy, config.timeout_seconds, "connection_or_state_timeout");
        Check(connection.ServerInstanceId == config.expected_server_instance_id && connection.OwnerId == config.expected_owner_id, "production_connection_identity_changed");
        var expected = item.expected_state;
        CompareState(connection.LatestState, expected, "fixture_state");
        current.server_dto_valid = connection.LatestState.IsValidCommonState(item.pet_id);
        var manager = UnityEngine.Object.FindAnyObjectByType<PetStateManager>(FindObjectsInactive.Include);
        var ui = UnityEngine.Object.FindAnyObjectByType<UIManager>(FindObjectsInactive.Include);
        var dialogue = UnityEngine.Object.FindAnyObjectByType<DialoguePrototype>(FindObjectsInactive.Include);
        Check(manager != null && ui != null && dialogue != null, "existing_main_scene_components_missing");
        ui.ShowHome(); await Task.Delay(150, lifetime.Token);
        CheckUi(manager, connection.LatestState);
        int thresholdStage = expected.level >= 30 ? 3 : expected.level >= 20 ? 2 : expected.level >= 10 ? 1 : 0;
        Check(connection.LatestState.evolution_target_stage == thresholdStage, "v22_level_evolution_condition_mismatch");
        current.evolution_condition_matches = true;
        if (item.expected_evolution_profile != null)
        {
            var profile = JsonUtility.FromJson<ProfileState>(await Http("GET", "/pets/" + Uri.EscapeDataString(item.pet_id) + "/state"))?.evolution_profile;
            var wanted = item.expected_evolution_profile;
            Check(profile != null && profile.stage == wanted.stage && Mathf.Abs(profile.strength - wanted.strength) < .001f &&
                Mathf.Abs(profile.difference - wanted.difference) < .001f && profile.appearance == wanted.appearance &&
                profile.body_balance == wanted.body_balance && profile.nutrition_condition == wanted.nutrition_condition &&
                profile.energy_condition == wanted.energy_condition && profile.generation_required == wanted.generation_required &&
                profile.recovery == wanted.recovery, "score_based_evolution_profile_mismatch");
            current.score_evolution_profile_matches = true;
            current.appearance = profile.appearance; current.body_balance = profile.body_balance;
            current.nutrition_condition = profile.nutrition_condition; current.energy_condition = profile.energy_condition;
        }
        if (item.run_workout_smoke)
        {
            var instant = DateTime.UtcNow.AddSeconds(-1).ToString("o");
            var workout = new WorkoutFixture { event_id = "native-" + runId + "-" + item.case_id, occurred_at = instant, started_at = instant };
            string body = JsonUtility.ToJson(workout);
            string path = "/pets/" + Uri.EscapeDataString(item.pet_id) + "/workouts";
            var first = JsonUtility.FromJson<WorkoutAck>(await Http("POST", path, body));
            var duplicate = JsonUtility.FromJson<WorkoutAck>(await Http("POST", path, body));
            Check(first != null && duplicate != null && first.stored && duplicate.stored && duplicate.duplicate, "workout_not_durable_or_duplicate");
            Check(Mathf.Abs(first.state.lower_body - item.expected_lower_body_after_workout) < .001f &&
                Mathf.Abs(first.state.lower_body - duplicate.state.lower_body) < .001f, "workout_score_or_idempotency_mismatch");
            current.workout_idempotent = true;
            connection.RefreshState();
            await WaitFor(() => connection.LatestState.state_version >= duplicate.state_version && !connection.Api.IsStateBusy, 30, "workout_ui_refresh_timeout");
            CheckUi(manager, connection.LatestState);
        }
        if (item.run_auth_recovery_smoke)
        {
            await VerifyAuthenticationRecovery(item);
            await WaitFor(() => !connection.Api.IsStateBusy && !connection.Api.IsBusy, 30, "auth_recovery_state_refresh_timeout");
            CheckUi(manager, connection.LatestState);
        }
        CopyObservedState(connection.LatestState);
        if (config.capture_screenshots) current.home_screenshot = await Capture(item.case_id + "-home.png");
        if (item.require_model_display)
        {
            await VerifyNativeModelDisplay(item);
        }
        if (item.run_dialogue_layout_smoke) await VerifyDialogueLayoutSmoke(item, ui, dialogue);
        if (item.run_food_smoke) await VerifyFoodSmoke(item, ui, dialogue, manager);
        if (item.run_chat)
        {
            ui.ShowDialogue(); dialogue.EnterConversation();
            await WaitFor(() => dialogue.IsConnected && dialogue.Api.ConversationReady && !dialogue.Api.IsBusy,
                config.timeout_seconds, "conversation_not_ready");
            PetState beforeChat = JsonUtility.FromJson<PetState>(JsonUtility.ToJson(connection.LatestState));
            ChatResult received = null;
            Action<ChatResult> listener = result => received = result;
            connection.Api.ChatReceived += listener;
            try
            {
                var input = Field<TMP_InputField>(dialogue, "messageInput");
                Check(input != null, "dialogue_input_not_bound");
                input.SetTextWithoutNotify(item.prompt);
                dialogue.SendMessage();
                await WaitFor(() => received != null && dialogue.LastRequestId == received.request_id,
                    config.timeout_seconds, "actual_dialogue_response_timeout");
            }
            finally { connection.Api.ChatReceived -= listener; }
            Check(received.response != null && received.metrics != null && !string.IsNullOrWhiteSpace(received.response.speech) && !received.metrics.fallback, "llm_response_missing_or_fallback");
            Check(Field<TMP_Text>(dialogue, "characterResponseText").text == received.response.speech && dialogue.LastSpeech == received.response.speech,
                "dialogue_ui_does_not_match_received_response");
            current.dialogue_text_matches = true;
            // Same persisted request ID returns its cached result; no second inference is requested.
            var cached = JsonUtility.FromJson<RawChat>(await Http("POST", "/pets/" + Uri.EscapeDataString(item.pet_id) + "/chat",
                JsonUtility.ToJson(new ChatRequest { request_id = received.request_id, text = item.prompt, state_version = connection.Api.StateVersion })));
            Check(cached != null && cached.response != null && cached.request_id == received.request_id && cached.response.speech == received.response.speech, "cached_chat_identity_mismatch");
            CompareState(cached.state_used, beforeChat, "llm_context"); current.llm_context_matches_server = true;
            current.real_llm_contract = cached.provenance == "real" && cached.metrics != null && cached.metrics.backend == "remote" &&
                !cached.metrics.synthetic && !cached.metrics.fallback;
            if (config.require_real_llm) Check(current.real_llm_contract, "real_llm_required_mock_or_fallback_is_not_success");
            if (current.real_llm_contract) report.real_llm_cases++;
            current.request_id = received.request_id; current.response_characters = received.response.speech.Length;
            current.response_sha256 = Hash(Encoding.UTF8.GetBytes(received.response.speech)); responseHashes.Add(current.response_sha256);
            current.provenance = cached.provenance; current.backend = cached.metrics?.backend;
            await VerifyDialogueGeometry(dialogue);
            if (config.capture_screenshots) current.dialogue_screenshot = await Capture(item.case_id + "-dialogue.png");
            connection.RefreshState();
            await WaitFor(() => !connection.Api.IsBusy && !connection.Api.IsStateBusy, 30, "after_chat_refresh_timeout");
            CheckUi(manager, connection.LatestState);
            dialogue.LeaveConversation();
        }
        current.status = "passed"; report.passed_cases++;
    }

    private async Task VerifyDialogueGeometry(DialoguePrototype dialogue)
    {
        var layout = dialogue.GetComponent<DialogueRuntimeLayout>();
        Check(layout != null, "runtime_dialogue_layout_missing");
        layout.ApplyNow(); await Task.Delay(120, lifetime.Token); Canvas.ForceUpdateCanvases();
        Check(layout.HasValidLayout, "runtime_dialogue_layout_has_no_usable_space");
        var controls = new[] { layout.UserBubble, layout.ResponseBubble, layout.InputArea, layout.BottomNavigation };
        int overlaps = 0;
        for (int i = 0; i < controls.Length; i++)
        {
            Check(controls[i] != null && controls[i].gameObject.activeInHierarchy, "dialogue_control_not_visible");
            Rect bounds = layout.BoundsInPanel(controls[i]);
            Check(bounds.width > 0 && bounds.height > 0 && bounds.xMin >= layout.Panel.rect.xMin - .5f &&
                bounds.xMax <= layout.Panel.rect.xMax + .5f && bounds.yMin >= layout.Panel.rect.yMin - .5f &&
                bounds.yMax <= layout.Panel.rect.yMax + .5f, "dialogue_control_outside_panel");
            for (int j = 0; j < i; j++) if (bounds.Overlaps(layout.BoundsInPanel(controls[j]))) overlaps++;
        }
        current.dialogue_overlap_count = overlaps;
        Check(overlaps == 0, "dialogue_user_response_input_or_navigation_overlap");
        var input = Field<TMP_InputField>(dialogue, "messageInput");
        var button = Field<Button>(dialogue, "sendButton");
        Rect inputBounds = layout.BoundsInPanel(input.GetComponent<RectTransform>());
        Rect sendBounds = layout.BoundsInPanel(button.GetComponent<RectTransform>());
        Check(!inputBounds.Overlaps(sendBounds) && inputBounds.width > sendBounds.width &&
            ContainsBounds(layout.BoundsInPanel(layout.InputArea), inputBounds) && ContainsBounds(layout.BoundsInPanel(layout.InputArea), sendBounds),
            "dialogue_input_or_send_button_clipped_or_overlapping");
        foreach (var scroll in new[] { layout.UserScroll, layout.ResponseScroll })
            Check(scroll != null && scroll.viewport.GetComponent<RectMask2D>() != null && scroll.vertical && !scroll.horizontal &&
                scroll.viewport.rect.width > 0 && scroll.viewport.rect.height > 0, "dialogue_text_scroll_or_mask_missing");
        current.dialogue_geometry_verified = true;
        VerifyDialogueRaycasts(layout);
        current.manual_visual_review_required = true; report.manual_visual_review_required = true;
    }
    private static bool ContainsBounds(Rect parent, Rect child)
    { return child.xMin >= parent.xMin - .5f && child.xMax <= parent.xMax + .5f && child.yMin >= parent.yMin - .5f && child.yMax <= parent.yMax + .5f; }

    private void VerifyDialogueRaycasts(DialogueRuntimeLayout layout)
    {
        var events = EventSystem.current;
        Check(events != null, "dialogue_event_system_missing");
        current.dialogue_input_module = events.currentInputModule?.GetType().FullName;
        current.dialogue_input_module_active = events.currentInputModule != null && events.currentInputModule.isActiveAndEnabled;
        current.dialogue_application_focused = Application.isFocused;
        current.dialogue_event_system_focused = events.isFocused;
        current.dialogue_run_in_background = Application.runInBackground;
        current.dialogue_input_update_mode = InputSystem.settings.updateMode.ToString();
        current.dialogue_editor_input_behavior = InputSystem.settings.editorInputBehaviorInPlayMode.ToString();
        current.dialogue_background_behavior = InputSystem.settings.backgroundBehavior.ToString();
        var module = events.currentInputModule as InputSystemUIInputModule;
        if (module != null)
        {
            current.dialogue_scroll_delta_per_tick = module.scrollDeltaPerTick;
            current.dialogue_input_actions = new[] { AuditInputAction("point", module.point), AuditInputAction("left_click", module.leftClick),
                AuditInputAction("scroll_wheel", module.scrollWheel) };
        }
        var evidence = new List<NativeDialogueRaycastProbe>();
        foreach (var scroll in new[] { layout.UserScroll, layout.ResponseScroll })
        {
            Rect viewport = scroll.viewport.rect;
            float inset = Mathf.Min(8, Mathf.Min(viewport.width, viewport.height) * .1f);
            var points = new[] { viewport.center, new Vector2(viewport.xMin + inset, viewport.yMin + inset),
                new Vector2(viewport.xMax - inset, viewport.yMin + inset), new Vector2(viewport.xMin + inset, viewport.yMax - inset),
                new Vector2(viewport.xMax - inset, viewport.yMax - inset) };
            var names = new[] { "center", "bottom_left", "bottom_right", "top_left", "top_right" };
            var canvas = scroll.GetComponentInParent<Canvas>();
            Camera camera = canvas != null && canvas.renderMode != RenderMode.ScreenSpaceOverlay ? canvas.worldCamera : null;
            for (int i = 0; i < points.Length; i++)
            {
                Vector2 screen = RectTransformUtility.WorldToScreenPoint(camera, scroll.viewport.TransformPoint(points[i]));
                var hits = new List<RaycastResult>();
                events.RaycastAll(new PointerEventData(events) { position = screen }, hits);
                var top = hits.Count == 0 ? null : hits[0].gameObject;
                var ancestor = top == null ? null : top.GetComponentInParent<ScrollRect>();
                evidence.Add(new NativeDialogueRaycastProbe { viewport = scroll == layout.UserScroll ? "user" : "response", sample = names[i],
                    screen_position = screen, hit_count = hits.Count, top_hit_path = HierarchyPath(top == null ? null : top.transform),
                    top_hit_type = top == null ? null : top.GetComponent<Graphic>()?.GetType().FullName,
                    top_scroll_path = HierarchyPath(ancestor == null ? null : ancestor.transform), top_hit_routes_to_expected_scroll = ancestor == scroll });
            }
        }
        // Record all points before asserting so an obstructing Graphic remains
        // diagnosable in a failed report. Raycasts send no click/scroll events.
        current.dialogue_raycast_probes = evidence.ToArray();
        Check(current.dialogue_input_module_active, "dialogue_input_module_inactive");
        Check(module != null, "dialogue_expected_input_system_ui_module_missing");
        foreach (var action in current.dialogue_input_actions)
            Check(action.reference_present && action.action_present && action.action_enabled, "dialogue_" + action.slot + "_action_not_enabled");
        foreach (var probe in evidence)
            Check(probe.top_hit_routes_to_expected_scroll, "dialogue_" + probe.viewport + "_" + probe.sample + "_raycast_blocked");
        current.dialogue_raycast_verified = true;
    }
    private static NativeInputActionEvidence AuditInputAction(string slot, InputActionReference reference)
    {
        var action = reference == null ? null : reference.action;
        var bindings = new List<string>(); var controls = new List<string>();
        if (action != null)
        {
            foreach (var binding in action.bindings) bindings.Add(binding.effectivePath);
            foreach (var control in action.controls) controls.Add(control.path);
        }
        return new NativeInputActionEvidence { slot = slot, reference_present = reference != null, action_present = action != null,
            action_enabled = action != null && action.enabled, action_name = action?.name, action_type = action?.type.ToString(),
            binding_paths = bindings.ToArray(), resolved_control_paths = controls.ToArray() };
    }
    private static string HierarchyPath(Transform target)
    {
        if (target == null) return null;
        string path = target.name;
        for (var parent = target.parent; parent != null; parent = parent.parent) path = parent.name + "/" + path;
        return path;
    }

    private async Task VerifyDialogueLayoutSmoke(NativeE2ECase item, UIManager ui, DialoguePrototype dialogue)
    {
        Check(!item.run_chat && !connection.Api.HasPendingChat, "synthetic_layout_smoke_must_not_replace_actual_chat");
        string originalRequestId = dialogue.LastRequestId;
        int originalRealLlmCount = report.real_llm_cases;
        ui.ShowDialogue(); dialogue.EnterConversation();
        await WaitFor(() => dialogue.Api.ConversationReady && !dialogue.Api.IsBusy, config.timeout_seconds, "layout_smoke_conversation_not_ready");
        dialogue.LeaveConversation(); // Stop status/heartbeat text before placing labelled UI-only text.
        var user = Field<TMP_Text>(dialogue, "userMessageText");
        var response = Field<TMP_Text>(dialogue, "characterResponseText");
        user.text = SyntheticUiText(1500); response.text = SyntheticUiText(500);
        current.dialogue_layout_synthetic = true;
        current.dialogue_layout_user_characters = user.text.Length;
        current.dialogue_layout_response_characters = response.text.Length;
        Check(user.text.Length == 1500 && response.text.Length == 500, "synthetic_layout_fixture_length_mismatch");
        await VerifyDialogueGeometry(dialogue);
        var layout = dialogue.GetComponent<DialogueRuntimeLayout>();
        layout.UserScroll.StopMovement(); layout.ResponseScroll.StopMovement();
        layout.UserScroll.verticalNormalizedPosition = 1; layout.ResponseScroll.verticalNormalizedPosition = 1;
        await Task.Delay(100, lifetime.Token); Canvas.ForceUpdateCanvases();
        current.dialogue_layout_start_screenshot = await Capture(item.case_id + "-ui-layout-start.png");
        current.dialogue_user_viewport = new NativeDialogueViewportEvidence();
        current.dialogue_response_viewport = new NativeDialogueViewportEvidence();
        await VerifyTextViewport(user, layout.UserScroll, current.dialogue_user_viewport);
        current.dialogue_user_scroll_reaches_end = current.dialogue_user_viewport.scroll_performed && current.dialogue_user_viewport.last_glyph_within_viewport;
        await VerifyTextViewport(response, layout.ResponseScroll, current.dialogue_response_viewport);
        current.dialogue_response_scroll_reaches_end = current.dialogue_response_viewport.scroll_performed && current.dialogue_response_viewport.last_glyph_within_viewport;
        await VerifyDialogueGeometry(dialogue);
        current.dialogue_layout_end_screenshot = await Capture(item.case_id + "-ui-layout-end.png");
        Check(dialogue.LastRequestId == originalRequestId && !connection.Api.HasPendingChat && report.real_llm_cases == originalRealLlmCount,
            "ui_only_layout_smoke_sent_chat_or_incremented_real_llm_count");
        current.dialogue_layout_no_chat_sent = true;
        current.dialogue_layout_smoke_verified = true; report.dialogue_layout_smoke_cases++;
        // Intentionally leave the labelled synthetic UI-only content for manual
        // Game-view review. No LastSpeech/server response/data is replaced.
    }
    private static string SyntheticUiText(int length)
    {
        const string prefix = "[합성 UI 검증 · 서버 미전송]\n";
        const string suffix = "\n[UI 끝]";
        if (length < prefix.Length + suffix.Length) throw new ArgumentException("UI-only text length is too short.");
        var text = new StringBuilder(prefix);
        for (int line = 1; text.Length < length; line++)
            text.Append("[" + line.ToString("000") + "] 합성 가독성 확인용 문구입니다. 위아래 위치와 줄 번호를 비교합니다.\n");
        return text.ToString(0, length - suffix.Length) + suffix;
    }
    private async Task VerifyTextViewport(TMP_Text text, ScrollRect scroll, NativeDialogueViewportEvidence evidence)
    {
        evidence.content_height = scroll.content.rect.height; evidence.viewport_height = scroll.viewport.rect.height;
        evidence.scroll_required = NativeDialogueViewportEvidence.RequiresScrolling(evidence.content_height, evidence.viewport_height);
        evidence.fits_viewport = !evidence.scroll_required;
        scroll.StopMovement(); scroll.verticalNormalizedPosition = evidence.scroll_required ? 0 : 1;
        evidence.scroll_performed = evidence.scroll_required;
        await Task.Delay(150, lifetime.Token); Canvas.ForceUpdateCanvases();
        text.ForceMeshUpdate();
        Rect viewport = scroll.viewport.rect;
        evidence.viewport_min = viewport.min; evidence.viewport_max = viewport.max;
        evidence.vertical_normalized_position = scroll.verticalNormalizedPosition;
        int first = -1, last = -1;
        bool allInside = true;
        for (int index = 0; index < text.textInfo.characterCount; index++)
        {
            var glyph = text.textInfo.characterInfo[index];
            if (!glyph.isVisible) continue;
            Vector2 bottom = scroll.viewport.InverseTransformPoint(text.transform.TransformPoint(glyph.bottomLeft));
            Vector2 top = scroll.viewport.InverseTransformPoint(text.transform.TransformPoint(glyph.topRight));
            bool inside = bottom.x >= viewport.xMin - 3 && top.x <= viewport.xMax + 3 && bottom.y >= viewport.yMin - 3 && top.y <= viewport.yMax + 3;
            if (first < 0)
            {
                first = index; evidence.first_glyph_min = bottom; evidence.first_glyph_max = top;
                evidence.first_glyph_within_viewport = inside;
            }
            last = index; evidence.last_glyph_min = bottom; evidence.last_glyph_max = top;
            evidence.last_glyph_within_viewport = inside; allInside &= inside;
        }
        evidence.all_glyphs_within_viewport = allInside && first >= 0;
        Check(first >= 0 && last >= first, "text_viewport_has_no_visible_glyph");
        Check(evidence.ReadabilityVerified(), evidence.scroll_required
            ? "last_dialogue_glyph_cannot_be_read_at_scroll_end" : "fitting_dialogue_glyphs_outside_viewport");
    }

    private async Task VerifyFoodSmoke(NativeE2ECase item, UIManager ui, DialoguePrototype dialogue, PetStateManager manager)
    {
        Check(connection.EnvironmentName == "test" && !connection.Api.IsBusy && !connection.Api.HasPendingChat,
            "food_smoke_requires_idle_isolated_connection");
        string imagePath = Path.GetFullPath(item.food_image_path);
        string allowed = Path.GetFullPath(Path.Combine(Application.dataPath, "HealthMon/Scripts/Food/food.jpg"));
        Check(string.Equals(imagePath, allowed, StringComparison.OrdinalIgnoreCase), "food_smoke_existing_team_fixture_only");
        byte[] image = File.ReadAllBytes(imagePath);
        current.food_image_sha256 = Hash(image);
        Check(current.food_image_sha256 == "1549ae05c766686c9f62a21c7d6b6474688d076a187a931b9b956e6cb06654b2",
            "food_smoke_fixture_photo_changed");
        string path = "/pets/" + Uri.EscapeDataString(item.pet_id) + "/meals";
        var beforeRecords = JsonUtility.FromJson<FoodSourceList>(await Http("GET", path));
        Check(beforeRecords?.records != null && beforeRecords.records.Length == 0, "food_smoke_requires_new_pet_without_meals");
        string chatBefore = dialogue.LastRequestId;
        ui.ShowFoodScan();
        var food = UnityEngine.Object.FindAnyObjectByType<FoodScanPrototype>(FindObjectsInactive.Include);
        Check(food != null, "production_food_scan_missing");
        await WaitFor(() => Field<TMP_InputField>(food, "gramsInput") != null && Field<TMP_InputField>(food, "vegetablesInput") != null,
            20, "production_food_confirmation_controls_missing");
        food.EnableSyntheticConsumptionFixture();
        food.UseImage(image);
        Check(Field<RawImage>(food, "capturedPreview")?.texture != null && Field<byte[]>(food, "capturedBytes")?.Length == image.Length,
            "food_fixture_not_loaded_in_production_preview");
        food.AnalyzeFood();
        await WaitFor(() => food.LastAnalysis != null && !connection.Api.IsBusy, config.timeout_seconds, "actual_food_vision_timeout");
        var analysis = food.LastAnalysis;
        Check(CommonServerContract.ValidFoodAnalysis(analysis) && !analysis.consumption_confirmed, "food_analysis_contract_invalid");
        current.food_analysis_id = analysis.analysis_id; current.food_backend = analysis.backend;
        current.food_provenance = analysis.provenance; current.food_analysis_synthetic = analysis.synthetic;
        current.food_real_vision_contract = analysis.backend == "remote" && analysis.provenance == "real" && !analysis.IsSynthetic;
        if (item.food_require_real_vision) Check(current.food_real_vision_contract, "actual_vision_required_synthetic_analysis_not_success");
        Check(Field<GameObject>(food, "candidateView").activeInHierarchy &&
            food.DisplayedAnalysisOrigin.Contains(current.food_real_vision_contract ? "REAL" : "SYNTHETIC") &&
            food.DisplayedAnalysisOrigin.Contains("SYNTHETIC 테스트 입력"), "food_provenance_not_visible_in_candidates");
        var buttons = Field<Button[]>(food, "candidateButtons");
        current.food_candidate_count = analysis.candidates.Length;
        for (int index = 0; index < analysis.candidates.Length; index++)
            Check(buttons[index] != null && buttons[index].gameObject.activeInHierarchy &&
                buttons[index].GetComponentInChildren<TMP_Text>(true).text.Contains(analysis.candidates[index].food),
                "actual_food_candidate_missing_from_ui");
        current.food_analysis_displayed = true;
        current.manual_visual_review_required = true; report.manual_visual_review_required = true;
        if (config.capture_screenshots) current.food_candidates_screenshot = await Capture(item.case_id + "-food-candidates.png");
        Check(item.food_candidate_index >= 0 && item.food_candidate_index < analysis.candidates.Length, "food_candidate_index_invalid");
        food.SelectCandidate(item.food_candidate_index);
        var candidate = analysis.candidates[item.food_candidate_index];
        var grams = Field<TMP_InputField>(food, "gramsInput");
        var vegetables = Field<TMP_InputField>(food, "vegetablesInput");
        var quantityConfirmed = Field<Toggle>(food, "quantityConfirmed");
        var vegetablesConfirmed = Field<Toggle>(food, "vegetablesConfirmed");
        var kcalConfirmed = Field<Toggle>(food, "kcalConfirmed");
        Check(grams.text == "" && vegetables.text == "" && !quantityConfirmed.isOn && !vegetablesConfirmed.isOn && !kcalConfirmed.isOn,
            "photo_estimate_silently_confirmed_consumption");
        string unknownJson = JsonUtility.ToJson(CommonServerContract.FoodConfirmationPayload(analysis.analysis_id, candidate.candidate_id, null, null, "snack"));
        Check(!unknownJson.Contains("\"grams\"") && !unknownJson.Contains("\"vegetable_fruit_g\""), "unknown_food_quantity_serialized_as_zero");
        current.food_estimate_not_confirmed = true;
        current.food_analysis_produce_available = candidate.per_100g.vegetable_fruit_g != null && candidate.per_100g.vegetable_fruit_g.available;
        current.food_candidate_id = candidate.candidate_id; current.food_candidate_name = candidate.food; current.food_confidence = candidate.confidence;
        if (config.capture_screenshots) current.food_confirmation_screenshot = await Capture(item.case_id + "-food-confirmation-reference.png");
        grams.text = item.food_fixture_grams.ToString(System.Globalization.CultureInfo.InvariantCulture);
        vegetables.text = item.food_fixture_vegetable_fruit_g.ToString(System.Globalization.CultureInfo.InvariantCulture);
        food.ConfirmFood();
        Check(!food.IsConfirming && !connection.Api.IsBusy && food.LastConfirmation == null,
            "unconfirmed_tester_quantity_was_sent");
        quantityConfirmed.isOn = true; vegetablesConfirmed.isOn = true;
        kcalConfirmed.isOn = item.food_fixture_kcal_reconfirmed;
        food.SelectMealType(item.food_fixture_meal_type);
        var notice = Field<TMP_Text>(food, "confirmationNotice");
        // Re-render the production form after the intentional missing-checkbox check.
        grams.onValueChanged.Invoke(grams.text);
        Check(notice.text.Contains("SYNTHETIC CONSUMPTION FIXTURE") &&
            Field<TMP_Text>(food, "analysisOriginText").text.Contains(current.food_real_vision_contract ? "REAL" : "SYNTHETIC"),
            "synthetic_consumption_and_analysis_origin_not_distinguished");
        var scroll = Field<ScrollRect>(food, "confirmationScroll");
        Canvas.ForceUpdateCanvases(); scroll.verticalNormalizedPosition = .23f;
        if (config.capture_screenshots) current.food_quantities_screenshot = await Capture(item.case_id + "-food-explicit-quantities.png");
        current.food_confirmed_grams = item.food_fixture_grams;
        current.food_confirmed_vegetable_fruit_g = item.food_fixture_vegetable_fruit_g;
        current.food_meal_type = item.food_fixture_meal_type; current.food_kcal_reconfirmed = item.food_fixture_kcal_reconfirmed;
        current.food_synthetic_consumption = true; current.food_explicit_quantity_verified = true;
        food.ConfirmFood();
        await WaitFor(() => food.LastConfirmation != null && !connection.Api.IsBusy && !connection.Api.IsStateBusy,
            config.timeout_seconds, "production_food_confirm_timeout");
        var first = food.LastConfirmation;
        Check(first.stored && !first.duplicate && first.analysis_id == analysis.analysis_id && !string.IsNullOrWhiteSpace(first.source_id),
            "food_confirmation_not_durably_stored");
        current.food_source_id = first.source_id;
        connection.RefreshState();
        await WaitFor(() => !connection.Api.IsStateBusy && connection.LatestState.state_version >= first.state_version, 30, "food_state_refresh_timeout");
        CompareState(connection.LatestState, first.state, "food_confirm_state"); CheckUi(manager, connection.LatestState);
        current.food_state_ui_verified = true;
        var afterRecords = JsonUtility.FromJson<FoodSourceList>(await Http("GET", path));
        Check(afterRecords?.records != null && afterRecords.records.Length == 1, "food_smoke_expected_exactly_one_meal");
        var source = afterRecords.records[0];
        Check(source.event_id == first.source_id && source.synthetic && source.record != null && source.record.confirmed &&
            source.record.quantity_confirmed && source.record.food_name == candidate.food && source.record.meal_type == item.food_fixture_meal_type &&
            Mathf.Abs(source.record.grams - item.food_fixture_grams) < .001f &&
            Mathf.Abs(source.record.vegetable_fruit_g - item.food_fixture_vegetable_fruit_g) < .001f &&
            source.record.kcal_reconfirmed == item.food_fixture_kcal_reconfirmed, "stored_food_source_differs_from_confirmed_ui_input");
        FoodConfirmationResult duplicate = null;
        connection.Api.ConfirmFood(analysis.analysis_id, candidate.candidate_id, item.food_fixture_grams, value => duplicate = value,
            mealType: item.food_fixture_meal_type, kcalReconfirmed: item.food_fixture_kcal_reconfirmed,
            vegetableFruitGrams: item.food_fixture_vegetable_fruit_g, syntheticFixture: true);
        await WaitFor(() => duplicate != null && !connection.Api.IsBusy && !connection.Api.IsStateBusy, 30, "food_duplicate_confirmation_timeout");
        Check(duplicate.stored && duplicate.duplicate && duplicate.source_id == first.source_id && duplicate.state_version == first.state_version,
            "food_confirmation_same_event_not_idempotent");
        CompareState(duplicate.state, first.state, "food_duplicate_state");
        var finalRecords = JsonUtility.FromJson<FoodSourceList>(await Http("GET", path));
        Check(finalRecords?.records?.Length == 1 && finalRecords.records[0].event_id == first.source_id, "duplicate_confirmation_created_second_meal");
        Check(dialogue.LastRequestId == chatBefore && !connection.Api.HasPendingChat, "synthetic_food_smoke_sent_unrequested_chat");
        current.food_record_count = finalRecords.records.Length; current.food_idempotent = true; current.food_no_chat_sent = true;
        ui.ShowHome(); CheckUi(manager, connection.LatestState); CopyObservedState(connection.LatestState);
        if (config.capture_screenshots) current.food_recorded_screenshot = await Capture(item.case_id + "-food-recorded-home.png");
        current.food_smoke_verified = true; report.food_smoke_cases++;
        if (current.food_real_vision_contract) report.real_vision_cases++;
    }

    private async Task VerifyAuthenticationRecovery(NativeE2ECase item)
    {
        var api = connection.Api;
        Check(connection.IsConnected && connection.EnvironmentName == "test" && !api.IsBusy && !api.HasPendingChat && api.HasStateVersion,
            "auth_smoke_requires_verified_idle_isolated_connection");
        MessageHistory before = null;
        api.GetHistory(value => before = value, 100);
        await WaitFor(() => before != null && !api.IsBusy, 30, "auth_smoke_history_before_timeout");
        Check(before.pet_id == item.pet_id, "auth_smoke_history_pet_mismatch");
        var earlierIds = new HashSet<string>();
        foreach (var message in before.messages ?? new HistoryMessage[0]) earlierIds.Add(message.request_id);
        var bearer = typeof(HealthmonApiClient).GetField("bearerToken", BindingFlags.Instance | BindingFlags.NonPublic);
        Check(bearer != null && bearer.IsNotSerialized, "auth_smoke_runtime_credential_field_missing");
        Check((string)bearer.GetValue(api) == token.Trim(), "auth_smoke_original_test_credential_mismatch");
        string invalid = "healthmon-invalid-native-auth-" + Guid.NewGuid().ToString("N");
        const string controlText = "오늘 쉬고 싶어";
        try
        {
            // Deliberately invalidate only this runtime API field. No token on
            // the server, DB, other component or other account is changed.
            bearer.SetValue(api, invalid);
            ApiFailure rejected = null;
            long originalVersion = api.StateVersion;
            expectedAuth401Phase = "initial_chat";
            api.SendChat(controlText, _ => { }, error => rejected = error);
            await WaitFor(() => rejected != null && !api.IsBusy, 30, "auth_smoke_initial_401_timeout");
            expectedAuth401Phase = null;
            Check(rejected.StatusCode == 401 && api.HasPendingChat, "auth_smoke_initial_request_not_retained_after_401");
            current.auth_initial_401_verified = true;
            string frozenJson = api.ExportPendingChat();
            var pending = JsonUtility.FromJson<PendingChatSnapshot>(frozenJson);
            Check(pending != null && pending.request != null && pending.request.text == controlText &&
                !string.IsNullOrWhiteSpace(pending.request.request_id) && pending.pet_id == item.pet_id &&
                pending.request.state_version == originalVersion &&
                CommonServerContract.MatchesPendingScope(pending, config.api_base_url, config.expected_server_instance_id,
                    config.expected_owner_id, item.pet_id), "auth_smoke_pending_scope_or_payload_invalid");
            current.auth_request_id = pending.request.request_id;
            current.auth_original_request_version = pending.request.state_version;
            current.auth_pending_snapshot_sha256 = Hash(Encoding.UTF8.GetBytes(frozenJson));

            ApiFailure invalidCandidate = null;
            expectedAuth401Phase = "invalid_candidate";
            connection.ReauthenticatePendingToken(invalid, _ => { }, error => invalidCandidate = error);
            await WaitFor(() => invalidCandidate != null && !api.IsBusy, 30, "auth_smoke_invalid_candidate_timeout");
            expectedAuth401Phase = null;
            Check(invalidCandidate.StatusCode == 401 && api.HasPendingChat && api.ExportPendingChat() == frozenJson &&
                (string)bearer.GetValue(api) == invalid, "auth_smoke_failed_candidate_changed_pending_or_credential");
            current.auth_invalid_candidate_rejected = true;

            PetState authenticated = null;
            ApiFailure recoveryFailure = null;
            // Exercise the same production connection path as the panel, with
            // surrounding copied spaces. Never print the header or credential.
            connection.ReauthenticatePendingToken("  " + token + "  ", value => authenticated = value, error => recoveryFailure = error);
            await WaitFor(() => (authenticated != null || recoveryFailure != null) && !api.IsBusy, 30, "auth_smoke_valid_candidate_timeout");
            Check(recoveryFailure == null && authenticated != null && authenticated.IsValidCommonState(item.pet_id) &&
                api.VerifiedServerInstanceId == config.expected_server_instance_id && api.VerifiedOwnerId == config.expected_owner_id &&
                connection.IsConnected &&
                api.HasPendingChat && api.ExportPendingChat() == frozenJson && (string)bearer.GetValue(api) == token.Trim(),
                "auth_smoke_same_scope_reauthentication_failed_or_changed_request");
            current.auth_pending_preserved = true; current.auth_same_scope_reauthenticated = true;
            current.auth_whitespace_candidate_verified = true;
            using (var authorized = UnityWebRequest.Get(CommonServerContract.ResolveApiUrl(connection.BaseUrl, "/pets/" + Uri.EscapeDataString(item.pet_id) + "/state")))
            {
                connection.Authorize(authorized);
                Check(authorized.GetRequestHeader("Authorization") == "Bearer " + (string)bearer.GetValue(api) &&
                    authorized.GetRequestHeader("Authorization") == "Bearer " + CommonServerContract.NormalizeBearerToken(token),
                    "auth_smoke_connection_download_header_differs_from_api_credential");
            }
            current.auth_connection_header_matches = true;

            ChatResult completed = null;
            ApiFailure retryFailure = null;
            // An explicit retry, not SendChat, is the only second chat transport.
            api.RetryPendingChat(value => completed = value, error => retryFailure = error);
            await WaitFor(() => (completed != null || retryFailure != null) && !api.IsBusy, 30, "auth_smoke_same_request_retry_timeout");
            Check(retryFailure == null && completed != null && completed.request_id == pending.request.request_id && !api.HasPendingChat,
                "auth_smoke_retry_changed_id_or_left_pending");
            Check(completed.provenance == "server_rule" && completed.response != null &&
                !string.IsNullOrWhiteSpace(completed.response.speech) && completed.metrics != null && !completed.metrics.fallback &&
                !completed.metrics.synthetic, "auth_smoke_control_response_was_not_server_rule");
            current.auth_same_id_retry_verified = true; current.auth_server_rule_response_verified = true;

            MessageHistory after = null;
            api.GetHistory(value => after = value, 100);
            await WaitFor(() => after != null && !api.IsBusy, 30, "auth_smoke_history_after_timeout");
            Check(after.pet_id == item.pet_id, "auth_smoke_history_after_pet_mismatch");
            var newIds = new HashSet<string>();
            int matching = 0;
            foreach (var message in after.messages ?? new HistoryMessage[0])
            {
                if (!earlierIds.Contains(message.request_id)) newIds.Add(message.request_id);
                if (message.request_id == pending.request.request_id) matching++;
            }
            current.auth_history_new_request_count = newIds.Count;
            Check(newIds.Count == 1 && newIds.Contains(pending.request.request_id) && matching == 1,
                "auth_smoke_server_history_contains_duplicate_or_new_request_id");
            Check(current.auth_expected_401_observations >= 2, "auth_smoke_expected_401_evidence_missing");
            current.auth_recovery_smoke_verified = true; report.auth_recovery_cases++;
            // No real_llm_cases increment: the explicit control uses server rules.
        }
        finally { expectedAuth401Phase = null; }
    }

    private void CheckUi(PetStateManager manager, PetState state)
    {
        Check(manager.HasVerifiedServerState && manager.CurrentLevel == state.level && manager.CurrentCoin == state.coin &&
            manager.CurrentIntimacy == Mathf.RoundToInt(state.affinity) && manager.CurrentActivity == Mathf.RoundToInt(state.activity), "pet_state_manager_mismatch");
        Label(manager, "homeLevelText", "Lv. " + state.level);
        Label(manager, "homeExpText", "EXP " + state.current_exp + " / " + state.required_exp);
        Label(manager, "homeCoinText", "코인 " + state.coin);
        Label(manager, "homeIntimacyText", "친밀도 " + Mathf.RoundToInt(state.affinity));
        Label(manager, "homeActivityText", "활동성 " + Mathf.RoundToInt(state.activity));
        Label(manager, "statusLevelText", "Lv. " + state.level);
        Label(manager, "statusExpText", "EXP " + state.current_exp + " / " + state.required_exp);
        Label(manager, "growthStageText", "현재 단계 : 목표 " + state.evolution_target_stage + " / 모델 " + state.published_model_stage + " (" + state.asset_status + ")");
        current.ui_matches_server = true;
    }
    private void Label(object component, string name, string expected)
    { var label = Field<TMP_Text>(component, name); Check(label != null && label.text == expected, "ui_" + name + "_mismatch"); current.ui_assertions++; }
    private static T Field<T>(object component, string name) where T : class
    { return component.GetType().GetField(name, BindingFlags.NonPublic | BindingFlags.Instance)?.GetValue(component) as T; }
    private void CompareState(PetState actual, PetState expected, string code)
    {
        Check(actual != null && actual.IsValidCommonState(expected.pet_id), code + "_invalid_dto");
        foreach (string key in new[] { "level", "current_exp", "required_exp", "total_exp", "coin", "evolution_target_stage", "published_model_stage" })
            Check((int)typeof(PetState).GetField(key).GetValue(actual) == (int)typeof(PetState).GetField(key).GetValue(expected), code + "_" + key);
        foreach (string key in new[] { "upper_body", "lower_body", "nutrition", "energy_balance", "activity", "affinity", "initiative" })
            Check(Mathf.Abs((float)typeof(PetState).GetField(key).GetValue(actual) - (float)typeof(PetState).GetField(key).GetValue(expected)) < .001f, code + "_" + key);
        Check(actual.asset_status == expected.asset_status && actual.model_reference == expected.model_reference, code + "_asset_reference");
    }
    private void CopyObservedState(PetState state)
    {
        current.level = state.level; current.target_stage = state.evolution_target_stage; current.published_stage = state.published_model_stage;
        current.state_version = state.state_version; current.upper_body = state.upper_body; current.lower_body = state.lower_body;
        current.nutrition = state.nutrition; current.energy_balance = state.energy_balance;
        current.activity = state.activity; current.affinity = state.affinity; current.initiative = state.initiative;
    }
    private async Task VerifyNativeModelDisplay(NativeE2ECase item)
    {
        // Automation cannot attest that overlay UI leaves the model visible.
        // Root reviews the real Game view and model PNG separately.
        current.manual_visual_review_required = true; report.manual_visual_review_required = true;
        var state = connection.LatestState;
        Check(state.published_model_stage >= 0 && !string.IsNullOrWhiteSpace(state.model_reference), "published_model_state_missing");
        await WaitFor(() => EvolutionClient.Instance?.Current != null &&
            EvolutionClient.Instance.Current.pet_id == item.pet_id &&
            EvolutionClient.Instance.Current.stage == state.published_model_stage &&
            EvolutionClient.Instance.Current.model_url == state.model_reference,
            config.timeout_seconds, "published_model_manifest_not_loaded");
        var evolution = EvolutionClient.Instance;
        var manifest = evolution.Current;
        var job = JsonUtility.FromJson<CommonEvolutionJob>(await Http("GET", "/pets/" + Uri.EscapeDataString(item.pet_id) +
            "/evolutions/" + Uri.EscapeDataString(manifest.revision)));
        Check(job != null && job.status == "succeeded" && job.job_id == manifest.revision &&
            job.stage == state.published_model_stage && job.state_version <= state.state_version &&
            (job.model_reference ?? job.model_url) == state.model_reference && job.model_sha256 == manifest.model_sha256,
            "published_model_job_manifest_state_mismatch");
        if (!string.IsNullOrEmpty(item.expected_model_revision))
            Check(manifest.revision == item.expected_model_revision, "published_model_revision_differs_from_fixture");
        if (!string.IsNullOrEmpty(item.expected_model_sha256))
            Check(manifest.model_sha256 == item.expected_model_sha256, "published_model_sha_differs_from_fixture");
        // This is the production authenticated/cache-verified download method used
        // by ArEvolutionModel. Compare its actual bytes with the server job too.
        byte[] bytes = await evolution.DownloadModel(manifest);
        string actualHash = Hash(bytes);
        Check(actualHash == manifest.model_sha256 && actualHash == job.model_sha256 && bytes.Length >= 20 &&
            bytes[0] == (byte)'g' && bytes[1] == (byte)'l' && bytes[2] == (byte)'T' && bytes[3] == (byte)'F',
            "published_model_glb_or_sha_invalid");
        current.model_asset_sha256_verified = true;
        current.model_revision = manifest.revision; current.model_sha256 = actualHash; current.model_job_status = job.status;

        Camera camera = Camera.main;
        Check(camera != null && camera.isActiveAndEnabled && camera.gameObject.activeInHierarchy &&
            camera.pixelWidth > 0 && camera.pixelHeight > 0, "active_main_game_camera_missing");
        ArEvolutionModel view = null;
        if (item.simulate_ar_placement)
        {
            var placement = UnityEngine.Object.FindAnyObjectByType<ARPlacementManager>();
            Check(placement != null && placement.isActiveAndEnabled, "production_ar_placement_manager_missing");
            const float distance = 1.2f;
            var pose = new Pose(camera.transform.position + camera.transform.forward * distance - camera.transform.up * .2f,
                Quaternion.LookRotation(camera.transform.forward, camera.transform.up));
            placement.PlaceAt(pose);
            Check(placement.SpawnedHealthMon != null, "production_ar_prefab_not_instantiated");
            view = placement.SpawnedHealthMon.GetComponent<ArEvolutionModel>();
            Check(view != null, "production_ar_prefab_evolution_view_missing");
            current.placement_is_simulated = true; report.placement_is_simulated = true;
            current.simulated_placement_distance_m = distance;
        }
        else
        {
            await WaitFor(() => FindDisplayedModel(manifest.revision) != null, config.timeout_seconds, "published_model_not_displayed");
            view = FindDisplayedModel(manifest.revision);
        }
        // Never treat a deterministic Editor placement as plane tracking evidence.
        current.physical_ar_tracking = false; report.physical_ar_tracking = false;
        await WaitFor(() => view != null && view.gameObject.activeInHierarchy && view.DisplayedRevision == manifest.revision &&
            string.IsNullOrEmpty(view.LastError), config.timeout_seconds, "published_model_native_import_not_displayed");
        current.displayed_revision = view.DisplayedRevision;
        Check(current.displayed_revision == job.job_id, "native_displayed_revision_mismatch");
        // Inspect only the actual imported visual child, rather than a prefab's
        // placeholder skin. This is observation of the production object tree.
        var visual = Field<GameObject>(view, "displayed");
        Check(visual != null && visual.activeInHierarchy, "actual_imported_visual_missing");
        var skins = visual.GetComponentsInChildren<SkinnedMeshRenderer>(false);
        Check(skins.Length > 0, "native_import_has_no_skinned_renderer");
        current.native_skinned_renderer_count = skins.Length;
        bool haveBounds = false;
        Bounds bounds = new Bounds();
        foreach (var skin in skins)
        {
            Mesh mesh = skin.sharedMesh;
            Check(mesh != null && mesh.vertexCount > 0 && mesh.bindposes != null && mesh.bindposes.Length > 0,
                "native_skin_mesh_or_bindposes_missing");
            Check(skin.bones != null && skin.bones.Length >= mesh.bindposes.Length, "native_skin_bones_missing");
            foreach (var bone in skin.bones) Check(bone != null, "native_skin_null_bone");
            current.native_bone_count += skin.bones.Length;
            current.native_mesh_vertices += mesh.vertexCount;
            var baked = new Mesh();
            try
            {
                skin.BakeMesh(baked);
                Check(baked.vertexCount == mesh.vertexCount && Finite(baked.bounds.center) &&
                    Finite(baked.bounds.size) && baked.bounds.size.sqrMagnitude > .00000001f,
                    "native_bake_mesh_has_no_finite_geometry");
            }
            finally { Destroy(baked); }
            if (!haveBounds) { bounds = skin.bounds; haveBounds = true; }
            else bounds.Encapsulate(skin.bounds);
        }
        Check(haveBounds && Finite(bounds.center) && Finite(bounds.size) && bounds.size.sqrMagnitude > .00000001f,
            "native_skin_world_bounds_invalid");
        current.native_skin_verified = true; current.bones_verified = true;
        current.model_bounds_center = bounds.center; current.model_bounds_size = bounds.size;
        current.model_camera = camera.name;

        var stability = new NativeRenderStabilityGate();
        double renderStarted = EditorApplication.timeSinceStartup;
        current.model_render_wait_timeout_seconds = 30;
        Action<Camera> observeCamera = rendered =>
        {
            if (rendered != camera) return;
            var planes = GeometryUtility.CalculateFrustumPlanes(camera);
            int renderable = 0;
            foreach (var skin in skins) if (RenderableByCamera(skin, camera, planes) && skin.isVisible) renderable++;
            current.native_renderable_renderer_count = renderable;
            stability.ObserveFrame(Time.frameCount, ShaderUtil.anythingCompiling, renderable > 0);
        };
        Action<ScriptableRenderContext, Camera> onPipelineCamera = (context, rendered) => observeCamera(rendered);
        Camera.CameraCallback onBuiltinCamera = rendered => observeCamera(rendered);
        RenderPipelineManager.endCameraRendering += onPipelineCamera;
        Camera.onPostRender += onBuiltinCamera;
        try
        {
            await WaitFor(() =>
            {
                bool pending = ShaderUtil.anythingCompiling;
                stability.ObserveShaderPending(pending);
                return !pending && stability.Ready;
            }, current.model_render_wait_timeout_seconds, "native_model_shader_or_camera_frames_not_stable");
            current.model_shader_pending_at_capture = ShaderUtil.anythingCompiling;
            Check(!current.model_shader_pending_at_capture, "native_model_shader_started_compiling_before_capture");
            // Keep observing until the actual screenshot has been written.
            current.model_screenshot = await Capture(item.case_id + "-native-model.png");
            Check(!ShaderUtil.anythingCompiling && stability.Ready, "native_model_shader_or_render_changed_during_capture");
        }
        finally
        {
            RenderPipelineManager.endCameraRendering -= onPipelineCamera;
            Camera.onPostRender -= onBuiltinCamera;
            current.model_camera_frames_observed = stability.CameraFrames;
            current.model_stable_camera_frames = stability.StableFrames;
            current.model_shader_pending_observations = stability.ShaderPendingObservations;
            current.model_shader_pending_camera_frames = stability.ShaderPendingCameraFrames;
            current.model_shader_compilation_observed = stability.ShaderPendingObservations > 0;
            current.model_render_wait_seconds = (float)(EditorApplication.timeSinceStartup - renderStarted);
        }
        current.native_camera_frame_seen = stability.CameraFrames > 0;
        current.camera_frustum_verified = true; current.native_renderability_verified = true;
        Check(view.DisplayedRevision == manifest.revision && evolution.Current != null &&
            evolution.Current.pet_id == item.pet_id && evolution.Current.revision == manifest.revision &&
            evolution.Current.model_sha256 == actualHash && connection.LatestState.model_reference == state.model_reference &&
            connection.LatestState.published_model_stage == state.published_model_stage,
            "published_model_changed_during_native_render_verification");
        current.model_renderability_verified = true; report.model_renderability_cases++;
    }
    private static ArEvolutionModel FindDisplayedModel(string revision)
    {
        foreach (var model in UnityEngine.Object.FindObjectsByType<ArEvolutionModel>(FindObjectsInactive.Exclude, FindObjectsSortMode.None))
            if (model.DisplayedRevision == revision && string.IsNullOrEmpty(model.LastError)) return model;
        return null;
    }
    private static bool RenderableByCamera(SkinnedMeshRenderer skin, Camera camera, Plane[] planes)
    {
        if (skin == null || !skin.enabled || skin.forceRenderingOff || !skin.gameObject.activeInHierarchy ||
            (camera.cullingMask & (1 << skin.gameObject.layer)) == 0 || !GeometryUtility.TestPlanesAABB(planes, skin.bounds)) return false;
        var materials = skin.sharedMaterials;
        if (materials == null || materials.Length == 0) return false;
        foreach (var material in materials)
            if (material == null || material.shader == null || !material.shader.isSupported || material.passCount <= 0 ||
                material.shader.name == "Hidden/InternalErrorShader") return false;
        return true;
    }
    private static bool Finite(Vector3 value)
    { return !float.IsNaN(value.x) && !float.IsInfinity(value.x) && !float.IsNaN(value.y) && !float.IsInfinity(value.y) && !float.IsNaN(value.z) && !float.IsInfinity(value.z); }
    private async Task<string> Http(string method, string path, string body = null, bool authorize = true)
    {
        using (var request = new UnityWebRequest(CommonServerContract.ResolveApiUrl(config.api_base_url, path), method))
        {
            request.downloadHandler = new DownloadHandlerBuffer(); request.timeout = config.timeout_seconds; request.redirectLimit = 0;
            request.SetRequestHeader("Accept", "application/json");
            if (authorize) request.SetRequestHeader("Authorization", "Bearer " + token);
            if (body != null) { request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body)); request.SetRequestHeader("Content-Type", "application/json"); }
            var operation = request.SendWebRequest();
            using (lifetime.Token.Register(request.Abort))
                await WaitFor(() => operation.isDone, config.timeout_seconds + 5, "http_transport_timeout");
            Check(request.result == UnityWebRequest.Result.Success, "http_status_" + request.responseCode);
            return request.downloadHandler.text;
        }
    }
    private async Task WaitFor(Func<bool> predicate, int seconds, string failure)
    {
        double started = EditorApplication.timeSinceStartup;
        while (!predicate())
        {
            lifetime.Token.ThrowIfCancellationRequested();
            if (productionFailure != null && productionFailure.StatusCode >= 400)
                throw new CheckFailure("production_api_http_" + productionFailure.StatusCode);
            if (!Application.isPlaying || EditorApplication.timeSinceStartup - started > seconds) throw new CheckFailure(failure);
            await Task.Delay(50, lifetime.Token);
        }
    }
    private async Task<string> Capture(string name)
    {
        string path = Path.Combine(outputDirectory, name);
        ScreenCapture.CaptureScreenshot(path);
        await WaitFor(() => File.Exists(path) && new FileInfo(path).Length > 0, 20, "game_view_screenshot_not_written");
        return name;
    }
    private void Protect(string relative)
    { protectedHashes[relative] = Hash(File.ReadAllBytes(Path.Combine(Directory.GetParent(Application.dataPath).FullName, relative))); }
    private bool ProtectedUnchanged(string relative)
    {
        string path = Path.Combine(Directory.GetParent(Application.dataPath).FullName, relative);
        return protectedHashes.ContainsKey(relative) && File.Exists(path) && protectedHashes[relative] == Hash(File.ReadAllBytes(path));
    }
    private static string Hash(byte[] data)
    { using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(data)).Replace("-", "").ToLowerInvariant(); }
    private void Check(bool condition, string code)
    { report.assertions++; if (!condition) throw new CheckFailure(code); }
    private void CountRuntimeError(string condition, string trace, LogType type)
    { if (type == LogType.Error || type == LogType.Exception || type == LogType.Assert) report.runtime_error_count++; }
    private void ProductionApiFailed(ApiFailure failure)
    {
        if (expectedAuth401Phase != null && failure.StatusCode == 401)
        {
            report.expected_auth_401_observations++;
            if (current != null) current.auth_expected_401_observations++;
            return;
        }
        productionFailure = failure;
    }
    private void OnDestroy()
    {
        if (!finished) lifetime.Cancel(); Application.logMessageReceived -= CountRuntimeError;
        if (connection != null && connection.Api != null) connection.Api.Failed -= ProductionApiFailed;
        token = null;
    }
}
#endif
