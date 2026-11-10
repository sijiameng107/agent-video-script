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

无时长或规则结果时，断言记录失败并保存输出，而不是访问空值而崩溃。复现检查确认失败记录可落盘。真实模型五项必验用例待补测。
