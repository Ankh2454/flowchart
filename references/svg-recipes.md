# 物件与 SVG 配方

## 使用材料

把 `assets/paper.css` 实际内联进 HTML 的 style，把 `assets/objects.svg` 中需要的
filter / symbol 复制到同一个根 SVG 的 defs。不要通过外链 use 引用文件。
样例 HTML 已全部内联；节点名称、路径、布局按新主题重算。

物件库是语汇，不是固定布局：document 文档，service 处理服务，store 存储，
queue 队列，person 人员，gate 分流/条件，event 事件，result 输出结果。
每个 symbol 的坐标为 0 0 160 160。实例可这样使用：

```html
<use href="#pc-store" x="420" y="260" width="160" height="160"/>
<text x="500" y="458" class="node-title">任务存储</text>
```

要动画某个内部部件，将 symbol 的内容展开为节点内的 g，再给部件包一层运动 g。
不要试图用 `.instance .part` 穿透 use 的影子树；同样，物件颜色在 symbol 内定义，
或使用可继承 CSS 变量。标题和说明放在运动 g 之外。

## 两层纸与折角

```html
<g filter="url(#pc-shadow)">
  <path d="M8 13 110 7 119 139 17 145Z" fill="#639e95"/>
  <path d="M15 5H90L116 31V134H15Z" fill="#fffdf4"/>
  <path d="M90 5V31H116Z" fill="#d7ddce"/>
</g>
```

filter 可单独施加在纸层上以得到层间接触阴影，避免在每个小细节上重复投影。
保留足够的 filter bounds，例如 -25% / 160%，防止边缘切掉阴影。
额外背衬必须表达层次或数量，不用十几张近似副本制造厚重 3D。

## 带方向的纸带与载荷

```html
<defs>
  <marker id="arrow" viewBox="0 0 20 22" refX="18" refY="11"
    markerWidth="20" markerHeight="22" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M0 0 20 11 0 22 5 11Z" fill="#e95b38"/>
  </marker>
  <g id="payload">
    <path d="M-12-9H7L12-4V9H-12Z" fill="#fffdf4" stroke="#203e43" stroke-width="1.2"/>
    <path d="M7-9V-4H12M-7-2H3M-7 3H6" fill="none" stroke="#203e43" stroke-width="1.2"/>
  </g>
</defs>
<path class="route" d="M250 350H420" stroke="#e95b38" marker-end="url(#arrow)"/>
<g class="ticket" style="offset-path:path('M250 350H420');--duration:3000ms">
  <use href="#payload"/>
</g>
```

路径先画、节点后画。SVG 的线与 CSS offset-path 坐标一致；调整锚点时两处一起改。
示例的配色写在 defs 内，避免 use 的内部元素变成黑块。
载荷与宽线的对比由纸白填充和深青细边保证。箭头条件不要叠在线上。

## 纸纹

用静态 feTurbulence，fixed seed，低透明度；既不逐帧改变 seed，也不动画噪声。
在复杂图或小尺寸图中直接省略。纸纹是最后一步，不是掩盖造型单薄的补丁。

## 输出文件骨架

完整 HTML 使用内联 SVG、CSS、可选的播放控制脚本。根 SVG 包含可访问的 title/desc。
`.canvas` 的 SVG viewBox 给出数值坐标，导出脚本据此固定尺寸，避免小视口改变 GIF 尺寸。
预览按钮置于 `.canvas` 外，标记 `data-preview-controls`；默认暂停/播放只控制 CSS 动画。
没有远程资源时，双击 HTML 即可离线使用。
