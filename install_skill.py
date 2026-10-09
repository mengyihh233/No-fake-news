"""Install this project's portable Skill without overwriting existing skills."""
import os
import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description="Install tell-me-truth / 安装 Skill / Skill をインストール")
    parser.add_argument("--language", choices=("zh-CN", "en", "ja"), default="zh-CN",
                        help="Message language / 提示语言 / メッセージの言語")
    language = parser.parse_args().language
    messages = {
        "zh-CN": ("Skill 已存在：{path}\n已保留现有文件。", "已安装 tell-me-truth：{path}\n请新建聊天或重新加载 Skills。"),
        "en": ("Skill already exists: {path}\nExisting files were preserved.", "Installed tell-me-truth: {path}\nStart a new chat or reload skills."),
        "ja": ("Skill は既に存在します：{path}\n既存のファイルを保持しました。", "tell-me-truth をインストールしました：{path}\n新しいチャットを開始するか、Skills を再読み込みしてください。"),
    }
    source = Path(__file__).resolve().parent / "skills" / "tell-me-truth"
    codex_dir = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    target = codex_dir / "skills" / "tell-me-truth"
    if target.exists():
        print(messages[language][0].format(path=target))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(messages[language][1].format(path=target))


if __name__ == "__main__":
    main()
