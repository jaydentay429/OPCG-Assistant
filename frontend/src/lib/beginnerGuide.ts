/**
 * Beginner guide copy. Source: official "Rule Guidance Manual Ver.1.11"
 * (official_rules/). Each string is a Traditional source with its English
 * version; /zh-hans is converted from the Traditional text by serverCopy.
 * Only rules printed in the manual belong here; if the manual and a card
 * text disagree, the card text wins.
 */

export type GuideLine = { hant: string; en: string };
export type GuideSection = {
  id: string;
  title: GuideLine;
  kind: "p" | "ul" | "ol";
  items: GuideLine[];
};

export const BEGINNER_GUIDE_VERSION = "Ver.1.11";

export const BEGINNER_GUIDE: GuideSection[] = [
  {
    id: "goal",
    title: { hant: "這是什麼遊戲", en: "What the game is" },
    kind: "p",
    items: [
      {
        hant: "兩人對戰。把對方領袖的生命卡打到 0 張，再成功攻擊一次領袖，就贏了。",
        en: "A two-player game. Take the opponent's Leader down to 0 Life cards, then land one more attack on the Leader to win.",
      },
    ],
  },
  {
    id: "win",
    title: { hant: "兩種獲勝方式", en: "Two ways to win" },
    kind: "ul",
    items: [
      {
        hant: "對方生命卡為 0 張時，你的攻擊在與對方領袖的戰鬥中獲勝。",
        en: "When the opponent has 0 Life cards, win a battle against their Leader.",
      },
      {
        hant: "對方的卡組變成 0 張（抽不到牌）。此時正在發動的所有效果取消，卡組為 0 張的一方敗北。",
        en: "The opponent's deck reaches 0 cards. All effects being activated at that moment are cancelled, and the player with 0 cards loses.",
      },
    ],
  },
  {
    id: "prepare",
    title: { hant: "要準備什麼", en: "What you need" },
    kind: "ul",
    items: [
      { hant: "領袖卡 1 張。", en: "1 Leader card." },
      {
        hant: "卡組：角色卡、事件卡、舞台卡合計正好 50 張。只能放與領袖顏色相同的卡；同一編號的卡最多 4 張。",
        en: "Deck: exactly 50 cards in total from Character, Event and Stage cards. Only cards that share a color with your Leader; at most 4 copies of the same card number.",
      },
      { hant: "咚!!卡組：10 張咚!!卡。", en: "DON!! deck: 10 DON!! cards." },
      {
        hant: "對戰桌墊不是必需，但每人準備一張會更方便。",
        en: "A playmat is not required, but one each makes play easier.",
      },
    ],
  },
  {
    id: "areas",
    title: { hant: "場地上有哪些區域", en: "The play areas" },
    kind: "ul",
    items: [
      { hant: "領袖區：放 1 張領袖卡，整場正面朝上。", en: "Leader area: holds the Leader card, face up for the whole game." },
      { hant: "角色區：放角色卡，最多 5 張。", en: "Character area: holds Character cards, up to 5." },
      { hant: "舞台區：最多 1 張舞台卡。", en: "Stage area: holds up to 1 Stage card." },
      { hant: "卡組：放抽牌用的卡組。", en: "Deck: where you draw from." },
      { hant: "廢棄區：被 KO 的角色卡、用過的事件卡等。", en: "Trash: KO'd Characters, played Events and similar cards." },
      { hant: "費用區：放從咚!!卡組拿出的咚!!卡。", en: "Cost area: holds DON!! cards taken from the DON!! deck." },
      { hant: "咚!!卡組：放咚!!卡組。", en: "DON!! deck: where the DON!! cards start." },
      {
        hant: "生命區：背面朝上放生命卡，數量等於領袖卡上的生命值。領袖受到傷害，生命卡就減少。",
        en: "Life area: Life cards face down, as many as the Life value on your Leader. Each time the Leader takes damage, you lose one.",
      },
      {
        hant: "領袖區、角色區、舞台區、費用區合起來叫「場上」。",
        en: "The Leader, Character, Stage and Cost areas together are called \"the field\".",
      },
    ],
  },
  {
    id: "multicolor",
    title: { hant: "多種顏色的卡", en: "Multicolor cards" },
    kind: "p",
    items: [
      {
        hant: "有些卡同時有兩種以上的顏色（例如「紅・綠」），視為擁有它的所有顏色。",
        en: "Some cards have more than one color (for example red and green). Such a card is treated as having all of its colors.",
      },
    ],
  },
  {
    id: "setup",
    title: { hant: "對戰準備（按順序）", en: "Setting up" },
    kind: "ol",
    items: [
      { hant: "洗切卡組，放到指定位置。", en: "Shuffle your deck and place it in its spot." },
      { hant: "領袖卡正面朝上放好。", en: "Place your Leader card face up." },
      { hant: "猜拳決定先後攻，贏的一方可以選擇先攻或後攻。", en: "Play rock-paper-scissors; the winner chooses to go first or second." },
      { hant: "各從卡組抽 5 張作為手牌。", en: "Each player draws 5 cards as their starting hand." },
      {
        hant: "每位玩家有且僅有 1 次機會，可把手牌全部放回卡組切洗後重抽 5 張（由先攻的玩家先決定是否重抽）。",
        en: "Each player gets exactly one chance to put the whole hand back, shuffle, and draw 5 again (the first player decides first).",
      },
      {
        hant: "從卡組最上方抽出與領袖生命值相同張數的卡，不看內容，背面朝上放到生命區。",
        en: "Without looking, place cards from the top of your deck face down in the Life area, as many as your Leader's Life value.",
      },
      { hant: "從先攻玩家開始遊戲。", en: "The first player starts the game." },
    ],
  },
  {
    id: "states",
    title: { hant: "活躍狀態與休息狀態", en: "Active and rested" },
    kind: "p",
    items: [
      {
        hant: "場上的角色或舞台通常豎著放，叫「活躍狀態」。進行攻擊或阻擋等行動後會橫過來，叫「休息狀態」。把休息狀態變回活躍叫「轉為活躍狀態」，反過來叫「轉為休息狀態」。",
        en: "Characters and Stages on the field normally stand upright: that is \"active\". After attacking or blocking they turn sideways: \"rested\". Turning a rested card upright is \"setting it active\"; turning it sideways is \"resting\" it.",
      },
    ],
  },
  {
    id: "cost",
    title: { hant: "支付費用", en: "Paying costs" },
    kind: "p",
    items: [
      {
        hant: "角色登場、舞台登場、發動事件時，要把費用區裡指定張數的咚!!卡轉為休息狀態來支付費用。",
        en: "To play a Character, play a Stage or activate an Event, rest the required number of DON!! cards in your Cost area.",
      },
    ],
  },
  {
    id: "don",
    title: { hant: "咚!!卡牌", en: "DON!! cards" },
    kind: "ul",
    items: [
      {
        hant: "使用卡牌時，作為費用所需要的卡牌。",
        en: "DON!! cards are the cards you use to pay costs when playing cards.",
      },
      {
        hant: "也可以依附在角色卡或領袖卡上。被依附咚!!卡的卡，在我方回合中每依附 1 張，力量增加 1000。",
        en: "They can also be attached to Character or Leader cards. During your turn, a card gets +1000 power for each DON!! card attached to it.",
      },
      {
        hant: "依附咚!!卡的角色被 KO，或因回到手牌的效果等離開場上時，依附在卡上的咚!!卡會以休息狀態回到費用區。",
        en: "When a Character with attached DON!! cards is KO'd or leaves the field (for example by returning to the hand), its attached DON!! cards return to the Cost area rested.",
      },
    ],
  },
  {
    id: "turn",
    title: { hant: "一個回合怎麼走", en: "How a turn runs" },
    kind: "ol",
    items: [
      {
        hant: "重置階段：我方場上所有休息狀態的卡轉為活躍，所有依附在卡上的咚!!卡以活躍狀態放回費用區。",
        en: "Refresh Phase: set all your rested cards active, and return all DON!! cards attached to cards to your Cost area, active.",
      },
      {
        hant: "抽卡階段：從卡組最上方抽 1 張。先攻玩家的第 1 回合不抽卡。",
        en: "Draw Phase: draw 1 card from the top of your deck. The first player does not draw on their first turn.",
      },
      {
        hant: "咚!!階段：從咚!!卡組把 2 張咚!!卡以活躍狀態放進費用區；咚!!卡組只剩 1 張就放 1 張。先攻玩家的第 1 回合只放 1 張。",
        en: "DON!! Phase: place 2 DON!! cards from the DON!! deck into the Cost area, active (just 1 if only 1 is left). The first player places only 1 on their first turn.",
      },
      {
        hant: "主要階段：可以自選順序，盡可能做下面的行動，宣言結束後進入結束階段。",
        en: "Main Phase: do the actions below in any order, as many as you can. Declare the end of the phase to move on.",
      },
      {
        hant: "結束階段：處理「回合結束時」的效果，之後移交回合。",
        en: "End Phase: resolve \"end of your turn\" effects, then pass the turn.",
      },
    ],
  },
  {
    id: "main",
    title: { hant: "主要階段能做什麼", en: "What you can do in the Main Phase" },
    kind: "ul",
    items: [
      {
        hant: "登場角色：從手牌把角色卡以活躍狀態放進角色區，支付登場費用。角色區已有 5 張時，可以把其中 1 張放進廢棄區，再讓新角色登場。",
        en: "Play a Character: place it from your hand into the Character area, active, and pay its cost. With 5 Characters already in play, trash 1 of them to play a new one.",
      },
      {
        hant: "登場舞台：同樣放進舞台區並支付費用。舞台區已有舞台時，可以把舊的放進廢棄區再登場新的。",
        en: "Play a Stage: place it in the Stage area and pay its cost. If you already have a Stage, trash it to play a new one.",
      },
      {
        hant: "發動事件：從手牌公開事件卡，支付發動費用，放進廢棄區即發動。【觸發】效果無法從手牌發動。",
        en: "Activate an Event: reveal it from your hand, pay its cost and place it in the Trash to activate it. [Trigger] effects cannot be activated from the hand.",
      },
      {
        hant: "使用卡牌的效果：可使用領袖、角色、事件、舞台的效果。",
        en: "Use card effects: Leaders, Characters, Events and Stages can use their effects.",
      },
      {
        hant: "依附咚!!卡：把費用區 1 張活躍狀態的咚!!卡，重疊在我方領袖或角色卡的下方，叫「依附」。被依附的卡，在我方回合中每依附 1 張咚!!卡，力量上升 1000，可多次依附。",
        en: "Attach DON!! cards: place 1 active DON!! card from your Cost area under your Leader or a Character. During your turn, each attached DON!! card gives that card +1000 power, and you can attach several.",
      },
      { hant: "戰鬥：見下一節。", en: "Battle: see the next section." },
    ],
  },
  {
    id: "battle",
    title: { hant: "戰鬥的 5 個步驟", en: "The 5 steps of a battle" },
    kind: "ol",
    items: [
      {
        hant: "攻擊宣言：把我方 1 張活躍狀態的領袖或角色轉為休息狀態來攻擊，選擇攻擊對象：對方領袖，或對方角色區中 1 張休息狀態的角色。有【攻擊時】效果此時發動。",
        en: "Attack declaration: rest one of your active Leader or Characters to attack, and choose a target: the opponent's Leader, or one of their rested Characters. [When Attacking] effects activate now.",
      },
      {
        hant: "阻擋步驟：被攻擊的一方可以發動我方角色的【阻擋者】效果。",
        en: "Block step: the defending player may activate a Character's [Blocker] effect.",
      },
      {
        hant: "反擊步驟：被攻擊的一方可按任意順序，把手牌中有【反擊】效果的角色卡置入廢棄區，用反擊值加我方 1 張領袖或角色的力量；也可發動帶【反擊】的事件卡。",
        en: "Counter step: the defending player may, in any order, trash Characters with a [Counter] effect from their hand to add the Counter value to the power of one of their Leader or Characters, and may activate Events with [Counter].",
      },
      {
        hant: "傷害步驟：比較雙方力量。攻擊方力量與被攻擊方相同或更高，則攻擊方獲勝：打領袖，領袖受 1 點傷害；打領袖時生命卡已是 0 張，攻擊方獲勝；打角色，該角色被 KO（放進廢棄區）。攻擊方力量較低，則戰鬥失敗，什麼都不發生。",
        en: "Damage step: compare power. If the attacker's power is equal or higher, it wins: against a Leader, the Leader takes 1 damage; against a Leader with 0 Life cards, the attacker wins the game; against a Character, that Character is KO'd (placed in the Trash). If the attacker's power is lower, the battle is lost and nothing happens.",
      },
      {
        hant: "戰鬥結束：處理「戰鬥結束時」的效果，「本次戰鬥中」的效果失效。",
        en: "End of battle: resolve \"end of battle\" effects; \"during this battle\" effects expire.",
      },
    ],
  },
  {
    id: "battle-notes",
    title: { hant: "戰鬥補充", en: "Battle notes" },
    kind: "ul",
    items: [
      {
        hant: "先攻、後攻的第 1 回合都不能攻擊。",
        en: "Neither player can attack on their first turn.",
      },
      {
        hant: "領袖受到傷害時，如果確認到的生命卡有【觸發】效果，可以公開該卡並發動其【觸發】效果來代替加入手牌，也可以選擇不發動，不公開該卡，直接加入手牌。受到 2 點以上傷害（如【雙重攻擊】）時，逐點重複處理。",
        en: "When your Leader takes damage and the Life card has a [Trigger] effect, you may reveal it and activate the [Trigger] instead of adding it to your hand, or choose not to and add it to your hand without revealing it. With 2 or more damage (such as [Double Attack]), this repeats for each point.",
      },
    ],
  },
  {
    id: "keywords",
    title: { hant: "常見效果用語", en: "Common effect keywords" },
    kind: "ul",
    items: [
      { hant: "【登場時】：擁有此效果的角色登場至場上時發動。", en: "[On Play]: activates when a Character with this effect is played onto the field." },
      { hant: "【啟動主要】：可以在我方的主要階段中發動。", en: "[Activate: Main]: can be activated during your Main Phase." },
      { hant: "【我方的回合中】：在我方的回合中發動。", en: "[Your Turn]: activates during your turn." },
      { hant: "【我方的回合結束時】：在我方回合的結束階段發動。", en: "[End of Your Turn]: activates in the End Phase of your turn." },
      { hant: "【主要】：事件卡的效果，可以在我方的主要階段使用。", en: "[Main]: an Event effect you can use during your Main Phase." },
      { hant: "【反擊】：事件卡的效果，可在對方回合的反擊步驟打出。", en: "[Counter]: an Event effect you can play during the Counter step of the opponent's turn." },
      { hant: "【每回合1次】：每回合只能發動 1 次。", en: "[Once Per Turn]: can be activated only once per turn." },
      { hant: "【咚!!×N】：當該角色依附有 N 張以上咚!!卡時（可以）發動的效果。", en: "[DON!! xN]: an effect that applies when the Character has N or more DON!! cards attached." },
      { hant: "①：把我方費用區的 1 張咚!!卡轉為休息狀態來發動，張數依數字而不同。", en: "①: activated by resting 1 DON!! card in your Cost area; the number of cards depends on the number shown." },
      { hant: "【咚!!−N】：把我方場上（領袖、角色區、費用區）的 N 張咚!!卡放回咚!!卡組來發動。依附的咚!!卡不論活躍或休息，都可以放回咚!!卡組。", en: "[DON!! −N]: activated by returning N DON!! cards from your field (Leader, Character area, Cost area) to the DON!! deck. Attached DON!! cards can be returned whether active or rested." },
      { hant: "【阻擋者】：可以在阻擋步驟發動，代替被對方攻擊的領袖或角色接受攻擊。", en: "[Blocker]: can be activated in the Block step to take the attack in place of the attacked Leader or Character." },
      { hant: "【速攻】：可以在登場的回合中進行攻擊。", en: "[Rush]: the Character can attack on the turn it is played." },
      { hant: "【雙重攻擊】：擁有此效果的角色攻擊給予對方領袖傷害時，給予 2 點傷害。", en: "[Double Attack]: when this Character's attack damages the opponent's Leader, it deals 2 damage." },
      { hant: "【流放】：擁有此效果的角色攻擊給予對方領袖傷害時，不會發動觸發效果，直接將該卡置於廢棄區。", en: "[Banish]: when this Character's attack damages the opponent's Leader, the [Trigger] does not activate and that card is placed in the Trash." },
    ],
  },
  {
    id: "end",
    title: { hant: "結束階段與效果順序", en: "End Phase and effect order" },
    kind: "ol",
    items: [
      { hant: "我方「回合結束時」的效果發動並解決。", en: "Your \"end of turn\" effects activate and resolve." },
      { hant: "對方「回合結束時」的效果發動並解決。", en: "The opponent's \"end of turn\" effects activate and resolve." },
      { hant: "我方「本回合中」等指定期限的效果失效。", en: "Your \"during this turn\" effects expire." },
      { hant: "對方的同類效果失效。", en: "The opponent's such effects expire." },
      { hant: "移交回合。", en: "Pass the turn." },
    ],
  },
  {
    id: "order",
    title: { hant: "效果同時發生時", en: "When effects happen at the same time" },
    kind: "p",
    items: [
      {
        hant: "同一時間發生多個效果，由效果所屬卡牌的持有玩家決定順序。雙方效果同時發生時，先發動並解決該回合玩家的所有效果，之後才輪到對方玩家。",
        en: "If several effects trigger at once, their owner chooses the order. If both players have effects at once, the turn player activates and resolves all of theirs first, then the other player's.",
      },
    ],
  },
];
