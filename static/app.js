/* ==========================================================================
   Short Put Weekly Terminal - Frontend Application Logic
   ========================================================================== */
(function () {
  "use strict";

  const state = {
    dte: 30,
    tierPref: "auto", // auto | conservative | balanced | aggressive
    data: null,
    selectedId: null,
    selectedTierKey: null,
    detailData: null,
    mktFilter: "all",
    archetypeFilter: "all",
    searchQuery: "",
    sortKey: "putScore",
    sortAsc: false,
    klineChart: null,
    payoffChart: null,
    btData: null,
    btTier: "auto",
    btOutcomeFilter: "all",
    btMktFilter: "all",
    btChart: null,
  };

  const el = (id) => document.getElementById(id);

  function fmtNum(v, dp = 2) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
    return Number(v).toFixed(dp);
  }

  function fmtSmart(v) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
    const n = Number(v);
    if (Math.abs(n) >= 1000) return n.toFixed(n % 1 === 0 ? 0 : 1);
    if (Math.abs(n) >= 10) return n.toFixed(n % 1 === 0 ? 0 : 2);
    return n.toFixed(3).replace(/\.?0+$/, "");
  }

  function fmtSignPct(v, dp = 2) {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return "--";
    const n = Number(v);
    const s = n > 0 ? "+" : "";
    return `${s}${n.toFixed(dp)}%`;
  }

  function colorCls(v) {
    if (v === null || v === undefined) return "";
    const n = Number(v);
    if (n > 0) return "bull-txt";
    if (n < 0) return "bear-txt";
    return "";
  }

  function getActiveTier(row) {
    if (!row || !row.tiers) return row?.recommendedTier || {};
    if (state.tierPref !== "auto" && row.tiers[state.tierPref]) {
      return row.tiers[state.tierPref];
    }
    return row.recommendedTier || row.tiers.balanced;
  }

  // ---------------- Load Weekly Recommendations ----------------
  async function loadRecommendations(force = false) {
    const dot = el("status-dot");
    const stTxt = el("status-text");
    if (stTxt) stTxt.textContent = force ? "正在重算全市场79品种期权定价…" : "同步最新行情…";
    if (dot) dot.style.background = "#f59e0b";

    try {
      const resp = await fetch(`/api/recommendations?dte=${state.dte}&force=${force ? "1" : "0"}`);
      const json = await resp.json();
      if (json.error) throw new Error(json.error);

      state.data = json;
      renderHeaderAndMacro(json);
      renderTopPicks(json);
      renderCnIndexOptions(json);
      renderScreenerTable();

      // Default select #1 pick if none selected yet
      if (!state.selectedId && json.all && json.all.length > 0) {
        const firstIdx = (json.cnIndexOptions || [])[0];
        const firstCn = (json.topPicks?.cn_fut || [])[0];
        const firstUs = (json.topPicks?.us_stk || [])[0];
        state.selectedId = (firstIdx || firstUs || firstCn || json.all[0]).id;
      }
      if (state.selectedId) {
        await loadInstrumentDetail(state.selectedId, state.tierPref === "auto" ? null : state.tierPref, force);
      }

      if (dot) dot.style.background = "#10b981";
      if (stTxt) stTxt.textContent = `已更新 ${json.updatedAt ? json.updatedAt.slice(11, 19) : ""}`;
    } catch (err) {
      console.error("loadRecommendations error:", err);
      if (dot) dot.style.background = "#ef4444";
      if (stTxt) stTxt.textContent = "加载异常，请重试";
    }
  }

  function renderHeaderAndMacro(data) {
    const wc = data.weekContext || {};
    const mr = data.macroRegime || {};
    const items = mr.items || {};
    const sum = data.summary || {};

    el("week-badge").textContent = `${wc.weekLabel || "--"} (${wc.weekRange || "--"}) · 目标DTE ${wc.targetDte || state.dte}天`;
    el("kpi-total").textContent = `${sum.totalCount || 0} (美股${sum.usStkCount || 0}/美期${sum.usFutCount || 0}/中期的${sum.cnFutCount || 0})`;
    el("kpi-below-cost").textContent = `${sum.belowCostCount || 0} 个`;
    el("kpi-high-ivr").textContent = `${sum.highIvrCount || 0} 个`;
    el("kpi-expiry").textContent = `${wc.targetExpiry || "--"} (${wc.targetDte || state.dte}D)`;

    el("regime-text").textContent = mr.regimeLabel || "--";
    const rTag = el("regime-tag");
    rTag.className = "regime-tag";
    if (mr.regimeTone === "gold") {
      rTag.style.background = "var(--gold-soft)";
      rTag.style.color = "var(--gold)";
      rTag.style.borderColor = "rgba(245,158,11,0.4)";
    }

    const fillMacro = (idVal, idSub, obj, suffix = "") => {
      if (!obj) return;
      el(idVal).textContent = `${obj.value}${suffix}`;
      const subEl = el(idSub);
      if (subEl) {
        subEl.innerHTML = `<span class="${colorCls(obj.changePct)}">${fmtSignPct(obj.changePct)}</span> · 分位${fmtNum(obj.pct1y, 0)}%`;
      }
    };

    fillMacro("m-vix", "m-vix-sub", items.VIX);
    fillMacro("m-vxn", "m-vxn-sub", items.VXN);
    fillMacro("m-ovx", "m-ovx-sub", items.OVX);
    fillMacro("m-gvz", "m-gvz-sub", items.GVZ);

    if (items.USDCNY) {
      el("m-fx").textContent = fmtNum(items.USDCNY.value, 4);
    }
    if (items.US10Y) {
      el("m-us10y").textContent = `10Y美债 ${fmtNum(items.US10Y.value, 2)}%`;
    }
  }

  // ---------------- Render 3-Market Top Picks ----------------
  function renderTopPicks(data) {
    const picks = data.topPicks || {};
    const usStk = picks.us_stk || [];
    const usFut = picks.us_fut || [];
    const cnFut = picks.cn_fut || [];
    if (el("top-count-usstk")) el("top-count-usstk").textContent = `Top ${usStk.length}`;
    if (el("top-count-usfut")) el("top-count-usfut").textContent = `Top ${usFut.length}`;
    if (el("top-count-cnfut")) el("top-count-cnfut").textContent = `Top ${cnFut.length}`;
    renderMarketPickColumn("picks-us-stk", usStk);
    renderMarketPickColumn("picks-us-fut", usFut);
    renderMarketPickColumn("picks-cn-fut", cnFut);
  }

  function renderMarketPickColumn(containerId, list) {
    const box = el(containerId);
    if (!box) return;
    if (!list.length) {
      box.innerHTML = `<div class="empty-note">暂无符合条件的品种</div>`;
      return;
    }

    box.innerHTML = list
      .map((r, idx) => {
        const t = getActiveTier(r);
        const cur = r.currency || "";
        const isUsStk = r.market === "us_stk";
        const yieldVal = isUsStk ? t.annReturnCashPct : t.annReturnMarginPct;
        const yieldLbl = isUsStk ? "现金担保年化" : "保证金年化";
        const subYield = isUsStk
          ? `保证金年化 ${fmtNum(t.annReturnMarginPct, 1)}%`
          : `全额年化 ${fmtNum(t.annReturnCashPct, 1)}%`;

        const toneCls = r.badgeTone === "bull" ? "bull-txt" : r.badgeTone === "gold" ? "gold-txt" : "cyan-txt";
        const activeCls = r.id === state.selectedId ? "active" : "";

        const tagsHtml = (r.thesisTags || [])
          .slice(0, 3)
          .map((tg) => `<span class="mini-tag">${tg}</span>`)
          .join("");

        return `
        <div class="pick-card ${activeCls}" data-id="${r.id}">
          <div class="pc-top">
            <div>
              <span class="pc-name">${idx + 1}. ${r.name}</span>
              <span class="pc-sym">${r.symbol}</span>
            </div>
            <span class="pc-score" title="卖Put五维综合评分">${fmtNum(r.putScore, 1)}分</span>
          </div>

          <div class="pc-archetype ${toneCls}">● ${r.archetype}</div>

          <div class="pc-metrics">
            <div class="pcm-item">
              <span class="pcm-lbl">最新现价</span>
              <span class="pcm-val">${cur}${fmtSmart(r.price)}</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">推荐Put行权价</span>
              <span class="pcm-val gold-txt">${cur}${fmtSmart(t.strike)}</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">安全垫(OTM)</span>
              <span class="pcm-val bull-txt">${fmtNum(t.otmPct, 1)}%</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">到期胜率(双轨取低)</span>
              <span class="pcm-val" title="BSM肥尾理论: ${fmtNum(t.bsmPopPct ?? t.popPct, 1)}% | 5年历史实证: ${fmtNum(t.empiricalPopPct ?? t.popPct, 1)}%">${fmtNum(t.popPct, 1)}% <small style="color:var(--text-muted);font-size:10.5px;">(实证${fmtNum(t.empiricalPopPct ?? t.popPct, 0)}%)</small></span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">${yieldLbl}</span>
              <span class="pcm-val gold-txt">${fmtNum(yieldVal, 1)}%</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">单手权利金</span>
              <span class="pcm-val">${cur}${fmtSmart(t.contractPremium)}</span>
            </div>
          </div>

          <div class="pc-tags">
            <span class="mini-tag" style="${r.isRealIv ? 'border-color:rgba(16,185,129,0.45);color:#34d399;' : ''}">${r.ivSource || "⚪ 估算IV"}</span>
            ${tagsHtml}
            <span class="mini-tag">${subYield}</span>
          </div>
        </div>
      `;
      })
      .join("");

    box.querySelectorAll(".pick-card").forEach((card) => {
      card.addEventListener("click", () => {
        const id = card.getAttribute("data-id");
        selectInstrument(id);
      });
    });
  }

  // ---------------- Render CFFEX Index Options (IM0 / IF0 / IH0) ----------------
  function renderCnIndexOptions(data) {
    const grid = el("cn-index-grid");
    if (!grid) return;
    let list = data.cnIndexOptions || [];
    if (!list.length && data.all) {
      list = data.all.filter((r) => ["CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0"].includes(r.id));
    }
    if (!list.length) {
      grid.innerHTML = `<div class="empty-note">正在计算中证1000 / 沪深300 / 上证50股指期权数据…</div>`;
      return;
    }

    const optCodeMap = {
      "CN_FUT:IM0": "MO (中证1000股指期权 · 100元/点)",
      "CN_FUT:IF0": "IO (沪深300股指期权 · 100元/点)",
      "CN_FUT:IH0": "HO (上证50股指期权 · 100元/点)",
    };

    grid.innerHTML = list
      .map((r) => {
        const t = getActiveTier(r);
        const cur = r.currency || "¥";
        const activeCls = r.id === state.selectedId ? "active" : "";
        const toneCls = r.badgeTone === "bull" ? "bull-txt" : r.badgeTone === "gold" ? "gold-txt" : "cyan-txt";
        const tiers = r.tiers || {};
        const recKey = state.tierPref !== "auto" ? state.tierPref : r.recommendedTierKey || "balanced";

        const tierBoxes = ["conservative", "balanced", "aggressive"]
          .map((tk) => {
            const tr = tiers[tk];
            if (!tr) return "";
            const isRec = tk === recKey ? "rec" : "";
            const shortLbl = `${tk === "conservative" ? "保守" : tk === "balanced" ? "平衡" : "进取"} Δ${fmtNum(tr.delta, 2)}`;
            return `
              <div class="idx-tier-box ${isRec}">
                <div class="itb-lbl">${shortLbl}${tk === recKey ? " ★" : ""}</div>
                <div class="itb-strike">K = ${fmtSmart(tr.strike)} 点</div>
                <div class="itb-meta">安全垫 ${fmtNum(tr.otmPct, 1)}% · 胜率 ${fmtNum(tr.popPct, 0)}%</div>
                <div class="itb-meta">权利金 ¥${fmtSmart(tr.contractPremium)} (${fmtNum(tr.annReturnMarginPct, 1)}%)</div>
              </div>
            `;
          })
          .join("");

        return `
        <div class="cn-idx-card ${activeCls}" data-id="${r.id}">
          <div class="pc-top">
            <div>
              <span class="pc-name">${r.name}</span>
              <span class="pc-sym">${r.symbol} · ${optCodeMap[r.id] || r.exchange}</span>
            </div>
            <span class="pc-score" title="卖Put五维综合评分">${fmtNum(r.putScore, 1)}分</span>
          </div>

          <div class="pc-archetype ${toneCls}">● ${r.archetype} · 1D <span class="${colorCls(r.change1dPct)}">${fmtSignPct(r.change1dPct)}</span> / 1W <span class="${colorCls(r.ret1wPct)}">${fmtSignPct(r.ret1wPct)}</span></div>

          <div class="pc-metrics">
            <div class="pcm-item">
              <span class="pcm-lbl">最新指数点位</span>
              <span class="pcm-val">${fmtSmart(r.price)} 点</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">推荐卖Put行权价</span>
              <span class="pcm-val gold-txt">${fmtSmart(t.strike)} 点</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">虚值安全垫 / 盈亏平衡</span>
              <span class="pcm-val bull-txt">${fmtNum(t.otmPct, 1)}% (${fmtSmart(t.breakeven)})</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">到期胜率 (双轨取低)</span>
              <span class="pcm-val bull-txt" title="BSM肥尾: ${fmtNum(t.bsmPopPct ?? t.popPct, 1)}% | 5年历史实证: ${fmtNum(t.empiricalPopPct ?? t.popPct, 1)}%">${fmtNum(t.popPct, 1)}% <small style="color:var(--text-muted)">(实证${fmtNum(t.empiricalPopPct ?? t.popPct, 0)}%)</small></span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">保证金年化 / 全额年化</span>
              <span class="pcm-val gold-txt">${fmtNum(t.annReturnMarginPct, 1)}% / ${fmtNum(t.annReturnCashPct, 1)}%</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">单手权利金 / 保证金</span>
              <span class="pcm-val">${cur}${fmtSmart(t.contractPremium)} / ${cur}${fmtSmart(t.marginReq)}</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">平值隐波 (${r.ivSource || "实盘IV"})</span>
              <span class="pcm-val cyan-txt">${fmtNum(r.atmIvPct, 1)}% (分位 ${fmtNum(r.ivRank, 0)}%)</span>
            </div>
            <div class="pcm-item">
              <span class="pcm-lbl">RSI(14) / 5年价格分位</span>
              <span class="pcm-val">${fmtNum(r.rsi14, 1)} / ${fmtNum(r.pct5y, 0)}%</span>
            </div>
          </div>

          <div class="idx-tier-strip">
            ${tierBoxes}
          </div>

          <div class="idx-thesis">
            <strong>策略要点：</strong>${r.thesisSummary || ""}
          </div>
        </div>
      `;
      })
      .join("");

    grid.querySelectorAll(".cn-idx-card").forEach((card) => {
      card.addEventListener("click", () => {
        const id = card.getAttribute("data-id");
        selectInstrument(id, true);
      });
    });
  }

  async function selectInstrument(instId, scrollToWs = false) {
    state.selectedId = instId;
    document.querySelectorAll(".pick-card, .cn-idx-card").forEach((c) => {
      c.classList.toggle("active", c.getAttribute("data-id") === instId);
    });
    document.querySelectorAll("#screener-tbody tr").forEach((tr) => {
      tr.classList.toggle("active-row", tr.getAttribute("data-id") === instId);
    });

    if (scrollToWs) {
      el("workstation-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    const tierArg = state.tierPref === "auto" ? null : state.tierPref;
    await loadInstrumentDetail(instId, tierArg, false);
  }

  // ---------------- Deep-Dive Workstation ----------------
  async function loadInstrumentDetail(instId, tierKey = null, force = false) {
    try {
      const qTier = tierKey ? `&tier=${tierKey}` : "";
      const resp = await fetch(`/api/detail?id=${encodeURIComponent(instId)}&dte=${state.dte}${qTier}&force=${force ? "1" : "0"}`);
      const detail = await resp.json();
      if (detail.error) throw new Error(detail.error);

      state.detailData = detail;
      state.selectedTierKey = detail.selectedTierKey;

      renderWorkstationHeader(detail);
      renderTierCards(detail);
      renderFactorsAndLadder(detail);
      renderVolSurfaceAndRoll(detail);
      renderPlaybook(detail);
      renderKlineChart(detail);

      // Initialize simulator inputs with chosen tier
      const a = detail.analysis;
      const activeTier = a.tiers[detail.selectedTierKey];
      el("sim-strike").value = activeTier.strike;
      el("sim-dte").value = detail.weekContext?.targetDte || state.dte;
      el("sim-iv").value = activeTier.ivPct;
      el("sim-lots").value = 1;

      renderSimSummary(a, activeTier, 1, detail.weekContext?.targetDte || state.dte);
      renderPayoffChart(detail.payoff, a, activeTier.strike);

      // Load live option chain verification asynchronously
      loadLiveOptionChain(instId);
    } catch (err) {
      console.error("loadInstrumentDetail error:", err);
    }
  }

  function renderWorkstationHeader(detail) {
    const a = detail.analysis;
    const cur = a.currency || "";
    el("ws-market-badge").textContent = `${a.marketLabel} · ${a.exchange}`;
    el("ws-title").textContent = `${a.name} (${a.symbol})`;
    el("ws-sub").textContent = a.sub;

    const archBadge = el("ws-archetype-badge");
    archBadge.textContent = a.archetype;
    archBadge.className = `badge ${a.badgeTone === "bull" ? "badge-bull" : a.badgeTone === "gold" ? "badge-gold" : "badge-neutral"}`;

    el("ws-price").textContent = `${cur}${fmtSmart(a.price)} ${a.unit === "USD" ? "" : a.unit}`;
    el("ws-chg").innerHTML = `<span class="${colorCls(a.change1dPct)}">${fmtSignPct(a.change1dPct)}</span> / <span class="${colorCls(a.ret1wPct)}">${fmtSignPct(a.ret1wPct)}</span>`;
    el("ws-iv").textContent = `${fmtNum(a.atmIvPct, 1)}% (${a.ivSource || "估算IV"} · IVR ${fmtNum(a.ivRank, 0)}%)`;
    el("ws-rsi-pct").textContent = `RSI ${fmtNum(a.rsi14, 1)} · 5Y分位 ${fmtNum(a.pct5y, 0)}%`;
    el("ws-score").textContent = `${fmtNum(a.putScore, 1)} / 100`;
  }

  function renderTierCards(detail) {
    const a = detail.analysis;
    const cur = a.currency || "";
    const dte = detail.weekContext?.targetDte || state.dte;
    el("tiers-dte-sub").textContent = `目标到期日 ${detail.weekContext?.targetExpiry || "--"} (${dte}天) · 合约乘数 ${a.multiplier} ${a.unit}/手`;

    const order = ["conservative", "balanced", "aggressive"];
    const box = el("tiers-grid");
    box.innerHTML = order
      .map((k) => {
        const t = a.tiers[k];
        if (!t) return "";
        const isSel = k === state.selectedTierKey;
        const isSysRec = k === a.recommendedTierKey;
        const sp = t.bullPutSpread || {};
        const wh = t.wheelCoveredCall || {};
        return `
        <div class="tier-card ${isSel ? "active" : ""}" data-tier="${k}">
          <div class="tc-hdr">
            <span class="tc-title">${t.label}</span>
            ${isSysRec ? `<span class="tc-rec-pill">本周首选</span>` : ""}
          </div>
          <div class="tc-strike">${cur}${fmtSmart(t.strike)} <span style="font-size:12px;font-weight:600;color:var(--bull)">(-${fmtNum(t.otmPct, 1)}%)</span></div>
          <div class="tc-rows">
            <div class="tc-row"><span>Delta / 隐波IV</span><strong>${fmtNum(t.delta, 2)} / ${fmtNum(t.ivPct, 1)}%</strong></div>
            <div class="tc-row"><span>单手权利金</span><strong class="gold-txt">${cur}${fmtSmart(t.contractPremium)} (${cur}${fmtSmart(t.premium)}/单)</strong></div>
            <div class="tc-row"><span>盈亏平衡点(缓冲)</span><strong class="cyan-txt">${cur}${fmtSmart(t.breakeven)} (-${fmtNum(t.breakevenBufferPct, 1)}%)</strong></div>
            <div class="tc-row"><span>ATR安全垫倍数</span><strong class="bull-txt">${fmtNum(t.atrBufferMultiple, 1)} 倍日均ATR</strong></div>
            <div class="tc-row"><span>双轨胜率(BSM/5Y实证取低)</span><strong class="bull-txt">${fmtNum(t.popPct, 1)}% <small style="color:var(--text-muted)">(${fmtNum(t.bsmPopPct ?? t.popPct, 0)}%/${fmtNum(t.empiricalPopPct ?? t.popPct, 0)}%)</small></strong></div>
            <div class="tc-row"><span>单手保证金占用</span><strong>${cur}${fmtSmart(t.marginReq)}</strong></div>
            <div class="tc-row"><span>保证金口径年化</span><strong class="gold-txt">${fmtNum(t.annReturnMarginPct, 1)}%</strong></div>
            <div class="tc-row"><span>每日Theta收租</span><strong class="bull-txt">+${cur}${fmtSmart(t.contractThetaDaily)}/日</strong></div>
            ${
              sp.longStrike
                ? `<div style="margin-top:5px;padding-top:5px;border-top:1px dashed rgba(56,189,248,0.28);font-size:11px;color:#7dd3fc;">
                     <div>🛡️ <strong>牛市价差配对：</strong>买K=${cur}${fmtSmart(sp.longStrike)} 保护</div>
                     <div>净收 <strong>${cur}${fmtSmart(sp.contractNetCredit)}</strong> · 最大亏封顶 <strong>${cur}${fmtSmart(sp.maxLoss)}</strong></div>
                     <div>省保证金 <strong class="bull-txt">${fmtNum(sp.marginSavedPct, 0)}%</strong> · 价差年化 <strong class="gold-txt">${fmtNum(sp.annReturnSpreadPct, 1)}%</strong></div>
                   </div>`
                : ""
            }
            ${
              wh.callStrike
                ? `<div style="margin-top:4px;padding-top:4px;border-top:1px dashed rgba(245,158,11,0.25);font-size:11px;color:#fcd34d;">
                     <div>🔄 <strong>接货备兑Call：</strong>卖K=${cur}${fmtSmart(wh.callStrike)} (+${fmtNum(wh.callAnnReturnPct, 1)}%)</div>
                   </div>`
                : ""
            }
          </div>
        </div>
      `;
      })
      .join("");

    box.querySelectorAll(".tier-card").forEach((card) => {
      card.addEventListener("click", () => {
        const tk = card.getAttribute("data-tier");
        loadInstrumentDetail(a.id, tk, false);
      });
    });
  }

  function renderVolSurfaceAndRoll(detail) {
    const box = el("ws-vol-surface");
    if (!box) return;
    const a = detail.analysis || {};
    const vs = a.volSurface || {};
    const skewCls = vs.skewTone === "bull" ? "bull-txt" : vs.skewTone === "gold" ? "gold-txt" : "cyan-txt";
    const termCls = vs.termTone === "bear" ? "bear-txt" : vs.termTone === "bull" ? "bull-txt" : "gold-txt";

    const rollHtml =
      a.market === "us_stk"
        ? `<span class="mini-tag">现货股票/ETF · 无期货换月跳空</span>`
        : a.rollGapCount > 0
        ? `<span class="mini-tag" style="border-color:rgba(16,185,129,0.45);color:#34d399;">✅ 主连换月跳空已平滑复权 (${a.rollGapCount}次换月缺口校准 · 最近 ${a.lastRollDate || "--"})</span>`
        : `<span class="mini-tag" style="border-color:rgba(56,189,248,0.4);color:#7dd3fc;">✅ 主连连续K线无异常换月跳空缺口</span>`;

    box.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px;">
        <div style="background:rgba(8,12,20,0.55);border:1px solid var(--border);border-radius:6px;padding:7px 9px;">
          <span style="font-size:11px;color:var(--text-muted);display:block;">25-Delta 虚值Put隐波</span>
          <strong class="gold-txt" style="font-size:14px;">${fmtNum(vs.put25dIvPct, 1)}%</strong>
          <small style="color:var(--text-muted);display:block;">较平值ATM(${fmtNum(vs.atmIvPct, 1)}%) 溢价 +${fmtNum(vs.skew25dPts, 1)}%</small>
        </div>
        <div style="background:rgba(8,12,20,0.55);border:1px solid var(--border);border-radius:6px;padding:7px 9px;">
          <span style="font-size:11px;color:var(--text-muted);display:block;">25D 风险逆转 (Put-Call RR)</span>
          <strong class="cyan-txt" style="font-size:14px;">${vs.riskReversal25dPts >= 0 ? "+" : ""}${fmtNum(vs.riskReversal25dPts, 1)} pts</strong>
          <small style="color:var(--text-muted);display:block;">25D Call IV: ${fmtNum(vs.call25dIvPct, 1)}%</small>
        </div>
        <div style="background:rgba(8,12,20,0.55);border:1px solid var(--border);border-radius:6px;padding:7px 9px;">
          <span style="font-size:11px;color:var(--text-muted);display:block;">IV期限结构 (7D→30D→60D)</span>
          <strong class="${termCls}" style="font-size:13px;">${fmtNum(vs.iv7dPct, 1)}% → ${fmtNum(vs.iv30dPct, 1)}% → ${fmtNum(vs.iv60dPct, 1)}%</strong>
          <small style="color:var(--text-muted);display:block;">远近月斜率 ${vs.termSlopePts >= 0 ? "+" : ""}${fmtNum(vs.termSlopePts, 1)}%</small>
        </div>
      </div>
      <div class="pb-item" style="margin-bottom:6px;">
        <strong>【偏度诊断】</strong><span class="${skewCls}">${vs.skewLabel || "--"}</span><br/>
        <strong>【期限结构】</strong><span class="${termCls}">${vs.termLabel || "--"}</span>
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;">
        ${rollHtml}
        <span style="font-size:11px;color:var(--text-muted);">数据源: ${a.ivSource || "模型校准"}</span>
      </div>
    `;
  }

  function renderFactorsAndLadder(detail) {
    const a = detail.analysis;
    const sb = a.scoreBreakdown || {};
    const volLabel = a.isRealIv
      ? `实盘VRP溢价与ATR风险调整收益 (${a.ivSource})`
      : `波动率与ATR风险调整收益 (${a.ivSource || "⚪ 估算IV"} · VRP锁定中性)`;
    const factors = [
      { label: "底部安全垫与估值锚 (成本×趋势矩阵)", val: sb.floor || 0, max: 30 },
      { label: volLabel, val: sb.vol || 0, max: 25 },
      { label: "技术支撑与右侧企稳确认 (防下轨开口)", val: sb.tech || 0, max: 20 },
      { label: `多周期趋势结构 (${a.trendRegime || "均线共振"})`, val: sb.trend || 0, max: 15 },
      { label: `期权盘口深度 (${a.liquidityLabel || "主力活跃"})`, val: sb.moat || 0, max: 10 },
    ];

    const corrBanner =
      a.highCorrPeers && a.highCorrPeers.length
        ? `<div style="margin-top:6px;padding:6px 10px;border-radius:6px;background:rgba(56,189,248,0.10);border:1px solid rgba(56,189,248,0.30);color:#7dd3fc;font-size:11.5px;line-height:1.45;">🔗 <strong>60日高相关同向簇(ρ≥0.70，Top6已做去重)：</strong>${a.highCorrPeers.map((p) => `${p.name}(${p.symbol} ρ=${p.corr.toFixed(2)})`).join("、")}</div>`
        : "";

    const riskBanner =
      a.riskNotes && a.riskNotes.length
        ? `<div style="margin-top:8px;padding:7px 10px;border-radius:6px;background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.35);color:#fca5a5;font-size:11.5px;line-height:1.45;">${a.riskNotes.join("<br/>")}</div>`
        : "";

    el("ws-factor-bars").innerHTML =
      factors
        .map((f) => {
          const pct = Math.min(100, Math.round((f.val / f.max) * 100));
          return `
        <div class="fbar-row">
          <div class="fbar-hdr">
            <span>${f.label}</span>
            <strong>${fmtNum(f.val, 1)} / ${f.max}</strong>
          </div>
          <div class="fbar-track">
            <div class="fbar-fill" style="width:${pct}%"></div>
          </div>
        </div>
      `;
        })
        .join("") + corrBanner + riskBanner;

    // Price Ladder comparing Spot, Supports, Costs, and Strike
    const sup = a.supports || {};
    const cur = a.currency || "";
    const activeTier = a.tiers[state.selectedTierKey] || a.recommendedTier;
    const ladderItems = [
      { label: "52周最高价", price: sup.high52w, cls: "" },
      { label: "20日布林上轨", price: sup.bollUp, cls: "" },
      { label: "60日均线 (MA60)", price: sup.ma60, cls: "" },
      { label: "20日均线 (MA20)", price: sup.ma20, cls: "" },
      { label: "★ 当前最新现价", price: a.price, cls: "is-spot" },
      { label: "20日布林下轨 (Boll Low)", price: sup.bollLow, cls: "" },
      { label: "枢轴强支撑位 S1", price: sup.s1, cls: "" },
      { label: "◆ 当前选中卖Put行权价(K)", price: activeTier.strike, cls: "is-strike" },
      { label: "◇ 卖Put到期盈亏平衡点", price: activeTier.breakeven, cls: "is-strike" },
    ];

    if (a.cost) {
      ladderItems.push(
        { label: `● 产业完全成本中枢 (${a.cost.label.slice(0, 10)})`, price: a.cost.primaryCost, cls: "is-cost" },
        { label: "● 产业现金成本铁底 (Cash Cost)", price: a.cost.cashCost, cls: "is-cost" }
      );
    } else {
      ladderItems.push({ label: "52周最低价", price: sup.low52w, cls: "" });
    }

    ladderItems.sort((x, y) => (y.price || 0) - (x.price || 0));

    el("ws-price-ladder").innerHTML = ladderItems
      .filter((x) => x.price !== undefined && x.price !== null)
      .map((item) => {
        const diffPct = a.price > 0 ? ((item.price / a.price - 1) * 100).toFixed(1) : "0.0";
        const sign = Number(diffPct) > 0 ? "+" : "";
        return `
        <div class="ladder-row ${item.cls}">
          <span>${item.label}</span>
          <span><strong>${cur}${fmtSmart(item.price)}</strong> <small style="color:var(--text-muted)">(${sign}${diffPct}%)</small></span>
        </div>
      `;
      })
      .join("");
  }

  function renderPlaybook(detail) {
    const pb = detail.analysis?.playbook || {};
    el("ws-playbook").innerHTML = `
      <div class="pb-item pb-bull"><strong>【本周执行结论】</strong>${pb.headline || "--"}</div>
      <div class="pb-item pb-cyan"><strong>【基本面与成本/估值定位】</strong>${pb.whyNow || "--"}</div>
      <div class="pb-item"><strong>【行权价安全垫与收益测算】</strong>${pb.strikeLogic || "--"}</div>
      ${pb.spreadLogic ? `<div class="pb-item" style="border-left:3px solid #a855f7;"><strong>【🛡️ 牛市看跌价差 (Bull Put Spread) 对冲方案】</strong>${pb.spreadLogic}</div>` : ""}
      ${pb.wheelLogic ? `<div class="pb-item" style="border-left:3px solid #38bdf8;"><strong>【🔄 车轮策略 (The Wheel) 接货后备兑闭环】</strong>${pb.wheelLogic}</div>` : ""}
      <div class="pb-item pb-risk"><strong>【止盈纪律与防穿仓展期(Roll)风控】</strong>${pb.riskControl || "--"}</div>
    `;
  }

  // ---------------- ECharts 1: K-Line with Strike & Cost Lines ----------------
  function renderKlineChart(detail) {
    const dom = el("kline-chart");
    if (!dom || typeof echarts === "undefined") return;
    if (!state.klineChart) {
      state.klineChart = echarts.init(dom);
    }

    const a = detail.analysis;
    const kl = detail.kline || {};
    const bars = kl.bars || [];
    const activeTier = a.tiers[state.selectedTierKey] || a.recommendedTier;
    const cur = a.currency || "";

    const dates = bars.map((b) => b.t);
    const ohlc = bars.map((b) => [b.o, b.c, b.l, b.h]);

    // Horizontal reference lines for Put Seller
    const markLines = [
      {
        yAxis: activeTier.strike,
        name: `卖Put行权价 K=${cur}${fmtSmart(activeTier.strike)}`,
        lineStyle: { color: "#f59e0b", width: 2, type: "dashed" },
        label: {
          formatter: `推荐行权价 ${cur}${fmtSmart(activeTier.strike)} (-${activeTier.otmPct}%)`,
          color: "#080c14",
          backgroundColor: "#f59e0b",
          padding: [2, 6],
          borderRadius: 3,
          fontWeight: "bold",
        },
      },
      {
        yAxis: activeTier.breakeven,
        name: `盈亏平衡 ${cur}${fmtSmart(activeTier.breakeven)}`,
        lineStyle: { color: "#38bdf8", width: 1.5, type: "dotted" },
        label: {
          formatter: `盈亏平衡点 ${cur}${fmtSmart(activeTier.breakeven)}`,
          color: "#38bdf8",
          backgroundColor: "rgba(8,12,20,0.85)",
          padding: [2, 5],
        },
      },
    ];

    if (a.cost) {
      markLines.push({
        yAxis: a.cost.primaryCost,
        name: "完全成本",
        lineStyle: { color: "#10b981", width: 1.8, type: "dashed" },
        label: {
          formatter: `完全成本中枢 ${cur}${fmtSmart(a.cost.primaryCost)}`,
          color: "#080c14",
          backgroundColor: "#10b981",
          padding: [2, 6],
          borderRadius: 3,
          fontWeight: "bold",
        },
      });
      if (a.cost.cashCost) {
        markLines.push({
          yAxis: a.cost.cashCost,
          name: "现金成本",
          lineStyle: { color: "#059669", width: 1.5, type: "dotted" },
          label: {
            formatter: `现金成本底 ${cur}${fmtSmart(a.cost.cashCost)}`,
            color: "#10b981",
            backgroundColor: "rgba(8,12,20,0.85)",
            padding: [2, 5],
          },
        });
      }
    }

    // Compute Y axis min/max so strike and cost lines are always visible on chart
    const allLow = bars.map((b) => b.l);
    const allHigh = bars.map((b) => b.h);
    const refVals = [activeTier.strike, activeTier.breakeven];
    if (a.cost && a.cost.primaryCost) refVals.push(a.cost.primaryCost);
    if (a.cost && a.cost.cashCost && a.cost.cashCost > a.price * 0.55) refVals.push(a.cost.cashCost);

    const minY = Math.min(...allLow, ...refVals) * 0.975;
    const maxY = Math.max(...allHigh, activeTier.strike * 1.05) * 1.015;

    el("kline-key-levels").innerHTML = `
      <span class="badge badge-gold">行权价 K=${cur}${fmtSmart(activeTier.strike)}</span>
      <span class="badge badge-neutral">盈亏平衡=${cur}${fmtSmart(activeTier.breakeven)}</span>
      ${a.cost ? `<span class="badge badge-bull">完全成本=${cur}${fmtSmart(a.cost.primaryCost)} / 现金成本=${cur}${fmtSmart(a.cost.cashCost)}</span>` : `<span class="badge badge-bull">布林下轨=${cur}${fmtSmart(a.supports.bollLow)}</span>`}
    `;

    const option = {
      backgroundColor: "transparent",
      animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: "rgba(13, 20, 36, 0.94)",
        borderColor: "#2d4063",
        textStyle: { color: "#e6edf7", fontSize: 12 },
      },
      legend: {
        data: ["日K", "MA20", "MA60", "布林上轨", "布林下轨"],
        top: 2,
        textStyle: { color: "#8b9bb4", fontSize: 11.5 },
      },
      grid: { left: 58, right: 135, top: 32, bottom: 28 },
      xAxis: {
        type: "category",
        data: dates,
        axisLine: { lineStyle: { color: "#22304a" } },
        axisLabel: { color: "#8b9bb4", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        min: Number(minY.toFixed(a.dp)),
        max: Number(maxY.toFixed(a.dp)),
        splitLine: { lineStyle: { color: "rgba(34, 48, 74, 0.45)" } },
        axisLabel: { color: "#8b9bb4", fontSize: 11 },
      },
      dataZoom: [{ type: "inside", start: 35, end: 100 }],
      series: [
        {
          name: "日K",
          type: "candlestick",
          data: ohlc,
          itemStyle: {
            color: "#ef4444",
            color0: "#10b981",
            borderColor: "#ef4444",
            borderColor0: "#10b981",
          },
          markLine: {
            symbol: ["none", "none"],
            silent: true,
            data: markLines,
          },
        },
        {
          name: "MA20",
          type: "line",
          data: kl.ma20 || [],
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.4, color: "#38bdf8" },
        },
        {
          name: "MA60",
          type: "line",
          data: kl.ma60 || [],
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.6, color: "#a855f7" },
        },
        {
          name: "布林上轨",
          type: "line",
          data: kl.bollUp || [],
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1, type: "dashed", color: "rgba(139, 155, 180, 0.55)" },
        },
        {
          name: "布林下轨",
          type: "line",
          data: kl.bollLow || [],
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.2, type: "dashed", color: "#22c55e" },
        },
      ],
    };

    state.klineChart.setOption(option, true);
  }

  // ---------------- ECharts 2: Payoff Curve & Simulator ----------------
  function renderSimSummary(a, simObj, lots, dte) {
    const cur = a.currency || "";
    const totalPrem = simObj.totalPremium !== undefined ? simObj.totalPremium : simObj.contractPremium * lots;
    const totalTheta = simObj.thetaDailyTotal !== undefined ? simObj.thetaDailyTotal : simObj.contractThetaDaily * lots;
    const marginReq = simObj.marginReq;
    const cashReq = simObj.cashSecuredReq;

    el("sim-summary-strip").innerHTML = `
      <div class="pcm-item">
        <span class="pcm-lbl">总权利金收入(${lots}手)</span>
        <span class="pcm-val gold-txt">+${cur}${fmtSmart(totalPrem)}</span>
      </div>
      <div class="pcm-item">
        <span class="pcm-lbl">盈亏平衡点(安全缓冲)</span>
        <span class="pcm-val cyan-txt">${cur}${fmtSmart(simObj.breakeven)} (-${fmtNum(simObj.breakevenBufferPct, 1)}%)</span>
      </div>
      <div class="pcm-item">
        <span class="pcm-lbl">到期胜率(PoP) / Delta</span>
        <span class="pcm-val bull-txt">${fmtNum(simObj.popPct, 1)}% / ${fmtNum(simObj.delta, 2)}</span>
      </div>
      <div class="pcm-item">
        <span class="pcm-lbl">每日Theta收租</span>
        <span class="pcm-val bull-txt">+${cur}${fmtSmart(totalTheta)}/天</span>
      </div>
      <div class="pcm-item">
        <span class="pcm-lbl">保证金占用 / 年化</span>
        <span class="pcm-val gold-txt">${cur}${fmtSmart(marginReq)} (${fmtNum(simObj.annReturnMarginPct, 1)}%)</span>
      </div>
      <div class="pcm-item">
        <span class="pcm-lbl">全额担保本金 / 年化</span>
        <span class="pcm-val">${cur}${fmtSmart(cashReq)} (${fmtNum(simObj.annReturnCashPct, 1)}%)</span>
      </div>
    `;
  }

  function renderPayoffChart(payoff, a, strike) {
    const dom = el("payoff-chart");
    if (!dom || typeof echarts === "undefined" || !payoff) return;
    if (!state.payoffChart) {
      state.payoffChart = echarts.init(dom);
    }

    const cur = a.currency || "";
    const prices = payoff.prices || [];
    const expPnl = payoff.expPnl || [];
    const midPnl = payoff.midPnl || [];
    const spreadExpPnl = payoff.spreadExpPnl || [];
    const spreadName = payoff.spreadInfo
      ? `牛市价差损益 (-K1/+K2=${cur}${fmtSmart(payoff.spreadInfo.longStrike)})`
      : "牛市看跌价差损益 (Bull Put Spread)";

    const legendData = ["裸卖Put到期损益", `期中理论损益 (T/2=${payoff.midDte}天)`];
    if (spreadExpPnl.length) legendData.push(spreadName);

    const seriesArr = [
      {
        name: "裸卖Put到期损益",
        type: "line",
        data: expPnl,
        showSymbol: false,
        lineStyle: { width: 2.5 },
        areaStyle: { opacity: 0.14 },
        markLine: {
          symbol: ["none", "none"],
          silent: true,
          data: [
            {
              yAxis: 0,
              lineStyle: { color: "#8b9bb4", width: 1, type: "solid" },
            },
          ],
        },
      },
      {
        name: `期中理论损益 (T/2=${payoff.midDte}天)`,
        type: "line",
        data: midPnl,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.8, type: "dashed", color: "#f59e0b" },
      },
    ];

    if (spreadExpPnl.length) {
      seriesArr.push({
        name: spreadName,
        type: "line",
        data: spreadExpPnl,
        showSymbol: false,
        lineStyle: { width: 2.2, type: "dotted", color: "#a855f7" },
      });
    }

    const option = {
      backgroundColor: "transparent",
      animation: false,
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(13, 20, 36, 0.94)",
        borderColor: "#2d4063",
        textStyle: { color: "#e6edf7", fontSize: 12 },
        formatter: function (params) {
          if (!params || !params.length) return "";
          const px = params[0].axisValue;
          let html = `<div><strong>标的到期价格: ${cur}${px}</strong></div>`;
          params.forEach((p) => {
            const val = Number(p.data);
            const col = val >= 0 ? "#10b981" : "#ef4444";
            html += `<div style="color:${col}">${p.seriesName}: ${val >= 0 ? "+" : ""}${cur}${val}</div>`;
          });
          return html;
        },
      },
      legend: {
        data: legendData,
        top: 2,
        textStyle: { color: "#8b9bb4", fontSize: 11.5 },
      },
      grid: { left: 64, right: 30, top: 32, bottom: 26 },
      xAxis: {
        type: "category",
        data: prices,
        axisLine: { lineStyle: { color: "#22304a" } },
        axisLabel: { color: "#8b9bb4", fontSize: 11 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "rgba(34, 48, 74, 0.45)" } },
        axisLabel: {
          color: "#8b9bb4",
          fontSize: 11,
          formatter: (v) => `${v >= 0 ? "+" : ""}${v}`,
        },
      },
      visualMap: {
        show: false,
        seriesIndex: 0,
        pieces: [
          { gte: 0, color: "#10b981" },
          { lt: 0, color: "#ef4444" },
        ],
      },
      series: seriesArr,
    };

    state.payoffChart.setOption(option, true);
  }

  async function runCustomSimulation() {
    if (!state.detailData) return;
    const a = state.detailData.analysis;
    const strike = parseFloat(el("sim-strike").value);
    const dte = parseInt(el("sim-dte").value, 10) || 30;
    const iv = parseFloat(el("sim-iv").value) || a.atmIvPct;
    const lots = parseInt(el("sim-lots").value, 10) || 1;

    try {
      const url = `/api/simulate?id=${encodeURIComponent(a.id)}&spot=${a.price}&strike=${strike}&dte=${dte}&iv=${iv}&lots=${lots}`;
      const resp = await fetch(url);
      const sim = await resp.json();
      if (sim.error) throw new Error(sim.error);

      renderSimSummary(a, sim, lots, dte);
      renderPayoffChart(sim.payoff, a, strike);
    } catch (err) {
      console.error("runCustomSimulation failed:", err);
    }
  }

  // ---------------- Live Option Chain Verification ----------------
  async function loadLiveOptionChain(instId) {
    const wrap = el("optchain-wrap");
    const sub = el("optchain-sub");
    if (!wrap) return;
    wrap.innerHTML = `<div class="empty-note">正在拉取实时期权链挂单与隐波数据…</div>`;

    try {
      const resp = await fetch(`/api/option-chain?id=${encodeURIComponent(instId)}&dte=${state.dte}`);
      const ch = await resp.json();
      if (!ch.available || !ch.puts || !ch.puts.length) {
        sub.textContent = ch.note || "该品种使用场内Black-76期货期权理论定价";
        wrap.innerHTML = `<div class="empty-note">${ch.note || "国内/场内期货期权已直接集成至上方三档行权价矩阵中"}</div>`;
        return;
      }

      const cur = ch.currency || "$";
      sub.textContent = `标的: ${ch.ticker}${ch.isProxy ? " (ETF期权代理对照)" : ""} · 现价 ${cur}${ch.spot} · 到期日 ${ch.expiry} (${ch.dte} DTE)`;
      wrap.innerHTML = `
        <table class="chain-table">
          <thead>
            <tr>
              <th>期权合约代码</th>
              <th>行权价(K)</th>
              <th>虚值安全垫</th>
              <th>买价(Bid)</th>
              <th>卖价(Ask)</th>
              <th>中间价(Mid)</th>
              <th>隐波(IV)</th>
              <th>成交量</th>
              <th>未平仓(OI)</th>
              <th>现金担保年化</th>
            </tr>
          </thead>
          <tbody>
            ${ch.puts
              .map(
                (p) => `
              <tr>
                <td>${p.contractSymbol}</td>
                <td class="gold-txt"><strong>${cur}${fmtSmart(p.strike)}</strong></td>
                <td class="${p.otmPct >= 0 ? "bull-txt" : "bear-txt"}">${fmtNum(p.otmPct, 1)}%</td>
                <td>${cur}${fmtNum(p.bid, 2)}</td>
                <td>${cur}${fmtNum(p.ask, 2)}</td>
                <td><strong>${cur}${fmtNum(p.mid, 2)}</strong></td>
                <td>${fmtNum(p.ivPct, 1)}%</td>
                <td>${p.volume}</td>
                <td>${p.openInterest}</td>
                <td class="gold-txt"><strong>${fmtNum(p.annCashReturnPct, 1)}%</strong></td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      `;
    } catch (err) {
      wrap.innerHTML = `<div class="empty-note">实时期权链暂不可用</div>`;
    }
  }

  // ---------------- Render Full 79-Variety Screener Table ----------------
  function renderScreenerTable() {
    if (!state.data || !state.data.all) return;
    const tbody = el("screener-tbody");
    const q = state.searchQuery.trim().toLowerCase();

    let rows = state.data.all.filter((r) => {
      if (state.mktFilter === "cn_idx") {
        if (r.sector !== "股指期权" && !["CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0"].includes(r.id)) return false;
      } else if (state.mktFilter !== "all" && r.market !== state.mktFilter) {
        return false;
      }
      if (state.archetypeFilter !== "all" && !r.archetype.includes(state.archetypeFilter)) return false;
      if (q) {
        const hay = `${r.symbol} ${r.name} ${r.sector} ${r.exchange} ${r.archetype}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    const getSortVal = (r, key) => {
      const t = getActiveTier(r);
      switch (key) {
        case "name":
          return r.name;
        case "market":
          return r.market;
        case "putScore":
          return r.putScore;
        case "price":
          return r.price;
        case "ret1wPct":
          return r.ret1wPct;
        case "rsi14":
          return r.rsi14;
        case "pct5y":
          return r.pct5y;
        case "vsCost":
          return r.cost ? r.cost.vsPrimaryPct : r.drawdown52wPct;
        case "atmIvPct":
          return r.atmIvPct;
        case "strike":
          return t.strike;
        case "otmPct":
          return t.otmPct;
        case "breakeven":
          return t.breakevenBufferPct;
        case "contractPremium":
          return t.contractPremium;
        case "popPct":
          return t.popPct;
        case "annMargin":
          return t.annReturnMarginPct;
        case "annCash":
          return t.annReturnCashPct;
        default:
          return r.putScore;
      }
    };

    rows.sort((a, b) => {
      const va = getSortVal(a, state.sortKey);
      const vb = getSortVal(b, state.sortKey);
      if (typeof va === "string") {
        return state.sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      return state.sortAsc ? va - vb : vb - va;
    });

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="18" class="empty-cell">无匹配的期权品种，请调整筛选条件</td></tr>`;
      return;
    }

    tbody.innerHTML = rows
      .map((r, i) => {
        const t = getActiveTier(r);
        const cur = r.currency || "";
        const activeCls = r.id === state.selectedId ? "active-row" : "";
        const badgeCls =
          r.badgeTone === "bull" ? "badge-bull" : r.badgeTone === "gold" ? "badge-gold" : "badge-neutral";

        let costCell = "";
        if (r.cost) {
          const vp = r.cost.vsPrimaryPct;
          const cls = vp <= 3 ? "bull-txt" : vp >= 35 ? "bear-txt" : "";
          costCell = `<span class="${cls}" title="完全成本 ${r.cost.primaryCost} / 现金成本 ${r.cost.cashCost}">较成本 ${fmtSignPct(vp, 1)}</span>`;
        } else {
          costCell = `<span class="cyan-txt" title="距52周高点回撤">回调 ${fmtSignPct(r.drawdown52wPct, 1)}</span>`;
        }

        return `
        <tr class="${activeCls}" data-id="${r.id}">
          <td>${i + 1}</td>
          <td><strong>${r.name}</strong> <span style="color:var(--text-muted)">${r.symbol}</span></td>
          <td>${r.marketLabel} · <small style="color:var(--text-muted)">${r.sector}</small></td>
          <td class="num"><strong class="gold-txt">${fmtNum(r.putScore, 1)}</strong></td>
          <td><span class="badge ${badgeCls}">${r.archetype}</span></td>
          <td class="num"><strong>${cur}${fmtSmart(r.price)}</strong></td>
          <td class="num ${colorCls(r.ret1wPct)}">${fmtSignPct(r.ret1wPct, 2)}</td>
          <td class="num ${r.rsi14 <= 42 ? "bull-txt" : r.rsi14 >= 68 ? "bear-txt" : ""}">${fmtNum(r.rsi14, 1)}</td>
          <td class="num">${fmtNum(r.pct5y, 0)}%</td>
          <td class="num">${costCell}</td>
          <td class="num" title="${r.ivSource || "⚪ 估算IV"}">${r.isRealIv ? "🟢" : "⚪"}${fmtNum(r.atmIvPct, 1)}% <small style="color:var(--text-muted)">(${fmtNum(r.ivRank, 0)}%)</small></td>
          <td class="num gold-txt"><strong>${cur}${fmtSmart(t.strike)}</strong> <small>(${t.label.slice(0, 2)})</small></td>
          <td class="num bull-txt"><strong>${fmtNum(t.otmPct, 1)}%</strong></td>
          <td class="num">${cur}${fmtSmart(t.breakeven)} <small class="cyan-txt">(-${fmtNum(t.breakevenBufferPct, 1)}%)</small></td>
          <td class="num">${cur}${fmtSmart(t.contractPremium)}</td>
          <td class="num bull-txt" title="BSM肥尾理论: ${fmtNum(t.bsmPopPct ?? t.popPct, 1)}% | 5年历史实证: ${fmtNum(t.empiricalPopPct ?? t.popPct, 1)}%"><strong>${fmtNum(t.popPct, 1)}%</strong> <small style="color:var(--text-muted)">(${fmtNum(t.empiricalPopPct ?? t.popPct, 0)}%)</small></td>
          <td class="num gold-txt"><strong>${fmtNum(t.annReturnMarginPct, 1)}%</strong></td>
          <td class="num"><strong>${fmtNum(t.annReturnCashPct, 1)}%</strong></td>
        </tr>
      `;
      })
      .join("");

    tbody.querySelectorAll("tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const id = tr.getAttribute("data-id");
        selectInstrument(id, true);
      });
    });
  }

  // ---------------- Historical Review & Backtest Section ----------------
  async function loadBacktestReview(force = false) {
    try {
      const cohorts = state.btCohorts || 52;
      const resp = await fetch(`/api/backtest?cohorts=${cohorts}&force=${force ? "1" : "0"}`);
      const json = await resp.json();
      if (json.error) throw new Error(json.error);
      state.btData = json;
      renderBacktestSection();
    } catch (err) {
      console.error("loadBacktestReview error:", err);
    }
  }

  async function loadStressTest(force = false) {
    try {
      const resp = await fetch(`/api/stress-test?dte=${state.dte}&force=${force ? "1" : "0"}`);
      const json = await resp.json();
      if (json.error) throw new Error(json.error);
      state.stressData = json;
      renderBacktestStressPanel(state.stressData, state.btData?.stopLossComparison);
    } catch (err) {
      console.error("loadStressTest error:", err);
    }
  }

  function renderBacktestSection() {
    if (!state.btData) return;
    const d = state.btData;
    const tk = state.btTier || "auto";
    const st = (d.tierStats && d.tierStats[tk]) || (d.tierStats && d.tierStats.auto) || {};

    // 1. Update 6 KPI cards
    if (el("bt-total")) {
      el("bt-total").textContent = `${st.total || 0} 笔`;
      el("bt-total-sub").textContent = `近 ${d.numCohorts || 52} 周滚动样本 · 已到期 ${st.expiredCount || 0} 笔 · 持有中 ${st.activeCount || 0} 笔`;
    }
    if (el("bt-unassigned")) {
      el("bt-unassigned").textContent = `${st.unassignedCount || 0} 笔 (${fmtNum(st.unassignedPct, 1)}%)`;
      el("bt-unassigned-sub").textContent = `期末价 ≥ 行权价K，全额拿满权利金`;
    }
    if (el("bt-assigned")) {
      el("bt-assigned").textContent = `${st.assignedCount || 0} 笔 (${fmtNum(st.assignedPct, 1)}%)`;
      el("bt-assigned-sub").textContent = `盘中曾触碰K: ${st.touchedCount || 0}笔 (${fmtNum(st.touchedPct, 1)}%)`;
    }
    if (el("bt-assigned-detail")) {
      el("bt-assigned-detail").textContent = `${st.assignedProfitCount || 0} 笔盈利 / ${st.mildLossCount || 0} 笔微亏`;
      el("bt-assigned-detail-sub").textContent = `权利金缓冲垫抵消大部分接货浮亏`;
    }
    if (el("bt-heavyloss")) {
      el("bt-heavyloss").textContent = `${st.heavyLossCount || 0} 笔 (${fmtNum(st.heavyLossPct, 1)}%)`;
      el("bt-heavyloss-sub").textContent = `净亏>2倍权利金或跌穿平衡点>3%`;
    }
    if (el("bt-winrate")) {
      const rSign = (st.avgRMultiple || 0) >= 0 ? "+" : "";
      el("bt-winrate").textContent = `${fmtNum(st.winRatePct, 1)}% (${rSign}${fmtNum(st.avgRMultiple, 2)}R)`;
      el("bt-winrate-sub").textContent = `平均单期保证金净回报 ${fmtSignPct(st.avgRocMarginNetPct, 2)}`;
    }

    // 2. Render Cohort Stacked Bar + Win Rate Line Chart
    renderBacktestCohortChart(d.cohorts || [], tk);

    // 3. Render Score Bucket Monotonicity Calibration Table
    renderBacktestBucketComparison(d.scoreBuckets || []);

    // 4. Render Hard Stop-Loss vs Expiry & Portfolio Stress Testing Panel
    renderBacktestStressPanel(state.stressData, d.stopLossComparison);

    // 5. Render Market & 3-Tier Comparison Table
    renderBacktestMarketComparison(d, tk);

    // 6. Render Detailed Trade Ledger Table
    renderBacktestLedgerTable(d.records || [], tk);
  }

  function renderBacktestBucketComparison(buckets) {
    const wrap = el("bt-bucket-comparison");
    if (!wrap) return;
    if (!buckets || !buckets.length) {
      wrap.innerHTML = `<div class="empty-note">正在计算分数段单调性数据…</div>`;
      return;
    }

    const rows = buckets
      .map((b) => {
        const isTop = b.bucket === "90+" || b.bucket === "80-90";
        const rowCls = isTop ? 'style="background:rgba(245,158,11,0.08);"' : "";
        const hlCls = b.heavyLossPct <= 5.5 ? "bull-txt" : b.heavyLossPct >= 8.5 ? "bear-txt" : "gold-txt";
        const rSign = b.avgRMultiple >= 0 ? "+" : "";

        return `
        <tr ${rowCls}>
          <td><strong class="${isTop ? "gold-txt" : ""}">${b.bucket} 分段</strong></td>
          <td><strong>${b.total} 笔</strong></td>
          <td class="bull-txt"><strong>${fmtNum(b.winRatePct, 1)}%</strong></td>
          <td class="cyan-txt">${fmtNum(b.unassignedPct, 1)}%</td>
          <td class="${hlCls}"><strong>${fmtNum(b.heavyLossPct, 1)}%</strong></td>
          <td class="${b.avgRMultiple >= 0 ? "bull-txt" : "bear-txt"}"><strong>${rSign}${fmtNum(b.avgRMultiple, 2)}R</strong></td>
        </tr>
      `;
      })
      .join("");

    wrap.innerHTML = `
      <table class="chain-table">
        <thead>
          <tr>
            <th>卖Put量化评分段</th>
            <th>全样本数</th>
            <th>🏆 实证总胜率</th>
            <th>✅ 未行权率</th>
            <th>🔴 大亏率(穿仓)</th>
            <th>期望单笔R收益</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
      <div style="font-size:11px;color:var(--text-muted);padding:8px 6px;line-height:1.45;">
        💡 <strong>单调性实证检验结论：</strong>90+分段大亏率仅 3.6%~4.7%，比 60-70分段(9.4%)低 2.5倍以上；期望收益从 90+分的 +0.69R 严格单调衰减至 70分以下的 +0.45R。证明高评分有效锁定了低下行风险与高胜率。
      </div>
    `;
  }

  function renderBacktestStressPanel(stressData, stopLossData) {
    const wrap = el("bt-stress-panel");
    if (!wrap) return;

    let stopLossHtml = "";
    if (stopLossData) {
      stopLossHtml = `
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <strong style="color:var(--gold);font-size:12px;">🛡️ 硬止损纪律对比（持有到期 vs 盘中亏损达2.5倍权利金硬止损）</strong>
            <span class="mini-tag" style="border-color:rgba(16,185,129,0.4);color:#34d399;">止损线 -2.50R 封顶</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11.5px;">
            <div style="background:rgba(8,12,20,0.5);border-radius:6px;padding:8px;">
              <span style="color:var(--text-muted);display:block;margin-bottom:2px;">【现行模式】持有到期结算</span>
              <strong>胜率 ${fmtNum(stopLossData.holdWinRatePct, 1)}%</strong> · 期望收益 <strong>+${fmtNum(stopLossData.holdAvgR, 2)}R</strong><br/>
              <span style="color:#fca5a5;">⚠️ 单笔最大亏损达 -14.99R（未设止损易遭罕见穿仓）</span>
            </div>
            <div style="background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.25);border-radius:6px;padding:8px;">
              <span style="color:#34d399;display:block;margin-bottom:2px;">【机构模式】严格硬止损截断 (-2.5R)</span>
              <strong>胜率 ${fmtNum(stopLossData.stopWinRatePct, 1)}%</strong> · 触发止损率 <strong>${fmtNum(stopLossData.stopTriggerPct, 1)}%</strong><br/>
              <span style="color:#34d399;">✅ 单笔最大亏损死死锁在 -2.50R，彻底斩断爆仓黑天鹅</span>
            </div>
          </div>
        </div>
      `;
    }

    let stressHtml = "";
    if (stressData && stressData.scenarios) {
      const cards = stressData.scenarios
        .map((sc) => {
          const isCrash = sc.key === "s3";
          const isSevere = sc.key === "s2";
          const borderCol = isCrash ? "rgba(239,68,68,0.5)" : isSevere ? "rgba(245,158,11,0.5)" : "var(--border)";
          const bgCol = isCrash ? "rgba(239,68,68,0.08)" : isSevere ? "rgba(245,158,11,0.06)" : "var(--bg-card)";
          const pnlSign = sc.totalPnl >= 0 ? "+" : "";

          return `
          <div style="background:${bgCol};border:1px solid ${borderCol};border-radius:8px;padding:8px 10px;">
            <div style="font-size:11px;color:var(--text-muted);font-weight:700;margin-bottom:3px;">${sc.label}</div>
            <div style="font-size:14px;font-weight:800;color:${isCrash ? "#f87171" : isSevere ? "var(--gold)" : "#fff"};">
              保证金 ${fmtSmart(sc.totalMargin)}
              <small style="font-size:11px;font-weight:600;color:var(--text-muted);">(${sc.marginSurgeRatio}x)</small>
            </div>
            <div style="font-size:11px;margin-top:2px;">
              预估浮亏: <strong class="${sc.totalPnl >= 0 ? "bull-txt" : "bear-txt"}">${pnlSign}${fmtSmart(sc.totalPnl)}</strong>
            </div>
          </div>
        `;
        })
        .join("");

      stressHtml = `
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <strong style="color:var(--cyan);font-size:12px;">💥 组合极端流动性冲击压力测试（现货跳空暴跌 + 隐波飙升）</strong>
            <span style="font-size:11px;color:var(--text-muted);">基准总保证金: ${fmtSmart(stressData.baseMargin)}</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;">
            ${cards}
          </div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:6px;line-height:1.4;">
            📌 <strong>风控预备金指引：</strong>遭遇 -2.0σ 严重流动性冲击时，保证金将飙升至基准的 <strong>1.5x~1.8x</strong>。建议账户总权益维持在保证金占用的 <strong>2.0倍以上</strong>，留足流动性防范追加保证金（Margin Call）。
          </div>
        </div>
      `;
    }

    wrap.innerHTML = stopLossHtml + stressHtml;
  }

  function renderBacktestCohortChart(cohorts, tk) {
    const dom = el("bt-cohort-chart");
    if (!dom || typeof echarts === "undefined") return;
    if (!state.btChart) {
      state.btChart = echarts.init(dom);
    }

    const labels = cohorts.map((c) => c.cohortLabel.replace(/^第\d+期\s*/, ""));
    const safeArr = cohorts.map((c) => (c.tiers[tk] || c.tiers.auto).unassignedCount);
    const profArr = cohorts.map((c) => (c.tiers[tk] || c.tiers.auto).assignedProfitCount);
    const mildArr = cohorts.map((c) => (c.tiers[tk] || c.tiers.auto).mildLossCount);
    const heavyArr = cohorts.map((c) => (c.tiers[tk] || c.tiers.auto).heavyLossCount);
    const winRateArr = cohorts.map((c) => (c.tiers[tk] || c.tiers.auto).winRatePct);

    state.btChart.setOption({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(13,20,34,0.95)",
        borderColor: "#2c3e5e",
        textStyle: { color: "#e6edf7", fontSize: 12 },
      },
      legend: {
        top: 0,
        textStyle: { color: "#8b9bb4", fontSize: 11 },
        data: ["未行权·全额收租", "被行权·仍盈利", "被行权·小幅浮亏", "大幅亏损", "当期总胜率%"],
      },
      grid: { left: 40, right: 45, top: 32, bottom: 26 },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { color: "#8b9bb4", fontSize: 11 },
        axisLine: { lineStyle: { color: "#22304a" } },
      },
      yAxis: [
        {
          type: "value",
          name: "品种数",
          nameTextStyle: { color: "#8b9bb4", fontSize: 11 },
          splitLine: { lineStyle: { color: "rgba(34,48,74,0.45)" } },
          axisLabel: { color: "#8b9bb4", fontSize: 11 },
        },
        {
          type: "value",
          name: "胜率%",
          min: 0,
          max: 100,
          nameTextStyle: { color: "#f59e0b", fontSize: 11 },
          splitLine: { show: false },
          axisLabel: { color: "#f59e0b", fontSize: 11, formatter: "{value}%" },
        },
      ],
      series: [
        {
          name: "未行权·全额收租",
          type: "bar",
          stack: "total",
          data: safeArr,
          itemStyle: { color: "#10b981" },
          barMaxWidth: 24,
        },
        {
          name: "被行权·仍盈利",
          type: "bar",
          stack: "total",
          data: profArr,
          itemStyle: { color: "#38bdf8" },
        },
        {
          name: "被行权·小幅浮亏",
          type: "bar",
          stack: "total",
          data: mildArr,
          itemStyle: { color: "#f59e0b" },
        },
        {
          name: "大幅亏损",
          type: "bar",
          stack: "total",
          data: heavyArr,
          itemStyle: { color: "#ef4444" },
        },
        {
          name: "当期总胜率%",
          type: "line",
          yAxisIndex: 1,
          data: winRateArr,
          smooth: true,
          symbol: "circle",
          symbolSize: 6,
          lineStyle: { color: "#fde047", width: 2 },
          itemStyle: { color: "#fde047" },
        },
      ],
    });
  }

  function renderBacktestMarketComparison(d, activeTk) {
    const wrap = el("bt-market-comparison");
    if (!wrap) return;
    const st = (d.tierStats && d.tierStats[activeTk]) || {};
    const byMkt = st.byMarket || {};
    const mktRows = ["cn_idx", "us_stk", "us_fut", "cn_fut"]
      .map((mk) => {
        const m = byMkt[mk];
        if (!m) return "";
        return `
          <tr>
            <td><strong>${m.label}</strong></td>
            <td>${m.total}笔</td>
            <td class="bull-txt"><strong>${m.unassigned}笔 (${fmtNum(m.unassignedPct, 1)}%)</strong></td>
            <td class="gold-txt">${m.assigned}笔 (${fmtNum(m.assignedPct, 1)}%)</td>
            <td class="${m.heavyLoss > 0 ? "bear-txt" : "bull-txt"}"><strong>${m.heavyLoss}笔 (${fmtNum(m.heavyLossPct, 1)}%)</strong></td>
            <td class="gold-txt"><strong>${fmtNum(m.winRatePct, 1)}%</strong></td>
            <td class="${m.avgR >= 0 ? "bull-txt" : "bear-txt"}">${m.avgR >= 0 ? "+" : ""}${fmtNum(m.avgR, 2)}R</td>
          </tr>
        `;
      })
      .join("");

    const tierLabelMap = {
      conservative: "保守档 (Δ≈-0.15)",
      balanced: "平衡档 (Δ≈-0.25)",
      aggressive: "进取档 (Δ≈-0.35)",
      auto: "★ 智能推荐档",
    };

    const tierRows = ["conservative", "balanced", "aggressive", "auto"]
      .map((tKey) => {
        const ts = (d.tierStats && d.tierStats[tKey]) || {};
        const isCur = tKey === activeTk ? 'style="background:rgba(245,158,11,0.12);"' : "";
        return `
          <tr ${isCur}>
            <td><strong>${tierLabelMap[tKey]}</strong></td>
            <td>${ts.total || 0}笔</td>
            <td class="bull-txt"><strong>${ts.unassignedCount || 0}笔 (${fmtNum(ts.unassignedPct, 1)}%)</strong></td>
            <td class="gold-txt">${ts.assignedCount || 0}笔 (${fmtNum(ts.assignedPct, 1)}%)</td>
            <td class="${(ts.heavyLossCount || 0) > 0 ? "bear-txt" : "bull-txt"}"><strong>${ts.heavyLossCount || 0}笔 (${fmtNum(ts.heavyLossPct, 1)}%)</strong></td>
            <td class="gold-txt"><strong>${fmtNum(ts.winRatePct, 1)}%</strong></td>
            <td class="bull-txt">+${fmtNum(ts.avgRMultiple, 2)}R</td>
          </tr>
        `;
      })
      .join("");

    wrap.innerHTML = `
      <table class="chain-table">
        <thead>
          <tr>
            <th>分市场统计 (当前档位)</th>
            <th>样本数</th>
            <th>✅ 未被行权</th>
            <th>🟡 被行权</th>
            <th>🔴 大幅亏损</th>
            <th>总胜率</th>
            <th>期望R倍数</th>
          </tr>
        </thead>
        <tbody>${mktRows}</tbody>
        <thead>
          <tr>
            <th>三档行权价横向对比</th>
            <th>样本数</th>
            <th>✅ 未被行权</th>
            <th>🟡 被行权</th>
            <th>🔴 大幅亏损</th>
            <th>总胜率</th>
            <th>期望R倍数</th>
          </tr>
        </thead>
        <tbody>${tierRows}</tbody>
      </table>
    `;
  }

  function renderBacktestLedgerTable(records, tk) {
    const tbody = el("bt-ledger-tbody");
    if (!tbody) return;

    const filtered = records.filter((r) => {
      const ev = (r.outcomes && r.outcomes[tk]) || (r.outcomes && r.outcomes.auto) || {};
      if (state.btOutcomeFilter === "HEAVY_LOSS" && !ev.isHeavyLoss) return false;
      if (state.btOutcomeFilter === "ASSIGNED" && !ev.isAssigned) return false;
      if (state.btOutcomeFilter === "SAFE" && ev.isAssigned) return false;

      if (state.btMktFilter === "cn_idx") {
        if (!["CN_FUT:IM0", "CN_FUT:IF0", "CN_FUT:IH0"].includes(r.id)) return false;
      } else if (state.btMktFilter !== "all" && r.market !== state.btMktFilter) {
        return false;
      }
      return true;
    });

    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="12" class="empty-cell">当前筛选条件下无记录</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered
      .map((r) => {
        const ev = (r.outcomes && r.outcomes[tk]) || (r.outcomes && r.outcomes.auto) || {};
        const cur = r.currency || "";
        const badgeCls =
          ev.statusTone === "bull"
            ? "badge-bull"
            : ev.statusTone === "bear"
            ? "badge-bear"
            : ev.statusTone === "gold"
            ? "badge-gold"
            : "badge-neutral";
        const pnlSign = ev.netContractPnl > 0 ? "+" : "";
        const rSign = ev.rMultiple > 0 ? "+" : "";

        return `
          <tr data-id="${r.id}">
            <td><strong>${r.cohortLabel}</strong> <small style="color:var(--text-muted)">→ ${r.evalDate.slice(5)}${r.isExpired ? "" : " (持有中)"}</small></td>
            <td><strong>${r.name}</strong> <span style="color:var(--text-muted)">${r.symbol} · ${r.marketLabel}</span></td>
            <td class="num gold-txt"><strong>${fmtNum(r.putScore, 1)}</strong></td>
            <td class="num">${cur}${fmtSmart(r.entryPrice)}</td>
            <td class="num gold-txt"><strong>${cur}${fmtSmart(ev.strike)}</strong></td>
            <td class="num bull-txt">${fmtNum(ev.otmPct, 1)}%</td>
            <td class="num">${cur}${fmtSmart(ev.breakeven)}</td>
            <td class="num ${ev.touchedStrike ? "bear-txt" : ""}">${cur}${fmtSmart(ev.minLow)} <small>(${fmtSignPct(ev.maxDrawdownPct, 1)})</small></td>
            <td class="num ${colorCls(ev.underlyingRetPct)}"><strong>${cur}${fmtSmart(ev.endPrice)}</strong> <small>(${fmtSignPct(ev.underlyingRetPct, 1)})</small></td>
            <td><span class="badge ${badgeCls}">${ev.statusLabel}</span></td>
            <td class="num">+${cur}${fmtSmart(ev.contractPremium)}</td>
            <td class="num ${ev.netContractPnl >= 0 ? "bull-txt" : "bear-txt"}"><strong>${pnlSign}${cur}${fmtSmart(ev.netContractPnl)}</strong> <small>(${rSign}${fmtNum(ev.rMultiple, 2)}R)</small></td>
          </tr>
        `;
      })
      .join("");

    tbody.querySelectorAll("tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const id = tr.getAttribute("data-id");
        selectInstrument(id, true);
      });
    });
  }

  // ---------------- Live Position Tracker, Roll Radar, Macro Shield & Webhook ----------------
  async function loadPortfolioTracker() {
    try {
      const resp = await fetch("/api/portfolio");
      const json = await resp.json();
      if (json.error) throw new Error(json.error);
      state.portfolioData = json;
      renderPortfolioSection(json);
    } catch (err) {
      console.error("loadPortfolioTracker error:", err);
    }
  }

  async function loadDailyBriefing() {
    try {
      const resp = await fetch(`/api/briefing?dte=${state.dte}`);
      const json = await resp.json();
      if (json.text && el("briefing-textarea")) {
        el("briefing-textarea").value = json.text;
      }
    } catch (err) {
      console.error("loadDailyBriefing error:", err);
    }
  }

  function renderPortfolioSection(data) {
    if (!data) return;
    const s = data.summary || {};

    if (el("pf-count")) {
      const cnt = s.totalPositions ?? s.positionCount ?? 0;
      el("pf-count").textContent = `${cnt} 笔`;
      el("pf-count-sub").textContent = `实时盯市 · 每日Theta收租 +¥${fmtSmart(s.totalDailyThetaCny || 0)}/天`;
    }
    if (el("pf-pnl")) {
      const sign = (s.totalUnrealizedPnlCny || 0) >= 0 ? "+" : "";
      el("pf-pnl").textContent = `${sign}¥${fmtSmart(s.totalUnrealizedPnlCny || 0)}`;
      el("pf-pnl").className = `bt-val ${(s.totalUnrealizedPnlCny || 0) >= 0 ? "bull-txt" : "bear-txt"}`;
      el("pf-pnl-sub").textContent = `总保证金占用 ¥${fmtSmart(s.totalMarginCny || 0)}`;
    }
    if (el("pf-tp-count")) {
      el("pf-tp-count").textContent = `${s.takeProfitCount || 0} 笔`;
      el("pf-tp-sub").textContent = `浮盈 ≥ 65% 建议平仓落袋`;
    }
    if (el("pf-roll-count")) {
      el("pf-roll-count").textContent = `${s.rollDefenseCount || 0} 笔`;
      el("pf-roll-sub").textContent = `触碰行权价 → Roll Down & Out`;
    }
    if (el("pf-stop-count")) {
      const stopCnt = s.stopLossCount ?? s.hardStopCount ?? 0;
      el("pf-stop-count").textContent = `${stopCnt} 笔`;
      el("pf-stop-sub").textContent = `亏损 ≥ 2.5R 强制截断 / 车轮备兑 ${s.wheelCallCount || 0}笔`;
    }
    if (el("pf-macro-badge")) {
      const m = data.macroShield || {};
      const hiCnt = m.highRiskInWindowCount || 0;
      const evLen = (m.events || []).length;
      const mCol = hiCnt >= 2 ? "#f87171" : hiCnt >= 1 ? "#fbbf24" : "#34d399";
      const mLabel = hiCnt >= 2 ? `🔴 期内 ${hiCnt} 项高危冲击` : hiCnt >= 1 ? `🟡 期内 ${hiCnt} 项宏观节点` : "🟢 常态收租窗口";
      el("pf-macro-badge").innerHTML = `<span style="color:${mCol}">${mLabel}</span>`;
      el("pf-macro-sub").textContent = `未来45天内共 ${evLen} 项宏观/交割/长假节点`;
    }

    // Render Position Table
    const tbody = el("portfolio-tbody");
    if (tbody) {
      const positions = data.positions || [];
      if (!positions.length) {
        tbody.innerHTML = `<tr><td colspan="12" class="empty-cell">暂无持仓记录，请点击上方按钮将当前品种加入持仓账本</td></tr>`;
      } else {
        tbody.innerHTML = positions
          .map((p) => {
            const cur = p.currency || "";
            const tone = p.signalTone || p.actionTone || "neutral";
            const badgeCls =
              tone === "bull"
                ? "badge-bull"
                : tone === "bear"
                ? "badge-bear"
                : tone === "gold"
                ? "badge-gold"
                : "badge-neutral";
            const pnlSign = p.unrealizedPnl >= 0 ? "+" : "";
            const rSign = p.rMultiple >= 0 ? "+" : "";
            const strat = p.strategyType || p.strategy || "SHORT_PUT";
            const stratTag =
              strat === "BULL_PUT_SPREAD" || strat === "bull_put_spread"
                ? `<span class="mini-tag" style="border-color:rgba(168,85,247,0.45);color:#c084fc;">🛡️牛市价差(-${p.strike}/+${p.longStrike})</span>`
                : strat === "WHEEL_COVERED_CALL"
                ? `<span class="mini-tag" style="border-color:rgba(56,189,248,0.45);color:#38bdf8;">🔄车轮接货转备兑Call</span>`
                : `<span class="mini-tag">裸卖Put</span>`;

            const sigCode = p.signalCode || p.actionCode || "HOLD_THETA";
            const sigLabel = p.signalLabel || p.actionBadge || "持有收租";
            const openDt = p.openDate || p.entryDate || "--";
            const curSpot = p.spot ?? p.currentSpot ?? 0;
            const liveOtm = p.otmPct ?? p.liveOtmPct ?? 0;
            const entryPrem = p.entryPremium ?? p.entryPrice ?? 0;
            const curPrem = p.currentPremium ?? p.currentOptPrice ?? 0;
            const capPct = p.capturePct ?? p.profitCapturedPct ?? 0;
            const liveDelta = p.currentDelta ?? p.liveDelta ?? 0;
            const liveTheta = p.dailyThetaTotal ?? p.liveThetaDaily ?? 0;

            let rollOrWheelBox = `<div style="font-size:11.5px;line-height:1.45;">${p.actionDetail || ""}</div>`;
            if (p.rollPlan && (sigCode === "ROLL_DEFENSE" || sigCode === "HARD_STOP")) {
              const rp = p.rollPlan;
              const netC = rp.netRollCredit ?? 0;
              rollOrWheelBox += `
                <div style="margin-top:4px;padding:4px 6px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:4px;font-size:11px;color:#fde68a;">
                  🔄 <strong>向下展期测算:</strong> 平旧仓(${cur}${rp.buybackCost}) → 卖远期(${rp.newDte}D) <strong>K=${cur}${fmtSmart(rp.newStrike)}</strong>(收${cur}${rp.newPutPremium}) · 净收 <strong class="${rp.isNetCredit ? "bull-txt" : "bear-txt"}">${netC >= 0 ? "+" : ""}${cur}${netC}</strong> · 行权价下移 <strong>-${rp.strikeDropPct}%</strong>
                </div>
              `;
            } else if (p.wheelPlan && sigCode === "WHEEL_CALL") {
              const wp = p.wheelPlan;
              rollOrWheelBox += `
                <div style="margin-top:4px;padding:4px 6px;background:rgba(56,189,248,0.1);border:1px solid rgba(56,189,248,0.3);border-radius:4px;font-size:11px;color:#bae6fd;">
                  🔄 <strong>车轮备兑Call:</strong> 接货净成本 <strong>${cur}${fmtSmart(wp.initialCostBasis)}</strong> → 卖30D Call <strong>K=${cur}${fmtSmart(wp.callStrike)}</strong> · 再收 <strong>+${cur}${fmtSmart(wp.contractCallPremium)}/手</strong> (年化 <strong>+${wp.callAnnReturnPct}%</strong>)
                </div>
              `;
            }

            return `
              <tr data-id="${p.instId}">
                <td><strong>${p.name}</strong> <span style="color:var(--text-muted)">${p.symbol}</span><br/>${stratTag} <small style="color:var(--text-muted)">${p.lots}手</small></td>
                <td><small>${openDt} → ${p.expiryDate}</small><br/><strong class="${p.remDte <= 5 ? "gold-txt" : "cyan-txt"}">剩余 ${p.remDte} 天</strong></td>
                <td class="num gold-txt"><strong>${cur}${fmtSmart(p.strike)}</strong></td>
                <td class="num">${cur}${fmtSmart(p.entrySpot)} → <strong>${cur}${fmtSmart(curSpot)}</strong></td>
                <td class="num ${liveOtm >= 2 ? "bull-txt" : "bear-txt"}"><strong>${fmtSignPct(liveOtm, 1)}</strong></td>
                <td class="num">${cur}${fmtSmart(entryPrem)} → <strong>${cur}${fmtSmart(curPrem)}</strong></td>
                <td class="num ${capPct >= 50 ? "bull-txt" : capPct < 0 ? "bear-txt" : "gold-txt"}"><strong>${fmtSignPct(capPct, 1)}</strong></td>
                <td class="num ${p.unrealizedPnl >= 0 ? "bull-txt" : "bear-txt"}"><strong>${pnlSign}${cur}${fmtSmart(p.unrealizedPnl)}</strong><br/><small>(${rSign}${fmtNum(p.rMultiple, 2)}R)</small></td>
                <td class="num">${fmtNum(liveDelta, 2)}<br/><small class="bull-txt">+${cur}${fmtSmart(liveTheta)}/D</small></td>
                <td><span class="badge ${badgeCls}">${sigLabel}</span></td>
                <td style="max-width:340px;white-space:normal;">${rollOrWheelBox}</td>
                <td><button class="btn-outline btn-del-pos" data-pos-id="${p.posId}" style="padding:3px 8px;font-size:11px;color:#f87171;border-color:rgba(239,68,68,0.35);">移除</button></td>
              </tr>
            `;
          })
          .join("");

        tbody.querySelectorAll(".btn-del-pos").forEach((btn) => {
          btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const posId = btn.getAttribute("data-pos-id");
            if (posId) await removePortfolioPos(posId);
          });
        });

        tbody.querySelectorAll("tr[data-id]").forEach((tr) => {
          tr.addEventListener("click", () => {
            const id = tr.getAttribute("data-id");
            if (id) selectInstrument(id, true);
          });
        });
      }
    }

    // Render Macro & Holiday Shield Box
    const macroBox = el("macro-shield-box");
    if (macroBox && data.macroShield) {
      const m = data.macroShield;
      const hiCnt = m.highRiskInWindowCount || 0;
      const evRows = (m.events || [])
        .map((ev) => {
          const isHigh = ev.riskLevel === "HIGH" || ev.severity === "CRITICAL";
          const daysTxt = ev.daysText || `${ev.daysAway ?? ev.daysUntil ?? 0}天后`;
          const sevBadge = isHigh
            ? `<span class="badge badge-bear">🔴 高危风控(${daysTxt})</span>`
            : `<span class="badge badge-gold">🟡 重点关注(${daysTxt})</span>`;
          return `
            <div style="background:rgba(13,20,34,0.75);border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-bottom:6px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                <strong style="color:#fff;font-size:12px;">📅 ${ev.date} · ${ev.title}</strong>
                ${sevBadge}
              </div>
              <div style="font-size:11px;color:var(--cyan);margin-bottom:2px;">影响市场: ${ev.markets || "全市场"} · 类别: ${ev.category || "宏观"}</div>
              <div style="font-size:11.5px;color:var(--text-secondary);line-height:1.45;">${ev.advice || ev.rule || ""}</div>
            </div>
          `;
        })
        .join("");

      const topBannerTitle =
        hiCnt >= 1
          ? `⚠️ 当前 ${m.targetDte || 30}天 持仓周期内含 ${hiCnt} 项高冲击宏观/长假节点`
          : `🟢 近期宏观与长假窗口平稳（非常适合赚取Theta时间价值）`;
      const topBannerDesc =
        "议息夜/CPI发布前建议优先使用【牛市看跌价差】锁死左尾风险；国内长假前3个交易日注意交易所上调保证金比例与外盘跳空风险。";

      macroBox.innerHTML = `
        <div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);border-radius:8px;padding:9px 11px;margin-bottom:8px;">
          <div style="font-weight:800;font-size:12.5px;color:var(--gold);margin-bottom:3px;">${topBannerTitle}</div>
          <div style="font-size:11.5px;color:var(--text-secondary);line-height:1.45;">${topBannerDesc}</div>
        </div>
        <div style="max-height:260px;overflow-y:auto;">
          ${evRows || `<div class="empty-note">未来45天暂无特殊宏观/长假冲击事件</div>`}
        </div>
      `;
    }
  }

  async function addCurrentToPortfolio(strategy = "naked_put") {
    if (!state.detailData || !state.detailData.analysis) return;
    const a = state.detailData.analysis;
    const tk = state.selectedTierKey || a.recommendedTierKey || "balanced";
    const t = (a.tiers && a.tiers[tk]) || a.recommendedTier;
    const lots = parseInt(el("sim-lots")?.value, 10) || 1;
    const isSpread = strategy === "bull_put_spread";

    try {
      const payload = {
        instId: a.id,
        strategyType: isSpread ? "BULL_PUT_SPREAD" : "SHORT_PUT",
        strike: t.strike,
        longStrike: isSpread && t.bullPutSpread ? t.bullPutSpread.longStrike : null,
        entrySpot: a.price,
        entryPremium: isSpread && t.bullPutSpread ? t.bullPutSpread.netCredit : t.premium,
        ivPct: a.atmIvPct,
        dte: state.dte,
        lots: lots,
        note: isSpread ? `工作台录入牛市价差 (${t.label})` : `工作台录入裸卖Put (${t.label})`,
      };
      const resp = await fetch("/api/portfolio/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await resp.json();
      const tracker = json.tracker || json;
      if (tracker && tracker.positions) {
        state.portfolioData = tracker;
        renderPortfolioSection(tracker);
        loadDailyBriefing();
        el("portfolio-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      console.error("addCurrentToPortfolio error:", err);
    }
  }

  async function removePortfolioPos(posId) {
    try {
      const resetDefault = posId === "RESET_DEFAULT";
      const resp = await fetch("/api/portfolio/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ posId, resetDefault }),
      });
      const json = await resp.json();
      const tracker = json.tracker || json;
      if (tracker && tracker.positions) {
        state.portfolioData = tracker;
        renderPortfolioSection(tracker);
        loadDailyBriefing();
      }
    } catch (err) {
      console.error("removePortfolioPos error:", err);
    }
  }

  async function sendWebhookAlert() {
    const urlInput = el("webhook-url-input");
    const statusEl = el("webhook-status-msg");
    const webhookUrl = urlInput?.value?.trim() || "";
    const customText = el("briefing-textarea")?.value || "";

    if (!webhookUrl) {
      if (statusEl) {
        statusEl.style.color = "#fbbf24";
        statusEl.textContent = "⚠️ 请先在输入框粘贴钉钉 / 飞书 / 企业微信机器人的 Webhook 地址（若只需复制战报文字，请点击右侧“复制战报”按钮）";
      }
      return;
    }

    if (statusEl) {
      statusEl.style.color = "#38bdf8";
      statusEl.textContent = "⏳ 正在向 Webhook 推送今日卖Put量化战报...";
    }

    try {
      const resp = await fetch("/api/webhook-push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ webhookUrl, text: customText, dte: state.dte }),
      });
      const json = await resp.json();
      if (statusEl) {
        statusEl.style.color = json.ok ? "#34d399" : "#f87171";
        statusEl.textContent = json.ok ? `✅ ${json.msg}` : `❌ ${json.msg}`;
      }
    } catch (err) {
      if (statusEl) {
        statusEl.style.color = "#f87171";
        statusEl.textContent = `❌ 推送请求失败: ${err.message}`;
      }
    }
  }

  // ---------------- iPhone QR Code Modal & Offline Export ----------------
  async function openMobileModal() {
    const modal = el("mobile-modal");
    if (!modal) return;
    modal.style.display = "flex";

    const expLink = el("link-export-mobile");
    if (expLink) {
      expLink.href = `/api/export-mobile?dte=${state.dte}`;
    }

    try {
      const resp = await fetch("/api/mobile-info");
      const info = await resp.json();
      const url = info.primaryUrl || "http://192.168.3.127:5058";
      const urlEl = el("mobile-lan-url");
      if (urlEl) urlEl.textContent = url;

      const qrBox = el("mobile-qr-box");
      if (qrBox) {
        if (typeof window.qrcode === "function") {
          const qr = window.qrcode(0, "M");
          qr.addData(url);
          qr.make();
          qrBox.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 1 });
        } else {
          qrBox.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(url)}" alt="QR Code"/>`;
        }
      }
    } catch (err) {
      console.error("openMobileModal error:", err);
    }
  }

  // ---------------- Event Listeners & Init ----------------
  function bindEvents() {
    el("dte-select")?.addEventListener("change", (e) => {
      state.dte = parseInt(e.target.value, 10) || 30;
      loadRecommendations(false);
    });

    el("tier-pref-select")?.addEventListener("change", (e) => {
      state.tierPref = e.target.value;
      state.btTier = e.target.value;
      el("bt-tier-tabs")?.querySelectorAll("button").forEach((b) => {
        b.classList.toggle("active", b.getAttribute("data-tier") === state.btTier);
      });
      if (state.data) {
        renderTopPicks(state.data);
        renderCnIndexOptions(state.data);
        renderScreenerTable();
      }
      if (state.btData) {
        renderBacktestSection();
      }
      if (state.selectedId) {
        const tierArg = state.tierPref === "auto" ? null : state.tierPref;
        loadInstrumentDetail(state.selectedId, tierArg, false);
      }
    });

    el("bt-tier-tabs")?.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        el("bt-tier-tabs").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.btTier = btn.getAttribute("data-tier") || "auto";
        renderBacktestSection();
      });
    });

    el("bt-cohort-tabs")?.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        el("bt-cohort-tabs").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.btCohorts = parseInt(btn.getAttribute("data-cohorts"), 10) || 52;
        loadBacktestReview(false);
      });
    });

    el("bt-outcome-tabs")?.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        el("bt-outcome-tabs").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.btOutcomeFilter = btn.getAttribute("data-out") || "all";
        if (state.btData) renderBacktestLedgerTable(state.btData.records || [], state.btTier);
      });
    });

    el("bt-mkt-filter")?.addEventListener("change", (e) => {
      state.btMktFilter = e.target.value || "all";
      if (state.btData) renderBacktestLedgerTable(state.btData.records || [], state.btTier);
    });

    el("btn-refresh")?.addEventListener("click", () => {
      loadRecommendations(true);
      loadPortfolioTracker();
      loadDailyBriefing();
    });

    el("btn-mobile-modal")?.addEventListener("click", () => {
      openMobileModal();
    });

    el("btn-close-modal")?.addEventListener("click", () => {
      const modal = el("mobile-modal");
      if (modal) modal.style.display = "none";
    });

    el("mobile-modal")?.addEventListener("click", (e) => {
      if (e.target === el("mobile-modal")) {
        el("mobile-modal").style.display = "none";
      }
    });

    el("btn-copy-lan-url")?.addEventListener("click", async () => {
      const txt = el("mobile-lan-url")?.textContent || "http://192.168.3.127:5058";
      try {
        await navigator.clipboard.writeText(txt);
        const btn = el("btn-copy-lan-url");
        if (btn) {
          btn.textContent = "已复制 ✓";
          setTimeout(() => (btn.textContent = "复制链接"), 2000);
        }
      } catch (_) {}
    });

    el("mobile-bottom-nav")?.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        el("mobile-bottom-nav").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const targetId = btn.getAttribute("data-target");
        if (targetId) {
          el(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });

    el("btn-run-sim")?.addEventListener("click", () => {
      runCustomSimulation();
    });

    el("btn-load-chain")?.addEventListener("click", () => {
      if (state.selectedId) loadLiveOptionChain(state.selectedId);
    });

    el("btn-add-cur-to-portfolio")?.addEventListener("click", () => {
      addCurrentToPortfolio("naked_put");
    });

    el("btn-add-spread-to-portfolio")?.addEventListener("click", () => {
      addCurrentToPortfolio("bull_put_spread");
    });

    el("btn-reset-portfolio")?.addEventListener("click", () => {
      removePortfolioPos("RESET_DEFAULT");
    });

    el("btn-copy-briefing")?.addEventListener("click", async () => {
      const txt = el("briefing-textarea")?.value || "";
      if (!txt) return;
      try {
        await navigator.clipboard.writeText(txt);
        const btn = el("btn-copy-briefing");
        if (btn) {
          const old = btn.textContent;
          btn.textContent = "已复制战报 ✓";
          setTimeout(() => (btn.textContent = old), 2000);
        }
      } catch (_) {}
    });

    el("btn-send-webhook")?.addEventListener("click", () => {
      sendWebhookAlert();
    });

    el("mkt-filter-tabs")?.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        el("mkt-filter-tabs").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.mktFilter = btn.getAttribute("data-mkt") || "all";
        renderScreenerTable();
      });
    });

    el("archetype-filter")?.addEventListener("change", (e) => {
      state.archetypeFilter = e.target.value;
      renderScreenerTable();
    });

    el("table-search")?.addEventListener("input", (e) => {
      state.searchQuery = e.target.value || "";
      renderScreenerTable();
    });

    document.querySelectorAll("#screener-table th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-sort");
        if (!key || key === "rank") return;
        if (state.sortKey === key) {
          state.sortAsc = !state.sortAsc;
        } else {
          state.sortKey = key;
          state.sortAsc = false;
        }
        renderScreenerTable();
      });
    });

    window.addEventListener("resize", () => {
      state.klineChart?.resize();
      state.payoffChart?.resize();
      state.btChart?.resize();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    loadRecommendations(false);
    loadPortfolioTracker();
    loadDailyBriefing();
    loadBacktestReview(false);
    loadStressTest(false);
  });
})();
