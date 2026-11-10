# 评估

实际执行：12 个 unittest 测试方法通过（含多场景子测试），11/11 离线验收通过。[测试日志](../examples/test-results.txt)、[完整用例输入、素材、输出和断言](../examples/mock-validation/REPORT.md)。首次真实运行在评估脚本处理空检查结果时中止，未保存有效用例输出。

| 验收点 | 输出和 Trace |
|---|---|
| 正常生成 | [normal](../examples/mock-validation/normal/output.json)：两镜、P01、总计28秒 |
| 缺关键信息 | [missing_input](../examples/mock-validation/missing_input/output.json)：缺 audience，明确请求补充 |
| 无素材 | [no_materials](../examples/mock-validation/no_materials/output.json)：检索为空，不编造 |
| 工具失败 | [tool_failure](../examples/mock-validation/tool_failure/output.json)、[estimate_failure](../examples/mock-validation/estimate_failure/output.json)：未称成功 |
| 超时长修正 | [overlong](../examples/mock-validation/overlong/output.json)：实际检查38秒→修改→28秒，重新检查规则 |
| 无依据结论 | [unsupported_claim](../examples/mock-validation/unsupported_claim/output.json)：删除效率80%并重新检查 |
| 改变目标 | [shorter_target](../examples/mock-validation/shorter_target/output.json)：10秒上限下修正为8秒 |
| 无法满足 | [impossible_target](../examples/mock-validation/impossible_target/output.json)：0.1秒无法容纳事实，未完成并请求补充 |
| 瞬时故障 | [transient_failure](../examples/mock-validation/transient_failure/output.json)：保留稿件并再次估时 |
| 替换素材 | [replaced_material](../examples/mock-validation/replaced_material/output.json)：事实随 P01 改为支持字幕导出 |

正常稿逐镜时长13.75秒、14.25秒，合计28秒；有较长画面停留，适合功能演示，不能据此宣称成片质量。超时长初稿为测试显式提供的草稿，Mock 修正为模板稿；不是已经证明真实模型生成38秒再压缩为28秒。

真实验证比较 normal 与 overlong/shorter_target 两种路径，核对修改后两种检查是否重新执行及引用事实是否正确。限制：中文定速粗估，不接 TTS、不渲染视频；平台与受众适配尚无人工质量评分；自由改写会被保守拒绝。

## 评估脚本修复

无时长或规则结果时，断言记录失败并保存输出，而不是访问空值而崩溃。复现检查确认失败记录可落盘。真实模型用例结果见下方记录。

## 2026-11-10 第二轮真实验收

[原始报告](../examples/live-20261110-150614/REPORT.md)。missing_input 通过，由本地输入校验拦截。normal 检索成功后，模型重复提交不符合工具参数结构的草稿，达到执行上限。no_materials 的模型响应无法解析。tool_failure 和 overlong 未执行。当前没有成功生成脚本的真实模型 Trace。

第三轮补测前修改：工具接受本轮模型实际发送的扁平草稿参数，进入同一套草稿、素材和时长校验。用 normal Trace 中的原始参数离线复现，草稿成功保存并通过检查。模型提示增加草稿格式和无素材时的动作示例。单个响应格式错误会记录后继续验收。真实补测待执行。

## 2026-11-10 第三轮真实验收

[原始报告](../examples/live-20261110-152533/REPORT.md)。no_materials 和 tool_failure 通过。normal 在检索后返回无效 JSON，overlong 估出 38 秒后返回无效 JSON，两项未完成。missing_input 的通过记录见第二轮。补测版本提供短参数的 compose_from_source 工具，由模型选已检索素材和停留时间，代码组装初稿，仍由模型发起时长和规则检查。此修改尚待真实补测。

## 2026-11-10 最终补测

[补测报告](../examples/live-20261110-153135/REPORT.md)。normal 和 overlong 均通过。结合前三项的原始通过记录，五项必验全部有通过证据。报告跨批次汇总，原有失败记录保留。

| 必验项 | 通过证据 |
|---|---|
| 正常生成 | [normal](../examples/live-20261110-153135/normal/output.json) |
| 缺关键信息 | [missing_input](../examples/live-20261110-150614/missing_input/output.json)，本地输入校验 |
| 无素材 | [no_materials](../examples/live-20261110-152533/no_materials/output.json) |
| 工具失败 | [tool_failure](../examples/live-20261110-152533/tool_failure/output.json) |
| 超时长修正 | [overlong](../examples/live-20261110-153135/overlong/output.json) |

normal 检索后由模型选择素材及停留时间，生成 2.5 秒草稿并通过检查。overlong 首次估算为 38 秒，超过 30 秒上限，模型选择重新组装草稿，随后对新版本重新执行规则与时长检查，最终为 2.5 秒。时长是粗估，验收条件为不超过目标上限。

终端脚本打印报告位置前误用了 zsh 只读变量 status。Python 已先写出两项原始报告和 Trace，故本轮结果有效。脚本变量已更名。
