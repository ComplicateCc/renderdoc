# RenderDoc 贴图替换功能 — 开发复盘与经验总结

> 日期: 2026-04-06  
> 功能: `OverrideTextureData` — 运行时替换 RDC 抓帧中任意贴图的像素数据  
> 最终状态: ✅ 通过自动化 CLI 测试（贴图数据变更 + 渲染输出变更）

---

## 一、功能目标

在 RenderDoc 中实现"实时贴图替换"：用户选中一张贴图后，可以用纯色/棋盘格/本地文件替换它，**立即在 3D 渲染窗口看到效果变化**。

---

## 二、失败历程（按时间线）

### 第 1 轮：`UpdateSubresource` / `CopyResource` 直写

**尝试**: 拿到贴图的 real D3D11 指针，直接用 `UpdateSubresource` 写入新数据。

**结果**: ❌ 失败

**原因**: 游戏抓帧中的贴图大多是 `D3D11_USAGE_IMMUTABLE`，D3D11 规范明确禁止对 IMMUTABLE 资源调用 `UpdateSubresource` 或 `CopyResource`（目标）。

**教训**:  
> ⚠️ **必须检查资源的 `Usage` 属性**。游戏中 90% 的纹理都是 IMMUTABLE 的。

---

### 第 2 轮：`ReplaceResource` API

**尝试**: 使用 RenderDoc 已有的 `ReplaceResource(origId, proxyId)` 机制，创建一个 proxy 贴图，写入新数据，然后替换。

**结果**: ❌ 名字显示 "(Edited)" 但渲染画面不变

**原因**: `ReplaceResource` 只修改 `ResourceManager` 的查找表。它影响的是 **command 反序列化阶段** 的 `GetResource()` 调用。但在 replay 模式下：

```
┌─────────────────────────────────────────────────────────┐
│                 Capture 加载阶段                         │
│                                                         │
│  1. 读取命令流 → 创建所有 D3D11 资源                     │
│  2. 创建 SRV (ShaderResourceView)                       │
│     └── SRV 内部持有 real D3D11 资源的指针               │
│         (不经过 ResourceManager，直接指向 real 对象)      │
│                                                         │
│  3. ReplaceResource 只替换了 ResourceManager 的映射       │
│     └── 但已创建的 SRV 仍然指向 old real 资源！          │
│                                                         │
│  4. Replay 时 SRV 绑定的还是旧贴图 → 渲染不变           │
└─────────────────────────────────────────────────────────┘
```

**教训**:  
> ⚠️ **`ReplaceResource` 是"反序列化时"替换，不是"运行时"替换**。SRV 等 View 对象在加载阶段就已经创建完毕，它们持有的是 real D3D11 指针的直接引用，绕过了 ResourceManager 的查找表。

---

### 第 3 轮：参考 Shader 替换机制

**尝试**: 参考 RenderDoc 的 Shader 实时替换代码路径，尝试类似的 `ReplaceResource` + `SetFrameEvent` 重放。

**结果**: ❌ 渲染仍不变

**原因**: Shader 替换之所以能工作，是因为 Shader 对象在每次 replay 时会通过 `GetResource()` 重新查找。但 SRV 不一样：SRV 在加载时创建一次，replay 时只是 `PSSetShaderResources(slot, srv)` 绑定已有的 SRV 对象，**不会重新创建 SRV**。

**教训**:  
> ⚠️ **不同资源类型的替换路径完全不同**。Shader 和 Texture 虽然都是"资源"，但它们在 replay 管线中的绑定方式有本质区别。不能简单照搬 Shader 的替换方案到 Texture 上。

---

### 第 4 轮：指针替换（SwapReal）— 部分成功

**尝试**: 在 `WrappedDeviceChild11` 模板类中添加 `SwapReal()` 方法，直接替换 wrapped 对象内部的 `m_pReal` 指针。

```cpp
NestedType *SwapReal(NestedType *newReal)
{
    NestedType *oldReal = m_pReal;
    m_pDevice->GetResourceManager()->RemoveWrapper(oldReal);
    m_pDevice->GetResourceManager()->AddWrapper(this, newReal);
    m_pReal = newReal;
    return oldReal;
}
```

**结果**: ⚠️ 贴图数据读取确实变化了，但渲染画面仍不变

**原因**: `SwapReal` 替换了 wrapped texture 的 real 指针，但 **SRV 在创建时就把 old real texture 的指针"烤"进了自己的内部**。D3D11 SRV 一旦创建，它引用的底层资源就不会变。换句话说：

```
Wrapped Texture ──SwapReal──▶ new real texture
                                    ↑ 
                            SRV 不知道这件事！
                            SRV 内部仍指向 old real texture
```

**教训**:  
> ⚠️ **D3D11 View 对象（SRV/RTV/DSV/UAV）是不可变的**。创建后，它引用的底层资源指针无法修改。如果你替换了底层资源，必须同时重建所有引用它的 View。

---

### 第 5 轮：SwapReal + SRV 重建 — 接近成功

**尝试**: 除了 `SwapReal` 替换 texture 指针外，遍历 `ResourceManager` 的 `WrapperMap`，找到所有引用该 texture 的 SRV，为每个 SRV 也调用 `SwapReal`。

**关键代码**:
```cpp
// 收集所有引用该贴图的 SRV
rdcarray<WrappedID3D11ShaderResourceView1 *> srvList;
auto &wrapMap = m_pDevice->GetResourceManager()->GetWrapperMap();
for(auto &entry : wrapMap)
{
    if(WrappedID3D11ShaderResourceView1::IsAlloc(entry.second))
    {
        auto *wrapSRV = (WrappedID3D11ShaderResourceView1 *)entry.second;
        if(wrapSRV->GetResourceResID() == texid)
            srvList.push_back(wrapSRV);
    }
}
// 重建每个 SRV
for(auto *wrapSRV : srvList)
{
    D3D11_SHADER_RESOURCE_VIEW_DESC srvDesc;
    wrapSRV->GetReal()->GetDesc(&srvDesc);
    ID3D11ShaderResourceView *newRealSRV = NULL;
    m_pDevice->GetReal()->CreateShaderResourceView(newTex, &srvDesc, &newRealSRV);
    ID3D11ShaderResourceView *oldRealSRV = wrapSRV->SwapReal(newRealSRV);
    SAFE_RELEASE(oldRealSRV);
}
```

**结果**: ⚠️ 单次 replay 有效，但 `SetFrameEvent` 后数据被恢复

**原因**: `ReplayLog()` 在 `startEventID == 0` 时会调用 `ApplyInitialContents()`，把所有资源恢复到帧起始状态。我们的覆写数据被初始内容覆盖了。

```
用户调用 OverrideTextureData → 数据写入成功 ✅
用户调用 SetFrameEvent(eventId) 
  └── ReplayLog(0, eventId, eReplay_Full)
       └── ApplyInitialContents()  ← 恢复原始数据！❌
            └── CopyResource(wrappedReal, savedInitialData)
```

**教训**:  
> ⚠️ **RenderDoc 的 replay 管线有"初始内容恢复"机制**。每次从头 replay 时，所有资源的数据都会被恢复到抓帧时的状态。如果你想让修改在 replay 后生效，必须同时更新初始内容。

---

### 第 6 轮：SwapReal + SRV 重建 + InitialContents 更新 — ✅ 成功

**最终方案**: 在第 5 轮的基础上，增加第 6 步：用修改后的数据创建新的初始内容副本，替换 `ResourceManager` 中保存的初始内容。

```cpp
// Step 6: Update initial contents
D3D11_TEXTURE2D_DESC copyDesc = desc;
copyDesc.Usage = D3D11_USAGE_DEFAULT;
ID3D11Texture2D *initCopy = NULL;
m_pDevice->GetReal()->CreateTexture2D(&copyDesc, initData.data(), &initCopy);
D3D11InitialContents initContents(Resource_Texture2D, (ID3D11Resource *)initCopy);
m_pDevice->GetResourceManager()->SetInitialContents(texid, initContents);
```

**结果**: ✅ 完全通过

- Test A (贴图数据变更): **PASS** — MD5 hash 变化
- Test C (渲染输出变更): **PASS** — RT hash 变化
- 多次 `SetFrameEvent` 后仍然保持修改

---

## 三、遇到的额外问题

### 3.1 Python 绑定问题（SWIG）

**问题**: `OverrideTextureData(ResourceId, Subresource, byte*, size_t)` 在 Python 中调用失败，因为 SWIG 不知道如何把 Python `bytes` 转换为 `(byte*, size_t)` 参数对。

**修复**: 在 `renderdoc.i` 中添加自定义 typemap：
```swig
%typemap(in) (byte *data, size_t dataSize) {
    if(PyBytes_Check($input)) {
        $1 = (byte *)PyBytes_AsString($input);
        $2 = (size_t)PyBytes_Size($input);
    } else if(PyByteArray_Check($input)) {
        $1 = (byte *)PyByteArray_AsString($input);
        $2 = (size_t)PyByteArray_Size($input);
    }
}
%typemap(typecheck) (byte *data, size_t dataSize) {
    $1 = PyBytes_Check($input) || PyByteArray_Check($input);
}
```

**教训**:  
> ⚠️ **SWIG 的多参数 typemap 需要显式配置**。C++ 函数签名中的 `(byte*, size_t)` 模式在 Python 端应表现为单个 `bytes` 参数，但 SWIG 默认不会自动合并这两个参数。

### 3.2 Python 版本不匹配

**问题**: 系统安装的 Python 3.14 无法加载针对 Python 3.6 编译的 `renderdoc.pyd`。

**修复**: 下载 Python 3.6 embedded 发行版，创建独立的 `python36_env` 目录用于测试。

**教训**:  
> ⚠️ **Python `.pyd` 模块严格绑定编译时的 Python 版本**。必须用完全匹配的 Python 版本运行。

### 3.3 迭代 map 时修改导致 UB

**问题**: 遍历 `WrapperMap` 时对 SRV 调用 `SwapReal()` 会触发 `RemoveWrapper` + `AddWrapper`，修改正在迭代的 map，导致未定义行为。

**修复**: 分两阶段操作 — 先收集需要修改的 SRV 到临时列表，再统一修改。

**教训**:  
> ⚠️ **永远不要在迭代 `std::map` 的同时修改它**。先收集，再批量修改。

### 3.4 `GetWrapperMap()` 不存在

**问题**: `ResourceManager` 的 `m_WrapperMap` 是 `protected` 成员，没有公开访问方法。

**修复**: 在 `resource_manager.h` 中添加 `GetWrapperMap()` 公开只读方法。

---

## 四、最终架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    OverrideTextureData                           │
│                                                                 │
│  Step 1: 创建 STAGING 贴图，从 real texture 复制全部数据         │
│          └── CopyResource(staging, realTex)                     │
│          └── Map/Unmap 读出所有 subresource 数据                │
│                                                                 │
│  Step 2: 读取所有 subresource 到内存                             │
│                                                                 │
│  Step 3: 用用户数据替换目标 subresource                          │
│          └── memcpy(subresourceData[target], userData)           │
│                                                                 │
│  Step 4: 创建新 DEFAULT 贴图（含修改后的 initData）              │
│          └── CreateTexture2D(&newDesc, initData, &newTex)        │
│                                                                 │
│  Step 5: 根据原始 Usage 选择策略                                 │
│          ├── DEFAULT/STAGING → CopyResource(realTex, newTex)     │
│          └── IMMUTABLE → SwapReal(newTex) + 重建所有 SRV         │
│                          ├── 遍历 WrapperMap 收集引用 SRV        │
│                          ├── 为每个 SRV 重建 real D3D11 view     │
│                          └── SwapReal 替换 SRV 的 real 指针      │
│                                                                 │
│  Step 6: 更新 InitialContents                                    │
│          └── SetInitialContents(texid, newInitData)              │
│          └── 确保 ApplyInitialContents 使用修改后的数据           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、核心经验总结

### 经验 1：理解 D3D11 的"三层缓存"

修改一个 D3D11 贴图在 RenderDoc replay 中生效，必须同时更新三层：

| 层级 | 对象 | 更新方式 |
|------|------|---------|
| L1: Real Resource | `ID3D11Texture2D` | `CopyResource` 或 `SwapReal` |
| L2: Views | `ID3D11ShaderResourceView` | 重建并 `SwapReal` |
| L3: Initial Contents | `ResourceManager::m_InitialContents` | `SetInitialContents()` |

> 遗漏任何一层都会导致"看起来修改了但渲染不变"。

### 经验 2：先弄清 replay 管线再动手

RenderDoc 的 replay 流程：
```
SetFrameEvent(eid)
  └── ReplayLog(0, eid, eReplay_Full)
       ├── if(startEID == 0) → ApplyInitialContents()  // 恢复初始状态！
       └── 重放命令流 0..eid
```

任何资源修改如果不考虑 `ApplyInitialContents`，都会在下次 replay 时被恢复。

### 经验 3：Wrapped 对象 ≠ Real 对象

RenderDoc 对每个 D3D11 对象都有一层 Wrapper。理解 Wrapper 和 Real 的关系：
- `Wrapper->GetReal()` 获取内部 real 指针
- SRV 的 Wrapper 和 Texture 的 Wrapper 是独立的
- SRV 的 real 对象内部持有 Texture 的 real 指针（不是 Wrapper）
- 改了 Texture 的 real 指针，SRV 的 real 对象不会自动更新

### 经验 4：自动化测试是必须的

在这个功能的调试中，人工在 UI 中检查"渲染画面是否变化"效率极低且容易出错。最终通过编写 `test_cli.py`，使用 Python 3.6 + `renderdoc.pyd` 进行 headless 测试，才快速定位和验证了问题。

**测试策略**:
```
Test A: 贴图数据 MD5 是否变化    → 验证数据写入
Test C: 渲染目标 MD5 是否变化    → 验证渲染生效
```

### 经验 5：SWIG 绑定要提前验证

C++ 新增的 API 如果要通过 Python 调用，必须在 `.i` 文件中添加相应的 typemap。特别是多参数合并的情况（如 `byte*` + `size_t` → Python `bytes`），SWIG 不会自动处理。

---

## 六、修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `renderdoc/driver/d3d11/d3d11_resources.h` | 添加 `SwapReal()` 到 `WrappedDeviceChild11` 模板 |
| `renderdoc/core/resource_manager.h` | 添加 `GetWrapperMap()` 公开方法 |
| `renderdoc/driver/d3d11/d3d11_replay.h` | 声明 `OverrideTextureData` |
| `renderdoc/driver/d3d11/d3d11_replay.cpp` | 实现 `OverrideTextureData`（6 步策略） |
| `renderdoc/api/replay/renderdoc_replay.h` | 在 `IReplayController` 接口中添加 `OverrideTextureData` |
| `qrenderdoc/Code/pyrenderdoc/renderdoc.i` | SWIG typemap: `(byte*, size_t)` → Python `bytes` |
| `test_cli.py` | 自动化 CLI 测试脚本 |
