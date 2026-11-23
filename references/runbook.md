# 从新素材到 UE 实拍

工具使用 Python 3.10+、Pillow、FFmpeg 和 ffprobe。UE 自带的 Python 只运行 `ue_stage.py` 与 `ue_preset.py`；外部视频处理用系统 Python。以下 PowerShell 变量换成当次实际路径。可以在含空格、中文的目录使用。

```powershell
$toolsDir = Join-Path $env:USERPROFILE '.codex/skills/ue-vfx-recreate/scripts'
$job = 'D:/VfxReview/IceRing/v01'
$editor = 'E:/UE_5.9/Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
$project = 'D:/VfxReview/ArtReview/ArtReview.uproject'
python "$toolsDir/vfx.py" prepare 'D:/References/ice-ring.mp4' $job
```

## 1. 准备参考

`$job` 必须是新目录。默认使用完整画面和视频实际帧率。用 `--crop X Y W H` 排除软件面板或鼠标以外的界面；坐标从显示画面左上角算起。用 `--start 35 --end 83` 取原片第 35 到 82 帧，输出重新从 0 编号。变帧率用 `--fps 30` 或 `--fps 24000/1001` 明确指定评审时钟。保留 `job.json`、`reference.mkv` 和 `keyframes.jpg`。遇到很短的闪光可用下面的命令放大任意一帧。

```powershell
ffmpeg -v error -n -i "$job/reference.mkv" -vf 'select=eq(n\,7)' -frames:v 1 "$job/frame-007.png"
```

单张图先记录尺寸、形态和颜色，按用户给定的时长或清楚标为假设的时长制作演示；单图只验收构图与材质。多个镜头按剪切点建立单独任务。

## 2. 在 UE 制作系统，搭建镜头

根据分类表创建 Niagara System、Emitter、材质、网格或后处理。在资产编辑器预览触发和复位，把最终使用的资产及依赖保存在评审工程。若用引擎模板，复制到项目的新资产目录后再调参。先匹配主轮廓、运动和寿命，再调贴图、颜色与泛光；从独立实拍判断效果。

正面固定镜头可编辑 `$job/stage.json` 后运行自动搭台。如下是一个中心触发的示例配置，`system` 指向这次实际制作的资产。`width_cm` 是镜头横向覆盖的世界宽度，`trigger_frame` 是 Sequencer 的激活帧。资产内部的延迟可能让首个可见帧更晚。光照敏感的 Mesh 和烟雾还需在生成的关卡里加灯与背景、匹配曝光。

```json
{
  "system": "/Game/Effects/IceRing/NS_IceRing",
  "package": "/Game/VfxReview/IceRing_v01",
  "width_cm": 500,
  "trigger_frame": 3,
  "position_keys": []
}
```

固定中心保持空数组。固定的偏心位置可用单键，例如 `[[0,92,54]]`。移动源可用 `[[0,92,54],[8,108,62],[16,140,77]]`，三个值依次为输出帧号、裁切后的像素 X 和 Y，键间作线性插值。按可见发射源取样，转折处增加键并回看；遮挡帧记录插值依据。此预览使用 XZ 平面和正交相机。镜头透视明显、源在深度方向运动、角色挂点、双端光束或屏幕空间效果，手动搭相应关卡和 Camera Cut，使用后面的通用出片步骤。

```powershell
python "$toolsDir/review.py" stage $job --editor $editor --project $project
python "$toolsDir/review.py" render $job --editor $editor --project $project --take Take01
```

`stage` 在指定新目录创建 `L_Review`、`LS_Review`，沿用任务帧数与分数帧率，绑定相机及 Niagara 生命周期。可以打开生成的关卡调整布景和相机。修改 `stage.json` 后要生成新的关卡版本才会更新；同一关卡内只调整粒子或材质时，直接换 take 重新渲染。`render` 创建该 take 的 MRQ 预设、离屏输出 PNG，再编码和对照。默认首帧无预热、时间采样 1，适合判断起效帧；若参考从稳定段开始，按原片准备同样的预卷。检查 `stage.log`、take 下的 `preset.log` 和 `render.log` 定位启动或编译问题。

## 3. 用已有 UE 镜头出片

自定义相机、动画和屏幕空间效果使用自己的地图或 Sequencer。渲染前先确认相机绑定、固定曝光、触发事件、输出分辨率和结束帧。可以在 Movie Render Queue 选 PNG，把文件名设为 `{frame_number_rel}`，放入本次新目录，关闭帧号偏移和 handles，输出从 0 开始。UI 若在最终效果中可见，选择能够捕获对应 UI 合成层的渲染方式。已有独立 UE 净版视频可以直接走 `compare`。

```powershell
python "$toolsDir/vfx.py" pack $job "$job/CustomTake/png" "$job/CustomTake/capture.mp4"
python "$toolsDir/vfx.py" compare $job "$job/CustomTake/capture.mp4" "$job/CustomTake/delivery"
```

`pack` 检查逐帧编号、总数与时间轴。`compare` 检查参考与实拍的帧率、每帧时间、帧数和宽高比。成功输出净版 `UE.mp4`、左参考右 UE 的 `comparison.mp4`、关键帧拼图和 `timing.json`。所有视频都是无音轨的视觉评审片。遇到录屏带开头空白、掉帧或长度不符，先回到源头修正取帧区间和捕获设置。对照中先看第一次出现与最后一次消失，再检查峰值、速度、轮廓和颜色。

## 4. 留下能接手的结果

将最终系统、材质及实例、评审关卡、序列和最佳 take 的路径写进 `match.md`，同时记下游戏端应如何触发或停止、能调整哪些参数，以及原片无法确认的部分。通过 UE 资产依赖检查后再迁移到已指定的游戏项目。每次新参考新建任务目录，可在同一评审工程内使用不同的资产目录。

