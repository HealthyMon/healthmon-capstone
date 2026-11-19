using System.Collections.Generic;
using UnityEngine;

public class EliteGridManager : MonoBehaviour
{
    [Header("3x3 Grid")]
    [SerializeField] private GameObject tilePrefab;
    [SerializeField] private float cellSize = 1.5f;
    [SerializeField] private float tileHeight = 0.08f;
    [SerializeField] private Color normalColor = new Color(0.48f, 0.64f, 0.60f);
    [SerializeField] private Color warningColor = new Color(0.95f, 0.17f, 0.14f);

    private readonly Renderer[,] renderers = new Renderer[3, 3];
    private readonly Material[,] materials = new Material[3, 3];
    private readonly HashSet<Vector2Int> warningCells = new HashSet<Vector2Int>();

    public Vector2Int PlayerCell { get; private set; } = new Vector2Int(1, 1);

    private void Awake()
    {
        BuildGrid();
    }

    private void BuildGrid()
    {
        if (tilePrefab == null)
        {
            Debug.LogError("EliteGridManager: Tile Prefab is missing.", this);
            return;
        }

        for (int row = 0; row < 3; row++)
        {
            for (int col = 0; col < 3; col++)
            {
                Vector2Int cell = new Vector2Int(col, row);
                GameObject tile = Instantiate(tilePrefab, transform);
                tile.name = $"Tile_{row}_{col}";
                tile.transform.localPosition = CellToLocalPosition(cell);
                tile.transform.localRotation = Quaternion.identity;
                tile.transform.localScale = new Vector3(cellSize * 0.96f, tileHeight, cellSize * 0.96f);

                Renderer r = tile.GetComponent<Renderer>();
                if (r == null)
                {
                    Debug.LogError($"Tile prefab needs a Renderer: {tile.name}", tile);
                    continue;
                }

                renderers[row, col] = r;
                materials[row, col] = r.material;
                materials[row, col].color = normalColor;
            }
        }
    }

    public Vector3 CellToLocalPosition(Vector2Int cell)
    {
        return new Vector3((cell.x - 1) * cellSize, 0f, (cell.y - 1) * cellSize);
    }

    public Vector3 CellToWorldPosition(Vector2Int cell)
    {
        return transform.TransformPoint(CellToLocalPosition(cell));
    }

    public bool IsValidCell(Vector2Int cell)
    {
        return cell.x >= 0 && cell.x < 3 && cell.y >= 0 && cell.y < 3;
    }

    public int GetMoveDistance(Vector2Int destination)
    {
        return Mathf.Abs(destination.x - PlayerCell.x)
             + Mathf.Abs(destination.y - PlayerCell.y);
    }

    public bool SetPlayerCell(Vector2Int destination)
    {
        if (!IsValidCell(destination)) return false;
        PlayerCell = destination;
        return true;
    }

    public void ResetGrid()
    {
        PlayerCell = new Vector2Int(1, 1);
        ClearWarnings();
    }

    public void ShowSingleWarning(Vector2Int cell)
    {
        ClearWarnings();
        SetWarning(cell);
    }
    public void ShowRowWarning(int row)
    {
        ClearWarnings();
        if (row < 0 || row > 2) return;
        for (int col = 0; col < 3; col++)
            SetWarning(new Vector2Int(col, row));
    }

    public void ShowColumnWarning(int col)
    {
        ClearWarnings();
        if (col < 0 || col > 2) return;
        for (int row = 0; row < 3; row++)
            SetWarning(new Vector2Int(col, row));
    }

    private void SetWarning(Vector2Int cell)
    {
        if (!IsValidCell(cell)) return;
        warningCells.Add(cell);
        Material m = materials[cell.y, cell.x];
        if (m != null) m.color = warningColor;
    }

    public bool IsCellDangerous(Vector2Int cell)
    {
        return warningCells.Contains(cell);
    }

    public void ClearWarnings()
    {
        warningCells.Clear();
        for (int row = 0; row < 3; row++)
            for (int col = 0; col < 3; col++)
                if (materials[row, col] != null)
                    materials[row, col].color = normalColor;
    }

    private void OnDestroy()
    {
        for (int row = 0; row < 3; row++)
            for (int col = 0; col < 3; col++)
                if (materials[row, col] != null)
                    Destroy(materials[row, col]);
    }
}