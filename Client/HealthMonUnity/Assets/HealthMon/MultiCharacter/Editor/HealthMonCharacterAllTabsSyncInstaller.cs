#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class HealthMonCharacterAllTabsSyncInstaller
{
    private const string Root = "Assets/HealthMon/MultiCharacter";

    [MenuItem("Tools/HealthMon/Characters/7. 모든 탭 캐릭터 동기화 설치 (씬 백업)")]
    public static void Install()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode)
        {
            EditorUtility.DisplayDialog("헬스몬", "Play 모드를 종료하고 설치해 주세요.", "확인");
            return;
        }

        var roster = UnityEngine.Object.FindFirstObjectByType<HealthMonCharacterRosterController>(FindObjectsInactive.Include);
        if (roster == null || roster.catalog == null)
        {
            EditorUtility.DisplayDialog("헬스몬", "캐릭터 슬롯을 먼저 설치하고 MainARScene을 열어 주세요.\nHM_MultiCharacterSystem과 카탈로그가 필요합니다.", "확인");
            return;
        }

        try
        {
            Backup();
            var sync = roster.GetComponent<HealthMonCharacterAllTabsSync>();
            if (sync == null) sync = Undo.AddComponent<HealthMonCharacterAllTabsSync>(roster.gameObject);
            sync.roster = roster;
            sync.arPlacement = UnityEngine.Object.FindFirstObjectByType<ARPlacementManager>(FindObjectsInactive.Include);
            var previewRoot = Find("PetPreviewRoot");
            if (previewRoot != null)
            {
                var rig = previewRoot.GetComponentInChildren<HealthMon3DJewelryRig>(true);
                if (rig != null) sync.customizationPetRoot = rig.transform;
                else
                {
                    for (int i = 0; i < previewRoot.childCount; i++)
                    {
                        var child = previewRoot.GetChild(i);
                        if (child.GetComponentsInChildren<Renderer>(true).Length == 0) continue;
                        sync.customizationPetRoot = child;
                        break;
                    }
                }
            }
            var evolution = Find("EvolutionPetPreviewRig");
            sync.evolutionPetRoot = evolution != null ? evolution.Find("PetVisualCopy_AnimationOnly") : null;
            sync.originalHomePet = roster.originalHomePet != null ? roster.originalHomePet.transform : null;
            EditorUtility.SetDirty(sync);
            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            EditorSceneManager.SaveOpenScenes();
            Selection.activeObject = sync.gameObject;

            string details = "AR 대화/AR 배치: " + (sync.arPlacement != null ? "연결" : "없음") + "\n" +
                             "꾸미기 3D 프리뷰: " + (sync.customizationPetRoot != null ? "연결" : "없음") + "\n" +
                             "진화 3D 구체: " + (sync.evolutionPetRoot != null ? "연결" : "없음") + "\n" +
                             "홈 3D 캐릭터: " + (sync.originalHomePet != null ? "기존 슬롯 시스템 유지" : "기존 슬롯 Inspector 확인 필요");
            Debug.Log("[HealthMon All Tabs] " + details, sync);
            EditorUtility.DisplayDialog("모든 탭 캐릭터 동기화 설치 완료", details +
                "\n\n캐릭터 전환 후 각 패널을 열어 확인해 주세요.\n서버 권한 모드에서는 기존 서버 모델을 덮어쓰지 않습니다.", "확인");
        }
        catch (Exception e)
        {
            Debug.LogException(e);
            EditorUtility.DisplayDialog("설치 실패", e.Message + "\n기존 씬 백업을 확인하세요.", "확인");
        }
    }

    [MenuItem("Tools/HealthMon/Characters/8. 모든 탭 동기화 진단")]
    public static void Diagnose()
    {
        var roster = UnityEngine.Object.FindFirstObjectByType<HealthMonCharacterRosterController>(FindObjectsInactive.Include);
        var sync = roster != null ? roster.GetComponent<HealthMonCharacterAllTabsSync>() : null;
        string s = "캐릭터 슬롯: " + (roster != null ? "확인" : "없음") + "\n" +
                   "동기화 컴포넌트: " + (sync != null ? "확인" : "없음") + "\n" +
                   "AR 펫: " + (sync != null && sync.arPlacement != null ? "연결" : "미연결") + "\n" +
                   "꾸미기 3D: " + (sync != null && sync.customizationPetRoot != null ? "연결" : "미연결") + "\n" +
                   "진화 3D: " + (sync != null && sync.evolutionPetRoot != null ? "연결" : "미연결");
        Debug.Log("[HealthMon All Tabs] " + s);
        EditorUtility.DisplayDialog("헬스몬 캐릭터 동기화 진단", s, "확인");
    }

    [MenuItem("Tools/HealthMon/Characters/9. 모든 탭 동기화 제거 (다른 기능 유지)")]
    public static void Uninstall()
    {
        if (EditorApplication.isPlayingOrWillChangePlaymode) return;
        var roster = UnityEngine.Object.FindFirstObjectByType<HealthMonCharacterRosterController>(FindObjectsInactive.Include);
        if (roster == null) return;
        var sync = roster.GetComponent<HealthMonCharacterAllTabsSync>();
        if (sync == null) return;
        Backup();
        Undo.DestroyObjectImmediate(sync);
        EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
        EditorSceneManager.SaveOpenScenes();
        EditorUtility.DisplayDialog("완료", "동기화 컴포넌트만 제거했습니다. 캐릭터 슬롯·구매·육성 데이터는 유지됩니다.", "확인");
    }

    private static Transform Find(string name)
    {
        foreach (var t in UnityEngine.Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            if (t.name == name && t.gameObject.scene.IsValid()) return t;
        return null;
    }

    private static void Backup()
    {
        Scene scene = SceneManager.GetActiveScene();
        if (!scene.IsValid() || string.IsNullOrEmpty(scene.path))
            throw new InvalidOperationException("현재 MainARScene을 Ctrl+S로 먼저 저장해 주세요.");
        EditorSceneManager.SaveScene(scene);
        string folder = Root + "/Backups";
        if (!AssetDatabase.IsValidFolder(folder)) AssetDatabase.CreateFolder(Root, "Backups");
        string file = folder + "/" + Path.GetFileNameWithoutExtension(scene.path) +
                      "_BeforeAllTabsSync_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".unity";
        if (!AssetDatabase.CopyAsset(scene.path, file))
            throw new InvalidOperationException("씬 백업에 실패했기 때문에 설치를 중단했습니다.");
        AssetDatabase.Refresh();
        Debug.Log("[HealthMon All Tabs] Scene backup: " + file);
    }
}
#endif
