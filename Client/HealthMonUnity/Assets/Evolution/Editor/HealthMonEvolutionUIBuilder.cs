#if UNITY_EDITOR
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;
using HealthMon.Evolution;

namespace HealthMon.Evolution.Editor
{
    /// <summary>Builds the HealthMon evolution UI under UI > Canvas (not HomeBackgroundCanvas).</summary>
    public static class HealthMonEvolutionUIBuilder
    {
        private static readonly Color White = new Color(.94f,.98f,1f,1);
        private static readonly Color Muted = new Color(.70f,.79f,.93f,1);
        private static readonly Color Mint = new Color(.43f,1f,.87f,1);
        private static TMP_FontAsset projectKoreanFont;

        [MenuItem("Tools/HealthMon/1. 진화 UI 자동 생성")]
        public static void BuildNew() { Build(false); }

        [MenuItem("Tools/HealthMon/3. 진화 UI v3 디자인으로 교체")]
        public static void Upgrade() { Build(true); }

        [MenuItem("Tools/HealthMon/2. 선택한 TMP 한글 폰트를 진화 UI에 적용")]
        public static void ApplySelectedFont()
        {
            TMP_FontAsset font = Selection.activeObject as TMP_FontAsset;
            if (font == null) { EditorUtility.DisplayDialog("HealthMon", "Project에서 한글 TMP Font Asset을 선택하세요.", "확인"); return; }
            Canvas canvas = FindMainCanvas();
            if (canvas == null) return;
            Transform root=canvas.transform.Find("EvolutionOverlay");
            if (root==null) { EditorUtility.DisplayDialog("HealthMon", "EvolutionOverlay를 먼저 생성하세요.", "확인"); return; }
            int count=0;
            foreach(TMP_Text tmp in root.GetComponentsInChildren<TMP_Text>(true))
            { Undo.RecordObject(tmp,"Apply evolution font"); tmp.font=font; EditorUtility.SetDirty(tmp); count++; }
            Transform dev=canvas.transform.Find("DEV_EvolutionStartButton (출시 전 숨김)");
            if(dev!=null) foreach(TMP_Text tmp in dev.GetComponentsInChildren<TMP_Text>(true))
            { Undo.RecordObject(tmp,"Apply test font"); tmp.font=font; EditorUtility.SetDirty(tmp); }
            EditorSceneManager.MarkSceneDirty(canvas.gameObject.scene);
            EditorUtility.DisplayDialog("HealthMon",count+"개 텍스트 폰트를 적용했습니다.","확인");
        }

        private static void Build(bool replace)
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            { EditorUtility.DisplayDialog("HealthMon", "Play 모드를 종료한 뒤 실행하세요.","확인"); return; }
            Canvas canvas=FindMainCanvas();
            if(canvas==null)
            { EditorUtility.DisplayDialog("HealthMon", "MainARScene > UI > Canvas > HomePanel을 찾지 못했습니다.\nHomeBackgroundCanvas에는 생성하지 않습니다.","확인"); return; }
            bool hasOld=canvas.transform.Find("EvolutionOverlay")!=null || canvas.transform.Find("EvolutionUIManager")!=null;
            if(hasOld && !replace)
            { EditorUtility.DisplayDialog("HealthMon", "이미 진화 UI가 있습니다. '3. 진화 UI v3 디자인으로 교체'를 사용하세요.","확인"); return; }
            if(hasOld && replace && !EditorUtility.DisplayDialog("진화 UI v3 교체",
                "기존 Canvas의 EvolutionOverlay / EvolutionUIManager / DEV_EvolutionStartButton만 새 디자인으로 교체합니다.\n다른 게임 UI와 HomeWorld는 변경하지 않습니다.\n\n교체하기 전 씬을 백업해 두는 것을 권장합니다.","교체","취소")) return;

            int group=Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Create HealthMon Evolution UI v3");
            if(replace)
            {
                Kill(canvas.transform,"EvolutionOverlay");
                Kill(canvas.transform,"EvolutionUIManager");
                Kill(canvas.transform,"DEV_EvolutionStartButton (출시 전 숨김)");
                Kill(canvas.transform,"DEV_EvolutionStartButton");
            }
            projectKoreanFont = GuessKoreanFont(canvas);
            GameObject manager = new GameObject("EvolutionUIManager");
            manager.transform.SetParent(canvas.transform,false);
            Undo.RegisterCreatedObjectUndo(manager,"Evolution Manager");
            EvolutionUIController ctrl=manager.AddComponent<EvolutionUIController>();

            RectTransform test = RectAt("DEV_EvolutionStartButton (출시 전 숨김)",canvas.transform,
                new Vector2(.84f,.95f),new Vector2(200,66));
            Button start=CreateButton(test,"진화 TEST",EvolutionPanelGraphic.Theme.GhostButton,26,White);
            UnityEventTools.AddPersistentListener(start.onClick,ctrl.StartEvolution);

            RectTransform root=Stretch("EvolutionOverlay",canvas.transform);
            Undo.RegisterCreatedObjectUndo(root.gameObject,"Evolution Overlay");
            root.gameObject.AddComponent<CanvasGroup>();
            ctrl.evolutionOverlay=root.gameObject;
            // Background intercepts input intended for the underlying HomePanel.
            EvolutionBackdropGraphic backdrop=Graphic<EvolutionBackdropGraphic>(Stretch("Backdrop",root));
            backdrop.raycastTarget=true;
            RectTransform evolving=Stretch("EvolvingContent",root);
            ctrl.evolvingContent=evolving.gameObject;
            Txt("Brand",evolving,"✦  H E A L T H M O N  ✦",27,Muted,.5f,.952f,840,63,FontStyles.Normal);
            Txt("TitleText",evolving,"진화 중",82,White,.5f,.876f,830,133,FontStyles.Bold);
            Txt("SubtitleText",evolving,"새로운 모습을 생성하고 있어요...",34,Muted,.5f,.818f,920,92,FontStyles.Normal);

            RectTransform stage=RectAt("EvolutionStage",evolving,new Vector2(.5f,.561f),new Vector2(860,860));
            EvolutionAuraGraphic halo=Graphic<EvolutionAuraGraphic>(RectAt("EnergyAura",stage,new Vector2(.5f,.5f),new Vector2(800,800)));
            halo.floor=false;
            EvolutionAuraGraphic floor=Graphic<EvolutionAuraGraphic>(RectAt("EnergyPlatform",stage,new Vector2(.5f,.5f),new Vector2(765,400),new Vector2(0,-318)));
            floor.floor=true;
            EvolutionVortexGraphic vortexBack=Graphic<EvolutionVortexGraphic>(RectAt("VortexBack",stage,new Vector2(.5f,.5f),new Vector2(840,840)));
            vortexBack.FrontHalf=false;
            EvolutionOrbGraphic orbBack=Graphic<EvolutionOrbGraphic>(RectAt("SphereBack",stage,new Vector2(.5f,.5f),new Vector2(607,607)));
            orbBack.FrontGlass=false;
            RectTransform pet=RectAt("PetPreviewHolder",stage,new Vector2(.5f,.5f),new Vector2(380,390),new Vector2(0,-24));
            EvolutionPetGraphic petFallback=Graphic<EvolutionPetGraphic>(Stretch("PetPreviewFallback",pet));
            RawImage petRaw=Raw("PetPreview3D",pet);
            ctrl.petPreviewFallback=petFallback;
            ctrl.petPreview3D=petRaw;
            EvolutionOrbGraphic orbFront=Graphic<EvolutionOrbGraphic>(RectAt("SphereFrontGlass",stage,new Vector2(.5f,.5f),new Vector2(607,607)));
            orbFront.FrontGlass=true;
            EvolutionVortexGraphic vortexFront=Graphic<EvolutionVortexGraphic>(RectAt("VortexFront",stage,new Vector2(.5f,.5f),new Vector2(840,840)));
            vortexFront.FrontHalf=true;
            Graphic<EvolutionSparklesGraphic>(RectAt("Sparkles",stage,new Vector2(.5f,.5f),new Vector2(850,850)));
            EvolutionStageMotion motion=stage.gameObject.AddComponent<EvolutionStageMotion>();
            motion.petPreview=pet;
            motion.glow=halo.rectTransform;

            RectTransform status=RectAt("StatusBar",evolving,new Vector2(.5f,.313f),new Vector2(843,110));
            Panel(status,EvolutionPanelGraphic.Theme.Status,54);
            Txt("StatusText",status,"에너지 동기화 진행 중",37,White,.5f,.5f,810,100,FontStyles.Bold);
            ctrl.statusText=status.GetComponentInChildren<TMP_Text>(true);
            ctrl.elapsedText=Txt("ElapsedText",evolving,"경과 시간  00:00",36,Mint,.5f,.248f,720,80,FontStyles.Bold);

            RectTransform info=RectAt("InfoCard",evolving,new Vector2(.5f,.151f),new Vector2(922,172));
            Panel(info,EvolutionPanelGraphic.Theme.Hint,34);
            RectTransform chip=RectAt("AIIconBackground",info,new Vector2(.116f,.5f),new Vector2(112,112));
            Panel(chip,EvolutionPanelGraphic.Theme.Badge,28);
            Txt("AIIcon",chip,"AI",39,Mint,.5f,.5f,110,110,FontStyles.Bold);
            ctrl.tipText=Txt("TipText",info,"생성형 AI가 새로운 외형을 준비하고 있습니다.",30,White,.60f,.5f,690,126,FontStyles.Normal);

            RectTransform doneTest=RectAt("TestCompleteButton",evolving,new Vector2(.5f,.063f),new Vector2(570,113));
            Button finishButton=CreateButton(doneTest,"진화 완료 테스트",EvolutionPanelGraphic.Theme.MintButton,37,
                new Color(.035f,.19f,.24f,1));
            UnityEventTools.AddPersistentListener(finishButton.onClick,ctrl.CompleteEvolution);

            RectTransform completed=Stretch("CompletedContent",root);
            ctrl.completedContent=completed.gameObject;
            Graphic<EvolutionAuraGraphic>(RectAt("SuccessAura",completed,new Vector2(.5f,.52f),new Vector2(940,940)));
            Txt("SuccessTitle",completed,"진화 성공!",83,White,.5f,.854f,850,138,FontStyles.Bold);
            Txt("SuccessSubtitle",completed,"헬스몬이 새로운 모습으로 진화했어요!",35,Muted,.5f,.785f,1000,100,FontStyles.Normal);
            EvolutionOrbGraphic successOrb=Graphic<EvolutionOrbGraphic>(RectAt("SuccessBubble",completed,new Vector2(.5f,.53f),new Vector2(600,600)));
            successOrb.FrontGlass=false;
            RectTransform resultHolder=RectAt("ResultPetHolder",completed,new Vector2(.5f,.53f),new Vector2(390,390));
            ctrl.resultPreviewFallback=Graphic<EvolutionPetGraphic>(Stretch("ResultPreviewFallback",resultHolder));
            ctrl.resultPreview3D=Raw("ResultPreview3D",resultHolder);
            EvolutionOrbGraphic successGlass=Graphic<EvolutionOrbGraphic>(RectAt("SuccessGlass",completed,new Vector2(.5f,.53f),new Vector2(600,600)));
            successGlass.FrontGlass=true;
            Graphic<EvolutionSparklesGraphic>(RectAt("ResultSparkles",completed,new Vector2(.5f,.53f),new Vector2(830,830)));
            RectTransform successStatus=RectAt("SuccessStatus",completed,new Vector2(.5f,.294f),new Vector2(820,116));
            Panel(successStatus,EvolutionPanelGraphic.Theme.Status,52);
            Txt("SuccessMessage",successStatus,"새로운 헬스몬과 함께 모험을 계속해 봐요!",31,White,.5f,.5f,760,100,FontStyles.Normal);
            RectTransform homeBtn=RectAt("SuccessHomeButton",completed,new Vector2(.5f,.14f),new Vector2(680,131));
            Button home=CreateButton(homeBtn,"새로운 모습 확인하기",EvolutionPanelGraphic.Theme.MintButton,37,new Color(.03f,.20f,.25f,1));
            UnityEventTools.AddPersistentListener(home.onClick,ctrl.CloseEvolution);

            RectTransform error=Stretch("ErrorContent",root);
            ctrl.errorContent=error.gameObject;
            Txt("ErrorTitle",error,"진화를 완료하지 못했어요",58,White,.5f,.67f,950,140,FontStyles.Bold);
            ctrl.errorText=Txt("ErrorMessage",error,"네트워크 연결을 확인하고 다시 시도해 주세요.",34,Muted,.5f,.53f,970,210,FontStyles.Normal);
            RectTransform errorBtn=RectAt("ErrorCloseButton",error,new Vector2(.5f,.35f),new Vector2(670,125));
            Button errorClose=CreateButton(errorBtn,"홈으로 돌아가기",EvolutionPanelGraphic.Theme.GhostButton,37,White);
            UnityEventTools.AddPersistentListener(errorClose.onClick,ctrl.CloseEvolution);

            RectTransform flash=Stretch("FlashOverlay",root);
            Image flashImage=flash.gameObject.AddComponent<Image>();
            flashImage.color=Color.white;
            flashImage.raycastTarget=false;
            CanvasGroup groupFlash=flash.gameObject.AddComponent<CanvasGroup>();
            groupFlash.alpha=0f;
            groupFlash.blocksRaycasts=false;
            ctrl.flashCanvasGroup=groupFlash;

            completed.gameObject.SetActive(false);
            error.gameObject.SetActive(false);
            root.gameObject.SetActive(false);
            root.SetAsLastSibling();
            EditorUtility.SetDirty(ctrl);
            EditorSceneManager.MarkSceneDirty(canvas.gameObject.scene);
            Undo.CollapseUndoOperations(group);
            Selection.activeGameObject=root.gameObject;
            EditorUtility.DisplayDialog("HealthMon v3", "완료! UI > Canvas 아래에 진화 UI v3를 생성했어요.\n투명 구체, 회오리, 슬라임, 카드가 PNG 없이 표시됩니다.\nPlay ▶ '진화 TEST'로 확인하세요.","확인");
        }

        private static Canvas FindMainCanvas()
        {
            UnityEngine.SceneManagement.Scene scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            GameObject ui=GameObject.Find("UI");
            if(ui!=null && ui.scene==scene)
            {
                Transform c=ui.transform.Find("Canvas");
                if(c!=null && c.Find("HomePanel")!=null && c.GetComponent<Canvas>()!=null)
                    return c.GetComponent<Canvas>();
            }
            foreach(Canvas c in Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include,FindObjectsSortMode.None))
                if(c.gameObject.scene==scene && c.transform.Find("HomePanel")!=null) return c;
            return null;
        }
        private static TMP_FontAsset GuessKoreanFont(Canvas canvas)
        {
            Transform home=canvas.transform.Find("HomePanel");
            if(home==null) return null;
            TMP_Text[] texts=home.GetComponentsInChildren<TMP_Text>(true);
            foreach(TMP_Text t in texts) if(t.font!=null && t.font.HasCharacter('진')) return t.font;
            foreach(TMP_Text t in texts) if(t.font!=null) return t.font;
            return null;
        }
        private static void Kill(Transform parent,string name)
        {
            Transform item=parent.Find(name);
            if(item!=null) Undo.DestroyObjectImmediate(item.gameObject);
        }
        private static RectTransform Stretch(string name,Transform parent)
        {
            GameObject go=new GameObject(name,typeof(RectTransform));
            RectTransform r=go.GetComponent<RectTransform>();
            r.SetParent(parent,false);
            r.anchorMin=Vector2.zero; r.anchorMax=Vector2.one;
            r.offsetMin=r.offsetMax=Vector2.zero; r.localScale=Vector3.one;
            return r;
        }
        private static RectTransform RectAt(string name,Transform parent,Vector2 anchor,Vector2 size)
        { return RectAt(name,parent,anchor,size,Vector2.zero); }
        private static RectTransform RectAt(string name,Transform parent,Vector2 anchor,Vector2 size,Vector2 pos)
        {
            GameObject go=new GameObject(name,typeof(RectTransform));
            RectTransform r=go.GetComponent<RectTransform>();
            r.SetParent(parent,false); r.anchorMin=r.anchorMax=anchor;
            r.pivot=new Vector2(.5f,.5f); r.sizeDelta=size;
            r.anchoredPosition=pos; r.localScale=Vector3.one;
            return r;
        }
        private static T Graphic<T>(RectTransform r) where T:MaskableGraphic
        {
            T g=r.gameObject.AddComponent<T>();
            g.raycastTarget=false;
            return g;
        }
        private static EvolutionPanelGraphic Panel(RectTransform r,EvolutionPanelGraphic.Theme theme,float radius)
        {
            EvolutionPanelGraphic g=Graphic<EvolutionPanelGraphic>(r);g.theme=theme;g.radius=radius;g.SetVerticesDirty();return g;
        }
        private static RawImage Raw(string name,Transform parent)
        {
            RectTransform r=Stretch(name,parent);
            RawImage img=r.gameObject.AddComponent<RawImage>();
            img.texture=null;img.raycastTarget=false;img.enabled=false;return img;
        }
        private static TMP_Text Txt(string name,Transform parent,string text,float size,Color color,
            float x,float y,float w,float h,FontStyles style)
        {
            RectTransform r=RectAt(name,parent,new Vector2(x,y),new Vector2(w,h));
            TextMeshProUGUI label=r.gameObject.AddComponent<TextMeshProUGUI>();
            if(projectKoreanFont!=null) label.font=projectKoreanFont;
            label.text=text;label.fontSize=size;label.fontStyle=style;
            label.color=color;label.alignment=TextAlignmentOptions.Center;
            label.enableWordWrapping=true;label.overflowMode=TextOverflowModes.Overflow;
            label.raycastTarget=false;
            return label;
        }
        private static Button CreateButton(RectTransform r,string title,EvolutionPanelGraphic.Theme theme,
            float fontSize,Color fontColor)
        {
            EvolutionPanelGraphic panel=Panel(r,theme,62);panel.raycastTarget=true;
            Button button=r.gameObject.AddComponent<Button>();
            button.targetGraphic=panel;
            ColorBlock c=button.colors; c.normalColor=Color.white;
            c.highlightedColor=new Color(.92f,1f,1f,1);
            c.pressedColor=new Color(.75f,.91f,.90f,1);
            c.selectedColor=Color.white;button.colors=c;
            Txt("ButtonText",r,title,fontSize,fontColor,.5f,.5f,r.sizeDelta.x-22,r.sizeDelta.y-4,FontStyles.Bold);
            return button;
        }
    }
}
#endif
