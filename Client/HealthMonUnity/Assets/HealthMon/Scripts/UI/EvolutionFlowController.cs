using Healthmon.Common;
using Healthmon.Evolution;
using HealthMon.Evolution;
using UnityEngine;

// Bridges the real server job to the existing scene presentation. Success requires
// both the home visual and the result preview to have applied the published revision.
[DisallowMultipleComponent]
public sealed class EvolutionFlowController : MonoBehaviour
{
    public ArEvolutionModel HomeModel { get; private set; }
    public ArEvolutionModel PreviewModel { get; private set; }
    public bool IsApplied => EvolutionClient.Instance?.Current != null &&
        HomeModel != null && PreviewModel != null &&
        HomeModel.DisplayedRevision == EvolutionClient.Instance.Current.revision &&
        PreviewModel.DisplayedRevision == EvolutionClient.Instance.Current.revision;
    public bool NeedsModelRetry => !IsApplied &&
        (!string.IsNullOrEmpty(HomeModel?.LastError) || !string.IsNullOrEmpty(PreviewModel?.LastError));

    private UIManager manager;
    private EvolutionUIController screen;
    private Camera previewCamera;
    private Vector3 originalPreviewPosition;
    private float originalPreviewSize;
    private string framedRevision;
    private string scope, trackedRequest, dismissedRequest;
    private int targetStage;
    private bool tracking, showingError;

    public void Configure(UIManager owner)
    {
        manager = owner;
        screen = FindAnyObjectByType<EvolutionUIController>(FindObjectsInactive.Include);
        if (screen != null) screen.onEvolutionClosed.AddListener(Closed);
        var roster = FindAnyObjectByType<HealthMonCharacterRosterController>(FindObjectsInactive.Include);
        if (roster != null && roster.originalHomePet != null)
            HomeModel = Attach(roster.originalHomePet);
        var rig = GameObject.Find("EvolutionPetPreviewRig");
        var preview = rig != null ? rig.transform.Find("PetVisualCopy_AnimationOnly") : null;
        if (rig != null) previewCamera = rig.GetComponentInChildren<Camera>(true);
        if (previewCamera != null)
        { originalPreviewPosition = previewCamera.transform.position; originalPreviewSize = previewCamera.orthographicSize; }
        if (preview != null)
        {
            // This editor clone includes all accessory variants. The evolution preview
            // shows the body; copied equipment must not float around the old/new model.
            foreach (var child in preview.GetComponentsInChildren<Transform>(true))
                if (child.name.StartsWith("Jewelry_", System.StringComparison.OrdinalIgnoreCase) ||
                    child.name.IndexOf("AccessoryAnchor", System.StringComparison.OrdinalIgnoreCase) >= 0)
                    child.gameObject.SetActive(false);
            PreviewModel = Attach(preview.gameObject);
        }
    }

    private static ArEvolutionModel Attach(GameObject root)
    {
        var model = ArEvolutionModel.Attach(root);
        model.ConfigurePresentation();
        return model;
    }

    public void Begin()
    {
        var client = EvolutionClient.Instance;
        var connection = CommonServerConnection.Instance;
        if (client == null || connection == null || !connection.IsConnected || screen == null) return;
        if (HomeModel == null || PreviewModel == null)
        { screen.ShowEvolutionError("진화 화면 준비 실패 · 홈에서 다시 시도"); return; }
        // A local download/import retry must never submit another generation job.
        if (NeedsModelRetry && string.IsNullOrEmpty(client.ActiveRequestId))
        {
            Open(null, client.Current.stage);
            HomeModel.Changed(client.Current);
            PreviewModel.Changed(client.Current);
            return;
        }
        if (string.IsNullOrEmpty(client.ActiveRequestId) || client.HasTerminalError)
            client.RequestCommonEvolution();
        if (!string.IsNullOrEmpty(client.ActiveRequestId))
            Open(client.ActiveRequestId, connection.LatestState.evolution_target_stage);
    }

    private void Open(string request, int stage)
    {
        trackedRequest = request; targetStage = stage; dismissedRequest = null;
        tracking = true; showingError = false;
        manager.ShowHome();
        screen.StartEvolution();
    }

    private void Update()
    {
        var connection = CommonServerConnection.Instance;
        var client = EvolutionClient.Instance;
        if (screen == null || client == null || connection == null) return;
        FramePreview();
        if (!connection.IsConnected || connection.LatestState == null)
        {
            if (tracking && !showingError) screen.SetProgress("연결 복구 중 · 진화 기록 유지");
            return;
        }
        string identity = connection.ServerInstanceId + "/" + connection.OwnerId + "/" + connection.Api.PetId;
        if (scope != identity)
        {
            scope = identity; tracking = false; trackedRequest = dismissedRequest = null;
            if (screen.evolutionOverlay.activeSelf) screen.CloseEvolution();
        }
        if (!tracking && !string.IsNullOrEmpty(client.ActiveRequestId) && client.ActiveRequestId != dismissedRequest)
            Open(client.ActiveRequestId, connection.LatestState.evolution_target_stage);
        if (!tracking) return;
        if (client.HasTerminalError)
        { ShowError("진화 중단 · 홈에서 다시 도전"); return; }
        if (!string.IsNullOrEmpty(client.ActiveRequestId))
        {
            screen.SetProgress(client.IsReconnecting ? "연결 복구 중 · 진화 기록 유지" :
                client.Phase == "queued" || client.Phase == "waiting_for_gpu" ? "진화 에너지 충전 중" : "새로운 형태 각성 중");
            return;
        }
        if (client.Current == null || client.Current.stage < targetStage) return;
        if (NeedsModelRetry)
        { ShowError("진화 외형 불러오기 실패 · 홈에서 다시 시도"); return; }
        screen.MarkModelApplying();
        if (!IsApplied) return;
        tracking = false;
        screen.CompleteEvolution();
    }

    private void ShowError(string message)
    {
        if (showingError) return;
        showingError = true;
        screen.ShowEvolutionError(message);
    }

    private void FramePreview()
    {
        if (previewCamera == null || PreviewModel == null) return;
        if (string.IsNullOrEmpty(PreviewModel.DisplayedRevision))
        {
            if (framedRevision != null)
            {
                previewCamera.transform.position = originalPreviewPosition;
                previewCamera.orthographicSize = originalPreviewSize;
                framedRevision = null;
            }
            return;
        }
        if (PreviewModel.DisplayedRevision == framedRevision) return;
        bool found = false;
        Bounds bounds = default;
        foreach (var renderer in PreviewModel.GetComponentsInChildren<Renderer>(true))
        {
            if (!renderer.enabled || !renderer.gameObject.activeInHierarchy) continue;
            if (!found) { bounds = renderer.bounds; found = true; }
            else bounds.Encapsulate(renderer.bounds);
        }
        if (!found || bounds.size.y <= 0) return;
        previewCamera.orthographicSize = Mathf.Max(bounds.extents.y, bounds.extents.x / previewCamera.aspect) * 1.2f;
        previewCamera.transform.position = bounds.center - previewCamera.transform.forward * Mathf.Max(4f, bounds.extents.magnitude * 3f);
        framedRevision = PreviewModel.DisplayedRevision;
    }

    private void Closed()
    {
        dismissedRequest = trackedRequest;
        tracking = false;
        manager.ShowHome();
    }

    private void OnDestroy()
    {
        if (screen != null) screen.onEvolutionClosed.RemoveListener(Closed);
    }
}
