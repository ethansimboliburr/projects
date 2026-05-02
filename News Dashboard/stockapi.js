// Author: Karthik Nair
// Last Updated: 2026-05-01
const ALL_STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
    "NVDA", "META", "NFLX", "JPM", "V",
    "WMT", "DIS", "PYPL", "INTC", "AMD"
];

const DEFAULT_CARD_SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN",
    "TSLA", "NVDA", "META", "NFLX"
];

const cardSymbols = [...DEFAULT_CARD_SYMBOLS];
const API_KEY = "f770cb85890e4bca8f62c4deae13b0d9";
const GEMINI_API_KEY = "AIzaSyCFpNJA5pn72_yz1iiV1DCAhJELufr35bM"; // Gemini Key
const CACHE_KEY = "stock-dashboard-cache-v1";
const SUMMARY_CACHE_KEY = "stock-summary-cache-v2";
const CACHE_TTL_MS = 12 * 60 * 60 * 1000;

let stockCache = {};

function getContainer() {
    return document.getElementById("stock-container");
}

// readCache function written by Claude Code
function readCache() {
    try {
        const rawValue = localStorage.getItem(CACHE_KEY);
        if (!rawValue) {
            return null;
        }

        const parsedValue = JSON.parse(rawValue);
        if (!parsedValue?.timestamp || !parsedValue?.quotes) {
            return null;
        }

        if (Date.now() - parsedValue.timestamp > CACHE_TTL_MS) {
            localStorage.removeItem(CACHE_KEY);
            return null;
        }

        return parsedValue.quotes;
    } catch (error) {
        console.error("Error reading stocks cache:", error);
        return null;
    }
}

function writeCache(quotes) {
    try {
        localStorage.setItem(CACHE_KEY, JSON.stringify({
            timestamp: Date.now(),
            quotes
        }));
    } catch (error) {
        console.error("Error writing stocks cache:", error);
    }
}

function normalizeQuoteResponse(data, symbol) {
    if (!data || data.code || data.status === "error") {
        return null;
    }

    if (data.symbol === symbol) {
        return data;
    }

    if (data[symbol] && !data[symbol].code && data[symbol].status !== "error") {
        return data[symbol];
    }

    return null;
}

function formatMoney(value) {
    const num = parseFloat(value);
    return Number.isFinite(num) ? num.toFixed(2) : "N/A";
}

function formatMarketCap(value) {
    const num = parseFloat(value);
    if (!Number.isFinite(num)) {
        return "N/A";
    }
    if (num >= 1e12) return `${(num / 1e12).toFixed(2)}T`;
    if (num >= 1e9) return `${(num / 1e9).toFixed(2)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(2)}M`;
    return num.toLocaleString();
}

function formatPercent(value) {
    const num = parseFloat(value);
    return Number.isFinite(num) ? num.toFixed(2) : "0.00";
}

function createSelectMarkup(selectedSymbol) {
    return `
        <select class="stock-select">
            ${ALL_STOCKS.map((symbol) => (
                `<option value="${symbol}"${symbol === selectedSymbol ? " selected" : ""}>${symbol}</option>`
            )).join("")}
        </select>
    `;
}

function attachCardListener(card, cardIndex) {
    const select = card.querySelector(".stock-select");
    if (!select) {
        return;
    }

    select.addEventListener("change", function () {
        cardSymbols[cardIndex] = this.value;
        loadSingleCard(cardIndex, card);
    });
}

function renderCard(card, symbol, stock) {
    if (!stock) {
        card.innerHTML = `
            ${createSelectMarkup(symbol)}
            <p>Failed to load ${symbol}.</p>
        `;
        return;
    }

    const change = parseFloat(stock.percent_change);
    const changeColor = Number.isFinite(change) && change >= 0 ? "#4ade80" : "#f87171";

    card.innerHTML = `
        ${createSelectMarkup(symbol)}
        <h2>${stock.name || symbol} (${stock.symbol || symbol})</h2>
        <p><strong>Current Price:</strong> $${formatMoney(stock.close)}</p>
        <p>
            <strong>Daily Change:</strong>
            <span style="color:${changeColor}; font-weight:bold;">
                ${formatPercent(stock.percent_change)}%
            </span>
        </p>
        <p><strong>52-Week High:</strong> $${formatMoney(stock.fifty_two_week?.high)}</p>
        <p><strong>Market Cap:</strong> ${formatMarketCap(stock.market_cap)}</p>
    `;
}

function setCardLoading(card, symbol) {
    card.innerHTML = `
        ${createSelectMarkup(symbol)}
        <p>Loading...</p>
    `;
}

async function fetchQuoteMap(symbols) {
    const response = await fetch(
        `https://api.twelvedata.com/quote?symbol=${symbols.join(",")}&apikey=${API_KEY}`
    );
    const data = await response.json();

    return symbols.reduce((quotes, symbol) => {
        const quote = normalizeQuoteResponse(data, symbol);
        if (quote) {
            quotes[symbol] = quote;
        }
        return quotes;
    }, {});
}

async function fetchQuoteMapInBatches(symbols, batchSize = 8) {
    const quotes = {};

    for (let index = 0; index < symbols.length; index += batchSize) {
        const batch = symbols.slice(index, index + batchSize);
        const batchQuotes = await fetchQuoteMap(batch);
        Object.assign(quotes, batchQuotes);
    }

    return quotes;
}

async function fetchSingleQuote(symbol) {
    const response = await fetch(
        `https://api.twelvedata.com/quote?symbol=${symbol}&apikey=${API_KEY}`
    );
    const data = await response.json();
    return normalizeQuoteResponse(data, symbol);
}

// ensureStockCache function written by Claude Code
async function ensureStockCache(forceRefresh = false) {
    if (!forceRefresh) {
        const cachedQuotes = readCache();
        if (cachedQuotes) {
            stockCache = cachedQuotes;
            return stockCache;
        }
    }

    try {
        const freshQuotes = await fetchQuoteMapInBatches(ALL_STOCKS);
        if (Object.keys(freshQuotes).length > 0) {
            stockCache = { ...stockCache, ...freshQuotes };
            writeCache(stockCache);
        }
    } catch (error) {
        console.error("Error loading stock quotes:", error);
    }

    return stockCache;
}

async function loadStocks(forceRefresh = false) {
    const container = getContainer();
    if (!container) {
        return;
    }

    container.innerHTML = "";

    cardSymbols.forEach((symbol, index) => {
        const card = document.createElement("div");
        card.className = "card";
        card.dataset.index = index;
        setCardLoading(card, symbol);
        attachCardListener(card, index);
        container.appendChild(card);
    });

    const quotes = await ensureStockCache(forceRefresh);

    Array.from(container.children).forEach((card, index) => {
        const symbol = cardSymbols[index];
        renderCard(card, symbol, quotes[symbol] || null);
        attachCardListener(card, index);
    });

    generateAISummary(quotes, forceRefresh);
}

async function loadSingleCard(cardIndex, card) {
    const symbol = cardSymbols[cardIndex];
    setCardLoading(card, symbol);
    attachCardListener(card, cardIndex);

    if (stockCache[symbol]) {
        renderCard(card, symbol, stockCache[symbol]);
        attachCardListener(card, cardIndex);
        return;
    }

    try {
        const quote = await fetchSingleQuote(symbol);
        if (quote) {
            stockCache[symbol] = quote;
            writeCache(stockCache);
        }
        renderCard(card, symbol, quote);
    } catch (error) {
        console.error(`Error loading ${symbol}:`, error);
        renderCard(card, symbol, null);
    }

    attachCardListener(card, cardIndex);
    generateAISummary(stockCache, true);
}

// ── AI Summary ──────────────────────────────────────────────────────────────

function setSummary(content, state = "") {
    const el = document.getElementById("ai-summary");
    if (!el) return;
    if (state === "loading") {
        el.textContent = content;
    } else {
        el.innerHTML = content;
    }
    el.className = "ai-summary-text" + (state ? ` ${state}` : "");
}

function buildSummaryHTML({ sentiment, topGainer, topLoser, avgChange, analysis, outlook }) {
    const sentimentMap = {
        bullish: { label: "📈 Bullish", cls: "bullish" },
        bearish: { label: "📉 Bearish", cls: "bearish" },
        mixed:   { label: "↔ Mixed",   cls: "mixed" }
    };
    const s = sentimentMap[sentiment] || sentimentMap.mixed;

    const gainerChip = topGainer
        ? `<span class="stat-chip gainer">▲ ${topGainer.symbol} ${topGainer.change}</span>` : "";
    const loserChip = topLoser
        ? `<span class="stat-chip loser">▼ ${topLoser.symbol} ${topLoser.change}</span>` : "";
    const avgChip = avgChange
        ? `<span class="stat-chip neutral">Avg ${avgChange}</span>` : "";
    const outlookBlock = outlook
        ? `<div class="summary-outlook"><span class="outlook-icon">🔍</span><span>${outlook}</span></div>` : "";

    return `
        <div class="summary-header">
            <span class="sentiment-badge ${s.cls}">${s.label}</span>
            <div class="summary-stats">${gainerChip}${loserChip}${avgChip}</div>
        </div>
        <p class="summary-analysis">${analysis}</p>
        ${outlookBlock}
    `;
}

function readSummaryCache() {
    try {
        const raw = localStorage.getItem(SUMMARY_CACHE_KEY);
        if (!raw) return null;
        const { timestamp, text, symbols } = JSON.parse(raw);
        if (!timestamp || !text) return null;
        if (Date.now() - timestamp > CACHE_TTL_MS) {
            localStorage.removeItem(SUMMARY_CACHE_KEY);
            return null;
        }
        if (symbols && symbols.join(",") !== cardSymbols.join(",")) return null;
        return text;
    } catch {
        return null;
    }
}

function writeSummaryCache(text) {
    try {
        localStorage.setItem(SUMMARY_CACHE_KEY, JSON.stringify({
            timestamp: Date.now(),
            text,
            symbols: [...cardSymbols]
        }));
    } catch (e) {
        console.error("Error writing summary cache:", e);
    }
}

function buildFallbackSummary(quotes) {
    const entries = cardSymbols
        .map((sym) => ({ symbol: sym, change: parseFloat(quotes[sym]?.percent_change) }))
        .filter((e) => Number.isFinite(e.change));

    if (entries.length === 0) {
        return buildSummaryHTML({
            sentiment: "mixed",
            topGainer: null, topLoser: null, avgChange: null,
            analysis: "Market data is currently unavailable.",
            outlook: null
        });
    }

    const gainers = entries.filter((e) => e.change > 0);
    const losers  = entries.filter((e) => e.change < 0);
    const avg     = entries.reduce((sum, e) => sum + e.change, 0) / entries.length;
    const top     = entries.reduce((a, b) => (a.change > b.change ? a : b));
    const worst   = entries.reduce((a, b) => (a.change < b.change ? a : b));
    const sentiment = avg >= 1 ? "bullish" : avg <= -1 ? "bearish" : "mixed";

    const analysis =
        `The tracked portfolio is showing a ${sentiment} tone, with ${gainers.length} of ${entries.length} stocks in the green and an average daily move of ${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%. ` +
        `${top.symbol} leads today's gainers at +${top.change.toFixed(2)}%, while ${worst.symbol} is the weakest performer at ${worst.change.toFixed(2)}%.`;

    let outlook;
    if (losers.length === 0) {
        outlook = "Broad-based strength suggests positive market momentum across the board.";
    } else if (gainers.length === 0) {
        outlook = "Broad-based weakness indicates risk-off sentiment across the portfolio.";
    } else {
        outlook = "Divergence across the portfolio points to selective investor positioning rather than a broad market move.";
    }

    return buildSummaryHTML({
        sentiment,
        topGainer: { symbol: top.symbol, change: `+${top.change.toFixed(2)}%` },
        topLoser:  { symbol: worst.symbol, change: `${worst.change.toFixed(2)}%` },
        avgChange: `${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%`,
        analysis,
        outlook
    });
}

async function generateAISummary(quotes, forceRefresh = false) {
    if (!forceRefresh) {
        const cached = readSummaryCache();
        if (cached) {
            setSummary(cached);
            return;
        }
    }

    const visibleSymbols = cardSymbols.filter((sym) => quotes[sym]);
    if (visibleSymbols.length === 0) return;

    setSummary("Analyzing market data...", "loading");

    const stockLines = visibleSymbols.map((sym) => {
        const q = quotes[sym];
        const change = parseFloat(q.percent_change);
        const cap = q.market_cap ? ` | Market Cap: ${formatMarketCap(q.market_cap)}` : "";
        const high52 = q.fifty_two_week?.high ? ` | 52W High: $${formatMoney(q.fifty_two_week.high)}` : "";
        return `${sym}: $${formatMoney(q.close)} (${change >= 0 ? "+" : ""}${formatPercent(change)}%)${cap}${high52}`;
    });

    // prompt given to gemini api — requests structured JSON for rich rendering
    const prompt = `You are a financial analyst. Analyze the following stocks and return ONLY a raw JSON object (no markdown, no code fences). The JSON must have these exact fields:
- "sentiment": one of "bullish", "bearish", or "mixed"
- "topGainer": { "symbol": "TICKER", "change": "+X.XX%" }
- "topLoser": { "symbol": "TICKER", "change": "-X.XX%" }
- "avgChange": string like "+0.82%" or "-1.10%"
- "analysis": 3–5 sentence detailed analysis covering overall momentum, standout movers, sector trends or patterns, and any notable divergences
- "outlook": one concise forward-looking or key insight sentence about what to watch

Stock data:
${stockLines.join("\n")}`;

    try {
        const response = await fetch(
            `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_API_KEY}`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] })
            }
        );

        if (!response.ok) {
            const errBody = await response.json().catch(() => ({}));
            console.error("Gemini API error:", response.status, errBody);
            throw new Error(`Gemini API error: ${response.status}`);
        }

        const data = await response.json();
        const raw = data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
        if (!raw) throw new Error("Empty Gemini response");

        const parsed = JSON.parse(raw);
        const html = buildSummaryHTML(parsed);

        writeSummaryCache(html);
        setSummary(html);
    } catch (error) {
        console.error("AI summary error — using fallback:", error);
        const fallback = buildFallbackSummary(quotes);
        writeSummaryCache(fallback);
        setSummary(fallback);
    }
}

window.onload = () => loadStocks();
setInterval(() => loadStocks(true), CACHE_TTL_MS);
