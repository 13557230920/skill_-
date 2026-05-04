【可选：参考 PNG → 烘焙 GIF】
擂台页主界面为 **全程序 Canvas 像素**，不依赖底图 `<img>`。

若仍需要从豆包稿等 PNG 生成循环 GIF（演示视频、飞书附件等）：
1) 将 PNG 放到本目录（推荐文件名）：
   arena-reference.png
   或 financial-arena-reference.png / arena-banner.png / 金融Skill创新方向.png

2) 在 skill 根目录执行（默认整图推拉循环，输出 web/generated/arena-poster.gif）：
   pip install -r requirements.txt
   python scripts/bake_reference_gif.py -i assets/arena-reference.png

   轻微呼吸旧效果：加 --preset idle
   指定输出：-o web/generated/poster-idle.gif
