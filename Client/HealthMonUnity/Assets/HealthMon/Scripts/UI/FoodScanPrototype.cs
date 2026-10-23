using System;
using System.Collections;
using System.Globalization;
using Healthmon.Beta;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class FoodScanPrototype : MonoBehaviour
{
    [Header("Views")]
    [SerializeField] private GameObject captureView, candidateView, resultView;
    [Header("Result UI")]
    [SerializeField] private TMP_Text foodNameText, caloriesText, proteinText, carbText, fatText;
    [SerializeField] private QuestPrototype questPrototype;
    [Header("Camera")]
    [SerializeField] private ARFoodCameraCapture cameraCapture;
    [SerializeField] private RawImage capturedPreview;
    [SerializeField] private TMP_Text scanStatusText;
    [SerializeField] private Button analyzeButton;
    private DialoguePrototype dialogue;
    private byte[] capturedBytes;
    private FoodAnalysis analysis;
    private FoodCandidate selected;
    private TMP_InputField gramsInput;
    private TMP_InputField vegetablesInput;
    private Toggle quantityConfirmed, vegetablesConfirmed, kcalConfirmed;
    private TMP_Text analysisOriginText, candidateOriginText, confirmationNotice, confirmationFeedback;
    private ScrollRect confirmationScroll;
    private Button saveButton, estimateButton;
    private readonly System.Collections.Generic.Dictionary<string, Button> mealButtons = new System.Collections.Generic.Dictionary<string, Button>();
    private string selectedMealType;
    [NonSerialized] private bool syntheticFixture;
    [NonSerialized] private string syntheticFixtureScope;
    private string analysisScope;
    private readonly Button[] candidateButtons = new Button[3];
    private bool confirming;
    public string LastAnalysisId { get; private set; }
    public string LastRecordedSourceId { get; private set; }
    public FoodAnalysis LastAnalysis { get; private set; }
    public FoodConfirmationResult LastConfirmation { get; private set; }
    public long LastFailureStatus { get; private set; }
    public bool HasFoodFailure { get; private set; }
    public bool IsConfirming => confirming;
    public bool IsCheckingExistingRecord => false;
    public string DisplayedAnalysisOrigin => candidateOriginText == null ? null : candidateOriginText.text;
    private HealthmonApiClient Api => dialogue == null ? null : dialogue.Api;
    private string CurrentScope
    {
        get
        {
            var common = Healthmon.Common.CommonServerConnection.Instance;
            return common == null || !common.IsConnected ? null : common.BaseUrl + "|" + common.ServerInstanceId + "|" + common.OwnerId + "|" + Api?.PetId;
        }
    }

    private void Start()
    {
        dialogue = FindAnyObjectByType<DialoguePrototype>(FindObjectsInactive.Include);
        if (cameraCapture != null) { cameraCapture.OnCaptureCompleted += HandleCaptureCompleted; cameraCapture.OnCaptureFailed += HandleCaptureFailed; }
        foreach (var button in candidateView.GetComponentsInChildren<Button>(true))
            for (int i = 0; i < button.onClick.GetPersistentEventCount(); i++)
                if (button.onClick.GetPersistentTarget(i) == this)
                {
                    string method = button.onClick.GetPersistentMethodName(i);
                    int index = method == nameof(SelectChickenSalad) ? 0 : method == nameof(SelectChickenRice) ? 1 : method == nameof(SelectCaesarSalad) ? 2 : -1;
                    if (index >= 0) candidateButtons[index] = button;
                }
        // The updated team scene also has admin inputs. Clone the dialogue input explicitly.
        var template = Array.Find(FindObjectsByType<TMP_InputField>(FindObjectsInactive.Include),
            field => field.name == "MessageInput");
        if (template != null)
        {
            BuildConfirmationControls(template);
        }
#if UNITY_EDITOR
        if (analyzeButton != null)
        {
            var desktop = Instantiate(analyzeButton, analyzeButton.transform.parent);
            desktop.name = "ChooseDesktopFoodPhoto";
            desktop.onClick = new Button.ButtonClickedEvent();
            desktop.onClick.AddListener(ChooseDesktopPhoto);
            var desktopRect = desktop.GetComponent<RectTransform>();
            desktopRect.anchorMin = new Vector2(.74f, .12f);
            desktopRect.anchorMax = new Vector2(.96f, .22f);
            desktopRect.offsetMin = desktopRect.offsetMax = Vector2.zero;
            var label = desktop.GetComponentInChildren<TMP_Text>(true);
            if (label != null) label.text = "PC 사진 선택";
            desktop.interactable = true;
        }
#endif
        ShowCapture();
    }
    private void Update()
    {
        if (analyzeButton != null) analyzeButton.interactable = capturedBytes != null && Api != null && dialogue.IsConnected && !Api.IsBusy && !Api.HasPendingChat;
        if (saveButton != null) saveButton.interactable = selected != null && Api != null && !Api.IsBusy && !Api.HasPendingChat && !confirming;
    }
    public void CaptureRealPhoto()
    {
        if (cameraCapture == null) { Status("카메라가 연결되지 않았습니다."); return; }
        Status("촬영 중…"); cameraCapture.Capture();
    }
    private void HandleCaptureCompleted(Texture2D texture, byte[] bytes)
    {
        capturedBytes = bytes; analysis = null; selected = null; LastAnalysis = null; LastAnalysisId = null;
        if (capturedPreview != null) { capturedPreview.texture = texture; capturedPreview.gameObject.SetActive(true); }
        Status(cameraCapture != null && cameraCapture.LastCaptureWasTestImage
            ? "PC 시연 사진입니다. 음식 분석을 눌러주세요."
            : "사진 준비 완료. 음식 분석을 눌러주세요.");
    }
    private void HandleCaptureFailed(string error) { Status("촬영 실패: " + error); }
    public void UseImage(byte[] bytes)
    {
        var texture = new Texture2D(2, 2);
        if (!texture.LoadImage(bytes)) { Destroy(texture); Status("이미지를 읽지 못했습니다."); return; }
        HandleCaptureCompleted(texture, bytes);
    }
#if UNITY_EDITOR
    public void ChooseDesktopPhoto()
    {
        string path = UnityEditor.EditorUtility.OpenFilePanelWithFilters("음식 사진 선택", "", new[] { "사진", "jpg,jpeg,png" });
        if (!string.IsNullOrEmpty(path)) UseImage(System.IO.File.ReadAllBytes(path));
    }
#endif
    public void AnalyzeFood()
    {
        if (capturedBytes == null) { Status("먼저 사진을 촬영하거나 선택해 주세요."); return; }
        if (Api == null || !dialogue.IsConnected) { Status("서버에 먼저 연결해 주세요."); return; }
        HasFoodFailure = false; LastConfirmation = null;
        Status("음식을 분석하고 있어요…");
        Api.AnalyzeFood(capturedBytes, result =>
        {
            analysis = result; analysisScope = CurrentScope; LastAnalysis = result; LastAnalysisId = result.analysis_id; selected = null;
            UpdateAnalysisOrigin();
            if (result.candidates == null || result.candidates.Length == 0) { Status("음식을 찾지 못했어요. 다른 사진으로 시도해 주세요."); return; }
            for (int i = 0; i < candidateButtons.Length; i++)
            {
                var button = candidateButtons[i]; if (button == null) continue;
                button.gameObject.SetActive(i < result.candidates.Length);
                if (i < result.candidates.Length)
                {
                    var label = button.GetComponentInChildren<TMP_Text>(true);
                    if (label != null) label.text = result.candidates[i].food + "  " + (result.candidates[i].confidence * 100).ToString("F0") + "%";
                }
            }
            ShowCandidates();
            if (result.IsSynthetic)
                Status("MOCK / SYNTHETIC — 개발용 합성 분석입니다. 실제 영양 측정값이 아닙니다.");
            Debug.Log($"[HealthMon Vision] AnalysisDisplayed id={result.analysis_id} candidates={result.candidates.Length}");
        }, Failure);
    }
    // Keep the existing scene bindings; choose actual server candidates.
    public void SelectChickenSalad() { SelectCandidate(0); }
    public void SelectChickenRice() { SelectCandidate(1); }
    public void SelectCaesarSalad() { SelectCandidate(2); }
    public void SelectCandidate(int index)
    {
        if (analysis == null || index < 0 || index >= analysis.candidates.Length) return;
        selected = analysis.candidates[index];
        captureView.SetActive(false); candidateView.SetActive(false); resultView.SetActive(true);
        // A photo estimate is a reference, never a silently confirmed consumed amount.
        if (gramsInput != null) gramsInput.SetTextWithoutNotify("");
        if (vegetablesInput != null) vegetablesInput.SetTextWithoutNotify("");
        if (quantityConfirmed != null) quantityConfirmed.isOn = false;
        if (vegetablesConfirmed != null) vegetablesConfirmed.isOn = false;
        if (kcalConfirmed != null) kcalConfirmed.isOn = false;
        SelectMealType(null);
        RenderSelection();
        if (confirmationScroll != null) { Canvas.ForceUpdateCanvases(); confirmationScroll.verticalNormalizedPosition = 1; }
    }
    public void UseEstimatedQuantity()
    {
        if (selected == null || !selected.has_estimated_grams || gramsInput == null) return;
        gramsInput.text = selected.estimated_grams.ToString("0.0", CultureInfo.InvariantCulture);
        if (quantityConfirmed != null) quantityConfirmed.isOn = false;
        RenderSelection();
    }
    private bool Quantity(out float? grams)
    {
        grams = null;
        if (gramsInput == null || string.IsNullOrWhiteSpace(gramsInput.text)) return true;
        float value;
        if (!float.TryParse(gramsInput.text, NumberStyles.Float, CultureInfo.InvariantCulture, out value) || float.IsNaN(value) || float.IsInfinity(value) || value <= 0 || value > 10000) return false;
        grams = value; return true;
    }
    private static string Nutrient(string label, NutrientValue value, float scale, string unit)
    { return label + " : " + (value != null && value.available ? (value.value * scale).ToString("F1") + unit : "정보 없음"); }
    private void RenderSelection()
    {
        if (confirmationFeedback != null) confirmationFeedback.text = "";
        if (selected == null) return;
        float? grams; bool valid = Quantity(out grams);
        float scale = valid && grams.HasValue ? grams.Value / 100 : 1;
        if (estimateButton != null) estimateButton.gameObject.SetActive(selected.has_estimated_grams);
        var saveLabel = saveButton == null ? null : saveButton.GetComponentInChildren<TMP_Text>(true);
        if (saveLabel != null) saveLabel.text = "기록하기";
        foodNameText.text = selected.food + (grams.HasValue ? "\n입력한 " + grams.Value.ToString("F1") + "g 기준" : "\n100g당 참고값 (실제 섭취량 미입력)") +
            (selected.has_estimated_grams ? "\n사진 추정량 " + selected.estimated_grams.ToString("F1") + "g은 참고값입니다." : "");
        caloriesText.text = Nutrient("열량", selected.per_100g.energy_kcal, scale, " kcal");
        proteinText.text = Nutrient("단백질", selected.per_100g.protein_g, scale, " g");
        carbText.text = Nutrient("탄수화물", selected.per_100g.carbohydrate_g, scale, " g");
        fatText.text = Nutrient("지방", selected.per_100g.fat_g, scale, " g");
        if (confirmationNotice != null) confirmationNotice.text = (syntheticFixture ? "SYNTHETIC CONSUMPTION FIXTURE · 아래 양은 테스트 입력이며 실제 섭취/사진 정답이 아닙니다.\n" : "") +
            (selectedMealType == null ? "아침·점심·저녁·간식 중 실제 식사 구분을 선택하세요.\n" : "선택한 구분: " + MealLabel(selectedMealType) + "\n") +
            (!grams.HasValue ? "먹은 양을 비워 저장하면 식사 퀘스트·기록 EXP에 반영되지 않아요.\n" :
                quantityConfirmed != null && quantityConfirmed.isOn ? "실제 먹은 양을 확인했어요.\n" : "입력한 양이 실제 먹은 양인지 확인 체크해 주세요.\n") +
            (selectedMealType == "snack" ? "간식은 식사 퀘스트 횟수에 포함되지 않아요.\n" : "") +
            "사진 추정량은 참고값입니다. 채소·과일 정보가 없으면 영양 평가는 보류됩니다.\n" +
            Nutrient("분석 채소·과일 참고", selected.per_100g.vegetable_fruit_g, scale, " g");
    }
    public void ConfirmFood()
    {
        if (confirming || selected == null || Api == null || Api.IsBusy || Api.HasPendingChat) return;
        if (string.IsNullOrEmpty(analysisScope) || analysisScope != CurrentScope || (syntheticFixture && syntheticFixtureScope != CurrentScope))
        { StatusInConfirmation("분석 이후 연결이 바뀌었습니다. 현재 연결에서 사진을 다시 분석하세요."); return; }
        if (selectedMealType == null)
        { StatusInConfirmation("아침·점심·저녁·간식 중 실제 식사 구분을 먼저 선택해 주세요."); return; }
        float? grams;
        if (!Quantity(out grams)) { StatusInConfirmation("먹은 양을 0보다 크고 10,000g 이하로 입력해 주세요."); return; }
        if (grams.HasValue && (quantityConfirmed == null || !quantityConfirmed.isOn)) { StatusInConfirmation("입력한 양이 실제 먹은 양인지 확인 체크를 해 주세요."); return; }
        if (!grams.HasValue && quantityConfirmed != null && quantityConfirmed.isOn) { StatusInConfirmation("실제 먹은 양을 입력하거나, 모르면 확인 체크를 해제하세요."); return; }
        float? vegetables = null;
        if (vegetablesConfirmed != null && vegetablesConfirmed.isOn)
        {
            float value;
            if (vegetablesInput == null || !float.TryParse(vegetablesInput.text, NumberStyles.Float, CultureInfo.InvariantCulture, out value) ||
                !Healthmon.Common.CommonServerContract.Bounded(value, 0, 10000))
            { StatusInConfirmation("확인한 채소·과일량을 0~10,000g으로 입력하세요. 모르면 체크를 해제하세요."); return; }
            vegetables = value;
        }
        else if (vegetablesInput != null && !string.IsNullOrWhiteSpace(vegetablesInput.text))
        { StatusInConfirmation("채소·과일량을 확인 체크하거나, 모르면 입력을 비워 주세요."); return; }
        HasFoodFailure = false;
        LastConfirmation = null;
        confirming = true;
        StatusInConfirmation("음식 기록을 저장하고 있어요…");
        Api.ConfirmFood(analysis.analysis_id, selected.candidate_id, grams, result =>
        {
            confirming = false; LastRecordedSourceId = result.source_id; LastConfirmation = result;
            Healthmon.Common.CommonServerConnection.Instance?.ClearFoodCalorieConfirmation();
            if (!result.duplicate && questPrototype != null) questPrototype.AddFoodRecord();
            Healthmon.Common.CommonServerConnection.Instance?.RefreshQuests();
            ShowCapture();
            Status((syntheticFixture ? "SYNTHETIC 섭취 테스트 기록. " : "음식 기록 완료. ") +
                (!grams.HasValue ? "섭취량 미확인: 식사 퀘스트·기록 EXP에는 반영되지 않았어요." :
                    selectedMealType == "snack" ? "간식으로 저장했어요. 식사 퀘스트 횟수에는 포함되지 않아요." : "서버 상태와 퀘스트를 갱신했습니다.") +
                (!vegetables.HasValue ? " 채소·과일 정보 없음: Nutrition unknown." : ""));
            Debug.Log($"[HealthMon Food] FoodRecorded source_id={result.source_id} duplicate={result.duplicate} state_version={result.state_version}");
        }, error => { confirming = false; Failure(error); },
            mealType: selectedMealType, kcalReconfirmed: kcalConfirmed != null && kcalConfirmed.isOn,
            vegetableFruitGrams: vegetables, syntheticFixture: syntheticFixture);
    }
    public void ShowCapture()
    {
        captureView.SetActive(true); candidateView.SetActive(false); resultView.SetActive(false);
        capturedBytes = null; analysis = null; selected = null;
        if (capturedPreview != null) capturedPreview.gameObject.SetActive(false);
        Status("음식 사진을 촬영하거나 선택해 주세요.");
    }
    public void ShowCandidates() { captureView.SetActive(false); candidateView.SetActive(true); resultView.SetActive(false); }
    private void Status(string text) { if (scanStatusText != null) scanStatusText.text = text; }
    private void Failure(ApiFailure error)
    {
        HasFoodFailure = true; LastFailureStatus = error.StatusCode;
        string message = error.StatusCode == 409 && selected != null
            ? "이 분석 결과는 이미 기록됐어요. 새 기록은 촬영 화면에서 다시 시작해 주세요."
            : "분석·저장에 실패했어요 (" + error.StatusCode + "). 다시 시도해 주세요.";
        StatusInConfirmation(message);
        Debug.LogWarning($"[HealthMon Food] RequestFailed status={error.StatusCode}");
    }
    private void StatusInConfirmation(string message)
    {
        if (confirmationNotice != null) confirmationNotice.text = message;
        if (confirmationFeedback != null) confirmationFeedback.text = message;
        Status(message);
    }
    private void UpdateAnalysisOrigin()
    {
        string label = analysis == null ? "분석 대기" : analysis.IsSynthetic
            ? "MOCK / SYNTHETIC · 합성 분석 · 실제 영양 측정값 아님"
            : "REAL · 실제 원격 Vision 분석 · 사진 추정값은 섭취량 확정이 아님";
        if (syntheticFixture) label += "\n섭취 확인량은 별도의 SYNTHETIC 테스트 입력입니다.";
        if (candidateOriginText != null) candidateOriginText.text = label;
        if (analysisOriginText != null) analysisOriginText.text = label;
    }
    public void SelectMealType(string meal)
    {
        if (meal != null && meal != "breakfast" && meal != "lunch" && meal != "dinner" && meal != "snack") return;
        selectedMealType = meal;
        foreach (var pair in mealButtons)
        {
            var label = pair.Value.GetComponentInChildren<TMP_Text>(true);
            if (label != null) label.text = (pair.Key == meal ? "● " : "") + MealLabel(pair.Key);
        }
        RenderSelection();
    }
    private static string MealLabel(string meal) { return meal == "breakfast" ? "아침" : meal == "lunch" ? "점심" : meal == "dinner" ? "저녁" : "간식"; }
#if UNITY_EDITOR
    public void EnableSyntheticConsumptionFixture()
    {
        if (Healthmon.Common.CommonServerConnection.Instance?.EnvironmentName != "test") throw new InvalidOperationException("Only isolated test consumption may be synthetic.");
        syntheticFixture = true; syntheticFixtureScope = CurrentScope; UpdateAnalysisOrigin();
    }
    public void ClearSyntheticConsumptionFixture()
    {
        syntheticFixture = false; syntheticFixtureScope = null;
        ShowCapture(); UpdateAnalysisOrigin();
    }
#endif
    private void BuildConfirmationControls(TMP_InputField template)
    {
        var confirm = resultView.transform.Find("ConfirmButton")?.GetComponent<Button>();
        if (confirm == null) return;
        saveButton = confirm;
        confirmationFeedback = MakeLabel(resultView.transform, "FoodSaveFeedback", "", 76);
        var feedbackRect = confirmationFeedback.rectTransform;
        feedbackRect.anchorMin = new Vector2(.04f, 0); feedbackRect.anchorMax = new Vector2(.96f, 0);
        feedbackRect.pivot = new Vector2(.5f, 0); feedbackRect.anchoredPosition = new Vector2(0, 176);
        feedbackRect.sizeDelta = new Vector2(0, 76); confirmationFeedback.alignment = TextAlignmentOptions.Center;
        confirmationFeedback.color = new Color(1, .94f, .55f);
        var root = (RectTransform)new GameObject("FoodConfirmationScroll", typeof(RectTransform), typeof(Image), typeof(ScrollRect)).transform;
        root.SetParent(resultView.transform, false); root.anchorMin = Vector2.zero; root.anchorMax = Vector2.one;
        root.offsetMin = new Vector2(20, 260); root.offsetMax = new Vector2(-20, -145);
        root.GetComponent<Image>().color = Color.clear;
        var viewport = (RectTransform)new GameObject("Viewport", typeof(RectTransform), typeof(RectMask2D)).transform;
        viewport.SetParent(root, false); viewport.anchorMin = Vector2.zero; viewport.anchorMax = Vector2.one;
        viewport.offsetMin = viewport.offsetMax = Vector2.zero;
        var content = (RectTransform)new GameObject("Content", typeof(RectTransform), typeof(VerticalLayoutGroup), typeof(ContentSizeFitter)).transform;
        content.SetParent(viewport, false); content.anchorMin = new Vector2(0, 1); content.anchorMax = Vector2.one; content.pivot = new Vector2(.5f, 1);
        content.sizeDelta = Vector2.zero; content.anchoredPosition = Vector2.zero;
        var group = content.GetComponent<VerticalLayoutGroup>();
        group.spacing = 12; group.padding = new RectOffset(20, 20, 16, 16); group.childControlWidth = group.childControlHeight = true;
        group.childForceExpandWidth = true; group.childForceExpandHeight = false;
        content.GetComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
        confirmationScroll = root.GetComponent<ScrollRect>(); confirmationScroll.viewport = viewport; confirmationScroll.content = content;
        confirmationScroll.horizontal = false; confirmationScroll.vertical = true; confirmationScroll.movementType = ScrollRect.MovementType.Clamped; confirmationScroll.scrollSensitivity = 36;
        analysisOriginText = MakeLabel(content, "AnalysisOrigin", "분석 대기", 72);
        var meals = (RectTransform)new GameObject("MealTypeChoices", typeof(RectTransform), typeof(HorizontalLayoutGroup)).transform;
        meals.SetParent(content, false); LayoutHeight(meals.gameObject, 64);
        var mealLayout = meals.GetComponent<HorizontalLayoutGroup>(); mealLayout.spacing = 8; mealLayout.childForceExpandWidth = true;
        foreach (string meal in new[] { "breakfast", "lunch", "dinner", "snack" })
        {
            var choice = Instantiate(confirm, meals); choice.name = "Meal_" + meal; choice.onClick = new Button.ButtonClickedEvent();
            string selectedMeal = meal; choice.onClick.AddListener(() => SelectMealType(selectedMeal));
            var label = choice.GetComponentInChildren<TMP_Text>(true); if (label != null) { label.font = foodNameText.font; label.fontSize = 24; }
            mealButtons[meal] = choice;
        }
        var quantityRow = (RectTransform)new GameObject("QuantityRow", typeof(RectTransform), typeof(HorizontalLayoutGroup)).transform;
        quantityRow.SetParent(content, false); LayoutHeight(quantityRow.gameObject, 64);
        var quantityLayout = quantityRow.GetComponent<HorizontalLayoutGroup>(); quantityLayout.spacing = 12;
        quantityLayout.childControlWidth = quantityLayout.childControlHeight = true;
        quantityLayout.childForceExpandWidth = true;
        gramsInput = MakeInput(template, quantityRow, "ConsumedGrams", "실제로 먹은 양(g), 모르면 비움");
        estimateButton = Instantiate(confirm, quantityRow); estimateButton.name = "UseEstimatedQuantity";
        estimateButton.onClick = new Button.ButtonClickedEvent(); estimateButton.onClick.AddListener(UseEstimatedQuantity);
        var estimateLabel = estimateButton.GetComponentInChildren<TMP_Text>(true);
        if (estimateLabel != null) { estimateLabel.text = "사진 추정량 불러오기"; estimateLabel.font = foodNameText.font; estimateLabel.fontSize = 24; }
        foreach (var item in new[] { gramsInput.gameObject, estimateButton.gameObject })
        {
            var size = item.GetComponent<LayoutElement>() ?? item.AddComponent<LayoutElement>();
            size.preferredWidth = size.minWidth = 0; size.flexibleWidth = 1;
        }
        quantityConfirmed = MakeToggle(content, "ConsumedQuantityConfirmed", "입력한 g은 제가 실제 먹은 양을 확인한 값입니다.");
        quantityConfirmed.onValueChanged.AddListener(_ => RenderSelection());
        confirmationNotice = MakeLabel(content, "ConfirmationNotice", "식사 구분과 실제 먹은 양을 확인하세요.", 200);
        foreach (var label in new[] { foodNameText, caloriesText, proteinText, carbText, fatText })
        { label.transform.SetParent(content, false); LayoutHeight(label.gameObject, label == foodNameText ? 160 : 64); }
        vegetablesInput = MakeInput(template, content, "VegetableFruitGrams", "확인한 채소·과일량(g), 모르면 비움");
        vegetablesConfirmed = MakeToggle(content, "VegetableFruitConfirmed", "채소·과일량을 확인했습니다. 모르면 비우고 체크하지 않습니다.");
        kcalConfirmed = MakeToggle(content, "FoodKcalReconfirmed", "표시 열량을 실제 섭취량 기준으로 재확인했습니다 (게임 점수용).");
        candidateOriginText = MakeLabel(candidateView.transform, "CandidateAnalysisOrigin", "분석 대기", 70);
        var origin = candidateOriginText.rectTransform; origin.anchorMin = new Vector2(.08f, 1); origin.anchorMax = new Vector2(.92f, 1);
        origin.pivot = new Vector2(.5f, 1); origin.anchoredPosition = new Vector2(0, -140); origin.sizeDelta = new Vector2(0, 70);
        candidateOriginText.alignment = TextAlignmentOptions.Center;
        SelectMealType(null);
    }
    private static void LayoutHeight(GameObject target, float height)
    {
        var layout = target.GetComponent<LayoutElement>() ?? target.AddComponent<LayoutElement>();
        layout.minHeight = layout.preferredHeight = height; layout.flexibleHeight = 0;
    }
    private TMP_Text MakeLabel(Transform parent, string name, string text, float height)
    {
        var label = Instantiate(foodNameText, parent); label.name = name; label.fontSize = 24;
        label.text = text; label.alignment = TextAlignmentOptions.Left; label.enableAutoSizing = false; label.enableWordWrapping = true; label.raycastTarget = false;
        LayoutHeight(label.gameObject, height); return label;
    }
    private TMP_InputField MakeInput(TMP_InputField template, Transform parent, string name, string hint)
    {
        var field = Instantiate(template, parent); field.name = name;
        foreach (var label in field.GetComponentsInChildren<TMP_Text>(true)) { label.font = foodNameText.font; label.fontSize = 24; }
        field.onValueChanged = new TMP_InputField.OnChangeEvent(); field.onEndEdit = new TMP_InputField.SubmitEvent(); field.onSubmit = new TMP_InputField.SubmitEvent();
        field.text = ""; field.contentType = TMP_InputField.ContentType.DecimalNumber; field.characterLimit = 8;
        if (field.placeholder is TMP_Text placeholder) placeholder.text = hint;
        field.onValueChanged.AddListener(_ => RenderSelection()); field.gameObject.SetActive(true); LayoutHeight(field.gameObject, 64); return field;
    }
    private Toggle MakeToggle(Transform parent, string name, string text)
    {
        var root = new GameObject(name, typeof(RectTransform), typeof(Toggle)); root.transform.SetParent(parent, false); LayoutHeight(root, 80);
        var box = new GameObject("Box", typeof(RectTransform), typeof(Image)); box.transform.SetParent(root.transform, false);
        var rect = (RectTransform)box.transform; rect.anchorMin = rect.anchorMax = new Vector2(0, .5f); rect.pivot = new Vector2(0, .5f); rect.sizeDelta = new Vector2(32, 32);
        var mark = new GameObject("Checked", typeof(RectTransform), typeof(Image)); mark.transform.SetParent(box.transform, false);
        var checkedRect = (RectTransform)mark.transform; checkedRect.anchorMin = Vector2.zero; checkedRect.anchorMax = Vector2.one;
        checkedRect.offsetMin = new Vector2(7, 7); checkedRect.offsetMax = new Vector2(-7, -7); mark.GetComponent<Image>().color = Color.black;
        var label = MakeLabel(root.transform, "Label", text, 80); var labelRect = label.rectTransform;
        labelRect.anchorMin = Vector2.zero; labelRect.anchorMax = Vector2.one; labelRect.offsetMin = new Vector2(44, 0); labelRect.offsetMax = Vector2.zero;
        var toggle = root.GetComponent<Toggle>(); toggle.targetGraphic = box.GetComponent<Image>(); toggle.graphic = mark.GetComponent<Image>(); toggle.isOn = false; return toggle;
    }
    private void OnDestroy()
    {
        if (cameraCapture != null) { cameraCapture.OnCaptureCompleted -= HandleCaptureCompleted; cameraCapture.OnCaptureFailed -= HandleCaptureFailed; }
    }
}
