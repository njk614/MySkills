# Skills

该目录用于存放完整 Skill 包。

当前目录包含：

- [luanyi_interactive_assistant](luanyi_interactive_assistant)：孪易交互助手 Skill 包
- [Skill-Creator](Skill-Creator)：Skill 创建与打包参考模板

## 完整 Skill 的推荐结构

```text
skill-name/
├── SKILL.md
├── references/
├── scripts/        # 可选
└── assets/         # 可选
```

## 当前孪易交互助手 Skill 结构

```text
luanyi_interactive_assistant/
├── SKILL.md
├── references/
│  ├── command-rules.md
│  └── integration.md
└── scripts/
   ├── invoke_skill.py
   ├── skill_runtime.py
   └── requirements.txt
```

## 说明

- `SKILL.md` 是完整 Skill 的核心入口文件。
- `references/` 中存放技能执行时需要按需读取的规则和集成资料。
- `scripts/` 中存放可执行实现，用于真正复刻工作流能力，而不是只保留说明文档。
- 当前 `luanyi_interactive_assistant` 已整理为“完整 Skill 包 + 可执行脚本实现”。

## 如果需要打包

可参考 [Skill-Creator](Skill-Creator/SKILL.md) 中的说明，使用其脚本进行校验与打包。
