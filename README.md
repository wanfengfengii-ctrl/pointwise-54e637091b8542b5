# 北岸自然史馆标本标签资料室

虚构的北岸自然史馆用此工作台登记馆藏标签、交付离线校对单并重发目录。馆藏组提供带批号和行号的原始字节。编目组按交班清册领取，接班人可用旧件与回执核账。外观相同的标签可能是不同原行，也可能用了不同的 UTF-8 拼写。

## 一天的工作

1. 接收员提交有序批次。每条记录带行号及原始字节。
2. 工作台一次登记原行、标本、初始修订及当前指针。接收员按标本号和指定修订号冻结原件。
3. 编目组申请发行固定校对单。校对员在规范视图中核对重音所指的原字符和产物。
4. 校对员离线保存校对号，按旧视图填写替换或删除区间。
5. 档案员按校对号读取当时签发的单据，核对当前资格、编辑范围和原文可回写性。
6. 合法勘误同时提交新原文、父修订、当前指针和成功回执。
7. 编目组提交有序清册，工作台固定每个位置的修订、原行和适用回执。
8. 接班人按目录号、修订号或回执号领取当时的成果。

## 运行

使用 Python 3.11 标准库与 SQLite。每次打开资料室会补齐持久结构，已有数据和用户更正继续可领。演示使用临时资料室，并通过真实入库导入 `samples/batch.json`。平台物化时提供标准回归入口。

```text
python3 -B check_project.py
python3 -B -m unittest discover -v
python3 -B -m catalog.workroom demo
```

演示对照 `samples/corrections.json` 核对实际单据，比较两种等价拼写的签收结果，再重开数据库读取旧目录、新目录与回执。成功输出包括原始输入、独立预期、实际重发结果和下游结果，以及实际 Python 和 Unicode 数据版本。业务检查失败时退出码为非零。

## 命令与 Python API

资料室操作采用 `python3 -B -m catalog.workroom --db workroom.sqlite3 <操作>`。正常输出为 JSON，字节字段用十六进制，错误输出到标准错误流并返回非零退出码。

| 操作 | 命令参数 | Python 入口 | 成果 |
| --- | --- | --- | --- |
| 导入 | `import samples/batch.json` | `intake.batches.import_batch(db, batch_id, records)` | 批次及按输入次序的原行、标本号和初始修订号 |
| 冻结 | `freeze 3 3` | `revision.freeze.freeze_revision(db, label_id, revision_id)` | 标本、固定修订及原字节 |
| 领单 | `issue 3 3` | `issue.proof_sheet.issue_proof_sheet(db, frozen)` | 固定校对号、视图和逐出现出处 |
| 复领单据 | `sheet 1` | `issue.issued_sheets.get_issued_sheet(db, sheet_id)` | 当时签发的固定单据 |
| 签收勘误 | `apply request.json` | `correction.settlement.apply_correction(db, request)` | 新修订及原字节、规范视图和回执 |
| 发布目录 | `publish roster.json` | `catalog.manifests.publish_manifest(db, roster)` | 目录号及有序的固定条目 |
| 历史领取 | `read manifest 1`、`read revision 3`、`read receipt 1` | `catalog.historical_delivery.read_delivery(db, kind, number)` | 固定目录、修订或回执及其来源 |

Python 调用方用 `catalog.workroom.open_workroom(path)` 取得连接并负责关闭。公开写入操作拥有各自的事务，调用时传入空闲连接。`catalog.workroom.initialize_workroom(db)` 可在空闲连接上重复执行。`import_batch` 的 `records` 是按提交顺序排列的 `(row_number, original_bytes)` 对。批号是非空 UTF-8 文本，行号及记录编号是正的 SQLite 整数。标签字节严格解码，允许空字节串、同文异行和显式空批次。重用批号、批内重复行号、坏字节或缺失字段会拒绝整批。冻结要求标本和修订匹配。`issue.offline_delivery` 提供 `encode_proof_sheet` 与 `decode_proof_sheet`，档案员按档案中已签发的校对号处理请求。

### 规范视图与勘误

视图是按运行环境 Unicode 数据表计算的 NFD 字符串。位置以零基 Unicode 码点计量，编辑使用半开区间。出处使用零基原 UTF-8 字节半开区间及原字符内的零基 NFD 产物序号。组合类为零的出现形成重排边界。同类产物保持顺序。例如 `é` 加独立下加点的视图为 `e`、下加点、锐音。锐音处于 `[2,3)`，其原始区间为 `[0,2)`，产物序号为 `1`。下加点处于 `[1,2)`，其原始区间为 `[2,4)`，产物序号为 `0`。

可勘误字段的视图由一个底字及随后的 Unicode 组合标记组成。空标签或普通多底字标签仍可领单和编目。一次勘误至少提供一个有效编辑。编辑区间须落在旧视图的组合标记上，互不重叠。替换文字分解后只能贡献组合标记，空字符串表示删除。工作台在同一旧视图中应用整组编辑，再对结果一同做规范重排。回写须保全未触及原字符的确切字节及相对次序，保全被触及原字符中的底字和未改产物身份，并能重发出目标视图。系统可移动需改写的重音。

例如在干净数据库导入样例并为第 3 件标本的初始修订首次领单后，可把以下内容保存为 `request.json` 并签收。`samples/corrections.json` 包含同一请求和独立列出的固定单据。

```json
{"sheet_id": 1, "edits": [{"start": 2, "end": 3, "replacement": "\u0300"}]}
```

签收生成 `e`、下加点、重音。原下加点的字节可在新原文中核查。改为编辑 `[1,2)` 时，预组原件无法在保全 `é` 的前提下重发目标，因此拒绝。分解原件可以签收同一编辑。

Python 中用 `CorrectionRequest(sheet_id, (AccentEdit(start, end, replacement), ...))` 表示请求。格式错误为 `ValueError`，未知的合法编号为 `KeyError`，过期与不可回写分别为 `StaleSheet` 和 `UnwritableCorrection`。旧单仍可复领。SQLite 提交失败会传播数据库错误并回滚。集成验证可通过 `before_commit(db)` 在本次全部持久写入之后、提交之前施加数据库条件。该钩子在签存的事务中运行，不管理连接或事务。

### 清册与按号核账

`roster.json` 是标本号码组成的 JSON 数组，例如 `[3, 5, 1]`。顺序及重复位置逐一固定，显式 `[]` 发布空清册。缺少清册、无效清册或未知标本会拒绝发布，原目录仍可领取。目录领取按其固定修订号返回当时的字节和原行。初始修订的回执为空。回执固定校对号、父修订和后继修订，并可复领这三个关联件。
