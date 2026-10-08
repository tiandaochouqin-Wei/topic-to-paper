# 投稿包清单

期刊：
Guide for Authors 日期：

## 文件
- [ ] 正文（格式按 guide：md→LaTeX/DOCX/PDF）
- [ ] 盲稿（如 blind=true）
- [ ] 标题页（作者、单位、邮箱、ORCID、通讯作者）
- [ ] Cover letter
- [ ] Highlights（条数与字数按 guide）
- [ ] 图源文件（格式、dpi 按 guide）
- [ ] 补充材料
- [ ] 数据可用性声明
- [ ] 利益冲突声明
- [ ] 作者贡献（CRediT）
- [ ] 源文件（LaTeX/DOCX，首投是否要求见 guide）

## 一致性（gate_check.py submission 自动查，此处人工复核）
- [ ] 标题页标题 = 正文标题
- [ ] Cover letter 中的数字全部出现在正文
- [ ] Highlights 中的数字全部出现在正文
- [ ] 盲稿 grep 作者姓/单位/邮箱/基金号/"our previous"/"we previously" 为空
- [ ] 关键词数 ≤ keyword_max
- [ ] 参考文献数 ≤ ref_max
- [ ] 字数/页数 ≤ 上限

## 最后
- [ ] gate_check.py all 全绿，gate_report.md 日期为今天
- [ ] research-state.yaml gates.G0–G8 全部 pass
