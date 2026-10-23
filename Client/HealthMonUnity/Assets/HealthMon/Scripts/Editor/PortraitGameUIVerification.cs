#if UNITY_EDITOR
using System;
using System.IO;
using System.Reflection;
using System.Threading.Tasks;
using GLTFast;
using TMPro;
using UnityEditor;
using UnityEngine;
using UnityEngine.UI;

// Captures the actual Unity scene and saved rigged GLB without contacting the server.
public static class PortraitGameUIVerification
{
    public static async void Capture()
    {
        try
        {
            PortraitGameUIEditor.VerifyGeometry();
            var theme = UnityEngine.Object.FindAnyObjectByType<PortraitGameUI>();
            var canvas = theme.GetComponent<Canvas>();
            var entry = theme.GetComponent<PortraitCharacterMenu>() ?? theme.gameObject.AddComponent<PortraitCharacterMenu>();
            entry.Configure(theme, UnityEngine.Object.FindAnyObjectByType<UIManager>());
            var camera = Camera.main;
            if (camera == null) throw new InvalidOperationException("Main scene camera missing.");
            foreach (var renderer in UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include)) renderer.enabled = false;
            foreach (var other in UnityEngine.Object.FindObjectsByType<Camera>()) if (other != camera) other.enabled = false;
            var output = Path.GetFullPath(Path.Combine(Application.dataPath, "../../../.runtime/ui-verification"));
            Directory.CreateDirectory(output);
            var target = new RenderTexture(540, 1200, 24, RenderTextureFormat.ARGB32); target.Create();
            camera.targetTexture = target; camera.aspect = 540f / 1200; camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = new Color(.08f,.18f,.25f);
            canvas.renderMode = RenderMode.WorldSpace; canvas.worldCamera = camera;
            var root = (RectTransform)canvas.transform;
            root.sizeDelta = new Vector2(1080, 2400);
            float plane = .35f;
            root.SetPositionAndRotation(camera.transform.position + camera.transform.forward * plane, camera.transform.rotation);
            root.localScale = Vector3.one * (2 * plane * Mathf.Tan(camera.fieldOfView * Mathf.Deg2Rad * .5f) / 2400);
            theme.ApplyNow();
            var path = Environment.GetEnvironmentVariable("HEALTHMON_UI_MODEL_FIXTURE");
            GameObject model = null;
            Vector3 modelOffset = Vector3.zero;
            GltfImport importer = null;
            if (!string.IsNullOrEmpty(path) && File.Exists(path))
            {
                importer = new GltfImport(deferAgent: new UninterruptedDeferAgent());
                if (!await importer.Load(File.ReadAllBytes(path), new Uri(path))) throw new InvalidOperationException("Saved model fixture import failed.");
                model = new GameObject("Saved model visual verification");
                if (!await importer.InstantiateMainSceneAsync(model.transform)) throw new InvalidOperationException("Saved model fixture instantiation failed.");
                var renderers = model.GetComponentsInChildren<Renderer>(true);
                foreach (Transform visual in model.transform) visual.localRotation = Quaternion.Euler(0, 180, 0) * visual.localRotation;
                var bounds = ActualBounds(renderers);
                float scale = .6f / bounds.size.y;
                model.transform.localScale = Vector3.one * scale;
                // The fixture is placed like the existing camera-following pet, not a 2D replacement.
                model.transform.position -= new Vector3(bounds.center.x, bounds.min.y, bounds.center.z) * scale;
                modelOffset = model.transform.position;
            }
            string[] panels = { "HomePanel", "StatusPanel", "DialoguePanel", "FoodScanPanel", "QuestPanel", "RewardPanel", "CollectionPanel", "CustomizationPanel", "WearablePanel", "AdminPanel", "PetARPanel" };
            string[] shots = { "HomePanel", "DialoguePanel", "FoodScanPanel", "QuestPanel", "AdminPanel", "CollectionPanel", "StatusPanel", "WearablePanel", "PortraitStartPanel", "PortraitCharacterPanel" };
            foreach (int logicalHeight in new[] { 2400, 1920 })
            {
            target.Release(); target.height = logicalHeight / 2; target.Create(); camera.aspect = 1080f / logicalHeight;
            root.sizeDelta = new Vector2(1080, logicalHeight);
            root.localScale = Vector3.one * (2 * plane * Mathf.Tan(camera.fieldOfView * Mathf.Deg2Rad * .5f) / logicalHeight);
            foreach (string shot in shots)
            {
                entry.HideForVerification();
                foreach (string panel in panels) { var obj = canvas.transform.Find(panel); if (obj != null) obj.gameObject.SetActive(panel == shot); }
                if (shot == "PortraitStartPanel") entry.OpenStart();
                if (shot == "PortraitCharacterPanel") entry.OpenSelection(false);
                if (shot == "WearablePanel") UnityEngine.Object.FindAnyObjectByType<LiveWorkoutPageUI>(FindObjectsInactive.Include)?.ShowWaitingState();
                if (shot == "FoodScanPanel")
                {
                    foreach (string view in new[] { "CaptureView", "CandidateView", "ResultView" }) canvas.transform.Find("FoodScanPanel/" + view).gameObject.SetActive(view == "ResultView");
                }
                if (shot == "DialoguePanel")
                {
                    var dialogue = UnityEngine.Object.FindAnyObjectByType<DialoguePrototype>(FindObjectsInactive.Include);
                    typeof(DialoguePrototype).GetField("sendButton", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(dialogue, canvas.transform.Find("DialoguePanel/InputArea/SendButton").GetComponent<Button>());
                    typeof(DialoguePrototype).GetMethod("ConfigureRuntimeLayout", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(dialogue, null);
                }
                theme.ApplyNow();
                if (model != null)
                {
                    model.SetActive(shot == "HomePanel" || shot == "DialoguePanel" || shot == "PortraitStartPanel" || shot == "PortraitCharacterPanel");
                    if (PortraitGameUI.TryPresentationPose(camera, out var pose))
                    { model.transform.SetPositionAndRotation(pose.position + pose.rotation * modelOffset, pose.rotation); }
                }
                theme.PreviewEnvironment(camera);
                Canvas.ForceUpdateCanvases();
                foreach (var text in canvas.GetComponentsInChildren<TMP_Text>()) text.ForceMeshUpdate();
                await Task.Yield();
                camera.Render();
                var previous = RenderTexture.active; RenderTexture.active = target;
                var image = new Texture2D(target.width, target.height, TextureFormat.RGB24, false);
                image.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0); image.Apply();
                File.WriteAllBytes(Path.Combine(output, "native-" + shot + (logicalHeight == 1920 ? "-1920" : "") + ".png"), image.EncodeToPNG());
                UnityEngine.Object.DestroyImmediate(image); RenderTexture.active = previous;
                Debug.Log("HEALTHMON_PORTRAIT_CAPTURE " + shot + " height=" + logicalHeight);
            }
            }
            var continueButton = canvas.transform.Find("PortraitStartPanel/Continue").GetComponent<Button>();
            entry.Configure(theme, UnityEngine.Object.FindAnyObjectByType<UIManager>()); entry.OpenStart(); continueButton.onClick.Invoke();
            if (entry.IsOpen) throw new InvalidOperationException("Start menu callback did not enter the game.");
            Debug.Log("HEALTHMON_PORTRAIT_NATIVE_PASS screens=" + (shots.Length * 2) + " saved_rigged_model=" + (model != null));
            if (model != null) UnityEngine.Object.DestroyImmediate(model); importer?.Dispose(); camera.targetTexture = null; target.Release(); UnityEngine.Object.DestroyImmediate(target);
            EditorApplication.Exit(0);
        }
        catch (Exception error) { Debug.LogException(error); EditorApplication.Exit(1); }
    }
    private static Bounds ActualBounds(Renderer[] renderers)
    {
        bool first = true; Bounds result = default;
        foreach (var renderer in renderers)
        {
            Mesh baked = null; Bounds local;
            if (renderer is SkinnedMeshRenderer skin) { baked = new Mesh(); skin.BakeMesh(baked); local = baked.bounds; }
            else { var filter = renderer.GetComponent<MeshFilter>(); if (filter == null || filter.sharedMesh == null) continue; local = filter.sharedMesh.bounds; }
            for (int x = -1; x <= 1; x += 2) for (int y = -1; y <= 1; y += 2) for (int z = -1; z <= 1; z += 2)
            { var point = renderer.transform.TransformPoint(local.center + Vector3.Scale(local.extents, new Vector3(x, y, z))); if (first) { result = new Bounds(point, Vector3.zero); first = false; } else result.Encapsulate(point); }
            if (baked != null) UnityEngine.Object.DestroyImmediate(baked);
        }
        return result;
    }
}
#endif
