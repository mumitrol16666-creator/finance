$jdkPath = "C:\src\jdk17\jdk-17.0.19+10"
[Environment]::SetEnvironmentVariable("JAVA_HOME", $jdkPath, "User")
$oldPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($oldPath -notlike "*C:\src\jdk17\jdk-17.0.19+10*") {
    $newPath = "$jdkPath\bin;" + $oldPath
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
}
Write-Output "JAVA_HOME set to: $jdkPath"
