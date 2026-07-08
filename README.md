<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_reread?name=astrbot_plugin_reread&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_reread

_✨ 复读插件 ✨_  

[![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-4.0%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-Zhalslar-blue)](https://github.com/Zhalslar)

</div>

## 🤝 介绍

不依赖任何数据库的群聊复读插件。

- 支持 **文本 / 图片 / 表情** 分别设置复读阈值  
- 支持 **总响应概率** 与 **动作权重**  
- 支持 **跟随 / 打断 / 禁言** 按权重随机触发  
- 可要求 **消息必须来自不同用户**  
- 仅处理 **单段消息**，逻辑清晰、行为可预期  
- 使用 **内容指纹幂等保护**，避免重复刷同一条复读  

## 📦 安装

在 AstrBot 插件市场搜索 **astrbot_plugin_reread**，点击安装即可。

## ⌨️ 配置

请前往插件配置面板进行配置。

主要配置项包括：

- `thresholds`：各消息类型的复读阈值  
- `reread_prob`：达到阈值后的总响应概率  
- `follow.weight`：跟随复读权重  
- `interrupt.weight` / `interrupt.text`：打断动作权重与打断文本  
- `ban.weight` / `ban.duration` / `ban.prompt`：禁言动作权重、时长与提示词  
- `need_different`：是否要求来自不同用户  
- `group_whitelist`：群白名单  

## ⚙️ 工作机制说明

- 每个群维护独立的复读状态（内存态，不落库）
- 按 **消息类型** 分别统计复读窗口
- 当窗口内消息：
  - 数量达到阈值
  - 内容指纹完全一致  
  才可能触发动作
- 达到阈值后先按 `reread_prob` 判定是否响应，再按动作权重随机触发跟随、打断或禁言
- Bot 会记录 **最近一次成功复读的内容指纹**：
  - 若下一次候选复读内容相同 → 自动跳过  
  - 无需冷却时间，行为稳定且可预测
- 图片判等优先使用 `file`，为空时自动退化为 `url / path`

## 👥 贡献指南

- 🌟 Star 本项目（感谢支持）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 复读阈值不建议设置过低，容易刷屏
- 插件只处理单段消息，多段消息会被忽略
- 想第一时间反馈问题可加入插件反馈群（QQ群）：  
  **460973561**（不点 Star 不给进）
