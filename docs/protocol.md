# WebSocket 协议

客户端连接同域 `/ws`。消息使用 UTF-8 JSON；服务端按房间串行处理玩家意图，并在每次有效状态变化后增加 `revision`。

## 建立会话

WebSocket 建立后第一条消息必须是 `JOIN_ROOM`：

```json
{ "type": "JOIN_ROOM", "roomId": "ABCD", "playerName": "Alice" }
```

服务端在 `WELCOME` 中返回只保存在该玩家浏览器的 `playerId` 与 `reconnectToken`。断线后在 `JOIN_ROOM` 中附带这两个字段即可恢复身份。

## 玩家行动

所有状态行动都包含客户端生成的唯一 `actionId`：

```json
{ "type": "SET_VARIANT", "actionId": "a1", "doubleRacer": true }
{ "type": "SET_AUTO_DEAL", "actionId": "a2", "autoDeal": true }
{ "type": "ADD_BOT", "actionId": "a10" }
{ "type": "START_GAME", "actionId": "a3" }
{ "type": "ROLL_START", "actionId": "a4" }
{ "type": "DRAFT_ATHLETE", "actionId": "a5", "athleteId": "centaur" }
{ "type": "SELECT_RACERS", "actionId": "a6", "athleteIds": ["centaur", "banana"] }
{ "type": "ROLL_DICE", "actionId": "a7" }
{ "type": "RESOLVE_DECISION", "actionId": "a8", "decisionId": "d1", "optionId": "1" }
{ "type": "ADVANCE_RACE", "actionId": "a9" }
```

`SET_VARIANT` 只由房主在三人大厅使用。两人游戏始终是双赛车手，4–6 人始终是单赛车手。`SET_AUTO_DEAL` 同样只由房主在开局前的 `LOBBY` 使用：开启后 `START_GAME` 直接给每人随机发牌（普通局 4 张，双赛车手变体 8 张），跳过 `DRAFT_ROLL` 与 `DRAFTING`，直接进入第一场的 `RACE_ROLL`。`ROLL_START` 用于招募前和需要平局决胜的比赛前掷骰。比赛轮次由服务端自动推进到技能选择或 `WAITING_FOR_ROLL`；`ROLL_DICE` 只在后者有效，并且只能由 `pendingRoll.nextPlayerId`（没有 `pendingRoll` 时为 `activePlayerId`）提交。每次意图只生成当前步骤的一颗权威骰，不接受客户端点数或移动终点。`RESOLVE_DECISION` 只接受公开候选项中的 ID，且只能由 `pendingDecision.playerId` 提交。

`ADD_BOT` 同样只由房主在开局前的 `LOBBY` 使用：每次加入一名机器人，房间最多 6 人。机器人没有 WebSocket，`game.players[].isBot` 为 `true`。服务端会替机器人行动：掷起始骰、招募、选将、掷比赛骰，以及在技能选择时采用与超时自动选择相同的智能策略。每次机器人行动前会有约 1 秒的停顿，`STATE_UPDATED` 中机器人做出的选择同样带 `optionId` 与 `optionLabel`，技能选择事件额外带 `bot: true`。机器人可以被房主用 `KICK_PLAYER` 在大厅移出。

重复的 `actionId` 不会重复执行，服务端返回 `ACTION_ACK`。

## 游戏阶段

权威状态 `game.phase` 按以下流程推进：

```text
LOBBY
  -> DRAFT_ROLL -> DRAFTING   (默认：公开蛇形招募)
  -> RACE_ROLL -> CHARACTER_SELECTION -> RACING -> RACE_RESULTS
  -> CHARACTER_SELECTION / RACE_ROLL ...
  -> FINISHED

LOBBY
  -> RACE_ROLL                (房主开启 autoDeal：自动发牌，跳过招募)
  -> CHARACTER_SELECTION -> ...
```

`DRAFTING` 公开 `draftPool`、`activePlayerId`、各玩家 `team` 与招募轮次。自动发牌由 `autoDeal` 标记，`cardsPerPlayer` 是每人应得的牌数；自动发牌时服务端广播每名玩家的 `TEAM_DEALT` 事件。`CHARACTER_SELECTION` 只公开 `selectionLocked`；全部玩家锁定后，`activeRacers` 同时揭示。`raceNumber` 为 1–4，`trackName`、`raceRewards` 和 `scores` 始终来自服务端。

比赛状态还包含 `pendingDecision`、`pendingRoll`、`raceLog` 和 `resolutionStatus`。`resolutionStatus` 在轮次等待玩家掷骰时为 `WAITING_FOR_ROLL`，技能选择期间为 `WAITING_FOR_DECISION`。`pendingRoll.nextPlayerId` 是当前唯一可以提交 `ROLL_DICE` 的玩家，不一定等于回合的 `activePlayerId`；Duelist 会依次把投骰权交给挑战者和目标。待选和分步投骰状态均包含 60 秒的 `deadlineAt`，超时后由服务端自动选择或投骰并继续。重连会恢复同一个流程 ID、已投点数和截止时间。

## 状态广播

`game.previousWinners` 保存本局已结束比赛的真实冠军卡片，并跨比赛保留。双胞胎的复制候选仅来自这些冠军，重复冠军合并成一个选项；首场没有冠军时不出现复制选择。旧快照只恢复仍保留在 `raceResults` 中的冠军，不伪造已丢失的历史记录。

玩家可发送 `SET_AUTO_PLAY {actionId, enabled}` 开启或取消本人的全托管，其他玩家和旁观者不能代为设置。`game.players[].autoPlay` 表示当前托管状态；玩家身份与手牌保留，机器人代为完成投骰、招募、选人、技能选择和房主的下一场推进。托管会跨断线重连及房间快照保留，取消后未执行的自动行动停止，旁观者调用返回 `SPECTATOR_READ_ONLY`。

`JOIN_ROOM.role` 可为 `player`（默认）或 `spectator`。旁观者可在开局后或六个玩家席位已满时加入，另有 20 个旁观席；其身份和重连凭证与玩家分开保存。旁观者收到相同的公开赛事广播，`game.hand` 为空，并且只有 `LEAVE_ROOM` 可执行，其他行动返回 `SPECTATOR_READ_ONLY`。`WELCOME` 与广播快照额外包含 `viewerRole` 和 `spectators: [{id, name, connected}]`，旁观者退出不重置对局。

复制角色的候选选项包含可选的 `athlete: {id, name}`，客户端按 `id` 展示技能说明。蛋、双胞胎或模仿猫当前有复制对象时，其 `activeRacers` 条目包含 `copiedAthlete: {id, name}`；角色自身的 `id` 仍分别为 `egg`、`twin` 或 `copycat`，复制对象的技能文字由客户端本地化。模仿猫在比赛中换了领先者后，`copiedAthlete` 也随权威状态更新。

有效行动产生 `STATE_UPDATED`。`events` 用于移动动画和提示，`game` 是权威快照；客户端发现 revision 跳跃时直接采用最新快照。骰子结果通过 `rollResults` 明确广播给房间内所有客户端，每个结果带全局一致的 `id`，客户端必须以此字段中的 `values` 为权威点数。长腿的慢跑跳过掷骰，对应事件与结果会带 `noDice: true` 且 `values` 为空，客户端不应播放骰子动画。分步投骰的每颗骰子拥有独立结果 ID，并以 `rollSessionId` 分组；`kind` 区分 `MAIN_ROLL`、`ABILITY_ROLL` 和 `ROLL_OFF`，`participants` 标识该颗骰子的玩家及赛车手。`rollSerial` 在单场比赛内单调递增；一次待决策预览及其最终事件引用同一个结果 ID。

比赛掷骰被服务端确认后，会先广播不改变 revision 的 `ROLL_STARTED`，供所有客户端同步启动投掷动画；实际点数仍只在随后的 `STATE_UPDATED.events` 中公布。

```json
{
  "type": "STATE_UPDATED",
  "roomId": "ABCD",
  "revision": 18,
  "rollResults": [
    { "id": "race:2:serial:7", "playerId": "p1", "athleteId": "centaur", "values": [5], "rollSerial": 7, "baseValue": 5, "finalValue": 5 }
  ],
  "events": [
    { "type": "DICE_ROLLED", "playerId": "p1", "athleteId": "centaur", "value": 5 },
    { "type": "RACER_MOVED", "playerId": "p1", "athleteId": "centaur", "from": 4, "to": 9, "movementKind": "FORWARD" },
    { "type": "TURN_CHANGED", "playerId": "p2" }
  ],
  "game": { "phase": "RACING", "raceNumber": 2, "activePlayerId": "p2" }
}
```

比赛事件包括 `DIE_ROLLED`、`DICE_ROLLED`、`ABILITY_DICE_ROLLED`、`ABILITY_ROLL_RESOLVED`、`ABILITY_TRIGGERED`、`DECISION_REQUIRED`、`DECISION_RESOLVED`、`DECISION_TIMED_OUT`、`RACER_MOVED`、`RACER_TRIPPED`、`TRIP_RECOVERED`、`RACER_WARPED`、`RACERS_SWAPPED`、`RACER_FINISHED`、`RACER_ELIMINATED` 和 `TURN_CHANGED`。`DIE_ROLLED` / `ABILITY_DICE_ROLLED` 表示一次玩家实际投骰，`DICE_ROLLED` 表示主要移动最终选中并完成修正的结果。客户端按数组顺序播放，最后以同一消息中的 `game` 快照对齐。

`RACER_MOVED.movementKind` 区分 `FORWARD`、`BACKWARD` 和 `PUSH`；`RACER_WARPED.movementKind` 可为 `WARP`、`SWAP` 或 `PUSH`。这些字段描述规则动作的种类，客户端物理碰撞不能据此反向修改游戏状态。`TRIP_RECOVERED` 表示该赛车手跳过本次主要移动并恢复正常状态，因此同一回合不会伴随 `DICE_ROLLED`。`RACER_TRIPPED` 既可能来自角色能力，也可能来自棋盘上的绊倒格，后者的 `source` 为 `TripTile` 且没有 `sourcePlayerId`。

`DECISION_REQUIRED` 携带待选内容；`abilityName` 和选项 `label` 都是稳定的协议标识，由客户端翻译成当前语言（例如布尔选项使用 `skip` / `use`）。`DECISION_RESOLVED` / `DECISION_TIMED_OUT` 额外给出 `athleteId`、`athleteName` 与 `optionLabel`，超时自动选择时为空。`raceLog` 按出现顺序记录上述比赛事件，并包含 `DECISION_REQUIRED`、`TRIP_RECOVERED`、`RACER_ELIMINATED` 与 `RACE_FINISHED`，客户端可直接把 `raceLog` 当作本场比赛的完整播报。

全 3D 表现所需的事件归一化、同时事件分组和当前赛车手契约记录在 `docs/3d-race-plan.md`。这些目标字段完成服务端实现和测试前，不视为当前协议已经提供。

## 错误

格式或规则错误返回：

```json
{ "type": "ERROR", "code": "NOT_YOUR_TURN", "message": "还没轮到你", "actionId": "a6" }
```
