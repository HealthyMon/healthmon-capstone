#if UNITY_EDITOR
using System;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

public static class HealthMonPoseUIBuilder
{
    public static void BuildAndVerify() { Build(); HealthMonPoseVerification.Run(); }
    private const string Root="Assets/HealthMon/";
    [MenuItem("HealthMon/Pose/Rebuild exercise screen")]
    public static void Build()
    {
        var scene=EditorSceneManager.OpenScene(Root+"Scenes/MainARScene.unity");
        var canvas=GameObject.Find("UI/Canvas");if(canvas==null)throw new Exception("Main Canvas missing");
        var old=canvas.transform.Find("PosePanel");if(old!=null)UnityEngine.Object.DestroyImmediate(old.gameObject);
        var oldController=canvas.GetComponent<HealthMonPoseScreen>();if(oldController!=null)UnityEngine.Object.DestroyImmediate(oldController);
        var panel=new GameObject("PosePanel",typeof(RectTransform),typeof(HealthMonPoseView));panel.transform.SetParent(canvas.transform,false);
        var r=(RectTransform)panel.transform;r.anchorMin=Vector2.zero;r.anchorMax=Vector2.one;r.offsetMin=r.offsetMax=Vector2.zero;
        var view=panel.GetComponent<HealthMonPoseView>();
        view.font=AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(Root+"Shop/Fonts/HealthMonShop_KoreanDynamic.asset");
        view.background=Sprite("Backgrounds/BG_Wearable");view.card=Sprite("Cards/Card_Blue");view.lightCard=Sprite("Cards/Card_Sky");
        view.blueButton=Sprite("Buttons/BTN_Blue");view.mintButton=Sprite("Buttons/BTN_Mint");view.goldButton=Sprite("Buttons/BTN_Gold");
        var screen=canvas.AddComponent<HealthMonPoseScreen>();screen.view=view;
        var top=canvas.transform.Find("BottomNavV2/TopRow");if(top==null)throw new Exception("Navigation missing");
        var previous=top.Find("PoseButton");if(previous!=null)UnityEngine.Object.DestroyImmediate(previous.gameObject);
        var template=top.Find("FoodButton");if(template==null)throw new Exception("Navigation template missing");
        var entry=UnityEngine.Object.Instantiate(template.gameObject,top);entry.name="PoseButton";
        var button=entry.GetComponent<Button>();button.onClick=new Button.ButtonClickedEvent();UnityEventTools.AddPersistentListener(button.onClick,screen.Open);
        var label=entry.GetComponentInChildren<TMP_Text>(true);label.text="운동";label.font=view.font;
        foreach(var image in entry.GetComponentsInChildren<Image>(true))
            if(image.gameObject!=entry)UnityEngine.Object.DestroyImmediate(image.gameObject);
        var icon=new GameObject("PoseIcon",typeof(RectTransform),typeof(Image));icon.transform.SetParent(entry.transform,false);
        var iconRect=(RectTransform)icon.transform;iconRect.anchorMin=iconRect.anchorMax=new Vector2(.5f,1);iconRect.pivot=new Vector2(.5f,1);iconRect.sizeDelta=new Vector2(53,53);iconRect.anchoredPosition=new Vector2(0,-9);
        icon.GetComponent<Image>().sprite=AssetDatabase.LoadAssetAtPath<Sprite>(Root+"UIStyleKit/Sprites/Icons/Icon_Activity_Light.png");icon.GetComponent<Image>().preserveAspect=true;icon.GetComponent<Image>().raycastTarget=false;
        foreach(var text in top.GetComponentsInChildren<TMP_Text>(true)){text.fontSizeMax=30;text.fontSizeMin=20;text.enableAutoSizing=true;}
        EditorSceneManager.MarkSceneDirty(scene);EditorSceneManager.SaveScene(scene);AssetDatabase.SaveAssets();
        Debug.Log("HEALTHMON_POSE_UI_INSTALLED");
    }
    private static Sprite Sprite(string path)
    {var sprite=AssetDatabase.LoadAssetAtPath<Sprite>(Root+"UIStyleKit/UIStyleKitV3/Sprites/"+path+".png");if(sprite==null)throw new Exception("Missing style: "+path);return sprite;}
}
#endif
