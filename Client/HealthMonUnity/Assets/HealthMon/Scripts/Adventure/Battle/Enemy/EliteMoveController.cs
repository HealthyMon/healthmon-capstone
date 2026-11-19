
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.UI;

public class EliteMoveController : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private EliteGridManager grid;
    [SerializeField] private Transform playerVisual;
    [SerializeField] private Camera eliteCamera;
    [SerializeField] private BattleManager battleManager;

    [Header("Move UI")]
    [SerializeField] private GameObject movePanel;
    [SerializeField] private TMP_Text moveInfoText;
    [SerializeField] private Button confirmButton;
    [SerializeField] private Button cancelButton;

    [Header("Movement")]
    [SerializeField] private float staminaPerCell = 2f;
    [SerializeField] private float visualHeight = 1f;

    private Vector2Int selectedCell;
    private bool isSelecting;

    private void Awake()
    {
        confirmButton.onClick.AddListener(ConfirmMove);
        cancelButton.onClick.AddListener(CancelMove);

        movePanel.SetActive(false);
    }

    public void ResetMovement()
    {
        isSelecting = false;
        selectedCell = new Vector2Int(1, 1);

        grid.ResetGrid();

        if (playerVisual != null)
        {
            playerVisual.position =
                grid.CellToWorldPosition(grid.PlayerCell)
                + Vector3.up * visualHeight;
        }

        movePanel.SetActive(false);
    }

    public void BeginMoveSelection()
    {
        if (!battleManager.CanSelectEliteMove())
            return;

        isSelecting = true;
        selectedCell = grid.PlayerCell;

        movePanel.SetActive(true);
        RefreshMoveInfo();
    }

    private void Update()
    {
        if (!isSelecting || eliteCamera == null)
            return;

        if (Pointer.current == null ||
            !Pointer.current.press.wasPressedThisFrame)
            return;

        Vector2 screenPosition =
            Pointer.current.position.ReadValue();

        Ray ray = eliteCamera.ScreenPointToRay(
            screenPosition
        );

        if (!Physics.Raycast(ray, out RaycastHit hit, 100f))
            return;

        if (!hit.collider.transform.IsChildOf(
                grid.transform))
            return;

        string tileName = hit.collider.gameObject.name;

        // EliteGridManager가 생성하는 Tile_row_col 형식
        string[] parts = tileName.Split('_');

        if (parts.Length != 3 ||
            !int.TryParse(parts[1], out int row) ||
            !int.TryParse(parts[2], out int col))
            return;

        Vector2Int cell = new Vector2Int(col, row);

        if (!grid.IsValidCell(cell))
            return;

        selectedCell = cell;
        RefreshMoveInfo();
    }

    private void RefreshMoveInfo()
    {
        int distance = grid.GetMoveDistance(
            selectedCell
        );

        float cost = distance * staminaPerCell;

        moveInfoText.text =
            $"목적지: ({selectedCell.x}, {selectedCell.y})\n" +
            $"이동 거리: {distance}칸\n" +
            $"필요 ST: {cost:0.#}";

        confirmButton.interactable =
            distance > 0 &&
            battleManager.CanAffordEliteMove(cost);
    }

    private void ConfirmMove()
    {
        if (!isSelecting)
            return;

        int distance = grid.GetMoveDistance(
            selectedCell
        );

        if (distance <= 0)
            return;

        float cost = distance * staminaPerCell;

        if (!battleManager.CompleteEliteMove(cost))
        {
            RefreshMoveInfo();
            return;
        }

        grid.SetPlayerCell(selectedCell);

        if (playerVisual != null)
        {
            playerVisual.position =
                grid.CellToWorldPosition(selectedCell)
                + Vector3.up * visualHeight;
        }

        isSelecting = false;
        movePanel.SetActive(false);
    }

    public void CancelMove()
    {
        isSelecting = false;
        movePanel.SetActive(false);
    }
}
