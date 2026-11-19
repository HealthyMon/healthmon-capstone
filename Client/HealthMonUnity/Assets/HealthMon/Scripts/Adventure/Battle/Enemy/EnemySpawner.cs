
using System.Collections.Generic;
using UnityEngine;

public class EnemySpawner : MonoBehaviour
{
    [Header("Spawn")]
    [SerializeField]
    private Transform enemyVisualRoot;

    [Header("Normal Monster Prefabs")]
    [SerializeField]
    private List<GameObject> normalEnemies = new();

    [Header("Elite Monster Prefabs")]
    [SerializeField]
    private List<GameObject> eliteEnemies = new();

    [Header("Visual Controller")]
    [SerializeField]
    private BattleVisualController battleVisual;

    [Header("Normal Model Adjustment")]
    [SerializeField]
    private Vector3 spawnPosition = Vector3.zero;

    [SerializeField]
    private Vector3 spawnRotation = Vector3.zero;

    [SerializeField]
    private Vector3 spawnScale = Vector3.one;

    [Header("Elite Model Adjustment")]
    [SerializeField]
    private Vector3 eliteSpawnPosition = Vector3.zero;

    [SerializeField]
    private Vector3 eliteSpawnRotation = Vector3.zero;

    [SerializeField]
    private Vector3 eliteSpawnScale = Vector3.one;

    [Header("Legacy Model")]
    [SerializeField]
    private GameObject legacyEliteBody;

    private GameObject currentEnemy;

    public GameObject CurrentEnemy => currentEnemy;

    // 일반 몬스터 생성
    public bool SpawnNormalEnemy()
    {
        return SpawnEnemy(
            normalEnemies,
            spawnPosition,
            spawnRotation,
            spawnScale
        );
    }

    // 정예 몬스터 생성
    public bool SpawnEliteEnemy()
    {
        return SpawnEnemy(
            eliteEnemies,
            eliteSpawnPosition,
            eliteSpawnRotation,
            eliteSpawnScale
        );
    }

    // 공통 몬스터 생성
    private bool SpawnEnemy(
        List<GameObject> prefabs,
        Vector3 position,
        Vector3 rotation,
        Vector3 scale)
    {
        ClearEnemy();

        if (legacyEliteBody != null)
            legacyEliteBody.SetActive(false);

        if (enemyVisualRoot == null)
        {
            Debug.LogError(
                "[EnemySpawner] EnemyVisualRoot 미연결"
            );
            return false;
        }

        if (battleVisual == null)
        {
            Debug.LogError(
                "[EnemySpawner] BattleVisualController 미연결"
            );
            return false;
        }

        List<GameObject> candidates = new();

        if (prefabs != null)
        {
            foreach (GameObject prefab in prefabs)
            {
                if (prefab != null)
                    candidates.Add(prefab);
            }
        }

        if (candidates.Count == 0)
        {
            Debug.LogError(
                "[EnemySpawner] 몬스터 Prefab이 없습니다."
            );
            return false;
        }

        int index = Random.Range(0, candidates.Count);

        GameObject selectedPrefab = candidates[index];

        currentEnemy = Instantiate(
            selectedPrefab,
            enemyVisualRoot
        );

        currentEnemy.transform.localPosition = position;
        currentEnemy.transform.localRotation =
            Quaternion.Euler(rotation);
        currentEnemy.transform.localScale = scale;

        currentEnemy.SetActive(true);

        battleVisual.SetEnemyVisual(currentEnemy);

        Debug.Log(
            $"[EnemySpawner] 몬스터 생성: " +
            $"{selectedPrefab.name}"
        );

        return true;
    }

    // 현재 몬스터 제거
    public void ClearEnemy()
    {
        if (battleVisual != null)
            battleVisual.SetEnemyVisual(null);

        if (currentEnemy != null)
        {
            currentEnemy.SetActive(false);
            Destroy(currentEnemy);
            currentEnemy = null;
        }
    }
}
