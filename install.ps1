# demo-video-maker 一键安装（Windows PowerShell）
# 用法：
#   .\install.ps1                       # 装到默认位置
#   .\install.ps1 -Target "D:\skills\demo-video-maker"
# 若提示脚本被禁止运行，先执行：
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

param(
    [string]$Target = "$env:USERPROFILE\.workbuddy\skills\demo-video-maker"
)

$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot

# 这些是运行产物/仓库元数据，任意层级都不装进 skill 目录
$skipDirs = @('.git', '__pycache__', '_segs', '_frames', '_voice', '_selftest', '_chk', '输出', 'tools', '.venv', 'venv')

# 递归拷贝，逐项过滤，避免 Copy-Item -Recurse 把 __pycache__ 一并带过去
function Copy-SkillTree($from, $to) {
    New-Item -ItemType Directory -Path $to -Force | Out-Null
    foreach ($item in Get-ChildItem $from -Force) {
        if ($skipDirs -contains $item.Name) { continue }
        $dest = Join-Path $to $item.Name
        if ($item.PSIsContainer) {
            Copy-SkillTree $item.FullName $dest
        } elseif ($item.Extension -ne '.pyc') {
            Copy-Item $item.FullName $dest -Force
        }
    }
}

$parent = Split-Path -Parent $Target
if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }
Copy-SkillTree $src $Target

Write-Host "skill 已安装到: $Target" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:"
Write-Host "  1) 装依赖:  pip install -r `"$Target\requirements.txt`""
Write-Host "  2) 准备 ffmpeg（三选一）:"
Write-Host "     - 设环境变量 WB_FFMPEG_BIN 指向 ffmpeg 的 bin 目录"
Write-Host "     - 放到工作目录 tools\ffmpeg-9.0.2-essentials_build\bin\"
Write-Host "     - 安装到系统 PATH"
Write-Host "  3) 在对话里说关键词「演示视频流水线」即可触发"
