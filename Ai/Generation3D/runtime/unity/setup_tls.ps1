param([string]$RuntimeRoot = 'E:/qwen-llm/healthmon-generation3d/Ai/Generation3D')
$ErrorActionPreference='Stop'
$directory=Join-Path $RuntimeRoot 'outputs/unity_service/tls'
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$certificateFile=Join-Path $directory 'localhost.crt'
$keyFile=Join-Path $directory 'localhost.key'
if (-not (Test-Path -LiteralPath $certificateFile)) {
    $rsa=[System.Security.Cryptography.RSA]::Create(2048)
    $request=[System.Security.Cryptography.X509Certificates.CertificateRequest]::new('CN=localhost',$rsa,[System.Security.Cryptography.HashAlgorithmName]::SHA256,[System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $san=[System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
    $san.AddDnsName('localhost')
    $san.AddIpAddress([System.Net.IPAddress]::Parse('127.0.0.1'))
    $request.CertificateExtensions.Add($san.Build())
    $certificate=$request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1),[DateTimeOffset]::UtcNow.AddDays(90))
    [IO.File]::WriteAllText($certificateFile,$certificate.ExportCertificatePem())
    [IO.File]::WriteAllText($keyFile,$rsa.ExportPkcs8PrivateKeyPem())
    $rsa.Dispose()
} else {
    $certificate=[System.Security.Cryptography.X509Certificates.X509Certificate2]::CreateFromPemFile($certificateFile,$keyFile)
}
$pin=[Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($certificate.RawData)).ToLowerInvariant()
$settingsFile=Join-Path $PSScriptRoot 'HealthMonEvolution.json'
$settings=Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
$settings | Add-Member -NotePropertyName certificate_sha256 -NotePropertyValue $pin -Force
$localSettings=Join-Path $directory 'unity-settings.json'
$settings | ConvertTo-Json | Set-Content -LiteralPath $localSettings -Encoding utf8
Write-Output ('HTTPS localhost certificate configured; SHA256 pin '+$pin)
