# Rest Reminder

一个轻量的 Windows 休息提醒工具（Python + Tkinter）。

## 功能

- 默认每 20 分钟进行一次眼睛休息提醒。
- 默认每 2 小时进行一次强制休息提醒。
- 可自定义小提醒间隔、大提醒间隔和强制休息时长。
- 启动后会保存配置到 `config.json`。
- 新增副时钟（正计时），支持开启 / 暂停 / 清除计时。


## 运行

1. 确保安装 Python 3.10+（Windows 官方安装包通常可直接运行 Tkinter）。
2. 在项目目录执行：

```powershell
python .\rest_reminder.py
```

## 打包 exe（PyInstaller）

```powershell
python -m PyInstaller --noconfirm --clean RestReminder.spec
```

## 使用建议

- 小提醒建议 15~30 分钟。
- 大提醒建议 90~180 分钟。
- 强制休息时长建议 60~300 秒。

*Developed with ❤️ by Felix | 期待您的使用与反馈*
