# P6-人味 A/B 对比: 基线 vs 反机械改版

改版运行次数 n = 2(基线 n=1)


⚠ 所有 proxy 指标(disclaimer): 仅作趋势参考,不代表人味/AI 味判定。
⚠ n 小,只看方向,不下幅度结论(§4)。

## 章节指标升降表

| 章 | 指标 | 基线 | 改版(均值) | Δ | 方向 |
|---|---|---|---|---|---|
| T1 | exclaim_per_1k | 0.000 | 0.000 | →0.000 | → |
| T1 | dash_per_1k | 0.600 | 0.389 | ↓0.211 | ↓ |
| T1 | long_unpunct_sent_ratio | 0.000 | 0.000 | →0.000 | → |
| T1 | long_para_ratio | 0.000 | 0.002 | ↑0.002 | ↑ |
| T1 | modifier_density | 1.399 | 0.777 | ↓0.622 | ↓ |
| T1 | parallel_uniform_ratio | 0.157 | 0.159 | ↑0.002 | ↑ |
| T1 | idiom_density | 0.000 | 0.000 | →0.000 | → |
| T1 | raw4_density | 206.435 | 199.633 | ↓6.802 | ↓ |
| T2 | exclaim_per_1k | 0.000 | 0.000 | →0.000 | → |
| T2 | dash_per_1k | 0.000 | 0.000 | →0.000 | → |
| T2 | long_unpunct_sent_ratio | 0.000 | 0.000 | →0.000 | → |
| T2 | long_para_ratio | 0.000 | 0.000 | →0.000 | → |
| T2 | modifier_density | 0.632 | 0.834 | ↑0.202 | ↑ |
| T2 | parallel_uniform_ratio | 0.093 | 0.165 | ↑0.072 | ↑ |
| T2 | idiom_density | 0.000 | 0.084 | ↑0.084 | ↑ |
| T2 | raw4_density | 201.581 | 202.148 | ↑0.567 | ↑ |
| T3 | exclaim_per_1k | 0.000 | 0.000 | →0.000 | → |
| T3 | dash_per_1k | 0.377 | 0.077 | ↓0.300 | ↓ |
| T3 | long_unpunct_sent_ratio | 0.000 | 0.000 | →0.000 | → |
| T3 | long_para_ratio | 0.000 | 0.013 | ↑0.013 | ↑ |
| T3 | modifier_density | 0.754 | 1.168 | ↑0.414 | ↑ |
| T3 | parallel_uniform_ratio | 0.104 | 0.114 | ↑0.011 | ↑ |
| T3 | idiom_density | 0.126 | 0.077 | ↓0.049 | ↓ |
| T3 | raw4_density | 204.774 | 202.236 | ↓2.538 | ↓ |

## 代偿自检(降 A 升 B?)

期望: 改版降 exclaim/dash/idiom(反机械约束直击的目标)。
警惕: 同时升 modifier/parallel(代偿借尸还魂,文风变本加厉 AI 味)。

### T1
- 期望降(exclaim_per_1k,dash_per_1k,idiom_density): 实际降 ['dash_per_1k']
- 警惕升(modifier_density,parallel_uniform_ratio,raw4_density): 实际升 ['parallel_uniform_ratio']
- ⚠ **代偿信号**: 同时降 ['dash_per_1k'] 升 ['parallel_uniform_ratio'] —— 反机械约束可能挤压到其他维度,需人工核验正文样本。

### T2
- 期望降(exclaim_per_1k,dash_per_1k,idiom_density): 实际降 (无)
- 警惕升(modifier_density,parallel_uniform_ratio,raw4_density): 实际升 ['modifier_density', 'parallel_uniform_ratio', 'raw4_density']

### T3
- 期望降(exclaim_per_1k,dash_per_1k,idiom_density): 实际降 ['dash_per_1k', 'idiom_density']
- 警惕升(modifier_density,parallel_uniform_ratio,raw4_density): 实际升 ['modifier_density', 'parallel_uniform_ratio']
- ⚠ **代偿信号**: 同时降 ['dash_per_1k', 'idiom_density'] 升 ['modifier_density', 'parallel_uniform_ratio'] —— 反机械约束可能挤压到其他维度,需人工核验正文样本。
