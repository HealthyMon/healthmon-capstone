using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Add to the optional JewelryAdjustPanel child of CustomizationPanel.
/// Controls the selected REAL 3D jewelry model in PetPreviewRoot, using uGUI sliders
/// that work with mouse and touch. No Canvas overlay jewelry sprites are used.
/// </summary>
public sealed class HealthMon3DJewelryAdjustPanel : MonoBehaviour
{
    [Header("Preview 3D Rig (PetPreviewRoot/HealthMon_Slime)")]
    [SerializeField] private HealthMon3DJewelryRig previewRig;

    [Header("UI sliders")]
    [SerializeField] private Slider yawSlider;
    [SerializeField] private Slider rollSlider;
    [SerializeField] private Slider scaleSlider;

    [Header("Optional labels")]
    [SerializeField] private TMP_Text selectedNameText;
    [SerializeField] private TMP_Text yawValueText;
    [SerializeField] private TMP_Text rollValueText;
    [SerializeField] private TMP_Text scaleValueText;

    private int selectedSlot;
    private bool updatingUI;
    private bool dirty;

    private void Awake()
    {
        SetupSlider(yawSlider, -180f, 180f, OnYawChanged);
        SetupSlider(rollSlider, -180f, 180f, OnRollChanged);
        SetupSlider(scaleSlider, 0.4f, 2f, OnScaleChanged);
    }

    private static void SetupSlider(Slider slider, float min, float max,
        UnityEngine.Events.UnityAction<float> callback)
    {
        if (slider == null) return;
        slider.minValue = min;
        slider.maxValue = max;
        slider.wholeNumbers = false;
        slider.onValueChanged.AddListener(callback);
    }

    private void OnEnable()
    {
        RefreshValues();
    }

    private void OnDisable()
    {
        CommitIfDirty();
    }

    public void SelectSlot(int index, bool openPanel = true)
    {
        if (previewRig == null || index < 0 || index > 3) return;
        CommitIfDirty();
        selectedSlot = index;
        previewRig.SelectForCustomization(index);
        if (openPanel)
        {
            if (!gameObject.activeSelf) gameObject.SetActive(true);
            previewRig.EnsureEquipped(index); // Select and equip; do NOT toggle an equipped item OFF.
        }
        RefreshValues();
    }

    public void RefreshValues()
    {
        if (previewRig == null) return;
        updatingUI = true;
        bool available = previewRig.HasJewelry(selectedSlot) && previewRig.IsUnlocked(selectedSlot);
        if (selectedNameText != null)
            selectedNameText.text = previewRig.GetName(selectedSlot) +
                (available ? " · 회전 / 크기 조절" : " · 잠김");
        if (yawSlider != null)
        {
            yawSlider.interactable = available;
            yawSlider.SetValueWithoutNotify(previewRig.GetYaw(selectedSlot));
        }
        if (rollSlider != null)
        {
            rollSlider.interactable = available;
            rollSlider.SetValueWithoutNotify(previewRig.GetRoll(selectedSlot));
        }
        if (scaleSlider != null)
        {
            scaleSlider.interactable = available;
            scaleSlider.SetValueWithoutNotify(previewRig.GetScaleFactor(selectedSlot));
        }
        updatingUI = false;
        UpdateValueTexts();
    }

    private bool CanAdjust() => previewRig != null &&
        previewRig.HasJewelry(selectedSlot) && previewRig.IsUnlocked(selectedSlot);

    private void OnYawChanged(float value)
    {
        if (updatingUI || !CanAdjust()) return;
        previewRig.PreviewYaw(selectedSlot, value);
        dirty = true;
        UpdateValueTexts();
    }

    private void OnRollChanged(float value)
    {
        if (updatingUI || !CanAdjust()) return;
        previewRig.PreviewRoll(selectedSlot, value);
        dirty = true;
        UpdateValueTexts();
    }

    private void OnScaleChanged(float value)
    {
        if (updatingUI || !CanAdjust()) return;
        previewRig.PreviewScale(selectedSlot, value);
        dirty = true;
        UpdateValueTexts();
    }

    private void UpdateValueTexts()
    {
        if (previewRig == null) return;
        if (yawValueText != null) yawValueText.text = Mathf.RoundToInt(previewRig.GetYaw(selectedSlot)) + "°";
        if (rollValueText != null) rollValueText.text = Mathf.RoundToInt(previewRig.GetRoll(selectedSlot)) + "°";
        if (scaleValueText != null) scaleValueText.text = previewRig.GetScaleFactor(selectedSlot).ToString("F2") + "x";
    }

    // Optional OnClick target. Sliders preview immediately, and this commits the outfit to PlayerPrefs.
    public void SaveSelected()
    {
        if (!CanAdjust()) return;
        previewRig.CommitAppearance(selectedSlot);
        dirty = false;
        UpdateValueTexts();
    }

    private void CommitIfDirty()
    {
        if (dirty && previewRig != null && previewRig.HasJewelry(selectedSlot))
            previewRig.CommitAppearance(selectedSlot);
        dirty = false;
    }

    // Optional OnClick target.
    public void ResetSelected()
    {
        if (!CanAdjust()) return;
        previewRig.ResetAppearance(selectedSlot);
        dirty = false;
        RefreshValues();
    }

    // Optional OnClick target; closes without losing adjustments.
    public void Close()
    {
        CommitIfDirty();
        gameObject.SetActive(false);
    }

    // Optional tap-friendly +/- controls, useful instead of dragging slider thumbs.
    public void Grow10Percent() => NudgeScale(0.1f);
    public void Shrink10Percent() => NudgeScale(-0.1f);
    public void RotateLeft15() => NudgeYaw(-15f);
    public void RotateRight15() => NudgeYaw(15f);

    private void NudgeScale(float delta)
    {
        if (!CanAdjust()) return;
        previewRig.PreviewScale(selectedSlot, previewRig.GetScaleFactor(selectedSlot) + delta);
        dirty = true;
        RefreshValues();
    }

    private void NudgeYaw(float delta)
    {
        if (!CanAdjust()) return;
        previewRig.PreviewYaw(selectedSlot,
            Mathf.Repeat(previewRig.GetYaw(selectedSlot) + delta + 180f, 360f) - 180f);
        dirty = true;
        RefreshValues();
    }
}
