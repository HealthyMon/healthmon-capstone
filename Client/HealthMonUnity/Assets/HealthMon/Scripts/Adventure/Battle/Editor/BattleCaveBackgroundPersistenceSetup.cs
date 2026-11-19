#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

/// <summary>
/// 기존 BattleRoot 아래에 생성된 3D 동굴 배경을 별도 루트로 이동한다.
/// 위치/회전/크기를 유지하고 전투 관련 오브젝트는 옮기지 않는다.
/// </summary>
public static class BattleCaveBackgroundPersistenceSetup
{
    [MenuItem("HealthMon/Adventure/Keep Battle Cave After Battle")]
    public static void Apply()
    {
        if (Application.isPlaying)
        {
            EditorUtility.DisplayDialog("전투 배경", "Play Mode를 종료한 뒤 실행해 주세요.", "확인");
            return;
        }

        var controller = Object.FindFirstObjectByType<BattleController>(FindObjectsInactive.Include);
        if (controller == null)
        {
            EditorUtility.DisplayDialog("전투 배경", "현재 씬에 BattleController가 없습니다.", "확인");
            return;
        }

        var serialized = new SerializedObject(controller);
        var battleRoot = serialized.FindProperty("battleRoot").objectReferenceValue as GameObject;
        if (battleRoot == null)
        {
            EditorUtility.DisplayDialog("전투 배경", "Battle Root 인스펙터 참조가 없습니다.", "확인");
            return;
        }

        var switcher = battleRoot.GetComponent<BattleEnvironmentSwitcher>();
        if (switcher == null)
        {
            EditorUtility.DisplayDialog("전투 배경", "BattleRoot에 BattleEnvironmentSwitcher가 없습니다. 먼저 동굴 전투장을 생성해 주세요.", "확인");
            return;
        }

        var references = new SerializedObject(switcher);
        var normal = references.FindProperty("normalEnvironment").objectReferenceValue as GameObject;
        var elite = references.FindProperty("eliteEnvironment").objectReferenceValue as GameObject;
        if (normal == null || elite == null)
        {
            EditorUtility.DisplayDialog("전투 배경", "일반/정예 동굴 배경 연결이 누락됐습니다.", "확인");
            return;
        }

        Transform parent = battleRoot.transform.parent;
        if (parent == null)
        {
            EditorUtility.DisplayDialog("전투 배경", "BattleRoot의 상위 오브젝트를 확인해 주세요.", "확인");
            return;
        }

        var existingRoot = parent.Find("PersistentBattleCave");
        if (existingRoot != null && normal.transform.IsChildOf(existingRoot) && elite.transform.IsChildOf(existingRoot))
        {
            Debug.Log("[BattleCave] 이미 분리되어 있습니다. 재구성하지 않았습니다.");
            return;
        }

        var persistent = existingRoot;
        if (persistent == null)
        {
            persistent = new GameObject("PersistentBattleCave").transform;
            Undo.RegisterCreatedObjectUndo(persistent.gameObject, "Persistent Battle Cave Root");
            persistent.SetParent(parent, false);
            // 자식들을 SetParent(worldPositionStays:true)로 이동하므로 기존 월드 구도 유지.
        }

        Undo.SetTransformParent(normal.transform, persistent, "Move Normal Cave Outside BattleRoot");
        Undo.SetTransformParent(elite.transform, persistent, "Move Elite Cave Outside BattleRoot");
        // 새로 들어온 층에서는 배경을 끄고, 전투가 시작되면 SetMode가 켠다.
        normal.SetActive(false);
        elite.SetActive(false);
        EditorUtility.SetDirty(switcher);
        EditorSceneManager.MarkSceneDirty(battleRoot.scene);
        Selection.activeObject = persistent.gameObject;
        Debug.Log("[BattleCave] BattleRoot 밖으로 배경 분리 완료. 이제 전투 종료 후에도 유지됩니다.");
    }
}
#endif
