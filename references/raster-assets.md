# 平面剪纸素材库

## 选择合适的素材

素材库共 24 项：`assets/objects.svg` 中 8 个可编辑基础物件，以及
`assets/raster/` 中 16 个经过色板归一和透明处理的 512 × 512 PNG。
浏览 [素材库](../examples/material-library.html)，使用 `catalog.json` 的 id、名称和 tags 检索。
PNG 中主要图形约占 384px，四周留出统一安全边距；布局时连线接到实际轮廓附近，
而不是把 512px 透明外框误当物件边界。

| 用途 | PNG ID |
| --- | --- |
| 云服务、数据库、网关、上传导入、下载导出 | cloud-service / database / api-gateway / upload / download |
| AI、权限、检索、分析 | ai-chip / secure-access / document-search / analytics |
| 通知、定时、分支、重试 | notification / scheduler / branch / retry |
| 部署、归档、团队协作 | deployment / archive / collaboration |

库内图是节点插画，不能替代图中真实的连线和分支条件。
若一个概念已经有合适素材，直接复用；不要为了装饰加入不存在的系统组件。

## 与 SVG 一起使用

把 PNG 转成 data URI，再嵌入最终 SVG，保持单文件离线能力：

```python
import base64
from pathlib import Path
asset = Path('assets/raster/ai-chip.png')
uri = 'data:image/png;base64,' + base64.b64encode(asset.read_bytes()).decode()
# 在最终 SVG 中写入实际 uri：<image href="..." x="..." y="..." width="..." height="..."/>
```

通常显示为 160–220 CSS px。标签、连线、载荷、徽标继续用 SVG/CSS 绘制。
PNG 是一张合并后的位图，不具备独立纸层：不要承诺能直接动画内部零件。
需要压印、翻页等部件动作时，使用可编辑 SVG 或按素材轮廓重建必要图层。
可轻微移动整张插画或叠加状态标记，但不要让所有节点一起无意义地漂浮。

## 已验证的生成方向

用户确认的方向是 **flat 2D vector illustration / precise SVG-like geometry / paper-cut graphic design**。
强调纯色色块、两三层薄片、精确边缘、正面投影、少量短阴影和图标级可读性。
不要用 real cardstock、visible paper fibers、studio photography、realistic lighting 等描述，
它们会把图推向纸艺摄影，与原版不一致。生成图不包含标签，文字由 SVG 单独排版。

完整的每项提示词、seed、尺寸与步数保存于 `assets/raster/catalog.json`。
本批使用用户提供的本地图像服务，模型 `flux2-klein-4b`，768 × 768，4 步。
不是内置 image_gen 生成；成品额外经过固定色板归一、背景移除、短投影重建、统一留白和缩放。
同一 seed 便于记录来源，不保证跨模型版本与运行环境逐像素复现。

## 可选：用同一接口扩展

现有 PNG 不需要模型、API 或 Python。仅重新生成/处理素材时，需要 Python 3 与可用的服务。
服务需支持 `POST /v1/jobs`、`GET /v1/jobs/{id}`、`GET /v1/jobs/{id}/file`；请求为
`kind=image`、prompt、seed、width、height、steps。成功状态为 succeeded，响应文件为 PNG。
其他接口按实际文档适配，不将本机地址当成其他人的默认依赖。

```bash
python3 scripts/generate-assets.py --api-base http://127.0.0.1:8120 --out out/raw --only ai-chip
python3 -m pip install -r scripts/requirements-assets.txt
python3 scripts/normalize-assets.py --raw out/raw --out out/normalized --only ai-chip
```

生成脚本串行提交任务，保存原图与 job 回执。中断后运行相同命令，会继续等待已有任务或跳过
已下载文件，不重复生成；请求修改后使用新的输出目录。服务任务过期时应使用新的输出目录重新生成。
不把 raw 图、任务回执或服务地址写进交付图。

色板处理使用本次校准图测得的颜色锚点，可通过单个素材的 `paletteSamples` 增加
`source` / `target` 色值。它适用于这套纯色插画，不能拿来抠照片、任意背景或保留细腻透明材质。

## 入库验收

先比较原图与处理后图片，再放到原版 SVG 旁边，在 160px 和 512px 下检查：

- 造型含义明确，没有错误箭头、伪文字、多余物件、裁切或粘连。
- 颜色与原版一致；色板处理没有吞掉主体、把同一色块切成噪点或产生锯齿。
- 透明背景、内部孔洞和边缘正确，没有残留大矩形或彩色光晕。
- 纸层和投影克制；与原版并排时，不出现摄影质感、厚重立体感或过度复杂的细节。

处理脚本只检查尺寸和边界等机械条件，无法判断造型是否合格。视觉检查通过后才把 PNG
复制到 `assets/raster/`，同时更新目录、预览和示例。不要仅以文件生成成功作为入库标准。
