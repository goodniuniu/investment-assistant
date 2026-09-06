/* ============================================================
   公共逻辑：数据加载、格式化、SVG 图表引擎
   无第三方依赖，纯原生实现。
   ============================================================ */

(function (global) {
  'use strict';

  // ---------------------------------------------------- 路径
  // 页面可能位于根目录（index.html）或 pages/ 子目录，据此计算资源前缀
  function prefix() {
    return /\/pages\//.test(location.pathname) ? '../' : '';
  }

  function asset(p) {
    return prefix() + p.replace(/^\/+/, '');
  }

  // ---------------------------------------------------- 数据加载
  async function load(relPath) {
    const url = asset(relPath);
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return await res.json();
    } catch (e) {
      // file:// 协议下 fetch 会被浏览器拦截，给出明确指引而非白屏
      if (location.protocol === 'file:') {
        console.warn('[数据加载失败] 请通过本地服务器访问，而非直接双击打开 HTML');
      }
      console.warn('[数据加载失败] ' + url, e);
      return null;
    }
  }

  // 读取按月归档的历史数据：从当前月份向前回溯若干个月
  async function loadHistory(monthsBack) {
    monthsBack = monthsBack || 6;
    const months = [];
    const now = new Date();
    for (let i = 0; i < monthsBack; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      months.push(d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'));
    }
    const results = await Promise.all(
      months.map(m => load('data/market/history/' + m + '.json'))
    );
    const days = [];
    results.forEach(r => { if (r && Array.isArray(r.days)) days.push.apply(days, r.days); });
    days.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    // 去重（相邻月份文件可能有重叠）
    const seen = new Set();
    return days.filter(d => (seen.has(d.date) ? false : (seen.add(d.date), true)));
  }

  // ---------------------------------------------------- 格式化
  const fmt = {
    num: function (v, digits) {
      if (v === null || v === undefined || isNaN(v)) return '—';
      return Number(v).toFixed(digits === undefined ? 2 : digits);
    },
    // 带正负号
    signed: function (v, digits) {
      if (v === null || v === undefined || isNaN(v)) return '—';
      const d = digits === undefined ? 2 : digits;
      return (v > 0 ? '+' : '') + Number(v).toFixed(d);
    },
    pct: function (v, digits) {
      if (v === null || v === undefined || isNaN(v)) return '—';
      return fmt.signed(v, digits === undefined ? 2 : digits) + '%';
    },
    // 金额：元 → 亿元
    yi: function (v, digits) {
      if (v === null || v === undefined || isNaN(v)) return '—';
      return Number(v / 1e8).toFixed(digits === undefined ? 0 : digits) + ' 亿';
    },
    int: function (v) {
      if (v === null || v === undefined || isNaN(v)) return '—';
      return Number(v).toLocaleString('zh-CN');
    },
    date: function (s) {
      if (!s) return '—';
      return String(s).slice(0, 10);
    },
    md: function (s) {
      if (!s) return '—';
      const p = String(s).split('-');
      return p.length >= 3 ? p[1] + '/' + p[2] : s;
    }
  };

  // 涨跌配色类名（中国习惯：红涨绿跌）
  function cls(v) {
    if (v === null || v === undefined || isNaN(v)) return 'flat';
    return v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
  }

  // 把 **重点** 标记转为 <strong>
  function md2html(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  }

  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ---------------------------------------------------- SVG 图表
  const NS = 'http://www.w3.org/2000/svg';

  function svgEl(tag, attrs) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function createSvg(width, height) {
    const svg = svgEl('svg', {
      width: '100%',
      height: height,
      viewBox: '0 0 ' + width + ' ' + height,
      preserveAspectRatio: 'xMidYMid meet'
    });
    return svg;
  }

  function niceTicks(min, max, count) {
    if (min === max) { min -= 1; max += 1; }
    const range = max - min;
    const step0 = range / (count || 4);
    const mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const norm = step0 / mag;
    let step;
    if (norm <= 1) step = 1; else if (norm <= 2) step = 2;
    else if (norm <= 2.5) step = 2.5; else if (norm <= 5) step = 5; else step = 10;
    step *= mag;
    const start = Math.floor(min / step) * step;
    const end = Math.ceil(max / step) * step;
    const ticks = [];
    for (let v = start; v <= end + step * 0.001; v += step) {
      ticks.push(Math.round(v / step) * step);
    }
    return { ticks: ticks, min: start, max: end };
  }

  const chart = {
    /**
     * 折线图
     * opts: { width, height, pad, series:[{name,color,data:[{x,y}],fill}], xLabels, yFmt, yZeroLine }
     */
    line: function (opts) {
      // hidden: true 的系列不绘制、不参与 Y 轴范围计算（用于切换叠加指标）
      opts = Object.assign({}, opts, {
        series: (opts.series || []).filter(function (s) { return !s.hidden; })
      });
      const W = opts.width || 900, H = opts.height || 260;
      const pad = Object.assign({ t: 14, r: 52, b: 26, l: 46 }, opts.pad || {});
      const svg = createSvg(W, H);

      const all = [];
      opts.series.forEach(s => s.data.forEach(p => { if (p.y !== null && p.y !== undefined) all.push(p.y); }));
      if (opts.extraValues) all.push.apply(all, opts.extraValues);
      if (!all.length) return svg;

      let lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
      if (opts.yMin !== undefined) lo = opts.yMin;
      if (opts.yMax !== undefined) hi = opts.yMax;
      const span = (hi - lo) || 1;
      lo -= span * 0.08; hi += span * 0.08;
      const t = niceTicks(lo, hi, 4);
      lo = t.min; hi = t.max;

      const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
      const X = i => pad.l + (opts.series[0].data.length <= 1 ? iw / 2 : iw * i / (opts.series[0].data.length - 1));
      const Y = v => pad.t + ih - (v - lo) / (hi - lo) * ih;

      // 横向网格与刻度
      t.ticks.forEach(v => {
        const y = Y(v);
        if (y < pad.t - 1 || y > pad.t + ih + 1) return;
        svg.appendChild(svgEl('line', {
          x1: pad.l, y1: y, x2: W - pad.r, y2: y,
          stroke: (opts.yZeroLine !== undefined && Math.abs(v - opts.yZeroLine) < 1e-9)
            ? '#b9c0c9' : '#eef1f4', 'stroke-width': 1
        }));
        const lb = svgEl('text', {
          x: pad.l - 7, y: y + 3.5, 'text-anchor': 'end',
          'font-size': 10.5, fill: '#7c848e'
        });
        lb.textContent = opts.yFmt ? opts.yFmt(v) : v;
        svg.appendChild(lb);
      });

      // X 轴标签
      (opts.xLabels || []).forEach(l => {
        const tb = svgEl('text', {
          x: X(l.i), y: H - 8, 'text-anchor': 'middle',
          'font-size': 10.5, fill: '#7c848e'
        });
        tb.textContent = l.text;
        svg.appendChild(tb);
      });

      // 数据线
      opts.series.forEach(s => {
        const pts = [];
        s.data.forEach((p, i) => {
          if (p.y === null || p.y === undefined) return;
          pts.push([X(i), Y(p.y), p]);
        });
        if (!pts.length) return;
        if (s.fill) {
          const d = 'M' + pts[0][0] + ',' + (pad.t + ih) +
            ' ' + pts.map(p => 'L' + p[0] + ',' + p[1]).join(' ') +
            ' L' + pts[pts.length - 1][0] + ',' + (pad.t + ih) + ' Z';
          svg.appendChild(svgEl('path', { d: d, fill: s.color, opacity: 0.09 }));
        }
        const d = 'M' + pts.map(p => p[0] + ',' + p[1]).join(' L');
        svg.appendChild(svgEl('path', {
          d: d, fill: 'none', stroke: s.color, 'stroke-width': s.width || 1.9,
          'stroke-linejoin': 'round', 'stroke-linecap': 'round'
        }));
        if (s.dots) {
          pts.forEach(p => svg.appendChild(svgEl('circle', {
            cx: p[0], cy: p[1], r: 2.1, fill: s.color
          })));
        }
      });

      return svg;
    },

    /**
     * K线图（含成交量副图）
     * rows: [{date, open, close, high, low, volume}]
     * opts: { width, height, ma:{ma5,ma20} 需 rows 中带 ma 字段 }
     */
    candles: function (rows, opts) {
      opts = opts || {};
      const W = opts.width || 900, H = opts.height || 320;
      const pad = { t: 12, r: 52, b: 24, l: 46 };
      const volH = 46, gap = 8;
      const kH = H - pad.t - pad.b - volH - gap;
      const svg = createSvg(W, H);
      const data = rows.filter(r => r && r.close != null);
      if (data.length < 2) return svg;

      let lo = Infinity, hi = -Infinity, vmax = 0;
      data.forEach(r => {
        lo = Math.min(lo, r.low != null ? r.low : r.close);
        hi = Math.max(hi, r.high != null ? r.high : r.close);
        if (r.volume) vmax = Math.max(vmax, r.volume);
      });
      (opts.maKeys || ['ma5', 'ma20']).forEach(k => {
        data.forEach(r => {
          if (r[k] != null) { lo = Math.min(lo, r[k]); hi = Math.max(hi, r[k]); }
        });
      });
      const range = (hi - lo) || 1;
      lo -= range * 0.05; hi += range * 0.05;
      const t = niceTicks(lo, hi, 4);
      lo = t.min; hi = t.max;

      const iw = W - pad.l - pad.r;
      const step = iw / data.length;
      const bw = Math.max(1.2, Math.min(step * 0.62, 11));
      const X = i => pad.l + step * (i + 0.5);
      const Y = v => pad.t + kH - (v - lo) / (hi - lo) * kH;

      t.ticks.forEach(v => {
        const y = Y(v);
        if (y < pad.t - 1 || y > pad.t + kH + 1) return;
        svg.appendChild(svgEl('line', {
          x1: pad.l, y1: y, x2: W - pad.r, y2: y, stroke: '#eef1f4', 'stroke-width': 1
        }));
        const lb = svgEl('text', {
          x: pad.l - 7, y: y + 3.5, 'text-anchor': 'end', 'font-size': 10.5, fill: '#7c848e'
        });
        lb.textContent = v;
        svg.appendChild(lb);
      });

      // 蜡烛
      data.forEach((r, i) => {
        const up = r.close >= (r.open != null ? r.open : r.close);
        const c = up ? '#d0342c' : '#0e9f6e';
        const x = X(i);
        const o = r.open != null ? r.open : r.close;
        // 影线
        if (r.high != null && r.low != null) {
          svg.appendChild(svgEl('line', {
            x1: x, y1: Y(r.high), x2: x, y2: Y(r.low), stroke: c, 'stroke-width': 1
          }));
        }
        const y1 = Y(Math.max(o, r.close)), y2 = Y(Math.min(o, r.close));
        svg.appendChild(svgEl('rect', {
          x: x - bw / 2, y: y1, width: bw, height: Math.max(1, y2 - y1),
          fill: up ? '#ffffff' : c, stroke: c, 'stroke-width': 1
        }));
      });

      // 均线
      const maColors = { ma5: '#e8912d', ma10: '#8b5cf6', ma20: '#2563eb', ma60: '#0e9f6e' };
      (opts.maKeys || ['ma5', 'ma20']).forEach(k => {
        const pts = [];
        data.forEach((r, i) => { if (r[k] != null) pts.push([X(i), Y(r[k])]); });
        if (pts.length < 2) return;
        svg.appendChild(svgEl('path', {
          d: 'M' + pts.map(p => p[0] + ',' + p[1]).join(' L'),
          fill: 'none', stroke: maColors[k] || '#8b5cf6',
          'stroke-width': 1.4, opacity: .88
        }));
      });

      // 成交量副图
      const vTop = pad.t + kH + gap;
      if (vmax > 0) {
        data.forEach((r, i) => {
          if (!r.volume) return;
          const up = r.close >= (r.open != null ? r.open : r.close);
          const h = Math.max(1, r.volume / vmax * volH);
          svg.appendChild(svgEl('rect', {
            x: X(i) - bw / 2, y: vTop + volH - h, width: bw, height: h,
            fill: up ? '#d0342c' : '#0e9f6e', opacity: .42
          }));
        });
      }

      // X 轴日期
      const labelEvery = Math.max(1, Math.ceil(data.length / 8));
      data.forEach((r, i) => {
        if (i % labelEvery !== 0) return;
        const tb = svgEl('text', {
          x: X(i), y: H - 7, 'text-anchor': 'middle', 'font-size': 10, fill: '#7c848e'
        });
        tb.textContent = fmt.md(r.date);
        svg.appendChild(tb);
      });

      return svg;
    },

    /** 横向条形图：items [{name, value, color}] */
    bars: function (items, opts) {
      opts = opts || {};
      const W = opts.width || 420;
      const rowH = opts.rowH || 24;
      const H = Math.max(40, items.length * rowH + 8);
      const svg = createSvg(W, H);
      const labelW = opts.labelW || 96;
      const valW = opts.valW || 62;
      let max = 0;
      items.forEach(i => { max = Math.max(max, Math.abs(i.value)); });
      if (!max) return svg;
      const barW = W - labelW - valW;

      items.forEach((it, idx) => {
        const y = idx * rowH + 5;
        const nm = svgEl('text', {
          x: labelW - 8, y: y + 11, 'text-anchor': 'end', 'font-size': 12, fill: '#4a5058'
        });
        nm.textContent = it.name.length > 7 ? it.name.slice(0, 7) : it.name;
        svg.appendChild(nm);

        const w = Math.abs(it.value) / max * barW;
        svg.appendChild(svgEl('rect', {
          x: labelW, y: y + 2, width: Math.max(2, w), height: rowH - 11,
          rx: 2, fill: it.color || (it.value >= 0 ? '#d0342c' : '#0e9f6e'), opacity: .85
        }));
        const vv = svgEl('text', {
          x: W - 4, y: y + 11, 'text-anchor': 'end', 'font-size': 11.5,
          fill: it.value >= 0 ? '#d0342c' : '#0e9f6e', 'font-family': 'var(--mono)'
        });
        vv.textContent = opts.fmt ? opts.fmt(it.value) : it.value;
        svg.appendChild(vv);
      });
      return svg;
    }
  };

  // ---------------------------------------------------- 页面装配
  function mountNav(active) {
    const nav = document.querySelector('.nav');
    if (!nav) return;
    Array.prototype.forEach.call(nav.querySelectorAll('a'), a => {
      const href = a.getAttribute('href');
      if (href && href.indexOf(active) === 0) a.classList.add('active');
    });
  }

  function disclaimer() {
    return '<div class="disclaimer">本页面所有内容均为投资知识与方法论学习材料，' +
      '由程序按公开数据与既定规则自动生成，<strong>不构成任何投资建议、证券推荐或买卖要约</strong>。' +
      '市场有风险，任何决策及其后果由您本人承担。数据来自公开行情接口，可能存在延迟或缺失，请以交易所与券商数据为准。</div>';
  }

  function empty(text) {
    return '<div class="empty">' + esc(text) + '</div>';
  }

  // 无数据或 file:// 协议下的提示
  function dataNotice(ok, hint) {
    if (ok) return '';
    return '<div class="notice notice-warn">' +
      '<strong>数据未加载成功。</strong>' +
      (location.protocol === 'file:'
        ? '检测到您正以 file:// 方式打开页面，浏览器会拦截本地数据请求。请在项目根目录执行 ' +
          '<code>python -m http.server 8000</code>，然后访问 ' +
          '<code>http://localhost:8000</code>。'
        : (hint || '请确认 data/ 目录下已有抓取生成的 JSON 文件（可运行 scripts/fetch_market.py 生成）。')) +
      '</div>';
  }

  global.APP = {
    prefix: prefix, asset: asset, load: load, loadHistory: loadHistory,
    fmt: fmt, cls: cls, md2html: md2html, esc: esc,
    chart: chart, mountNav: mountNav, disclaimer: disclaimer,
    empty: empty, dataNotice: dataNotice, svgEl: svgEl
  };
})(window);
