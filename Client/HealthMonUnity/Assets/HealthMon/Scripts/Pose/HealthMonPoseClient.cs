using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

[Serializable] public sealed class PoseSnapshot
{
    public string session_id, exercise, message, phase, angle_text, body_assessment, jpeg_base64;
    public int count, left_count, right_count, sequence;
    public bool paused, tracked;
    public float processing_ms;
}
[Serializable] public sealed class PoseSessionRequest { public string exercise; public string squat_view="auto"; }
[Serializable] public sealed class PoseControlRequest { public string command; public bool paused; }

/// <summary>One request at a time; no camera frame queue, no automatic duplicate submissions.</summary>
public sealed class HealthMonPoseClient : MonoBehaviour
{
    public const string DefaultEndpoint="http://127.0.0.1:18095";
    private const string EndpointPreference="HealthMon.Pose.Endpoint";
    public string BaseUrl { get; private set; }=DefaultEndpoint;
    public static string ConfiguredEndpoint
    {
        get
        {
#if UNITY_EDITOR || DEVELOPMENT_BUILD
            if(TryNormalizeEndpoint(PlayerPrefs.GetString(EndpointPreference,DefaultEndpoint),out var endpoint))return endpoint;
#endif
            return DefaultEndpoint;
        }
    }
#if UNITY_EDITOR || DEVELOPMENT_BUILD
    public static bool SaveDevelopmentEndpoint(string address)
    {
        if(!TryNormalizeEndpoint(address,out var endpoint))return false;
        PlayerPrefs.SetString(EndpointPreference,endpoint);PlayerPrefs.Save();return true;
    }
#endif
    public bool Busy => active != null;
    private UnityWebRequest active;
    public bool Configure(string address)
    {
        if(!TryNormalizeEndpoint(address,out var endpoint))return false;
        BaseUrl=endpoint;return true;
    }
    private static bool TryNormalizeEndpoint(string address,out string endpoint)
    {
        endpoint=null;address=address?.Trim();
        if(!Uri.TryCreate(address,UriKind.Absolute,out var uri)||(uri.Scheme!="http"&&uri.Scheme!="https")||!string.IsNullOrEmpty(uri.UserInfo)||!string.IsNullOrEmpty(uri.Query)||!string.IsNullOrEmpty(uri.Fragment))return false;
        endpoint=address.TrimEnd('/');return true;
    }
    public IEnumerator Json(string method,string path,object payload,Action<PoseSnapshot,string> complete)
    {
        byte[] bytes=payload==null?null:Encoding.UTF8.GetBytes(JsonUtility.ToJson(payload));
        return Send(method,path,bytes,"application/json",complete);
    }
    public IEnumerator Frame(string session,int sequence,double timestamp,byte[] jpeg,Action<PoseSnapshot,string> complete)
    {
        var path="/sessions/"+session+"/frames?sequence="+sequence+"&timestamp="+timestamp.ToString("R",System.Globalization.CultureInfo.InvariantCulture);
        return Send("POST",path,jpeg,"image/jpeg",complete);
    }
    private IEnumerator Send(string method,string path,byte[] body,string contentType,Action<PoseSnapshot,string> complete)
    {
        if(active!=null) { complete(null,"처리 중 · 잠시 대기"); yield break; }
        using(var request=new UnityWebRequest(BaseUrl+path,method))
        {
            active=request; request.timeout=12; request.downloadHandler=new DownloadHandlerBuffer();
            if(body!=null) { request.uploadHandler=new UploadHandlerRaw(body); request.SetRequestHeader("Content-Type",contentType); }
            yield return request.SendWebRequest();
            if(active==request) active=null;
            if(request.result!=UnityWebRequest.Result.Success)
            {
                const string connectionError="연결 실패 · 잠시 후 재시도";
                complete(null,request.responseCode==404?"훈련 연결 만료 · 종료 후 새 훈련 시작":connectionError); yield break;
            }
            PoseSnapshot snapshot=null;
            try { snapshot=JsonUtility.FromJson<PoseSnapshot>(request.downloadHandler.text); } catch(ArgumentException) { }
            complete(snapshot,snapshot==null?"훈련 결과 수신 실패 · 재시도 필요":null);
        }
    }
    public void Abort() { if(active!=null) { active.Abort(); active=null; } }
    private void OnDestroy() { Abort(); }
}
