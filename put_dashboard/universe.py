# -*- coding: utf-8 -*-
"""
Curated Option-Eligible Universe across 3 Markets:
1. US Stocks & Core ETFs (us_stk) - High option liquidity, strong moat / Wheel-eligible
2. US Futures (us_fut) - CME / COMEX / NYMEX / CBOT / ICE liquid futures options
3. China Futures (cn_fut) - SHFE / DCE / CZCE / INE / GFEX listed commodity options
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 1. US STOCKS & CORE ETFs (美股与核心ETF - 100股/张)
# ---------------------------------------------------------------------------
US_STOCKS: List[Dict[str, Any]] = [
    # --- Core Index & Macro ETFs ---
    {
        "id": "US_STK:SPY", "symbol": "SPY", "sina_code": "gb_spy", "yahoo_code": "SPY",
        "name": "标普500 ETF", "sub": "SPDR S&P 500 · 全球期权流动性之王",
        "market": "us_stk", "sector": "宽基/宏观ETF", "exchange": "NYSE Arca",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 5.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.14,
        "moat_note": "美股大盘核心基准，每日到期期权极度活跃，急跌时VIX飙升是经典卖Put收租窗口。",
    },
    {
        "id": "US_STK:QQQ", "symbol": "QQQ", "sina_code": "gb_qqq", "yahoo_code": "QQQ",
        "name": "纳指100 ETF", "sub": "Invesco QQQ · 科技巨头指数期权核心",
        "market": "us_stk", "sector": "宽基/宏观ETF", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 5.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.14,
        "moat_note": "汇聚美股科技七巨头，隐含波动率高于SPY且长期慢牛向上，适合回调至60日均线附近卖Put。",
    },
    {
        "id": "US_STK:IWM", "symbol": "IWM", "sina_code": "gb_iwm", "yahoo_code": "IWM",
        "name": "罗素2000 ETF", "sub": "iShares Russell 2000 · 美股小盘宽基",
        "market": "us_stk", "sector": "宽基/宏观ETF", "exchange": "NYSE Arca",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.0,
        "margin_rate": 0.20, "quality_tier": "A", "iv_skew": 0.15,
        "moat_note": "对美联储降息周期与美国内需敏感，箱体震荡特征明显，区间下沿卖Put胜率高。",
    },
    {
        "id": "US_STK:SMH", "symbol": "SMH", "sina_code": "gb_smh", "yahoo_code": "SMH",
        "name": "半导体 ETF", "sub": "VanEck Semiconductor · AI硬件核心篮子",
        "market": "us_stk", "sector": "AI/半导体", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 5.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.13,
        "moat_note": "涵盖NVDA/TSM/AVGO，规避单一个股财报暴雷风险同时享受高IV权利金。",
    },
    {
        "id": "US_STK:TLT", "symbol": "TLT", "sina_code": "gb_tlt", "yahoo_code": "TLT",
        "name": "20年+美债 ETF", "sub": "iShares 20+ Year Treasury · 长端利率锚",
        "market": "us_stk", "sector": "宽基/宏观ETF", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 1.0,
        "margin_rate": 0.15, "quality_tier": "S", "iv_skew": 0.08,
        "moat_note": "10Y/30Y美债收益率冲高阶段对应TLT底部强支撑，卖Put兼具票息保护与利率均值回归。",
    },
    {
        "id": "US_STK:GLD", "symbol": "GLD", "sina_code": "gb_gld", "yahoo_code": "GLD",
        "name": "SPDR黄金 ETF", "sub": "SPDR Gold Trust · 实物黄金期权替代",
        "market": "us_stk", "sector": "宽基/宏观ETF", "exchange": "NYSE Arca",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.0,
        "margin_rate": 0.18, "quality_tier": "S", "iv_skew": 0.09,
        "moat_note": "全球央行购金与去美元化构筑中长期底仓，小账户可用GLD替代COMEX期金卖Put。",
    },
    {
        "id": "US_STK:IBIT", "symbol": "IBIT", "sina_code": "gb_ibit", "yahoo_code": "IBIT",
        "name": "比特币现货 ETF", "sub": "iShares Bitcoin Trust · 高波动数字资产",
        "market": "us_stk", "sector": "宽基/宏观ETF", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 1.0,
        "margin_rate": 0.30, "quality_tier": "A", "iv_skew": 0.16,
        "moat_note": "隐含波动率长期维持50%+，深度回调后卖远端深虚值Put（Delta -0.15）年化收租极厚。",
    },
    # --- Magnificent 7 & AI Leaders ---
    {
        "id": "US_STK:NVDA", "symbol": "NVDA", "sina_code": "gb_nvda", "yahoo_code": "NVDA",
        "name": "英伟达", "sub": "NVIDIA · AI算力绝对霸主",
        "market": "us_stk", "sector": "AI/半导体", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.22, "quality_tier": "S", "iv_skew": 0.14,
        "moat_note": "全市场期权成交额第一，IV溢价极丰厚，急跌回调至均线密集区是机构Wheel策略首选标的。",
    },
    {
        "id": "US_STK:AAPL", "symbol": "AAPL", "sina_code": "gb_aapl", "yahoo_code": "AAPL",
        "name": "苹果", "sub": "Apple · 巨量回购护盘现金牛",
        "market": "us_stk", "sector": "科技巨头", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 5.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.11,
        "moat_note": "每年千亿美元级股票回购提供天然买盘托底，适合稳健型资金卖Put收租或低位接货。",
    },
    {
        "id": "US_STK:MSFT", "symbol": "MSFT", "sina_code": "gb_msft", "yahoo_code": "MSFT",
        "name": "微软", "sub": "Microsoft · 云计算与企业AI底座",
        "market": "us_stk", "sector": "科技巨头", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 5.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.11,
        "moat_note": "AAA级资产负债表与极高经常性收入，回撤可控，回调至布林下轨时卖Put安全边际极高。",
    },
    {
        "id": "US_STK:GOOGL", "symbol": "GOOGL", "sina_code": "gb_googl", "yahoo_code": "GOOGL",
        "name": "谷歌A", "sub": "Alphabet · 搜索垄断+云+Gemini",
        "market": "us_stk", "sector": "科技巨头", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.12,
        "moat_note": "科技七巨头中PE估值极具性价比，现金流充沛，情绪打压回调往往提供高胜率卖Put机会。",
    },
    {
        "id": "US_STK:AMZN", "symbol": "AMZN", "sina_code": "gb_amzn", "yahoo_code": "AMZN",
        "name": "亚马逊", "sub": "Amazon · AWS云龙头+北美电商霸主",
        "market": "us_stk", "sector": "科技巨头", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.12,
        "moat_note": "经营现金流持续释放，期权链买卖价差极窄（1美分），适合30-45天周期滚动卖Put。",
    },
    {
        "id": "US_STK:META", "symbol": "META", "sina_code": "gb_meta", "yahoo_code": "META",
        "name": "Meta", "sub": "Meta Platforms · 社交广告印钞机+AI开源",
        "market": "us_stk", "sector": "科技巨头", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 5.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.13,
        "moat_note": "高ROE与强自由现金流，波动率高于微软苹果，权利金年化回报优异。",
    },
    {
        "id": "US_STK:TSLA", "symbol": "TSLA", "sina_code": "gb_tsla", "yahoo_code": "TSLA",
        "name": "特斯拉", "sub": "Tesla · 智驾FSD与人形机器人高波动龙头",
        "market": "us_stk", "sector": "科技巨头", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 5.0,
        "margin_rate": 0.25, "quality_tier": "A", "iv_skew": 0.16,
        "moat_note": "超高IV权利金之王，仅建议在阶段性大跌企稳后卖深虚值Put（安全垫>12%），严控仓位。",
    },
    {
        "id": "US_STK:AVGO", "symbol": "AVGO", "sina_code": "gb_avgo", "yahoo_code": "AVGO",
        "name": "博通", "sub": "Broadcom · AI定制ASIC芯片+VMware",
        "market": "us_stk", "sector": "AI/半导体", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.22, "quality_tier": "S", "iv_skew": 0.13,
        "moat_note": "AI网络与定制芯片双寡头，拆股后期权合约门槛亲民，适合逢回调卖Put。",
    },
    {
        "id": "US_STK:TSM", "symbol": "TSM", "sina_code": "gb_tsm", "yahoo_code": "TSM",
        "name": "台积电", "sub": "TSMC · 全球先进制程晶圆代工唯一龙头",
        "market": "us_stk", "sector": "AI/半导体", "exchange": "NYSE",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.13,
        "moat_note": "AI算力铲子股，估值具有扎实业绩支撑，回调至支撑位是极佳的以接货之心卖Put标的。",
    },
    {
        "id": "US_STK:AMD", "symbol": "AMD", "sina_code": "gb_amd", "yahoo_code": "AMD",
        "name": "超威半导体", "sub": "AMD · 数据中心CPU+AI GPU第二极",
        "market": "us_stk", "sector": "AI/半导体", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.22, "quality_tier": "A", "iv_skew": 0.14,
        "moat_note": "回撤充分时下方空间受限而IV较高，适合在历史低分位区间卖虚值Put。",
    },
    {
        "id": "US_STK:ASML", "symbol": "ASML", "sina_code": "gb_asml", "yahoo_code": "ASML",
        "name": "阿斯麦", "sub": "ASML · EUV光刻机全球独家垄断",
        "market": "us_stk", "sector": "AI/半导体", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 10.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.12,
        "moat_note": "半导体皇冠上的明珠，订单能见度跨越周期，急跌后卖Put具备极强产业壁垒保护。",
    },
    {
        "id": "US_STK:MU", "symbol": "MU", "sina_code": "gb_mu", "yahoo_code": "MU",
        "name": "美光科技", "sub": "Micron · HBM高带宽存储芯片主力",
        "market": "us_stk", "sector": "AI/半导体", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.22, "quality_tier": "A", "iv_skew": 0.14,
        "moat_note": "存储周期与HBM产能锁定量价齐升，波段回调幅度大、IV丰厚，适合低位卖Put。",
    },
    {
        "id": "US_STK:NFLX", "symbol": "NFLX", "sina_code": "gb_nflx", "yahoo_code": "NFLX",
        "name": "奈飞", "sub": "Netflix · 全球流媒体定价值龙头",
        "market": "us_stk", "sector": "科技巨头", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 10.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.12,
        "moat_note": "订阅制强现金流与广告变现双轮驱动，受关税与地缘扰动小。",
    },
    {
        "id": "US_STK:PLTR", "symbol": "PLTR", "sina_code": "gb_pltr", "yahoo_code": "PLTR",
        "name": "Palantir", "sub": "Palantir · AI政企操作系统龙头",
        "market": "us_stk", "sector": "AI/半导体", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 1.0,
        "margin_rate": 0.25, "quality_tier": "A", "iv_skew": 0.15,
        "moat_note": "纳入标普500后机构持仓稳固，单张期权资金占用低、IV极高，适合小资金高频收租。",
    },
    # --- Value Blue Chips & China ADRs ---
    {
        "id": "US_STK:BRK-B", "symbol": "BRK-B", "sina_code": "gb_brk$b", "yahoo_code": "BRK-B",
        "name": "伯克希尔B", "sub": "Berkshire Hathaway · 巨额现金储备价值锚",
        "market": "us_stk", "sector": "价值蓝筹", "exchange": "NYSE",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 5.0,
        "margin_rate": 0.18, "quality_tier": "S", "iv_skew": 0.09,
        "moat_note": "手握超3000亿美元短期国债现金，账面价值支撑极强，是防御型卖Put的压舱石。",
    },
    {
        "id": "US_STK:JPM", "symbol": "JPM", "sina_code": "gb_jpm", "yahoo_code": "JPM",
        "name": "摩根大通", "sub": "JPMorgan Chase · 美国银行业绝对龙头",
        "market": "us_stk", "sector": "价值蓝筹", "exchange": "NYSE",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.11,
        "moat_note": "低市盈率、高分红与回购，净息差与投行收入双强，回调卖Put接货性价比高。",
    },
    {
        "id": "US_STK:COST", "symbol": "COST", "sina_code": "gb_cost", "yahoo_code": "COST",
        "name": "开市客", "sub": "Costco · 会员制零售抗周期龙头",
        "market": "us_stk", "sector": "价值蓝筹", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 10.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.10,
        "moat_note": "90%+会员续费率穿越通胀与衰退周期，每次回踩120日均线均为经典买点。",
    },
    {
        "id": "US_STK:LLY", "symbol": "LLY", "sina_code": "gb_lly", "yahoo_code": "LLY",
        "name": "礼来", "sub": "Eli Lilly · GLP-1减重与代谢药全球霸主",
        "market": "us_stk", "sector": "价值蓝筹", "exchange": "NYSE",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 10.0,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.12,
        "moat_note": "医药板块最强成长确定性，与科技股相关性低，提供极佳的跨行业卖Put分散。",
    },
    {
        "id": "US_STK:XOM", "symbol": "XOM", "sina_code": "gb_xom", "yahoo_code": "XOM",
        "name": "埃克森美孚", "sub": "ExxonMobil · 低成本页岩+圭亚那高股息能源巨头",
        "market": "us_stk", "sector": "价值蓝筹", "exchange": "NYSE",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.20, "quality_tier": "S", "iv_skew": 0.10,
        "moat_note": "近4%股息率+强劲自由现金流，地缘与通胀对冲标的，底部支撑极为扎实。",
    },
    {
        "id": "US_STK:BABA", "symbol": "BABA", "sina_code": "gb_baba", "yahoo_code": "BABA",
        "name": "阿里巴巴", "sub": "Alibaba · 超高比例回购+阿里云AI价值重估",
        "market": "us_stk", "sector": "中概龙头", "exchange": "NYSE",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.22, "quality_tier": "A", "iv_skew": 0.14,
        "moat_note": "净现金加年度百亿美元回购+分红提供明确估值底，且期权IV较高，适合底部区间卖Put。",
    },
    {
        "id": "US_STK:PDD", "symbol": "PDD", "sina_code": "gb_pdd", "yahoo_code": "PDD",
        "name": "拼多多", "sub": "PDD Holdings · 极致性价比电商现金牛",
        "market": "us_stk", "sector": "中概龙头", "exchange": "NASDAQ",
        "unit": "USD", "currency": "$", "dp": 2, "multiplier": 100, "strike_step": 2.5,
        "margin_rate": 0.22, "quality_tier": "A", "iv_skew": 0.15,
        "moat_note": "PE估值处于全球科技股最低梯队，账面净现金极厚，回调企稳后卖虚值Put赔率优。",
    },
]

# ---------------------------------------------------------------------------
# 2. US FUTURES (美国期货 - CME / COMEX / NYMEX / CBOT / ICE)
#    All Yahoo symbols use identical units between real-time quote & daily K-lines
# ---------------------------------------------------------------------------
US_FUTURES: List[Dict[str, Any]] = [
    {
        "id": "US_FUT:GC", "symbol": "GC=F", "sina_code": "hf_GC", "yahoo_code": "GC=F",
        "name": "COMEX黄金", "sub": "COMEX Gold (OG) · 100盎司/手 · 另有微金MGC",
        "market": "us_fut", "sector": "贵金属", "exchange": "COMEX",
        "unit": "USD/盎司", "currency": "$", "dp": 1, "multiplier": 100, "strike_step": 25.0,
        "margin_rate": 0.08, "iv_skew": 0.08, "proxy_etf": "GLD",
        "cost": {
            "cash_cost": 1250.0, "primary_cost": 1550.0, "comfort_high": 2800.0,
            "label": "全球金矿AISC全维持成本", "source": "全球主要金企AISC综合",
        },
        "moat_note": "全球央行持续增持黄金构筑坚实买盘底，急跌回调至20/60日均线卖Put胜率极高。",
    },
    {
        "id": "US_FUT:SI", "symbol": "SI=F", "sina_code": "hf_SI", "yahoo_code": "SI=F",
        "name": "COMEX白银", "sub": "COMEX Silver (SO) · 5000盎司/手 · 另有微银SIL",
        "market": "us_fut", "sector": "贵金属", "exchange": "COMEX",
        "unit": "USD/盎司", "currency": "$", "dp": 2, "multiplier": 5000, "strike_step": 1.0,
        "margin_rate": 0.12, "iv_skew": 0.11, "proxy_etf": "SLV",
        "cost": {
            "cash_cost": 16.0, "primary_cost": 22.0, "comfort_high": 38.0,
            "label": "全球白银主产+副产综合成本", "source": "World Silver Survey",
        },
        "moat_note": "光伏与工业用银连续多年供需缺口，波动率显著高于黄金，建议选择远端深虚值行权价。",
    },
    {
        "id": "US_FUT:HG", "symbol": "HG=F", "sina_code": "hf_HG", "yahoo_code": "HG=F",
        "name": "COMEX铜", "sub": "COMEX Copper (HXE) · 25000磅/手",
        "market": "us_fut", "sector": "有色金属", "exchange": "COMEX",
        "unit": "USD/磅", "currency": "$", "dp": 3, "multiplier": 25000, "strike_step": 0.10,
        "margin_rate": 0.10, "iv_skew": 0.10, "proxy_etf": "CPER",
        "cost": {
            "cash_cost": 2.40, "primary_cost": 3.40, "comfort_high": 4.80,
            "label": "全球铜矿C1现金与全维持激励成本", "source": "矿山成本曲线90分位激励价",
        },
        "moat_note": "铜矿品位下滑与电网/AI数据中心长期需求支撑，回调至成本带与均线区适合卖Put。",
    },
    {
        "id": "US_FUT:PL", "symbol": "PL=F", "sina_code": "hf_PL", "yahoo_code": "PL=F",
        "name": "NYMEX铂金", "sub": "NYMEX Platinum (PO) · 50盎司/手",
        "market": "us_fut", "sector": "贵金属", "exchange": "NYMEX",
        "unit": "USD/盎司", "currency": "$", "dp": 1, "multiplier": 50, "strike_step": 25.0,
        "margin_rate": 0.10, "iv_skew": 0.10, "proxy_etf": "PPLT",
        "cost": {
            "cash_cost": 920.0, "primary_cost": 1080.0, "comfort_high": 1450.0,
            "label": "南非铂族金属综合矿山成本", "source": "WPIC南非矿企成本曲线",
        },
        "moat_note": "相比金价处于历史极低比价区，且南非深井矿山成本刚性极强，破成本后减产保护明确。",
    },
    {
        "id": "US_FUT:CL", "symbol": "CL=F", "sina_code": "hf_CL", "yahoo_code": "CL=F",
        "name": "WTI原油", "sub": "NYMEX WTI Crude (LO) · 1000桶/手 · 另有MCL",
        "market": "us_fut", "sector": "能源", "exchange": "NYMEX",
        "unit": "USD/桶", "currency": "$", "dp": 2, "multiplier": 1000, "strike_step": 2.5,
        "margin_rate": 0.10, "iv_skew": 0.15, "proxy_etf": "USO",
        "cost": {
            "cash_cost": 45.0, "primary_cost": 62.0, "comfort_high": 85.0,
            "label": "美国二叠纪页岩油全周期完井激励成本", "source": "Dallas Fed Energy Survey",
        },
        "moat_note": "60-65美元是美国页岩油新井盈亏平衡线及美国战略石油储备(SPR)回补触发带，底部支撑硬。",
    },
    {
        "id": "US_FUT:BZ", "symbol": "BZ=F", "sina_code": "hf_OIL", "yahoo_code": "BZ=F",
        "name": "布伦特原油", "sub": "ICE Brent Crude · 1000桶/手",
        "market": "us_fut", "sector": "能源", "exchange": "ICE",
        "unit": "USD/桶", "currency": "$", "dp": 2, "multiplier": 1000, "strike_step": 2.5,
        "margin_rate": 0.10, "iv_skew": 0.15, "proxy_etf": "BNO",
        "cost": {
            "cash_cost": 48.0, "primary_cost": 66.0, "comfort_high": 90.0,
            "label": "全球海运原油边际成本与OPEC+护盘锚", "source": "全球上游边际供给曲线",
        },
        "moat_note": "OPEC+联合减产机制对低油价高度敏感，配合远月贴水(Backwardation)结构适合逢低卖Put。",
    },
    {
        "id": "US_FUT:NG", "symbol": "NG=F", "sina_code": "hf_NG", "yahoo_code": "NG=F",
        "name": "Henry Hub天然气", "sub": "NYMEX NatGas (ON) · 10000 MMBtu/手",
        "market": "us_fut", "sector": "能源", "exchange": "NYMEX",
        "unit": "USD/MMBtu", "currency": "$", "dp": 3, "multiplier": 10000, "strike_step": 0.25,
        "margin_rate": 0.14, "iv_skew": 0.16, "proxy_etf": "UNG",
        "cost": {
            "cash_cost": 1.85, "primary_cost": 2.75, "comfort_high": 4.20,
            "label": "美国干气主产盆地全周期成本", "source": "Appalachian/Haynesville成本中枢",
        },
        "moat_note": "跌破2.5美元将迫使干气生产商关井减产，且LNG出口产能持续投放，低位卖Put赔率极佳。",
    },
    {
        "id": "US_FUT:ZS", "symbol": "ZS=F", "sina_code": "hf_S", "yahoo_code": "ZS=F",
        "name": "CBOT大豆", "sub": "CBOT Soybeans (OZS) · 5000蒲式耳/手",
        "market": "us_fut", "sector": "农产品", "exchange": "CBOT",
        "unit": "美分/蒲", "currency": "¢", "dp": 1, "multiplier": 50, "strike_step": 20.0,
        "margin_rate": 0.08, "iv_skew": 0.10, "proxy_etf": "SOYB",
        "cost": {
            "cash_cost": 940.0, "primary_cost": 1120.0, "comfort_high": 1350.0,
            "label": "美国中西部大豆完全种植成本(含地租)", "source": "USDA / 伊利诺伊大学农场预算",
        },
        "moat_note": "农作物跌破种植完全成本后次年种植面积将向玉米/休耕转移，成本锚以下卖Put安全垫扎实。",
    },
    {
        "id": "US_FUT:ZC", "symbol": "ZC=F", "sina_code": "hf_C", "yahoo_code": "ZC=F",
        "name": "CBOT玉米", "sub": "CBOT Corn (OZC) · 5000蒲式耳/手",
        "market": "us_fut", "sector": "农产品", "exchange": "CBOT",
        "unit": "美分/蒲", "currency": "¢", "dp": 1, "multiplier": 50, "strike_step": 10.0,
        "margin_rate": 0.08, "iv_skew": 0.10, "proxy_etf": "CORN",
        "cost": {
            "cash_cost": 370.0, "primary_cost": 445.0, "comfort_high": 560.0,
            "label": "美国玉米完全种植成本中枢", "source": "USDA ERS玉米生产成本",
        },
        "moat_note": "400-440美分处于美玉米完全种植成本带，农户惜售情绪强且乙醇刚需托底，适合底部卖Put。",
    },
    {
        "id": "US_FUT:ZW", "symbol": "ZW=F", "sina_code": "hf_W", "yahoo_code": "ZW=F",
        "name": "CBOT小麦", "sub": "CBOT Wheat (OZW) · 5000蒲式耳/手",
        "market": "us_fut", "sector": "农产品", "exchange": "CBOT",
        "unit": "美分/蒲", "currency": "¢", "dp": 1, "multiplier": 50, "strike_step": 15.0,
        "margin_rate": 0.09, "iv_skew": 0.11, "proxy_etf": "WEAT",
        "cost": {
            "cash_cost": 490.0, "primary_cost": 590.0, "comfort_high": 740.0,
            "label": "美国冬小麦完全种植成本带", "source": "USDA农场成本估计",
        },
        "moat_note": "主产国天气与黑海出口扰动易引发空头回补，在种植成本线附近卖虚值Put胜率高。",
    },
    {
        "id": "US_FUT:ZM", "symbol": "ZM=F", "sina_code": "hf_SM", "yahoo_code": "ZM=F",
        "name": "CBOT豆粕", "sub": "CBOT Soybean Meal (OZM) · 100短吨/手",
        "market": "us_fut", "sector": "农产品", "exchange": "CBOT",
        "unit": "USD/短吨", "currency": "$", "dp": 1, "multiplier": 100, "strike_step": 10.0,
        "margin_rate": 0.08, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 285.0, "primary_cost": 325.0, "comfort_high": 410.0,
            "label": "美豆压榨折豆粕成本中枢", "source": "CBOT压榨模型锚定",
        },
        "moat_note": "全球饲用蛋白基准，与国内大商所豆粕M0联动紧密，贴近300-320美元成本带时下方空间极小。",
    },
    {
        "id": "US_FUT:ZL", "symbol": "ZL=F", "sina_code": "hf_BO", "yahoo_code": "ZL=F",
        "name": "CBOT豆油", "sub": "CBOT Soybean Oil (OZL) · 60000磅/手",
        "market": "us_fut", "sector": "农产品", "exchange": "CBOT",
        "unit": "美分/磅", "currency": "¢", "dp": 2, "multiplier": 600, "strike_step": 2.0,
        "margin_rate": 0.09, "iv_skew": 0.11,
        "cost": {
            "cash_cost": 38.0, "primary_cost": 46.0, "comfort_high": 62.0,
            "label": "北美生物柴油掺混与压榨成本锚", "source": "EPA生柴政策与压榨成本",
        },
        "moat_note": "受美国可再生柴油(RD)掺混政令强支撑，回落至成本带是稳健卖Put区间。",
    },
    {
        "id": "US_FUT:SB", "symbol": "SB=F", "sina_code": "", "yahoo_code": "SB=F",
        "name": "ICE原糖11号", "sub": "ICE Sugar No.11 (YO) · 112000磅/手",
        "market": "us_fut", "sector": "农产品", "exchange": "ICE",
        "unit": "美分/磅", "currency": "¢", "dp": 2, "multiplier": 1120, "strike_step": 0.5,
        "margin_rate": 0.09, "iv_skew": 0.11, "proxy_etf": "CANE",
        "cost": {
            "cash_cost": 14.5, "primary_cost": 17.5, "comfort_high": 23.0,
            "label": "巴西醇糖比转换平衡点与印度出口成本", "source": "巴西中南部制糖/制醇切换锚",
        },
        "moat_note": "巴西糖厂可在制糖与乙醇间灵活切换，原糖跌近乙醇折糖价（16-18美分）时将触发制糖比例下调。",
    },
    {
        "id": "US_FUT:CT", "symbol": "CT=F", "sina_code": "hf_CT", "yahoo_code": "CT=F",
        "name": "ICE美棉", "sub": "ICE Cotton No.2 · 50000磅/手",
        "market": "us_fut", "sector": "农产品", "exchange": "ICE",
        "unit": "美分/磅", "currency": "¢", "dp": 2, "multiplier": 500, "strike_step": 2.0,
        "margin_rate": 0.08, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 66.0, "primary_cost": 78.0, "comfort_high": 92.0,
            "label": "美国得州陆地棉完全种植成本", "source": "USDA棉花成本预算",
        },
        "moat_note": "长期围绕70-80美分种植成本磨底，下方有美国农场补贴贷款与减种支撑，适合底部卖Put。",
    },
    {
        "id": "US_FUT:KC", "symbol": "KC=F", "sina_code": "hf_KC", "yahoo_code": "KC=F",
        "name": "ICE阿拉比卡咖啡", "sub": "ICE Coffee C · 37500磅/手",
        "market": "us_fut", "sector": "农产品", "exchange": "ICE",
        "unit": "美分/磅", "currency": "¢", "dp": 1, "multiplier": 375, "strike_step": 10.0,
        "margin_rate": 0.12, "iv_skew": 0.12,
        "cost": {
            "cash_cost": 135.0, "primary_cost": 175.0, "comfort_high": 250.0,
            "label": "巴西与哥伦比亚咖啡庄园完全成本", "source": "产地完全成本估计",
        },
        "moat_note": "库存周期紧平衡，若价格处于历史高位需等待回撤企稳后再卖远端深虚值Put。",
    },
    {
        "id": "US_FUT:ES", "symbol": "ES=F", "sina_code": "hf_ES", "yahoo_code": "ES=F",
        "name": "E-mini标普500期指", "sub": "CME E-mini S&P 500 · 50美元/点 · 另有MES",
        "market": "us_fut", "sector": "股指/利率", "exchange": "CME",
        "unit": "点", "currency": "$", "dp": 2, "multiplier": 50, "strike_step": 50.0,
        "margin_rate": 0.08, "iv_skew": 0.15, "proxy_etf": "SPY",
        "moat_note": "SPAN投资组合保证金效率极高（对比SPY节省一半保证金），且享受美国Section 1256税率优势。",
    },
    {
        "id": "US_FUT:NQ", "symbol": "NQ=F", "sina_code": "hf_NQ", "yahoo_code": "NQ=F",
        "name": "E-mini纳指100期指", "sub": "CME E-mini Nasdaq-100 · 20美元/点 · 另有MNQ",
        "market": "us_fut", "sector": "股指/利率", "exchange": "CME",
        "unit": "点", "currency": "$", "dp": 2, "multiplier": 20, "strike_step": 100.0,
        "margin_rate": 0.09, "iv_skew": 0.15, "proxy_etf": "QQQ",
        "moat_note": "23小时全天候交易，可在非美股交易时段随时对冲或捕捉恐慌脉冲高IV卖Put窗口。",
    },
    {
        "id": "US_FUT:ZN", "symbol": "ZN=F", "sina_code": "", "yahoo_code": "ZN=F",
        "name": "10年期美债期货", "sub": "CBOT 10-Year T-Note (OZN) · 1000美元/点",
        "market": "us_fut", "sector": "股指/利率", "exchange": "CBOT",
        "unit": "点", "currency": "$", "dp": 3, "multiplier": 1000, "strike_step": 0.5,
        "margin_rate": 0.04, "iv_skew": 0.07, "proxy_etf": "IEF",
        "moat_note": "全球利率定价锚，保证金占用极低，美联储限制性利率顶部区间适合逢低卖Put。",
    },
]

# ---------------------------------------------------------------------------
# 3. CHINA FUTURES (中国期货期权 - 中金所 / 上期所 / 大商所 / 郑商所 / 上期能源 / 广期所)
#    All have listed commodity or financial options in China!
# ---------------------------------------------------------------------------
CN_FUTURES: List[Dict[str, Any]] = [
    # --- 中金所 A股三大股指期权 (MO / IO / HO) ---
    {
        "id": "CN_FUT:IM0", "symbol": "IM0", "sina_code": "nf_IM0", "cffex_opt": "mo",
        "name": "中证1000股指", "sub": "中金所 · 中证1000股指期权(MO) · 100元/点",
        "market": "cn_fut", "sector": "股指期权", "exchange": "中金所",
        "unit": "点", "currency": "¥", "dp": 1, "multiplier": 100, "strike_step": 100.0,
        "margin_rate": 0.12, "iv_skew": 0.16, "quality_tier": "S",
        "moat_note": "中金所MO期权流动性极佳，受量化对冲与雪球结构影响常年存在贴水保护且虚值Put隐波极肥，急跌后卖深虚值Put收租性价比极高。",
    },
    {
        "id": "CN_FUT:IF0", "symbol": "IF0", "sina_code": "nf_IF0", "cffex_opt": "io",
        "name": "沪深300股指", "sub": "中金所 · 沪深300股指期权(IO) · 100元/点",
        "market": "cn_fut", "sector": "股指期权", "exchange": "中金所",
        "unit": "点", "currency": "¥", "dp": 1, "multiplier": 100, "strike_step": 50.0,
        "margin_rate": 0.10, "iv_skew": 0.13, "quality_tier": "S",
        "moat_note": "A股核心蓝筹宽基基准，PE估值安全边际厚且获汇金及险资宽基ETF持续托底，适合回调至60日均线或布林下轨时卖Put。",
    },
    {
        "id": "CN_FUT:IH0", "symbol": "IH0", "sina_code": "nf_IH0", "cffex_opt": "ho",
        "name": "上证50股指", "sub": "中金所 · 上证50股指期权(HO) · 100元/点",
        "market": "cn_fut", "sector": "股指期权", "exchange": "中金所",
        "unit": "点", "currency": "¥", "dp": 1, "multiplier": 100, "strike_step": 25.0,
        "margin_rate": 0.10, "iv_skew": 0.12, "quality_tier": "S",
        "moat_note": "汇聚高股息央国企与金融消费龙头，高分红率构筑扎实估值铁底，波动率温和可控，是防御型卖Put首选压舱石。",
    },
    # --- 贵金属 & 有色金属 ---
    {
        "id": "CN_FUT:AU0", "symbol": "AU0", "sina_code": "nf_AU0",
        "name": "沪金主连", "sub": "上期所 · 黄金期权 · 1000克/手",
        "market": "cn_fut", "sector": "贵金属", "exchange": "上期所",
        "unit": "元/克", "currency": "¥", "dp": 2, "multiplier": 1000, "strike_step": 8.0,
        "margin_rate": 0.10, "iv_skew": 0.08,
        "cost": {
            "cash_cost": 310.0, "primary_cost": 380.0, "comfort_high": 650.0,
            "label": "国内金矿全维持成本折算", "source": "国内头部金企年报成本",
        },
        "moat_note": "人民币计价黄金兼具国际金价支撑与汇率缓冲，回踩20/60日均线卖虚值Put胜率极高。",
    },
    {
        "id": "CN_FUT:AG0", "symbol": "AG0", "sina_code": "nf_AG0",
        "name": "沪银主连", "sub": "上期所 · 白银期权 · 15千克/手",
        "market": "cn_fut", "sector": "贵金属", "exchange": "上期所",
        "unit": "元/千克", "currency": "¥", "dp": 0, "multiplier": 15, "strike_step": 100.0,
        "margin_rate": 0.12, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 4200.0, "primary_cost": 5200.0, "comfort_high": 8500.0,
            "label": "国内银矿及冶炼综合成本", "source": "有色协会与矿企估计",
        },
        "moat_note": "国内白银期权流动性极佳，高波动带来丰厚权利金，宜选回调后的深虚值档位（Delta -0.15）。",
    },
    {
        "id": "CN_FUT:CU0", "symbol": "CU0", "sina_code": "nf_CU0",
        "name": "沪铜主连", "sub": "上期所 · 铜期权 · 5吨/手",
        "market": "cn_fut", "sector": "有色金属", "exchange": "上期所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 1000.0,
        "margin_rate": 0.10, "iv_skew": 0.09,
        "cost": {
            "cash_cost": 54000.0, "primary_cost": 65000.0, "comfort_high": 82000.0,
            "label": "全球铜矿90分位成本折人民币含税", "source": "矿山成本曲线+进口税费",
        },
        "moat_note": "国内电网投资与铜精矿TC加工费极低制约冶炼供应，回调至60日均线下方买盘极强。",
    },
    {
        "id": "CN_FUT:AL0", "symbol": "AL0", "sina_code": "nf_AL0",
        "name": "沪铝主连", "sub": "上期所 · 铝期权 · 5吨/手",
        "market": "cn_fut", "sector": "有色金属", "exchange": "上期所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 200.0,
        "margin_rate": 0.10, "iv_skew": 0.09,
        "cost": {
            "cash_cost": 16500.0, "primary_cost": 18200.0, "comfort_high": 21500.0,
            "label": "国内电解铝完全成本（氧化铝+电力）", "source": "SMM电解铝平均完全成本",
        },
        "moat_note": "中国4500万吨电解铝产能天花板硬约束，跌近18000元成本线时下方安全垫极厚。",
    },
    {
        "id": "CN_FUT:ZN0", "symbol": "ZN0", "sina_code": "nf_ZN0",
        "name": "沪锌主连", "sub": "上期所 · 锌期权 · 5吨/手",
        "market": "cn_fut", "sector": "有色金属", "exchange": "上期所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 200.0,
        "margin_rate": 0.10, "iv_skew": 0.09,
        "cost": {
            "cash_cost": 19500.0, "primary_cost": 21500.0, "comfort_high": 25500.0,
            "label": "锌矿山+冶炼综合完全成本", "source": "矿山+冶炼加工费模型",
        },
        "moat_note": "锌精矿加工费低位运行触发炼厂检修减产，成本中枢提供明确底部支撑。",
    },
    {
        "id": "CN_FUT:AO0", "symbol": "AO0", "sina_code": "nf_AO0",
        "name": "氧化铝主连", "sub": "上期所 · 氧化铝期权 · 20吨/手",
        "market": "cn_fut", "sector": "有色金属", "exchange": "上期所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 20, "strike_step": 50.0,
        "margin_rate": 0.11, "iv_skew": 0.11,
        "cost": {
            "cash_cost": 2650.0, "primary_cost": 2950.0, "comfort_high": 3600.0,
            "label": "晋豫进口矿氧化铝高成本边际线", "source": "山西/河南进口铝土矿完全成本",
        },
        "moat_note": "进口铝土矿与烧碱能源构成刚性现金成本，价格跌至2900-3100元区间后边际产能检修增多。",
    },
    # --- 黑色建材 ---
    {
        "id": "CN_FUT:RB0", "symbol": "RB0", "sina_code": "nf_RB0",
        "name": "螺纹钢主连", "sub": "上期所 · 螺纹钢期权 · 10吨/手",
        "market": "cn_fut", "sector": "黑色建材", "exchange": "上期所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 10, "strike_step": 50.0,
        "margin_rate": 0.09, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 2900.0, "primary_cost": 3120.0, "comfort_high": 3500.0,
            "label": "高炉长流程与谷电短流程成本带", "source": "钢厂铁水+废钢电炉成本模型",
        },
        "moat_note": "跌破电炉谷电成本与高炉现金成本（2900-3100元）会迅速引发钢厂主动减产去库，是典型成本底卖Put品种。",
    },
    {
        "id": "CN_FUT:I0", "symbol": "I0", "sina_code": "nf_I0",
        "name": "铁矿石主连", "sub": "大商所 · 铁矿石期权 · 100吨/手",
        "market": "cn_fut", "sector": "黑色建材", "exchange": "大商所",
        "unit": "元/吨", "currency": "¥", "dp": 1, "multiplier": 100, "strike_step": 10.0,
        "margin_rate": 0.12, "iv_skew": 0.12,
        "cost": {
            "cash_cost": 560.0, "primary_cost": 690.0, "comfort_high": 880.0,
            "label": "非主流矿与国产精粉边际成本折盘面", "source": "全球海运铁矿85-90分位成本（约85-90美元）",
        },
        "moat_note": "跌破85-90美元（盘面约680-720元）将挤出印度/非主流矿与国产矿供应，且主力合约常贴水现货，适合低位卖Put。",
    },
    {
        "id": "CN_FUT:SM0", "symbol": "SM0", "sina_code": "nf_SM0",
        "name": "锰硅主连", "sub": "郑商所 · 锰硅期权 · 5吨/手",
        "market": "cn_fut", "sector": "黑色建材", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 100.0,
        "margin_rate": 0.10, "iv_skew": 0.11,
        "cost": {
            "cash_cost": 5700.0, "primary_cost": 6150.0, "comfort_high": 7000.0,
            "label": "内蒙/宁夏主产区锰矿+电价完全成本", "source": "铁合金主产区即期电力与锰矿成本",
        },
        "moat_note": "高耗能铁合金品种，电力与进口锰矿占比超80%，跌破内蒙现金成本后下方空间被锁死。",
    },
    {
        "id": "CN_FUT:SF0", "symbol": "SF0", "sina_code": "nf_SF0",
        "name": "硅铁主连", "sub": "郑商所 · 硅铁期权 · 5吨/手",
        "market": "cn_fut", "sector": "黑色建材", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 100.0,
        "margin_rate": 0.10, "iv_skew": 0.11,
        "cost": {
            "cash_cost": 5600.0, "primary_cost": 6050.0, "comfort_high": 6900.0,
            "label": "主产区结算电价与兰炭硅石完全成本", "source": "宁夏/内蒙硅铁成本锚（约8000度电/吨）",
        },
        "moat_note": "单吨耗电约8000度，实质为“固态电力”，电价刚性使得5800-6100元成本底极难长期跌穿。",
    },
    # --- 能源与化工 ---
    {
        "id": "CN_FUT:SC0", "symbol": "SC0", "sina_code": "nf_SC0",
        "name": "原油SC主连", "sub": "上期能源 · 原油期权 · 1000桶/手",
        "market": "cn_fut", "sector": "能源", "exchange": "上期能源",
        "unit": "元/桶", "currency": "¥", "dp": 1, "multiplier": 1000, "strike_step": 10.0,
        "margin_rate": 0.11, "iv_skew": 0.13,
        "cost": {
            "cash_cost": 360.0, "primary_cost": 460.0, "comfort_high": 620.0,
            "label": "中东到岸原油平价成本带", "source": "OPEC+与页岩油成本折算人民币到岸价",
        },
        "moat_note": "期权IV充沛，贴近450-480元/桶页岩油全周期成本折算带时卖Put胜率极高。",
    },
    {
        "id": "CN_FUT:TA0", "symbol": "TA0", "sina_code": "nf_TA0",
        "name": "PTA主连", "sub": "郑商所 · PTA期权 · 5吨/手",
        "market": "cn_fut", "sector": "化工", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 50.0,
        "margin_rate": 0.09, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 4500.0, "primary_cost": 5050.0, "comfort_high": 6000.0,
            "label": "PX芳烃成本+300元极限低加工费", "source": "0.655*PX + 行业现金加工费底线",
        },
        "moat_note": "单手合约价值约2.5万元、保证金仅2500元，当PTA加工费压缩至250元以下时龙头大厂联合检修托底。",
    },
    {
        "id": "CN_FUT:MA0", "symbol": "MA0", "sina_code": "nf_MA0",
        "name": "甲醇主连", "sub": "郑商所 · 甲醇期权 · 10吨/手",
        "market": "cn_fut", "sector": "化工", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 10, "strike_step": 25.0,
        "margin_rate": 0.09, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 2050.0, "primary_cost": 2320.0, "comfort_high": 2700.0,
            "label": "西北煤制甲醇完全成本折华东交割价", "source": "坑口煤成本+西北至华东运费",
        },
        "moat_note": "冬季伊朗限气减产+国内煤制成本支撑明确，2250-2400元区间卖Put安全边际高。",
    },
    {
        "id": "CN_FUT:SA0", "symbol": "SA0", "sina_code": "nf_SA0",
        "name": "纯碱主连", "sub": "郑商所 · 纯碱期权 · 20吨/手",
        "market": "cn_fut", "sector": "化工", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 20, "strike_step": 20.0,
        "margin_rate": 0.11, "iv_skew": 0.12,
        "cost": {
            "cash_cost": 1250.0, "primary_cost": 1480.0, "comfort_high": 1950.0,
            "label": "联碱法/氨碱法综合现金与完全成本", "source": "氨碱法1550 / 联碱法1400 / 天然碱1100",
        },
        "moat_note": "经过大幅出清后价格已跌入氨碱与联碱亏损区间，高成本产能检修增加，破成本卖深虚值Put收租肥厚。",
    },
    {
        "id": "CN_FUT:FG0", "symbol": "FG0", "sina_code": "nf_FG0",
        "name": "玻璃主连", "sub": "郑商所 · 玻璃期权 · 20吨/手",
        "market": "cn_fut", "sector": "化工", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 20, "strike_step": 20.0,
        "margin_rate": 0.11, "iv_skew": 0.12,
        "cost": {
            "cash_cost": 1080.0, "primary_cost": 1260.0, "comfort_high": 1650.0,
            "label": "天然气/煤制气浮法玻璃完全成本中枢", "source": "沙河煤制气与华中天然气产线成本",
        },
        "moat_note": "浮法玻璃持续亏损将加速高龄窑炉冷修，冷修一旦启动复产需半年以上，跌破天然气成本线后适合卖Put。",
    },
    {
        "id": "CN_FUT:UR0", "symbol": "UR0", "sina_code": "nf_UR0",
        "name": "尿素主连", "sub": "郑商所 · 尿素期权 · 20吨/手",
        "market": "cn_fut", "sector": "化工", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 20, "strike_step": 20.0,
        "margin_rate": 0.09, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 1580.0, "primary_cost": 1750.0, "comfort_high": 2150.0,
            "label": "固定床煤制尿素与气头尿素完全成本", "source": "晋城无烟煤固定床与西南气头成本",
        },
        "moat_note": "农需刚性与国储托底并存，跌近固定床现金成本（1650-1750元）时向下空间极为有限。",
    },
    {
        "id": "CN_FUT:PP0", "symbol": "PP0", "sina_code": "nf_PP0",
        "name": "聚丙烯PP主连", "sub": "大商所 · 聚丙烯期权 · 5吨/手",
        "market": "cn_fut", "sector": "化工", "exchange": "大商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 50.0,
        "margin_rate": 0.08, "iv_skew": 0.09,
        "cost": {
            "cash_cost": 6700.0, "primary_cost": 7250.0, "comfort_high": 8100.0,
            "label": "油制与PDH丙烷脱氢综合成本", "source": "石脑油裂解与PDH工厂亏损停车线",
        },
        "moat_note": "PDH装置长期处于微利或亏损高开工弹性状态，价格波动率温和、底部扎实，适合稳健卖Put。",
    },
    {
        "id": "CN_FUT:L0", "symbol": "L0", "sina_code": "nf_L0",
        "name": "塑料LLDPE主连", "sub": "大商所 · 聚乙烯期权 · 5吨/手",
        "market": "cn_fut", "sector": "化工", "exchange": "大商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 50.0,
        "margin_rate": 0.08, "iv_skew": 0.09,
        "cost": {
            "cash_cost": 7100.0, "primary_cost": 7650.0, "comfort_high": 8500.0,
            "label": "油制线性聚乙烯完全成本中枢", "source": "石脑油裂解+煤化工综合成本",
        },
        "moat_note": "农膜与包装刚需稳定，常年呈窄幅箱体运行，非常适合箱体下沿卖Put收时间价值。",
    },
    {
        "id": "CN_FUT:V0", "symbol": "V0", "sina_code": "nf_V0",
        "name": "PVC主连", "sub": "大商所 · PVC期权 · 5吨/手",
        "market": "cn_fut", "sector": "化工", "exchange": "大商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 50.0,
        "margin_rate": 0.09, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 4750.0, "primary_cost": 5250.0, "comfort_high": 6100.0,
            "label": "外采电石法PVC现金与综合成本（含烧碱以碱补氯）", "source": "西北氯碱一体化与外采电石成本",
        },
        "moat_note": "处于历史极低分位磨底周期，跌破外采电石综合成本后向下弹性钝化，适合底部卖虚值Put。",
    },
    {
        "id": "CN_FUT:RU0", "symbol": "RU0", "sina_code": "nf_RU0",
        "name": "天然橡胶主连", "sub": "上期所 · 天胶期权 · 10吨/手",
        "market": "cn_fut", "sector": "化工", "exchange": "上期所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 10, "strike_step": 250.0,
        "margin_rate": 0.10, "iv_skew": 0.11,
        "cost": {
            "cash_cost": 11800.0, "primary_cost": 13500.0, "comfort_high": 17500.0,
            "label": "东南亚与云南/海南胶农弃割激励成本", "source": "ANRPC胶农割胶人工与全乳胶成本",
        },
        "moat_note": "前些年低胶价导致全球新种面积断档，树龄老化进入长周期产能收缩，回调至成本支撑带适合卖Put。",
    },
    # --- 农产品与生鲜 ---
    {
        "id": "CN_FUT:M0", "symbol": "M0", "sina_code": "nf_M0",
        "name": "豆粕主连", "sub": "大商所 · 豆粕期权（国内第一批商品期权）· 10吨/手",
        "market": "cn_fut", "sector": "农产品", "exchange": "大商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 10, "strike_step": 50.0,
        "margin_rate": 0.08, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 2650.0, "primary_cost": 2920.0, "comfort_high": 3500.0,
            "label": "进口美豆/巴西豆到港压榨折豆粕成本", "source": "进口大豆完税成本-豆油折算",
        },
        "moat_note": "国内商品期权流动性最佳品种之一，单手保证金仅约2500元，贴近进口压榨成本带卖Put胜率极高。",
    },
    {
        "id": "CN_FUT:RM0", "symbol": "RM0", "sina_code": "nf_RM0",
        "name": "菜粕主连", "sub": "郑商所 · 菜粕期权 · 10吨/手",
        "market": "cn_fut", "sector": "农产品", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 10, "strike_step": 25.0,
        "margin_rate": 0.09, "iv_skew": 0.11,
        "cost": {
            "cash_cost": 2100.0, "primary_cost": 2380.0, "comfort_high": 2900.0,
            "label": "进口油菜籽压榨折菜粕成本带", "source": "加拿大菜籽进口完税折算",
        },
        "moat_note": "水产养殖刚需且受贸易政策与进口菜籽成本支撑，低位高IV时卖虚值Put收租性价比突出。",
    },
    {
        "id": "CN_FUT:Y0", "symbol": "Y0", "sina_code": "nf_Y0",
        "name": "豆油主连", "sub": "大商所 · 豆油期权 · 10吨/手",
        "market": "cn_fut", "sector": "农产品", "exchange": "大商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 10, "strike_step": 100.0,
        "margin_rate": 0.08, "iv_skew": 0.09,
        "cost": {
            "cash_cost": 7000.0, "primary_cost": 7600.0, "comfort_high": 8800.0,
            "label": "进口大豆压榨折豆油成本锚", "source": "油厂压榨综合成本",
        },
        "moat_note": "油脂板块底部受生柴政策与进口成本双重托底，回调至均线密集区适合卖Put。",
    },
    {
        "id": "CN_FUT:P0", "symbol": "P0", "sina_code": "nf_P0",
        "name": "棕榈油主连", "sub": "大商所 · 棕榈油期权 · 10吨/手",
        "market": "cn_fut", "sector": "农产品", "exchange": "大商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 10, "strike_step": 100.0,
        "margin_rate": 0.09, "iv_skew": 0.10,
        "cost": {
            "cash_cost": 6800.0, "primary_cost": 7500.0, "comfort_high": 9200.0,
            "label": "印尼/马棕B40生柴政令与进口完税平价", "source": "产地FOB+出口税+海运费完税",
        },
        "moat_note": "印尼B40生物柴油强制掺混锁定全球油脂消费增量，产地树龄老化制约产量上限。",
    },
    {
        "id": "CN_FUT:C0", "symbol": "C0", "sina_code": "nf_C0",
        "name": "玉米主连", "sub": "大商所 · 玉米期权 · 10吨/手",
        "market": "cn_fut", "sector": "农产品", "exchange": "大商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 10, "strike_step": 20.0,
        "margin_rate": 0.07, "iv_skew": 0.08,
        "cost": {
            "cash_cost": 2050.0, "primary_cost": 2220.0, "comfort_high": 2550.0,
            "label": "东北租地种植集港成本与中储粮收储底", "source": "东北地租+农资折锦州港平舱成本",
        },
        "moat_note": "主粮安全底线品种，跌近东北种植成本（2150-2250元）即触发中储粮增储托市，是极低风险卖Put标的。",
    },
    {
        "id": "CN_FUT:SR0", "symbol": "SR0", "sina_code": "nf_SR0",
        "name": "白糖主连", "sub": "郑商所 · 白糖期权 · 10吨/手",
        "market": "cn_fut", "sector": "农产品", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 10, "strike_step": 100.0,
        "margin_rate": 0.08, "iv_skew": 0.09,
        "cost": {
            "cash_cost": 5200.0, "primary_cost": 5650.0, "comfort_high": 6500.0,
            "label": "广西甘蔗收购联动制糖完全成本", "source": "广西糖厂甘蔗收购价折算制糖成本（5500-5700元）",
        },
        "moat_note": "国内广西制糖成本（约5600元/吨）与配额外进口糖关税构筑双重政策护城河，贴近成本卖Put极稳。",
    },
    {
        "id": "CN_FUT:CF0", "symbol": "CF0", "sina_code": "nf_CF0",
        "name": "棉花主连", "sub": "郑商所 · 棉花期权 · 5吨/手",
        "market": "cn_fut", "sector": "农产品", "exchange": "郑商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 200.0,
        "margin_rate": 0.08, "iv_skew": 0.09,
        "cost": {
            "cash_cost": 13200.0, "primary_cost": 14500.0, "comfort_high": 16800.0,
            "label": "新疆机采棉包地种植+轧花加工完全成本", "source": "新疆籽棉收购价折皮棉公定成本与18600目标价补贴",
        },
        "moat_note": "13500-14500元处于新疆轧花厂综合成本区间，且受国家目标价格补贴保护，下方空间极其有限。",
    },
    {
        "id": "CN_FUT:LH0", "symbol": "LH0", "sina_code": "nf_LH0",
        "name": "生猪主连", "sub": "大商所 · 生猪期权 · 16吨/手",
        "market": "cn_fut", "sector": "农产品", "exchange": "大商所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 16, "strike_step": 250.0,
        "margin_rate": 0.10, "iv_skew": 0.11,
        "cost": {
            "cash_cost": 13200.0, "primary_cost": 14600.0, "comfort_high": 18000.0,
            "label": "规模猪场自繁自养完全成本（14.0-14.8元/公斤）", "source": "上市猪企与行业平均完全养殖成本",
        },
        "moat_note": "猪价跌破14000元/吨将引发能繁母猪主动淘汰与冻品收储预期，在养殖成本线下方卖Put胜率高。",
    },
    # --- 广期所新能源 ---
    {
        "id": "CN_FUT:SI0", "symbol": "SI0", "sina_code": "nf_SI0",
        "name": "工业硅主连", "sub": "广期所 · 工业硅期权 · 5吨/手",
        "market": "cn_fut", "sector": "新能源", "exchange": "广期所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 5, "strike_step": 100.0,
        "margin_rate": 0.10, "iv_skew": 0.11,
        "cost": {
            "cash_cost": 9200.0, "primary_cost": 10600.0, "comfort_high": 13500.0,
            "label": "新疆枯水期煤电硅与西南丰水期现金成本", "source": "SMM新疆/云南/四川工业硅完全成本",
        },
        "moat_note": "历经两年深跌已击穿西南全部产能及新疆部分产能现金成本，破现金成本区卖深虚值Put具备强减产支撑。",
    },
    {
        "id": "CN_FUT:LC0", "symbol": "LC0", "sina_code": "nf_LC0",
        "name": "碳酸锂主连", "sub": "广期所 · 碳酸锂期权 · 1吨/手",
        "market": "cn_fut", "sector": "新能源", "exchange": "广期所",
        "unit": "元/吨", "currency": "¥", "dp": 0, "multiplier": 1, "strike_step": 1000.0,
        "margin_rate": 0.12, "iv_skew": 0.13,
        "cost": {
            "cash_cost": 65000.0, "primary_cost": 78000.0, "comfort_high": 110000.0,
            "label": "江西锂云母与非洲矿/澳矿外采边际成本线", "source": "全球锂资源供给曲线75-90分位成本",
        },
        "moat_note": "70000-75000元已导致江西云母与部分澳矿停产检修，且期权IV长期高于35%，磨底区间卖虚值Put收租极丰厚。",
    },
]

ALL_INSTRUMENTS: List[Dict[str, Any]] = US_STOCKS + US_FUTURES + CN_FUTURES
BY_ID: Dict[str, Dict[str, Any]] = {item["id"]: item for item in ALL_INSTRUMENTS}
BY_SYMBOL: Dict[str, Dict[str, Any]] = {item["symbol"].upper(): item for item in ALL_INSTRUMENTS}


def get_universe(market: Optional[str] = None) -> List[Dict[str, Any]]:
    if market in ("us_stk", "us_fut", "cn_fut"):
        return [x for x in ALL_INSTRUMENTS if x["market"] == market]
    return list(ALL_INSTRUMENTS)


def get_instrument(inst_id_or_sym: str) -> Optional[Dict[str, Any]]:
    if not inst_id_or_sym:
        return None
    if inst_id_or_sym in BY_ID:
        return BY_ID[inst_id_or_sym]
    return BY_SYMBOL.get(inst_id_or_sym.upper())
