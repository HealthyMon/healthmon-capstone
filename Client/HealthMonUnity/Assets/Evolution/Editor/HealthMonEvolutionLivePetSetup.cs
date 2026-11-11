#if UNITY_EDITOR
using System;
using HealthMon.Evolution;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.Universal;

namespace HealthMon.Evolution.Editor
{
    /// <summary>
    /// Non-destructive bridge for v3 UI: selected 3D pet -> isolated visual preview
    /// -> dedicated Camera -> RenderTexture -> existing UI RawImages.
    /// </summary>
    public static class HealthMonEvolutionLivePetSetup
    {
        private const string PreviewLayerName = "HealthMonEvoPreview";
        private const string PreviewRigName = "EvolutionPetPreviewRig";

        [MenuItem("Tools/HealthMon/4. 선택한 3D 펫을 진화 구체에 연결")]
        public static void Setup()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                EditorUtility.DisplayDialog("HealthMon 진화", "Play 모드를 종료한 후 실행해 주세요.", "확인");
                return;
            }

            var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            GameObject source = Selection.activeGameObject;
            if (source == null || !source.scene.IsValid() || source.scene != scene)
            {
                EditorUtility.DisplayDialog("HealthMon 진화", "Hierarchy에서 실제 3D 슬라임 오브젝트를 먼저 선택하세요.\n(예: Character 하위의 슬라임 루트)", "확인");
                return;
            }
            if (source.transform.IsChildOf(FindMainCanvasTransform()) || source.name == PreviewRigName)
            {
                EditorUtility.DisplayDialog("HealthMon 진화", "UI가 아니라 실제 3D 펫 오브젝트를 선택해 주세요.", "확인");
                return;
            }

            Renderer[] renderers = source.GetComponentsInChildren<Renderer>(true);
            int meshCount = 0;
            foreach (var r in renderers)
            {
                if (r is MeshRenderer || r is SkinnedMeshRenderer) meshCount++;
            }
            if (meshCount == 0)
            {
                EditorUtility.DisplayDialog("HealthMon 진화",
                    "선택한 오브젝트에 3D MeshRenderer / SkinnedMeshRenderer가 없어요.\n하위에 실제 슬라임 메쉬가 있는 루트를 선택해 주세요.", "확인");
                return;
            }
            EvolutionUIController controller = UnityEngine.Object.FindFirstObjectByType<EvolutionUIController>(FindObjectsInactive.Include);
            if (controller == null || controller.evolutionOverlay == null)
            {
                EditorUtility.DisplayDialog("HealthMon 진화", "v3 진화 UI가 없습니다. 먼저 Tools > HealthMon > 3번 메뉴로 UI를 생성해 주세요.", "확인");
                return;
            }

            if (meshCount > 40 && !EditorUtility.DisplayDialog("많은 메쉬가 선택됨",
                $"'{source.name}'에 3D 메쉬가 {meshCount}개 있습니다.\n펫 이외의 배경까지 선택하지 않았는지 확인해 주세요.", "진행", "취소")) return;

            int layer = GetOrCreatePreviewLayer();
            if (layer < 0)
            {
                EditorUtility.DisplayDialog("HealthMon 진화",
                    "사용 가능한 사용자 Layer(8~31)가 없습니다.\n빈 레이어 하나를 확보한 뒤 다시 실행해 주세요.", "확인");
                return;
            }

            GameObject oldRig = GameObject.Find(PreviewRigName);
            if (oldRig != null && !EditorUtility.DisplayDialog("기존 진화용 펫 프리뷰 교체",
                "기존 EvolutionPetPreviewRig만 제거하고 다시 만들까요?\n원본 3D 펫과 기존 UI, 다른 카메라는 변경하지 않습니다.", "교체", "취소")) return;

            int group = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Setup HealthMon 3D evolution pet preview");
            if (oldRig != null) Undo.DestroyObjectImmediate(oldRig);

            RenderTexture rt = GetOrCreateRenderTexture();
            if (rt == null) return;
            GameObject rig = new GameObject(PreviewRigName);
            rig.transform.position = new Vector3(2000, 2000, 2000);
            Undo.RegisterCreatedObjectUndo(rig, "Create evolution preview rig");

            // Clone only into the distant, preview-only stage. The source is NEVER moved or modified.
            GameObject visual = UnityEngine.Object.Instantiate(source);
            visual.name = "PetVisualCopy_AnimationOnly";
            visual.transform.SetParent(rig.transform, false);
            visual.transform.localPosition = Vector3.zero;
            visual.transform.localRotation = Quaternion.identity;
            visual.transform.localScale = source.transform.lossyScale;
            visual.SetActive(true);
            PrepareVisualClone(visual, layer);

            Bounds bounds = GetVisualBounds(visual);
            var cameraGo = new GameObject("EvolutionPetRenderCamera");
            cameraGo.transform.SetParent(rig.transform, false);
            Camera camera = cameraGo.AddComponent<Camera>();
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0, 0, 0, 0);  // transparent
            camera.cullingMask = 1 << layer;
            camera.orthographic = true;
            camera.orthographicSize = Mathf.Max(0.25f, bounds.extents.y * 1.40f, bounds.extents.x * 1.46f);
            camera.nearClipPlane = 0.01f;
            camera.farClipPlane = 200f;
            camera.allowHDR = false;
            camera.allowMSAA = true;
            camera.useOcclusionCulling = false;
            camera.targetTexture = rt;
            camera.depth = -99;
            camera.transform.position = bounds.center + new Vector3(0, bounds.extents.y * 0.05f,
                Mathf.Max(4f, bounds.extents.z * 4f + 3f));
            camera.transform.LookAt(bounds.center);

            // No post-processing, to help preserve an alpha=0 background in URP.
            UniversalAdditionalCameraData urp = camera.GetUniversalAdditionalCameraData();
            urp.renderType = CameraRenderType.Base;
            urp.renderPostProcessing = false;
            urp.requiresColorOption = CameraOverrideOption.Off;
            urp.requiresDepthOption = CameraOverrideOption.Off;

            GameObject lightGo = new GameObject("EvolutionPetFillLight");
            lightGo.transform.SetParent(rig.transform, false);
            Light light = lightGo.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 0.9f;
            light.color = new Color(0.78f, 1f, 0.96f, 1f);
            light.cullingMask = 1 << layer;
            light.shadows = LightShadows.None;
            light.transform.localRotation = Quaternion.Euler(35, -30, 0);

            EvolutionLivePetCameraGate gate = rig.AddComponent<EvolutionLivePetCameraGate>();
            gate.Configure(controller, camera);
            camera.enabled = false;

            Undo.RecordObject(controller, "Assign 3D evolution render texture");
            if (controller.petPreview3D != null) Undo.RecordObject(controller.petPreview3D, "Assign preview texture");
            if (controller.resultPreview3D != null) Undo.RecordObject(controller.resultPreview3D, "Assign result texture");
            controller.SetPetRenderTexture(rt);
            EditorUtility.SetDirty(controller);
            EditorSceneManager.MarkSceneDirty(scene);
            Undo.CollapseUndoOperations(group);

            Selection.activeGameObject = rig;
            EditorGUIUtility.PingObject(rig);
            EditorUtility.DisplayDialog("헬스몬 실제 3D 펫 연결 완료",
                $"'{source.name}'의 시각적 복제본을 진화 화면에 연결했습니다.\n\n" +
                "Play ▶ 진화 TEST 로 확인하세요.\n원본 펫과 HomeCamera / PetPreviewCamera는 변경하지 않았습니다.\n" +
                "만약 어두운 네모 배경이 보이면 Camera의 투명도 설정을 확인해 주세요.", "확인");
        }

        private static Transform FindMainCanvasTransform()
        {
            GameObject ui = GameObject.Find("UI");
            return ui != null ? ui.transform.Find("Canvas") : null;
        }

        private static void PrepareVisualClone(GameObject visual, int layer)
        {
            foreach (Transform t in visual.GetComponentsInChildren<Transform>(true))
            {
                t.gameObject.layer = layer;
                t.gameObject.tag = "Untagged"; // avoid collisions with gameplay FindWithTag calls
            }
            // Stop gameplay/network/quest/control scripts on the CLONE only.
            foreach (MonoBehaviour behaviour in visual.GetComponentsInChildren<MonoBehaviour>(true))
                behaviour.enabled = false;
            foreach (Collider collider in visual.GetComponentsInChildren<Collider>(true))
                collider.enabled = false;
            foreach (AudioSource audio in visual.GetComponentsInChildren<AudioSource>(true))
                audio.enabled = false;
            foreach (Rigidbody rb in visual.GetComponentsInChildren<Rigidbody>(true))
            {
                rb.isKinematic = true;
                rb.useGravity = false;
            }
            foreach (Animator animator in visual.GetComponentsInChildren<Animator>(true))
            {
                animator.applyRootMotion = false;
                animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            }
            foreach (SkinnedMeshRenderer skin in visual.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                skin.updateWhenOffscreen = true;
        }

        private static Bounds GetVisualBounds(GameObject visual)
        {
            Renderer[] renderers = visual.GetComponentsInChildren<Renderer>(true);
            Bounds combined = new Bounds(visual.transform.position, Vector3.one);
            bool found = false;
            foreach (Renderer r in renderers)
            {
                if (!(r is MeshRenderer || r is SkinnedMeshRenderer) || !r.enabled || !r.gameObject.activeInHierarchy) continue;
                if (!found) { combined = r.bounds; found = true; }
                else combined.Encapsulate(r.bounds);
            }
            if (!found)
            {
                // Fallback for atypical meshes while still retaining a usable camera frame.
                combined = new Bounds(visual.transform.position, Vector3.one);
            }
            return combined;
        }

        // Both locations have appeared in HealthMon projects:
        // Assets/Evolution and Assets/HealthMon/Evolution.
        // Resolve the folder that actually contains the v3 UI, then create all parents safely.
        private static RenderTexture GetOrCreateRenderTexture()
        {
            string evolutionRoot = AssetDatabase.IsValidFolder("Assets/Evolution")
                ? "Assets/Evolution"
                : "Assets/HealthMon/Evolution";
            string renderTextureFolder = evolutionRoot + "/RenderTextures";
            if (!EnsureFolderExists(renderTextureFolder))
            {
                EditorUtility.DisplayDialog("RenderTexture 폴더 생성 실패",
                    "다음 경로를 Unity Project 창에서 확인하세요:\n" + renderTextureFolder,
                    "확인");
                return null;
            }

            string renderTexturePath = renderTextureFolder + "/EvolutionPet_512.renderTexture";
            RenderTexture existing = AssetDatabase.LoadAssetAtPath<RenderTexture>(renderTexturePath);
            if (existing != null) return existing;

            // Detect an asset with the same name but an incompatible file type.
            UnityEngine.Object occupied = AssetDatabase.LoadMainAssetAtPath(renderTexturePath);
            if (occupied != null)
            {
                Debug.LogError("[HealthMon] RenderTexture 경로에 다른 Asset이 이미 있습니다: "
                    + renderTexturePath);
                return null;
            }

            var rt = new RenderTexture(512, 512, 24, RenderTextureFormat.ARGB32)
            {
                name = "EvolutionPet_512",
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
                antiAliasing = 1,
                useMipMap = false,
                autoGenerateMips = false
            };
            try
            {
                AssetDatabase.CreateAsset(rt, renderTexturePath);
                AssetDatabase.SaveAssets();
                RenderTexture saved = AssetDatabase.LoadAssetAtPath<RenderTexture>(renderTexturePath);
                if (saved == null)
                {
                    Debug.LogError("[HealthMon] RenderTexture 저장 후 확인 실패: " + renderTexturePath);
                    return null;
                }
                Debug.Log("[HealthMon] RenderTexture 생성 완료: " + renderTexturePath);
                return saved;
            }
            catch (Exception ex)
            {
                Debug.LogError("[HealthMon] RenderTexture 생성 실패: " + ex.Message);
                if (rt != null && !AssetDatabase.Contains(rt))
                    UnityEngine.Object.DestroyImmediate(rt);
                return null;
            }
        }

        private static bool EnsureFolderExists(string assetFolder)
        {
            string[] parts = assetFolder.Replace('\\', '/').Split('/');
            if (parts.Length < 1 || parts[0] != "Assets") return false;

            string current = "Assets";
            for (int i = 1; i < parts.Length; i++)
            {
                if (string.IsNullOrEmpty(parts[i])) return false;
                string child = current + "/" + parts[i];
                if (!AssetDatabase.IsValidFolder(child))
                {
                    string guid = AssetDatabase.CreateFolder(current, parts[i]);
                    if (string.IsNullOrEmpty(guid) || !AssetDatabase.IsValidFolder(child))
                    {
                        Debug.LogError("[HealthMon] 폴더 생성 실패: " + child);
                        return false;
                    }
                }
                current = child;
            }
            return true;
        }

        private static int GetOrCreatePreviewLayer()
        {
            int layer = LayerMask.NameToLayer(PreviewLayerName);
            if (layer >= 0) return layer;
            UnityEngine.Object tagManager = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/TagManager.asset")[0];
            SerializedObject so = new SerializedObject(tagManager);
            SerializedProperty layers = so.FindProperty("layers");
            for (int i = 31; i >= 8; --i)
            {
                SerializedProperty item = layers.GetArrayElementAtIndex(i);
                if (!string.IsNullOrEmpty(item.stringValue)) continue;
                item.stringValue = PreviewLayerName;
                so.ApplyModifiedProperties();
                return i;
            }
            return -1;
        }
    }
}
#endif
