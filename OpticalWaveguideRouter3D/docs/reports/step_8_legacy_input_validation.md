# Step 8 前代输入验证报告

## 环境
Python 3.10.11；项目虚拟环境 openpyxl 3.1.5，必要依赖 et-xmlfile 2.0.0。未安装 pandas 或 pytest；直接调用测试函数。requirements.txt 未修改，复现环境须安装 openpyxl。

## 实际结构与规则
两个工作簿均仅有 Sheet1，第 1 行为 Port1/Port2，无标题、说明或空白数据行。256 文件两列均为数值；512 文件前 256 行为数值，后 256 行共 512 个公式单元格（例如 =A2 + 60、=B2 + 60），均有整数缓存结果。

解析采用 openpyxl 的只读缓存值，并读取原始值辨别真正空白行。不会执行或重算公式；无法保证缓存相对于外部编辑永远最新。无缓存公式、非整数、字符串（包括数字字符串）、布尔值、单侧缺值均报错；完全空白行跳过。1.0 接受。单工作表和首行唯一 Port1/Port2 为显式支持的结构，其他布局报错而不猜测。

## 对象语义
每个有效行生成独立 Waveguide，保持 start/end 顺序，重复行不去重。Waveguide ID 从 0 顺序编号，Port ID 为 2*i 和 2*i+1，在单个导入数据集中全局唯一且稳定；两个文件 ID 空间独立，不能直接合并而不重编号。local_id 和 position 均为 None。

## fiberBoard256.xlsx

```json
{
  "file": "C:\\Users\\lihao\\Desktop\\Graduation Project\\自动排布\\AutoRouter\\fiberBoard256.xlsx",
  "valid_rows": 256,
  "waveguides": 256,
  "pmt_count": 32,
  "pmt_min": 1,
  "pmt_max": 58,
  "self_connections": 0,
  "duplicate_undirected_pairs": 67,
  "extra_pair_rows": 134,
  "duplicate_examples": [
    [
      [
        1,
        8
      ],
      2
    ],
    [
      [
        1,
        9
      ],
      2
    ],
    [
      [
        1,
        26
      ],
      5
    ],
    [
      [
        1,
        58
      ],
      3
    ],
    [
      [
        2,
        11
      ],
      4
    ],
    [
      [
        2,
        21
      ],
      4
    ],
    [
      [
        2,
        56
      ],
      7
    ],
    [
      [
        6,
        8
      ],
      2
    ]
  ],
  "endpoint_counts": {
    "1": 16,
    "2": 16,
    "6": 16,
    "8": 16,
    "9": 16,
    "10": 16,
    "11": 16,
    "12": 16,
    "13": 16,
    "14": 16,
    "16": 16,
    "17": 16,
    "18": 16,
    "19": 16,
    "20": 16,
    "21": 16,
    "24": 16,
    "26": 16,
    "29": 16,
    "33": 16,
    "38": 16,
    "39": 16,
    "41": 16,
    "47": 16,
    "48": 16,
    "49": 16,
    "51": 16,
    "53": 16,
    "54": 16,
    "56": 16,
    "57": 16,
    "58": 16
  },
  "sheets": [
    "Sheet1"
  ],
  "used_sheet": "Sheet1",
  "header_row": 1,
  "headers": [
    "Port1",
    "Port2"
  ],
  "blank_rows": 0,
  "raw_cell_types": {
    "n": 512
  },
  "sha256_unchanged": "50dadf81426b3a1e56b67ff827809c4a3ab4af92e9b05da411072f850cce9a8b"
}
```

## fiberBoard512.xlsx

```json
{
  "file": "C:\\Users\\lihao\\Desktop\\Graduation Project\\自动排布\\AutoRouter\\fiberBoard512.xlsx",
  "valid_rows": 512,
  "waveguides": 512,
  "pmt_count": 64,
  "pmt_min": 1,
  "pmt_max": 118,
  "self_connections": 0,
  "duplicate_undirected_pairs": 134,
  "extra_pair_rows": 268,
  "duplicate_examples": [
    [
      [
        1,
        8
      ],
      2
    ],
    [
      [
        1,
        9
      ],
      2
    ],
    [
      [
        1,
        26
      ],
      5
    ],
    [
      [
        1,
        58
      ],
      3
    ],
    [
      [
        2,
        11
      ],
      4
    ],
    [
      [
        2,
        21
      ],
      4
    ],
    [
      [
        2,
        56
      ],
      7
    ],
    [
      [
        6,
        8
      ],
      2
    ]
  ],
  "endpoint_counts": {
    "1": 16,
    "2": 16,
    "6": 16,
    "8": 16,
    "9": 16,
    "10": 16,
    "11": 16,
    "12": 16,
    "13": 16,
    "14": 16,
    "16": 16,
    "17": 16,
    "18": 16,
    "19": 16,
    "20": 16,
    "21": 16,
    "24": 16,
    "26": 16,
    "29": 16,
    "33": 16,
    "38": 16,
    "39": 16,
    "41": 16,
    "47": 16,
    "48": 16,
    "49": 16,
    "51": 16,
    "53": 16,
    "54": 16,
    "56": 16,
    "57": 16,
    "58": 16,
    "61": 16,
    "62": 16,
    "66": 16,
    "68": 16,
    "69": 16,
    "70": 16,
    "71": 16,
    "72": 16,
    "73": 16,
    "74": 16,
    "76": 16,
    "77": 16,
    "78": 16,
    "79": 16,
    "80": 16,
    "81": 16,
    "84": 16,
    "86": 16,
    "89": 16,
    "93": 16,
    "98": 16,
    "99": 16,
    "101": 16,
    "107": 16,
    "108": 16,
    "109": 16,
    "111": 16,
    "113": 16,
    "114": 16,
    "116": 16,
    "117": 16,
    "118": 16
  },
  "sheets": [
    "Sheet1"
  ],
  "used_sheet": "Sheet1",
  "header_row": 1,
  "headers": [
    "Port1",
    "Port2"
  ],
  "blank_rows": 0,
  "raw_cell_types": {
    "n": 512,
    "f": 512
  },
  "sha256_unchanged": "71a19ec1739de75453608d1d9bd0bb2b9ad102140e4af5057c12e60c0accd7ff"
}
```

## 统计定义与结论
重复 pair 按无向 (min(PMT1,PMT2), max(PMT1,PMT2)) 统计；duplicate_undirected_pairs 为重复出现的不同 pair 数量，extra_pair_rows 为超过首次出现的行数总和。仅统计规范化，不改变模型方向。

实测分别为 256/512 根 Waveguide 和 32/64 个 PMT，与审计结论一致。每个 PMT 端点计数均为 16。无自连接、非法 ID 或缺值；公式缓存依赖已如上披露。读取前后原文件 SHA-256 一致。当前模型足以表达输入，无须伪造槽位或坐标。

## 测试与复验
{'io': 17, 'models': 15, 'geometry': 45, 'router_2d': 15, 'collision': 34, 'loss': 26}，合计 152 个测试全部通过。临时工作簿测试不依赖前代绝对路径，覆盖读取、重复与反向连接、稳定 ID、未分配状态、整数数值、空白行、缺值、缺列、非法值及公式无缓存。

在项目根目录运行 `python -B -m scripts.validate_legacy_inputs <256文件路径> <512文件路径>` 输出复验统计。脚本调用唯一 IO 解析实现。

本阶段读取阻碍已解除。后续进入 Router 前仍须另行确定端口槽位、物理位置及显式路由规格，本轮未实现自动布线或后续阶段。
