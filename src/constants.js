// 商人 id → 中文名映射（来自社区数据）
export const TRADER_ZH = {
  '54cb57776803fa99248b456e': '医生',
  '54cb50c76803fa8b248b4571': '普拉波尔（Prapor）',
  '58330581ace78e27b8b10cee': '斯基尔（Skier）',
  '5a7c2eca46aef81a7ca2145d': '和平使者（Peacekeeper）',
  '5935c25fb3acc3127c3d8cd9': '机械师（Mechanic）',
  '5c0647fdd443bc2504c2d371': '拉格曼（Ragman）',
  '6617beeaa9cfa777ca915b7c': '裁判官（Referee）',
  '579dc571d53a0658a154fbec': '围栏（Fence）',
  '5ac3b934156ae10c4430e83c': '枪匠（Jaeger）',
  '638f541a29ffd1183d187f57': '灯塔守卫（Lightkeeper）',
  '656f0f98d80a697f855d34b1': 'BTR 司机',
};

export function traderName(id) {
  return TRADER_ZH[id] ?? id;
}

// 地图 id → 中文名（任务涉及的地图）
export const MAP_ZH = {
  '5704e554d2720bac5b8b456e': '海关',
  '5704e4dad2720bb55b8b4567': '海岸线',
  '56f40101d2720b2a4d8b45d6': '工厂',
  '5714dbc124597777137212e0': '海关(夜)',
  '5714dc692459777137212e12': '海岸线',
  '55f2d3fd4bdc2d5f408b4567': '森林',
  '59fc81d786f774390775787e': '实验室',
  '5b0fc42d86f7744a585f9105': '实验室',
  '653e6760052c01c1c805532f': '曙光街区',
  '65b8d6f5cdde2479cb2a3125': '曙光街区',
  '5704e5fad2720bc05b8b4567': '灯塔',
  '5d0278b086f77478e1264b0e': '军事基地(储备站)',
};

export function mapName(id) {
  return MAP_ZH[id] ?? id;
}
