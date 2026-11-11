# ha_xiaomi_home — Lite-Safety 分支

基于小米官方 `XiaoMi/ha_xiaomi_home` **v0.5.0** 的分支（fork: `yousj666/ha_xiaomi_home`，分支 `Lite-Safety`）。

目标：**功能更多、内存更省，界面（配置流程、实体、名称）与官方版本完全一致。**

## 内存优化（miot/miot_spec.py）

1. **值列表驻留共享（interning）**
   官方版为每台设备单独解析一份规格树，同一型号的多台设备、乃至不同设备间的
   相同枚举（如开关 On/Off、模式列表）都会各存一份 `MIoTSpecValueList` 对象。
   Lite-Safety 在 `MIoTSpecValueList.from_spec` 与属性 `value_list` 的加载路径上
   按内容指纹共享同一对象（值列表构造后不可变，共享安全）；
   缓存上限 8192 条，超出后不再驻留。上线实测：跨实例加载同一规格时，
   值列表为同一对象，属性对象仍各设备独立（官方版在 spec_transform 中会
   按设备改写属性，故不能共享属性本身——本分支不动这条语义）。

2. **`__slots__`**
   `MIoTSpecValueRange`、`MIoTSpecValueListItem`、`MIoTSpecValueList`
   三个叶子类改用 `__slots__`，去掉每实例一份的 `__dict__`。
   这三类对象在规格树中数量最多（每个枚举项一个），收益直接。

## 功能增强（不改变任何界面）

3. **领域服务**（`__init__.py` + `services.yaml`）
   - `xiaomi_home.get_properties`：按 did/siid/piid 直读原始 MIoT 属性（带返回值）
   - `xiaomi_home.set_properties`：按 did/siid/piid 直写原始 MIoT 属性
   - `xiaomi_home.action`：按 did/siid/aiid 调用原始 MIoT 动作，可带入参
   覆盖没有生成实体的属性与动作，自动化里可直接调用。

4. **事件总线转发**（`miot/miot_client.py` + `__init__.py`）
   客户端分发的每条属性变化 / 设备事件，额外在 HA 总线上发出：
   - `xiaomi_home_property_changed`（did、device_name、model、siid、piid、value）
   - `xiaomi_home_event_occurred`（did、device_name、model、siid、eiid、arguments）
   钩子异常被捕获记录，不影响原有分发。

5. **诊断信息**（`diagnostics.py`）
   支持 HA 标准的“下载诊断”：设备数、在线数、型号直方图、钩子状态；
   入口数据经脱敏，不含设备 ID 与任何令牌。

## 版本与安装

- manifest 版本标记为 `0.5.0-lite.1`，domain 与名称与官方版一致（`xiaomi_home` / “Xiaomi Home”），可直接覆盖官方版目录使用，原配置条目通用。
- 安装：把 `custom_components/xiaomi_home` 覆盖到 HA 的 `custom_components` 后重启。
