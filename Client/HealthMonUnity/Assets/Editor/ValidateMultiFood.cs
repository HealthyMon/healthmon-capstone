using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class ValidateMultiFood
{
    public static void Run()
    {
        try
        {
            var scene=EditorSceneManager.OpenScene("Assets/HealthMon/Scenes/MainARScene.unity");
            var panels=UnityEngine.Object.FindObjectsByType<MultiFoodScanPanel>(FindObjectsInactive.Include);
            if(panels.Length!=1||panels[0].gameObject.name!="FoodScanPanel")throw new Exception("Scene panel binding failed");
            var so=new SerializedObject(panels[0]);
            if(so.FindProperty("cameraCapture").objectReferenceValue==null)throw new Exception("Camera binding missing");
            foreach(var legacy in UnityEngine.Object.FindObjectsByType<FoodScanPrototype>(FindObjectsInactive.Include))
                if(legacy.enabled)throw new Exception("Legacy scanner is still enabled");
            var args=Environment.GetCommandLineArgs();
            int at=Array.IndexOf(args,"-visionResponse");
            if(at<0)throw new Exception("Missing actual API response fixture");
            var data=JsonUtility.FromJson<VisionAnalysis>(File.ReadAllText(args[at+1]));
            MultiFoodScanPanel.Validate(data);
            foreach(var food in data.foods)
            {
                MultiFoodScanPanel.Recalculate(food);
                if(!food.has_weight||food.grams<=0)throw new Exception("Missing weight");
                float initial=food.nutrients.calories;
                food.grams*=2;MultiFoodScanPanel.Recalculate(food);
                if(Math.Abs(food.nutrients.calories-2*initial)>.01)throw new Exception("Mass scaling failed");
            }
            Debug.Log("MULTIFOOD_VALIDATION_OK: scene binding, camera, API JSON, "+data.foods.Length+" foods, nutrition scaling");
            EditorApplication.Exit(0);
        }
        catch(Exception ex){Debug.LogException(ex);EditorApplication.Exit(1);}
    }
}
