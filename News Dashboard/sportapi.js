const API_KEY = "123";
const BASE_URL = `https://www.thesportsdb.com/api/v1/json/${API_KEY}`;

//Ethan Burr 4/18
// Prevent duplicate API calls
const loadedLeagues = new Set();

//Ethan Burr 4/24
// Store all fetched events across leagues
const allLeagueEvents = [];

//Ethan Burr 5/1
let summaryGenerated = false;

//Ethan Burr 4/24
// Update summary text on page
function renderSummaryText(text) {
    const box = document.getElementById("sports-summary-box");
    if (box) {
        box.innerText = text;
    }
}

//Ethan Burr 4/24
// Load saved summary from storage
function loadStoredSummary() {
    return localStorage.getItem("sports_summary_data");
}

//Ethan Burr 4/24
// Save summary to storage
function storeSummaryText(text) {
    localStorage.setItem("sports_summary_data", text);
}

//Ethan Burr 4/24
// Fallback summary if AI fails
function fallbackSummary() {
    if (allLeagueEvents.length === 0) return "No sports data available.";

    const sample = allLeagueEvents.slice(0, 3).map(e =>
        `${e.strEvent} (${e.intHomeScore ?? "-"}-${e.intAwayScore ?? "-"})`
    );

    return `Recent games include: ${sample.join(", ")}.`;
}

//Ethan Burr 4/24
// Generate AI summary from all leagues
async function generateGeminiSummary() {
	if (summaryGenerated) return;
    if (allLeagueEvents.length < 3) return;
	summaryGenerated = true;

    const eventText = allLeagueEvents.slice(0, 30).map(e =>
		`• ${e.strEvent} on ${e.dateEvent}: ${e.intHomeScore ?? "-"}-${e.intAwayScore ?? "-"}`
    ).join("\n");
	//Ethan Burr 5/1 
	// Updated the AI prompt to have a more detailed summary
    const prompt = `
		You are a sports analyst. Summarize the following sports results briefly.

		Reply in exactly this format:

		HEADLINE: [one sentence]

		KEY RESULTS:
		[3 bullet points max]

		TRENDS:
		[1-2 sentences only]

		All recent games:
		${eventText}
	`;

    try {
        const response = await fetch(
            `https://api.groq.com/openai/v1/chat/completions`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
					"Authorization": "Bearer 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"
                },
                body: JSON.stringify({
                    model: "llama-3.3-70b-versatile",
					messages: [{ role: "user", content: prompt }]
                })
            }
        );

        const data = await response.json();

        const aiText =
            data?.choices?.[0]?.message?.content
		
		console.log("RAW AI RESPONSE:", aiText);
		
        if (!aiText) {
            const fallback = fallbackSummary();
            storeSummaryText(fallback);
            renderSummaryText(fallback);
            return;
        }

        storeSummaryText(aiText);
        renderSummaryText(aiText);

    } catch (error) {
        console.error("Gemini error:", error);

        const fallback = fallbackSummary();
        storeSummaryText(fallback);
        renderSummaryText(fallback);
    }
}

async function fetchLeagueData(leagueId, containerId, leagueKey) {
    const url = `${BASE_URL}/eventspastleague.php?id=${leagueId}`;

    try {
        const container = document.getElementById(containerId);

        if (loadedLeagues.has(leagueKey)) return;
        loadedLeagues.add(leagueKey);

        container.innerHTML = "Loading...";

        const response = await fetch(url);
        const data = await response.json();

        container.innerHTML = "";

        if (!data.events) {
            container.innerHTML = "No data available.";
            return;
        }
		
		//Ethan Burr
		// Collect more events, changed slice (0,5) to (0,10)
        data.events.slice(0, 10).forEach(event => {
            allLeagueEvents.push(event);
        });

        data.events.slice(0, 3).forEach(event => {
            const item = document.createElement("p");
            item.innerHTML = `
                <strong>${event.strEvent}</strong><br>
                Date: ${event.dateEvent}<br>
                Score: ${event.intHomeScore ?? "-"} - ${event.intAwayScore ?? "-"}
            `;
            container.appendChild(item);
        });

    } catch (error) {
        console.error("Error:", error);
        renderSummaryText("Error loading sports data.");
    }
}

//Ethan Burr 4/24
const activeFilters = new Set();

//Ethan Burr 4/24
function toggleFilter(league) {
    if (activeFilters.has(league)) {
        activeFilters.delete(league);
    } else {
        activeFilters.add(league);
    }

    document.querySelectorAll(".card").forEach(card => {
        const key = card.id.replace("-card", "");
        card.style.display = activeFilters.has(key) ? "block" : "none";
    });

    document.querySelectorAll(".filter-btn").forEach(btn => {
        btn.classList.toggle("active", activeFilters.has(btn.dataset.league));
    });

    const leagueMap = {
        nba: ["4387", "nbaNews"],
        nfl: ["4391", "nflNews"],
        mlb: ["4424", "mlbNews"],
        nhl: ["4380", "nhlNews"],
        mls: ["4346", "mlsNews"],
        epl: ["4328", "eplNews"]
    };

    if (activeFilters.has(league)) {
        const [id, container] = leagueMap[league];
        fetchLeagueData(id, container, league);
    }
}

//Ethan Burr 4/24
// Load saved summary on page refresh

//Ethan Burr 5/1
//Updated the onload to make it so that the AI summary already appears without a user selecting each league
window.onload = async () => {
    const saved = loadStoredSummary();
    if (saved) {
        renderSummaryText(saved);
    } else {
        renderSummaryText("Loading AI summary...");
    }

    const leagues = [
        ["4387", "nbaNews", "nba"],
        ["4391", "nflNews", "nfl"],
        ["4424", "mlbNews", "mlb"],
        ["4380", "nhlNews", "nhl"],
        ["4346", "mlsNews", "mls"],
        ["4328", "eplNews", "epl"]
    ];

    await Promise.all(leagues.map(([id, container, key]) =>
        fetchLeagueData(id, container, key)
    ));

    generateGeminiSummary();
};