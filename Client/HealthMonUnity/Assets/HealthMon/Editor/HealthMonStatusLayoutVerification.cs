using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using Healthmon.Beta;
using Healthmon.Common;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TextCore.LowLevel;
using UnityEngine.UI;

/// <summary>Offscreen production UI verification. No Play mode, servers, or account writes.</summary>
public static class HealthMonStatusLayoutVerification
{
    [Serializable] private sealed class Report
    {
        public bool passed;
        public string error;
        public string data = "Synthetic pet fixture rendered by production Unity status components; no gameplay/server test.";
        public List<string> checks = new List<string>();
        public List<string> screenshots = new List<string>();
    }
    private static Report report;
    private static void Check(bool valid, string description)
    {
        if (!valid) throw new Exception(description);
        report.checks.Add(description);
    }
    private static PetState Fixture() => new PetState {
        pet_id = "status-layout-fixture", rule_version = CommonServerContract.RuleVersion,
        asset_status = "none", level = 8, current_exp = 85, required_exp = 220, total_exp = 1285,
        upper_body = 72, lower_body = 64, nutrition = 68, energy_balance = 8,
        activity = 74, affinity = 80, initiative = 60, settings = new PetStateSettings { name = "헬스몬" }
    };

    public static void Run()
    {
        if (!Application.isBatchMode) throw new Exception("Run with -batchmode; this verifier must not open a game window.");
        string output = Environment.GetEnvironmentVariable("HEALTHMON_STATUS_OUTPUT");
        if (string.IsNullOrWhiteSpace(output)) throw new Exception("HEALTHMON_STATUS_OUTPUT is required.");
        Directory.CreateDirectory(output);
        report = new Report();
        TMP_FontAsset font = null;
        try
        {
            VerifyProjection();
            var source = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>("Assets/HealthMon/MultiCharacter/Fonts/HealthMon_Roster_KoreanDynamic.asset");
            Check(source != null && source.sourceFontFile != null, "Production Korean font is available");
            // Match the production dynamic font without persisting test glyphs into the shared asset.
            font = TMP_FontAsset.CreateFontAsset(source.sourceFontFile, 90, 9, GlyphRenderMode.SDFAA, 1024, 1024, AtlasPopulationMode.Dynamic, true);
            font.hideFlags = HideFlags.HideAndDontSave;
            font.material.hideFlags = HideFlags.HideAndDontSave;
            foreach (var atlas in font.atlasTextures) atlas.hideFlags = HideFlags.HideAndDontSave;
            Render(output, font, 720, 1280, new Rect(0, 0, 1, 1), "status-16x9");
            Render(output, font, 720, 1440, new Rect(0, 0, 1, 1), "status-18x9");
            Render(output, font, 720, 1600, new Rect(0, 48f / 1600, 1, 1 - 112f / 1600), "status-20x9-safe-area");
            Render(output, font, 360, 640, new Rect(0, 0, 1, 1), "status-small");
            report.passed = true;
        }
        catch (Exception e) { report.error = e.ToString(); Debug.LogError(e); }
        finally
        {
            if (font != null)
            {
                foreach (var atlas in font.atlasTextures) if (atlas != null) UnityEngine.Object.DestroyImmediate(atlas);
                if (font.material != null) UnityEngine.Object.DestroyImmediate(font.material);
                UnityEngine.Object.DestroyImmediate(font);
            }
            File.WriteAllText(Path.Combine(output, "status-layout-report.json"), JsonUtility.ToJson(report, true));
            EditorApplication.Exit(report.passed ? 0 : 1);
        }
    }

    private static void VerifyProjection()
    {
        var state = Fixture();
        var s = HealthMonStatusSnapshot.FromServer(state, state.pet_id, true);
        Check(s != null && s.Name == state.settings.name, "Current pet identity and nickname");
        Check(s.Axes.SequenceEqual(new float[] {72, 80, 74, 68, 60, 64}), "Radar clockwise axis mapping");
        Check(s.Combat.StatusText == PetCombatStats.FromState(state).StatusText, "Status uses the existing battle calculation unchanged");
        Check(Math.Abs(s.ExperienceFraction - 85f / 220) < .0001f, "Experience fraction from real fields");
        Check(HealthMonStatusSnapshot.FromServer(state, "other-pet", true) == null, "Never display another pet's cached state");
        Check(HealthMonStatusSnapshot.FromServer(state, state.pet_id, false).IsCached, "Disconnected valid snapshot is marked cached");
        state.nutrition = float.NaN;
        Check(HealthMonStatusSnapshot.FromServer(state, state.pet_id, true) == null, "Reject invalid server scores");
        state = Fixture();
        state.level = 10; state.evolution_target_stage = 1;
        Check(HealthMonStatusSnapshot.FromServer(state, state.pet_id, true).Evolution.Contains("진화 가능"), "Unlocked but unpublished evolution is shown as available");
        state.published_model_stage = 1;
        Check(HealthMonStatusSnapshot.FromServer(state, state.pet_id, true).Evolution.Contains("Lv.20"), "Published stage uses the next evolution milestone");
        state.level = 30; state.published_model_stage = state.evolution_target_stage = 3;
        s = HealthMonStatusSnapshot.FromServer(state, state.pet_id, true);
        Check(s.ExperienceFraction == 1 && s.Evolution == "최종 진화 완료", "Maximum level and final published evolution");
        Check(HealthMonStatusSnapshot.EnergyFraction(-100) == 0 && HealthMonStatusSnapshot.EnergyFraction(0) == .5f && HealthMonStatusSnapshot.EnergyFraction(100) == 1, "Bipolar energy mapping");
        Check(HealthMonStatusSnapshot.Unit(float.NaN) == 0 && HealthMonStatusSnapshot.Unit(float.PositiveInfinity) == 0, "Invalid graph values cannot generate invalid geometry");
        Check(Vector2.Distance(HealthMonRadarGraphic.AxisPoint(0, 100), new Vector2(0, 100)) < .001f && HealthMonRadarGraphic.AxisPoint(1, 100).x > 0, "Radar starts at top and proceeds clockwise");
    }

    private static void Render(string output, TMP_FontAsset font, int width, int height, Rect safe, string name)
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        RenderTexture target = null;
        Texture2D capture = null;
        try
        {
            Check(font != null, name + " dynamic font survives isolated scene creation");
            var root = new GameObject("StatusVerificationCanvas", typeof(RectTransform), typeof(Canvas));
            SceneManager.MoveGameObjectToScene(root, scene);
            var canvas = root.GetComponent<Canvas>(); canvas.renderMode = RenderMode.WorldSpace;
            ((RectTransform)root.transform).sizeDelta = new Vector2(width, height);
            var cameraObject = new GameObject("StatusVerificationCamera", typeof(Camera));
            SceneManager.MoveGameObjectToScene(cameraObject, scene);
            var camera = cameraObject.GetComponent<Camera>();
            camera.enabled = false;
            camera.cullingMask = 1 << 31;
            camera.transform.position = new Vector3(0, 0, -10);
            camera.orthographic = true; camera.orthographicSize = height / 2f; camera.aspect = (float)width / height;
            camera.clearFlags = CameraClearFlags.SolidColor; camera.backgroundColor = Color.black;
            camera.nearClipPlane = .1f; camera.farClipPlane = 100;
            canvas.worldCamera = camera;
            target = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32); target.Create(); camera.targetTexture = target;
            var panel = new GameObject("StatusPanel", typeof(RectTransform)); panel.transform.SetParent(root.transform, false);
            var fontReference = new GameObject("ExistingSceneFont", typeof(RectTransform), typeof(TextMeshProUGUI));
            fontReference.transform.SetParent(root.transform, false);
            fontReference.GetComponent<TMP_Text>().font = font;
            fontReference.SetActive(false);
            var view = panel.AddComponent<HealthMonStatusView>(); int closed = 0;
            var oldFont = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>("Assets/HealthMon/Fonts/MaplestoryFont_TTF/Maplestory Bold SDF.asset");
            view.Configure(oldFont, () => closed++);
            view.Present(HealthMonStatusSnapshot.FromServer(Fixture(), "status-layout-fixture", true));
            foreach (var child in root.GetComponentsInChildren<Transform>(true)) child.gameObject.layer = 31;
            typeof(HealthMonStatusView).GetMethod("ApplyViewport", BindingFlags.Instance | BindingFlags.NonPublic)
                .Invoke(view, new object[] {new Vector2(width, height), safe});
            Canvas.ForceUpdateCanvases();
            foreach (var text in panel.GetComponentsInChildren<TMP_Text>()) text.ForceMeshUpdate();
            Canvas.ForceUpdateCanvases();
            var content = panel.transform.Find("SafeArea/StatusContent");
            var lifestyle = content.Find("Lifestyle");
            var worldSafe = new Rect((safe.x - .5f) * width, (safe.y - .5f) * height, safe.width * width, safe.height * height);
            foreach (var text in panel.GetComponentsInChildren<TMP_Text>())
            {
                if (string.IsNullOrEmpty(text.text)) continue;
                Check(text.font.HasCharacters(text.text, out uint[] missing, true, true), name + " font glyphs: " + text.transform.parent.name + "/" + text.name);
                var bounds = Bounds(text.rectTransform);
                Check(Contains(worldSafe, bounds), name + " safe text bounds: " + text.transform.parent.name + "/" + text.name);
                Check(!text.isTextOverflowing, name + " text fits: " + text.transform.parent.name + "/" + text.name);
            }
            var upper = Bounds((RectTransform)lifestyle.Find("Axis0"));
            var title = Bounds((RectTransform)lifestyle.Find("SectionTitle"));
            var lower = Bounds((RectTransform)lifestyle.Find("Axis3"));
            var energy = Bounds((RectTransform)lifestyle.Find("Energy"));
            Check(!upper.Overlaps(title) && !lower.Overlaps(energy), name + " radar captions clear section title and energy gauge");
            Check(!Bounds((RectTransform)content.Find("Combat")).Overlaps(Bounds((RectTransform)content.Find("Evolution"))), name + " combat and evolution do not overlap");
            foreach (string button in new[] {"Back", "Confirm"}) content.Find(button).GetComponent<Button>().onClick.Invoke();
            Check(closed == 2, name + " both close buttons are wired");
            foreach (float energyValue in new[] {-100f, 0, 100f})
            {
                var s = HealthMonStatusSnapshot.FromServer(Fixture(), "status-layout-fixture", true); s.Energy = energyValue; view.Present(s);
                Canvas.ForceUpdateCanvases();
                var marker = lifestyle.Find("Energy/EnergyTrack/Inner/EnergyMarker");
                var track = lifestyle.Find("Energy/EnergyTrack");
                var b = Bounds((RectTransform)marker); var t = Bounds((RectTransform)track);
                Check(b.xMin >= t.xMin && b.xMax <= t.xMax, name + " energy endpoint marker fits: " + energyValue);
            }
            view.Present(null);
            Check(view.AxisText(0) == "—" && view.EnergyText == "—" && !lifestyle.Find("Energy/EnergyTrack/Inner/EnergyMarker").gameObject.activeSelf, name + " no fabricated values while loading");
            view.Present(HealthMonStatusSnapshot.FromServer(Fixture(), "status-layout-fixture", true));
            Canvas.ForceUpdateCanvases();
            camera.Render();
            var previous = RenderTexture.active; RenderTexture.active = target;
            try { capture = new Texture2D(width, height, TextureFormat.RGB24, false); capture.ReadPixels(new Rect(0, 0, width, height), 0, 0); capture.Apply(); }
            finally { RenderTexture.active = previous; }
            var pixels = capture.GetPixels32();
            Check(pixels.Count(p => p.b > 30 && p.b > p.r) > pixels.Length / 4, name + " rendered blue UI pixels");
            Check(pixels.Count(p => p.r > 180 && p.g > 100 && p.b < 140) > pixels.Length / 100, name + " rendered gold controls");
            File.WriteAllBytes(Path.Combine(output, name + ".png"), capture.EncodeToPNG());
            report.screenshots.Add(name + ".png");
        }
        finally
        {
            foreach (var root in scene.GetRootGameObjects()) UnityEngine.Object.DestroyImmediate(root);
            if (capture != null) UnityEngine.Object.DestroyImmediate(capture);
            if (target != null) { target.Release(); UnityEngine.Object.DestroyImmediate(target); }
        }
    }
    private static Rect Bounds(RectTransform transform)
    {
        var corners = new Vector3[4]; transform.GetWorldCorners(corners);
        return Rect.MinMaxRect(corners.Min(x => x.x), corners.Min(x => x.y), corners.Max(x => x.x), corners.Max(x => x.y));
    }
    private static bool Contains(Rect outer, Rect inner) => inner.xMin >= outer.xMin - 1 && inner.yMin >= outer.yMin - 1 && inner.xMax <= outer.xMax + 1 && inner.yMax <= outer.yMax + 1;
}
